"""HR agent — ferie, contratti, performance review."""
import json
import time
from datetime import date, timedelta
from pathlib import Path

from .team_base import TeamAgent


ROOT = Path(__file__).parent.parent
DATA_FILE = ROOT / "data" / "hr_data.json"
DATA_FILE.parent.mkdir(parents=True, exist_ok=True)


def _load() -> dict:
    if not DATA_FILE.exists():
        return {"employees": []}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"employees": []}


def _save(d: dict):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)


class HrAgent(TeamAgent):
    name = "hr"
    tier = 2
    icon = "👥"
    description = "HR: ferie, contratti, performance review"
    model_pref = "haiku"
    schedule = "weekly Monday 10:00"
    subscribes = []

    def run(self, payload):
        payload = payload or {}
        op = payload.get("op", "weekly_check")
        d = _load()

        if op == "weekly_check":
            today = date.today()
            issues = []
            for e in d["employees"]:
                remaining = e.get("annual_holidays", 26) - e.get("holidays_used", 0)
                if today.month >= 10 and remaining > 10:
                    issues.append(f"{e['name']}: {remaining:.0f} ferie residue "
                                    f"(rischio non goduta a fine anno)")
                if e.get("contract_end"):
                    try:
                        end = date.fromisoformat(e["contract_end"])
                        days = (end - today).days
                        if 0 < days <= 90:
                            issues.append(f"{e['name']}: contratto scade "
                                            f"{e['contract_end']} (tra {days}gg)")
                    except Exception:
                        pass
                try:
                    nr = date.fromisoformat(e.get("next_review", ""))
                    if nr <= today:
                        issues.append(f"{e['name']}: review scaduta {e['next_review']}")
                except Exception:
                    pass
            for i in issues[:5]:
                self.remember("todo", f"👥 HR: {i}",
                                importance=0.7, tags=["hr"])
            self._emit("weekly_done", {"issues": len(issues)})
            return {"ok": True, "issues_count": len(issues),
                    "issues": issues[:10]}

        if op == "add_employee":
            emp = {
                "id": f"e_{int(time.time())}",
                "name": payload.get("name", ""),
                "role": payload.get("role", ""),
                "contract_type": payload.get("contract_type", "indeterminato"),
                "contract_end": payload.get("contract_end", ""),
                "hire_date": payload.get("hire_date", date.today().isoformat()),
                "annual_holidays": int(payload.get("annual_holidays", 26)),
                "holidays_used": 0,
                "next_review": (date.today() + timedelta(days=90)).isoformat(),
            }
            d["employees"].append(emp)
            _save(d)
            return {"ok": True, "employee": emp}

        if op == "add_holidays":
            eid = payload.get("employee_id", "")
            for e in d["employees"]:
                if e["id"] == eid or e["name"].lower() == eid.lower():
                    e["holidays_used"] += float(payload.get("days", 0))
                    _save(d)
                    return {"ok": True, "employee": e}
            return {"ok": False, "error": "dipendente non trovato"}

        if op == "status":
            return {"ok": True, "employees_count": len(d["employees"]),
                    "employees": d["employees"][:20]}

        return {"ok": False, "error": f"op sconosciuta: {op}",
                "available_ops": ["weekly_check", "add_employee",
                                    "add_holidays", "status"]}


AGENT = HrAgent()
