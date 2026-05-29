"""CISO Agent — NIS2 (Dir UE 2022/2555, D.Lgs 138/2024).

Gestisce incidenti, vulnerabilità, posture review.
"""
import json
import time
import uuid
from pathlib import Path

from .team_base import TeamAgent


ROOT = Path(__file__).parent.parent
INCIDENTS_DIR = ROOT / "data" / "incidents"
INCIDENTS_DIR.mkdir(parents=True, exist_ok=True)


CISO_SYSTEM = """Sei il CISO operativo allineato a NIS2 (Dir UE 2022/2555,
recepimento D.Lgs 138/2024). Riferimenti operativi:

- Art. 21: misure di gestione del rischio (10 pilastri: policies, IR, BC,
  supply chain, vuln, training, crypto, access control, MFA, secure comms)
- Art. 23: notifica incidenti — early warning entro 24h, full 72h, final 1 mese
- Allineamento ACN (Agenzia Cybersicurezza Nazionale)

Classifica eventi/CVE in: 'routine' | 'significant' | 'major'.
Solo significant/major richiedono notifica formale a ACN.

Output SOLO JSON:
{
  "incident_id": "<auto>",
  "classification": "routine|significant|major",
  "nis2_notification_required": bool,
  "notification_deadline_hours": int o null,
  "actions": ["..."],
  "rationale": "1-2 frasi",
  "severity_score": 0.0..1.0
}
"""


class CISOAgent(TeamAgent):
    name = "ciso"
    tier = 1
    icon = "🛡"
    description = "CISO — NIS2: incident response, CVE triage, posture review"
    model_pref = "haiku"
    subscribes = ["cve.detected", "net.blocked", "prompt_shield.detected",
                  "auth.lockout", "output_filter.canary_leaked"]

    def on_event(self, event):
        """Reagisce a eventi di sicurezza dal bus: crea incident ticket."""
        topic = event.get("topic", "")
        payload = event.get("payload", {})
        if topic == "cve.detected":
            self.create_incident("cve_detected", payload)
        elif topic == "output_filter.canary_leaked":
            # CRITICO: confirmed data leak
            self.create_incident("data_leak", payload,
                                  classification_hint="major")
        elif topic == "auth.lockout":
            self.create_incident("brute_force_attempt", payload,
                                  classification_hint="significant")
        elif topic == "prompt_shield.detected":
            # Solo se risk alto
            if payload.get("risk", 0) >= 0.7:
                self.create_incident("prompt_injection", payload,
                                      classification_hint="significant")
        elif topic == "net.blocked":
            # Esfiltrazione tentata
            self.create_incident("egress_blocked", payload,
                                  classification_hint="significant")

    def classify(self, event_type: str, payload: dict) -> dict:
        """Ask Haiku to classify the incident per NIS2."""
        prompt = (
            f"{CISO_SYSTEM}\n\n"
            f"Evento: {event_type}\nPayload: {json.dumps(payload, default=str)[:500]}\n\n"
            f"JSON:"
        )
        result = self.call_haiku_json(prompt)
        if not result:
            return {
                "incident_id": "INC-" + uuid.uuid4().hex[:6].upper(),
                "classification": "routine",
                "nis2_notification_required": False,
                "notification_deadline_hours": None,
                "actions": [],
                "rationale": "fallback (LLM unavailable)",
                "severity_score": 0.3,
            }
        result.setdefault("classification", "routine")
        result.setdefault("severity_score", 0.5)
        return result

    def create_incident(self, event_type: str, payload: dict,
                          classification_hint: str = None) -> dict:
        cls = self.classify(event_type, payload)
        if classification_hint and cls.get("classification") == "routine":
            cls["classification"] = classification_hint
        iid = f"INC-{time.strftime('%Y%m')}-{uuid.uuid4().hex[:4].upper()}"
        record = {
            "id": iid,
            "discovered_at": int(time.time()),
            "discovered_by": "agent.ciso",
            "event_type": event_type,
            "classification": cls["classification"],
            "title": cls.get("rationale", event_type)[:200],
            "payload": payload,
            "nis2_notification_required": cls.get("nis2_notification_required", False),
            "notification_deadline_hours": cls.get("notification_deadline_hours"),
            "actions": cls.get("actions", []),
            "severity_score": cls.get("severity_score", 0.5),
            "status": "open",
        }
        path = INCIDENTS_DIR / f"{iid}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=2)
        self._emit("incident_created", {
            "id": iid, "class": cls["classification"],
            "notification_req": cls.get("nis2_notification_required"),
        })
        try:
            import audit_log
            audit_log.log("ciso.incident", {"id": iid,
                                              "class": cls["classification"]})
            # Card UI per significant/major
            if cls["classification"] in ("significant", "major"):
                import bus
                bus.publish("card", {
                    "type": "ciso_incident",
                    "data": {
                        "title": f"🛡 Incidente NIS2: {cls['classification']}",
                        "incident_id": iid,
                        "summary": cls.get("rationale", "")[:300],
                        "deadline_hours": cls.get("notification_deadline_hours"),
                        "actions": cls.get("actions", []),
                    },
                })
        except Exception:
            pass
        return record

    def list_incidents(self, status: str = None) -> list:
        out = []
        for p in sorted(INCIDENTS_DIR.glob("INC-*.json"), reverse=True):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    rec = json.load(f)
                if status and rec.get("status") != status:
                    continue
                out.append(rec)
            except Exception:
                pass
        return out

    def close_incident(self, iid: str, resolution: str) -> bool:
        p = INCIDENTS_DIR / f"{iid}.json"
        if not p.exists():
            return False
        try:
            with open(p, "r", encoding="utf-8") as f:
                rec = json.load(f)
            rec["status"] = "closed"
            rec["closed_at"] = int(time.time())
            rec["resolution"] = resolution
            with open(p, "w", encoding="utf-8") as f:
                json.dump(rec, f, ensure_ascii=False, indent=2)
            return True
        except Exception:
            return False

    def run(self, payload: dict) -> dict:
        op = payload.get("op")
        if op == "list":
            return {"ok": True, "incidents": self.list_incidents(payload.get("status"))}
        if op == "close":
            return {"ok": self.close_incident(payload.get("id", ""),
                                                payload.get("resolution", ""))}
        if op == "classify":
            return {"ok": True, "classification": self.classify(
                payload.get("event_type", ""), payload.get("data", {}))}
        return {"ok": False, "error": f"op sconosciuta: {op}"}


AGENT = CISOAgent()
