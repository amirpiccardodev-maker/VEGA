"""Client Onboarding agent — gestione completa nuovo cliente.

Checklist standard per ogni nuovo cliente:
  1. welcome_kit_sent       — kit di benvenuto inviato
  2. docs_requested         — documenti richiesti
  3. docs_received          — documenti ricevuti
  4. privacy_signoff        — firma GDPR (Art. 13/14)
  5. art30_registered       — trattamento registrato da DPO
  6. folder_created         — cartella cliente creata
  7. invoice_template_set   — template fatturazione attivo
  8. kickoff_scheduled      — kickoff meeting fissato

Persistenza in data/clients.json.
"""
import json
import time
from datetime import date, datetime
from pathlib import Path

from .team_base import TeamAgent


ROOT = Path(__file__).parent.parent
DATA_FILE = ROOT / "data" / "clients.json"
DATA_FILE.parent.mkdir(parents=True, exist_ok=True)


CHECKLIST_STEPS = [
    "welcome_kit_sent",
    "docs_requested",
    "docs_received",
    "privacy_signoff",
    "art30_registered",
    "folder_created",
    "invoice_template_set",
    "kickoff_scheduled",
]


def _load() -> dict:
    if not DATA_FILE.exists():
        return {"clients": []}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"clients": []}


def _save(d: dict):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)


def _find_client(name: str) -> dict:
    name_low = (name or "").strip().lower()
    for c in _load().get("clients", []):
        if c.get("name", "").lower() == name_low:
            return c
    return None


def create_client(name: str, email: str = "", phone: str = "",
                   piva: str = "", notes: str = "") -> dict:
    d = _load()
    existing = _find_client(name)
    if existing:
        return existing
    client = {
        "id": f"cli_{int(time.time())}",
        "name": name,
        "email": email,
        "phone": phone,
        "piva": piva,
        "notes": notes,
        "checklist": {step: False for step in CHECKLIST_STEPS},
        "checklist_history": [],
        "created_at": int(time.time()),
        "status": "onboarding",
    }
    d.setdefault("clients", []).append(client)
    _save(d)
    return client


def mark_step(client_name: str, step: str, value: bool = True,
                note: str = "") -> dict:
    if step not in CHECKLIST_STEPS:
        return {"error": f"step sconosciuto: {step}"}
    d = _load()
    for c in d.get("clients", []):
        if c.get("name", "").lower() == client_name.lower():
            c["checklist"][step] = value
            c["checklist_history"].append({
                "step": step, "value": value,
                "ts": int(time.time()), "note": note,
            })
            # Auto-promote to active if all done
            if all(c["checklist"].get(s, False) for s in CHECKLIST_STEPS):
                c["status"] = "active"
            _save(d)
            return c
    return {"error": "cliente non trovato"}


def checklist_progress(client_name: str) -> dict:
    c = _find_client(client_name)
    if not c:
        return {"error": "cliente non trovato"}
    done = sum(1 for s in CHECKLIST_STEPS if c["checklist"].get(s, False))
    total = len(CHECKLIST_STEPS)
    pending = [s for s in CHECKLIST_STEPS if not c["checklist"].get(s, False)]
    return {
        "client": client_name,
        "progress_pct": round(done / total * 100),
        "done": done, "total": total,
        "pending": pending,
        "status": c.get("status", "?"),
    }


def list_clients(status: str = None) -> list:
    out = _load().get("clients", [])
    if status:
        out = [c for c in out if c.get("status") == status]
    return out


class ClientOnboardingAgent(TeamAgent):
    name = "client_onboarding"
    tier = 2
    icon = "🏢"
    description = "Onboarding clienti: checklist 8-step, privacy, fatturazione"
    model_pref = "haiku"
    schedule = None
    subscribes = []

    def run(self, payload):
        payload = payload or {}
        op = payload.get("op", "list")

        if op == "create":
            client = create_client(
                name=payload.get("name", ""),
                email=payload.get("email", ""),
                phone=payload.get("phone", ""),
                piva=payload.get("piva", ""),
                notes=payload.get("notes", ""),
            )
            self.remember("fact",
                f"Cliente: {client['name']}. Email: {client.get('email', '?')}. "
                f"P.IVA: {client.get('piva', '?')}",
                importance=0.7, tags=["client", "onboarding", client["name"]])
            self._emit("client_created", {"name": client["name"]})
            return {"ok": True, "client": client}

        if op == "mark_step":
            r = mark_step(payload.get("client", ""),
                            payload.get("step", ""),
                            value=bool(payload.get("value", True)),
                            note=payload.get("note", ""))
            if "error" in r:
                return {"ok": False, **r}
            self._emit("step_completed", {
                "client": payload.get("client"),
                "step": payload.get("step")
            })
            return {"ok": True, "client": r}

        if op == "progress":
            return {"ok": True,
                    "progress": checklist_progress(payload.get("client", ""))}

        if op == "list":
            return {"ok": True, "clients":
                [{"name": c["name"], "status": c["status"],
                  "progress": sum(1 for s in CHECKLIST_STEPS
                                   if c["checklist"].get(s, False)),
                  "total": len(CHECKLIST_STEPS)}
                 for c in list_clients(payload.get("status"))]}

        if op == "welcome_kit":
            # Workflow hook
            client = payload.get("client", "")
            if not client:
                return {"ok": False, "error": "client required"}
            # Create if missing
            if not _find_client(client):
                create_client(client, email=payload.get("email", ""))
            mark_step(client, "welcome_kit_sent", True,
                       note="Welcome kit generato dal workflow")
            return {"ok": True, "client": client,
                    "next_steps": ["docs_requested", "privacy_signoff"]}

        if op == "checklist_template":
            return {"ok": True, "steps": CHECKLIST_STEPS}

        return {"ok": False, "error": f"op sconosciuta: {op}",
                "available_ops": ["create", "mark_step", "progress", "list",
                                    "welcome_kit", "checklist_template"]}


AGENT = ClientOnboardingAgent()
