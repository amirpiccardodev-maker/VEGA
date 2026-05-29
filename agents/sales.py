"""Sales agent — mini-CRM con pipeline lead, follow-up, proposal draft."""
import json
import time
from datetime import date, timedelta
from pathlib import Path

from .team_base import TeamAgent


ROOT = Path(__file__).parent.parent
DATA_FILE = ROOT / "data" / "sales_leads.json"
DATA_FILE.parent.mkdir(parents=True, exist_ok=True)


STAGES = ["cold", "warm", "hot", "proposal_sent", "negotiation", "won", "lost"]


def _load() -> dict:
    if not DATA_FILE.exists():
        return {"leads": []}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"leads": []}


def _save(d: dict):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)


def _find_lead(name_or_id: str):
    key = (name_or_id or "").strip().lower()
    for l in _load().get("leads", []):
        if l["id"] == name_or_id or l.get("contact_name", "").lower() == key:
            return l
    return None


def add_lead(contact_name: str, company: str = "", email: str = "",
              phone: str = "", value_estimate: float = 0,
              source: str = "", stage: str = "cold",
              notes: str = "") -> dict:
    d = _load()
    if stage not in STAGES:
        stage = "cold"
    lead = {
        "id": f"l_{int(time.time())}_{len(d['leads'])}",
        "contact_name": contact_name,
        "company": company,
        "email": email,
        "phone": phone,
        "value_estimate": float(value_estimate or 0),
        "source": source,
        "stage": stage,
        "notes": notes,
        "next_followup": (date.today() + timedelta(days=3)).isoformat(),
        "history": [{"ts": int(time.time()),
                       "event": "created", "stage": stage}],
        "created_ts": int(time.time()),
    }
    d.setdefault("leads", []).append(lead)
    _save(d)
    return lead


def update_stage(lead_id: str, new_stage: str, note: str = "") -> dict:
    if new_stage not in STAGES:
        return {"error": f"stage non valido: {new_stage}"}
    d = _load()
    for l in d.get("leads", []):
        if l["id"] == lead_id or l.get("contact_name", "").lower() == lead_id.lower():
            old = l["stage"]
            l["stage"] = new_stage
            l["history"].append({
                "ts": int(time.time()), "event": "stage_change",
                "from": old, "to": new_stage, "note": note,
            })
            if new_stage == "won":
                l["won_date"] = date.today().isoformat()
            elif new_stage == "lost":
                l["lost_date"] = date.today().isoformat()
                l["lost_reason"] = note
            _save(d)
            return l
    return {"error": "lead non trovato"}


def schedule_followup(lead_id: str, days: int = 7, note: str = "") -> dict:
    d = _load()
    for l in d.get("leads", []):
        if l["id"] == lead_id or l.get("contact_name", "").lower() == lead_id.lower():
            l["next_followup"] = (date.today() + timedelta(days=days)).isoformat()
            l["history"].append({"ts": int(time.time()),
                                    "event": "followup_scheduled",
                                    "days": days, "note": note})
            _save(d)
            return l
    return {"error": "lead non trovato"}


def overdue_followups() -> list:
    today_iso = date.today().isoformat()
    out = []
    for l in _load().get("leads", []):
        if l.get("stage") in ("won", "lost"):
            continue
        nf = l.get("next_followup", "")
        if nf and nf <= today_iso:
            out.append({**l, "days_overdue":
                (date.today() - date.fromisoformat(nf)).days})
    out.sort(key=lambda x: -x.get("days_overdue", 0))
    return out


def pipeline_summary() -> dict:
    leads = _load().get("leads", [])
    by_stage = {s: [] for s in STAGES}
    total_value = 0
    for l in leads:
        by_stage[l.get("stage", "cold")].append(l)
        total_value += l.get("value_estimate", 0)
    return {
        "total_leads": len(leads),
        "by_stage": {s: len(v) for s, v in by_stage.items()},
        "pipeline_value_estimate_eur": round(total_value, 2),
        "active": sum(len(v) for s, v in by_stage.items()
                       if s not in ("won", "lost")),
        "won_count": len(by_stage["won"]),
        "lost_count": len(by_stage["lost"]),
    }


class SalesAgent(TeamAgent):
    name = "sales"
    tier = 2
    icon = "💼"
    description = "Mini-CRM: lead pipeline, follow-up, proposal draft"
    model_pref = "haiku"
    schedule = "daily 09:00"
    subscribes = []

    def run(self, payload):
        payload = payload or {}
        op = payload.get("op", "daily_check")

        if op == "daily_check":
            overdue = overdue_followups()
            for l in overdue[:5]:
                self.remember("todo",
                    f"💼 Follow-up scaduto: {l.get('contact_name')} "
                    f"({l.get('company', '?')}) - stage {l.get('stage')} "
                    f"da {l.get('days_overdue', 0)}gg",
                    importance=0.75, tags=["sales", "followup"])
            self._emit("daily_check_done", {
                "overdue_count": len(overdue),
                "pipeline_value": pipeline_summary()["pipeline_value_estimate_eur"],
            })
            return {"ok": True, "overdue_followups": len(overdue),
                    "pipeline": pipeline_summary()}

        if op == "add_lead":
            l = add_lead(
                contact_name=payload.get("contact_name", ""),
                company=payload.get("company", ""),
                email=payload.get("email", ""),
                phone=payload.get("phone", ""),
                value_estimate=payload.get("value_estimate", 0),
                source=payload.get("source", ""),
                stage=payload.get("stage", "cold"),
                notes=payload.get("notes", ""),
            )
            self.remember("fact",
                f"Lead: {l['contact_name']} ({l.get('company')}). "
                f"Stage: {l['stage']}. Valore: €{l.get('value_estimate', 0)}",
                importance=0.6, tags=["sales", "lead"])
            return {"ok": True, "lead": l}

        if op == "update_stage":
            r = update_stage(payload.get("lead_id", ""),
                                payload.get("stage", ""),
                                payload.get("note", ""))
            if "error" in r:
                return {"ok": False, **r}
            return {"ok": True, "lead": r}

        if op == "schedule_followup":
            r = schedule_followup(payload.get("lead_id", ""),
                                     days=int(payload.get("days", 7)),
                                     note=payload.get("note", ""))
            return {"ok": True, "lead": r} if "error" not in r else {"ok": False, **r}

        if op == "pipeline":
            return {"ok": True, "summary": pipeline_summary()}

        if op == "overdue":
            return {"ok": True, "overdue": overdue_followups()}

        if op == "draft_proposal":
            # Use LLM to draft
            company = payload.get("company", "Cliente")
            service = payload.get("service", "consulenza")
            duration = payload.get("duration", "3 mesi")
            value = payload.get("value", "da definire")
            prompt = (
                f"Genera bozza proposta commerciale in italiano per {company}. "
                f"Servizio: {service}. Durata: {duration}. Valore: €{value}. "
                f"Struttura: 1) sintesi esecutiva, 2) approccio in 3 punti, "
                f"3) deliverable, 4) timeline, 5) investimento, 6) prossimi passi. "
                f"Tono: professionale ma non noioso. Max 400 parole."
            )
            draft = self.call_haiku(prompt)
            self.remember("note",
                f"Bozza proposta per {company}: {draft[:200]}",
                importance=0.6, tags=["sales", "proposal", company])
            return {"ok": True, "draft": draft, "company": company}

        if op == "set_lead_status_won":
            # Workflow hook (new_client_onboarding step)
            client = payload.get("client", "")
            lead = _find_lead(client)
            if lead:
                update_stage(lead["id"], "won", "Cliente onboardato")
                return {"ok": True, "lead": lead, "marked_won": True}
            return {"ok": True, "note": "lead non trovato, nessuna azione"}

        return {"ok": False, "error": f"op sconosciuta: {op}",
                "available_ops": ["daily_check", "add_lead", "update_stage",
                                   "schedule_followup", "pipeline", "overdue",
                                   "draft_proposal", "set_lead_status_won"]}


AGENT = SalesAgent()
