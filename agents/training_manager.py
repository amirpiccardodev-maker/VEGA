"""Training Manager — formazione obbligatoria + sviluppo soft skills."""
import json
import time
from datetime import date, timedelta
from pathlib import Path

from .team_base import TeamAgent


ROOT = Path(__file__).parent.parent
DATA_FILE = ROOT / "data" / "training_data.json"
DATA_FILE.parent.mkdir(parents=True, exist_ok=True)


MANDATORY_CATALOG = [
    {"name": "Sicurezza lavoro base", "hours": 8, "validity_months": 60},
    {"name": "Antincendio", "hours": 4, "validity_months": 60},
    {"name": "Primo soccorso", "hours": 12, "validity_months": 36},
    {"name": "GDPR per addetti trattamento", "hours": 4, "validity_months": 24},
]


def _load() -> dict:
    if not DATA_FILE.exists():
        return {"courses": [], "enrollments": []}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"courses": [], "enrollments": []}


def _save(d: dict):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)


class TrainingManagerAgent(TeamAgent):
    name = "training_manager"
    tier = 2
    icon = "🎓"
    description = "Formazione obbligatoria + soft skills, scadenze, registro"
    model_pref = "haiku"
    schedule = "monthly day 1 10:00"
    subscribes = []

    def run(self, payload):
        payload = payload or {}
        op = payload.get("op", "monthly_check")
        d = _load()

        if op == "monthly_check":
            today = date.today()
            expiring = []
            for e in d.get("enrollments", []):
                try:
                    exp = date.fromisoformat(e.get("expiry", ""))
                    days = (exp - today).days
                    if 0 <= days <= 60:
                        expiring.append({
                            "person": e.get("person", "?"),
                            "course": e.get("course", "?"),
                            "expiry": e.get("expiry"),
                            "days_until": days,
                        })
                except Exception:
                    pass
            for ex in expiring[:5]:
                self.remember("todo",
                    f"🎓 Formazione {ex['course']} per {ex['person']} "
                    f"scade {ex['expiry']} (tra {ex['days_until']}gg)",
                    importance=0.8 if ex['days_until'] <= 30 else 0.6,
                    tags=["training", "expiry"])
            self._emit("monthly_check", {"expiring_count": len(expiring)})
            return {"ok": True, "expiring_in_60d": expiring}

        if op == "enroll":
            course = payload.get("course", "")
            person = payload.get("person", "")
            done = payload.get("done_date", date.today().isoformat())
            # Find validity from catalog
            validity = 60
            for c in MANDATORY_CATALOG:
                if c["name"].lower() in course.lower():
                    validity = c["validity_months"]
                    break
            try:
                d_done = date.fromisoformat(done)
            except Exception:
                d_done = date.today()
            # add months
            exp_y = d_done.year + (d_done.month + validity - 1) // 12
            exp_m = (d_done.month + validity - 1) % 12 + 1
            exp = date(exp_y, exp_m, min(d_done.day, 28))
            rec = {
                "id": f"enr_{int(time.time())}",
                "person": person, "course": course,
                "done_date": done, "expiry": exp.isoformat(),
                "hours": int(payload.get("hours", 0)),
            }
            d.setdefault("enrollments", []).append(rec)
            _save(d)
            return {"ok": True, "enrollment": rec}

        if op == "catalog":
            return {"ok": True, "catalog": MANDATORY_CATALOG}

        if op == "status":
            return {"ok": True,
                    "enrollments_count": len(d.get("enrollments", [])),
                    "enrollments": d.get("enrollments", [])[:30]}

        return {"ok": False, "error": f"op sconosciuta: {op}",
                "available_ops": ["monthly_check", "enroll", "catalog", "status"]}


AGENT = TrainingManagerAgent()
