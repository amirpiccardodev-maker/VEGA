"""RSPP — Responsabile Servizio Prevenzione Protezione (D.Lgs 81/2008).

Tracker scadenze sicurezza sul lavoro:
- Formazione base: 8h (basso rischio) / 12h (medio) / 16h (alto), valida 5 anni
- Aggiornamento: 6h ogni 5 anni
- Formazione preposti: 8h aggiuntive
- Formazione dirigenti: 16h
- Antincendio: 4h (basso) / 8h (medio) / 16h (alto), aggiornamento ogni 5 anni
- Primo soccorso: 12h (gruppo B/C) o 16h (gruppo A), agg. ogni 3 anni
- Visite mediche: periodicità definita dal Medico Competente
- DVR aggiornamento: ad ogni cambio rilevante o almeno revisione periodica

Alert -90/-60/-30/-7 giorni prima scadenza.
"""
import json
import time
from datetime import date, timedelta
from pathlib import Path

from .team_base import TeamAgent


ROOT = Path(__file__).parent.parent
DATA_FILE = ROOT / "data" / "rspp_data.json"
DATA_FILE.parent.mkdir(parents=True, exist_ok=True)


# Validità in mesi
VALIDITY_MONTHS = {
    "formazione_base": 60,           # 5 anni
    "formazione_aggiornamento": 60,
    "formazione_preposto": 60,
    "antincendio_base": 60,
    "antincendio_aggiornamento": 60,
    "primo_soccorso_base": 36,       # 3 anni
    "primo_soccorso_aggiornamento": 36,
    "visita_medica": 12,             # default 1 anno (può variare)
    "dvr_revisione": 36,             # revisione triennale di buona prassi
}

ALERT_DAYS = [90, 60, 30, 7]


def _load() -> dict:
    if not DATA_FILE.exists():
        return {"workers": [], "trainings": [], "checkups": [], "dvr": None,
                "alerts_seen": []}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"workers": [], "trainings": [], "checkups": [], "dvr": None,
                "alerts_seen": []}


def _save(d: dict):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)


def _add_months(d: date, months: int) -> date:
    """Naive add months."""
    y = d.year + (d.month + months - 1) // 12
    m = (d.month + months - 1) % 12 + 1
    day = min(d.day, 28)
    return date(y, m, day)


def add_worker(name: str, role: str = "lavoratore",
                risk_class: str = "medio") -> str:
    """Add a worker to track. risk_class: basso/medio/alto."""
    d = _load()
    wid = f"w_{int(time.time())}_{len(d['workers'])}"
    d["workers"].append({
        "id": wid, "name": name, "role": role,
        "risk_class": risk_class,
        "added_ts": int(time.time()),
    })
    _save(d)
    return wid


def add_training(worker_id: str, training_type: str,
                  done_date: str, hours: int = 0,
                  trainer: str = "", notes: str = "") -> dict:
    """Record a training session. Auto-compute expiry."""
    d = _load()
    months = VALIDITY_MONTHS.get(training_type, 60)
    try:
        done = date.fromisoformat(done_date)
    except Exception:
        done = date.today()
    expiry = _add_months(done, months)
    record = {
        "id": f"t_{int(time.time())}",
        "worker_id": worker_id,
        "type": training_type,
        "done_date": done.isoformat(),
        "expiry_date": expiry.isoformat(),
        "hours": hours,
        "trainer": trainer,
        "notes": notes,
    }
    d["trainings"].append(record)
    _save(d)
    return record


def add_checkup(worker_id: str, done_date: str,
                 next_due: str = None, doctor: str = "",
                 outcome: str = "idoneo") -> dict:
    """Record a medical checkup."""
    d = _load()
    try:
        done = date.fromisoformat(done_date)
    except Exception:
        done = date.today()
    if next_due:
        try:
            next_d = date.fromisoformat(next_due)
        except Exception:
            next_d = _add_months(done, 12)
    else:
        next_d = _add_months(done, 12)
    record = {
        "id": f"c_{int(time.time())}",
        "worker_id": worker_id,
        "done_date": done.isoformat(),
        "next_due": next_d.isoformat(),
        "doctor": doctor,
        "outcome": outcome,
    }
    d["checkups"].append(record)
    _save(d)
    return record


def set_dvr(last_revision: str, next_revision: str = None) -> dict:
    """Set DVR (Documento Valutazione Rischi) revision dates."""
    d = _load()
    try:
        last = date.fromisoformat(last_revision)
    except Exception:
        last = date.today()
    if next_revision:
        try:
            nxt = date.fromisoformat(next_revision)
        except Exception:
            nxt = _add_months(last, VALIDITY_MONTHS["dvr_revisione"])
    else:
        nxt = _add_months(last, VALIDITY_MONTHS["dvr_revisione"])
    d["dvr"] = {"last_revision": last.isoformat(),
                  "next_revision": nxt.isoformat()}
    _save(d)
    return d["dvr"]


def upcoming_expiries(days_ahead: int = 90) -> list:
    """Tutte le scadenze sicurezza nei prossimi N giorni."""
    today = date.today()
    horizon = today + timedelta(days=days_ahead)
    d = _load()
    workers = {w["id"]: w for w in d.get("workers", [])}
    out = []
    # Trainings
    for t in d.get("trainings", []):
        try:
            exp = date.fromisoformat(t["expiry_date"])
        except Exception:
            continue
        if today <= exp <= horizon:
            w = workers.get(t["worker_id"], {})
            out.append({
                "category": "training",
                "type": t["type"],
                "worker_name": w.get("name", "?"),
                "date": exp.isoformat(),
                "days_until": (exp - today).days,
                "art_lgs81": "Art. 37 (formazione)",
            })
    # Checkups
    for c in d.get("checkups", []):
        try:
            nxt = date.fromisoformat(c["next_due"])
        except Exception:
            continue
        if today <= nxt <= horizon:
            w = workers.get(c["worker_id"], {})
            out.append({
                "category": "checkup",
                "type": "visita_medica",
                "worker_name": w.get("name", "?"),
                "date": nxt.isoformat(),
                "days_until": (nxt - today).days,
                "art_lgs81": "Art. 41 (sorveglianza sanitaria)",
            })
    # DVR
    dvr = d.get("dvr")
    if dvr:
        try:
            nxt = date.fromisoformat(dvr["next_revision"])
            if today <= nxt <= horizon:
                out.append({
                    "category": "dvr",
                    "type": "dvr_revisione",
                    "worker_name": "azienda",
                    "date": nxt.isoformat(),
                    "days_until": (nxt - today).days,
                    "art_lgs81": "Art. 28-29 (DVR)",
                })
        except Exception:
            pass
    out.sort(key=lambda x: x["days_until"])
    return out


class RsppAgent(TeamAgent):
    name = "rspp"
    tier = 1
    icon = "🦺"
    description = "RSPP D.Lgs 81/08: formazioni, visite mediche, DVR"
    model_pref = "haiku"
    schedule = "weekly Monday 08:00"
    subscribes = []

    def run(self, payload):
        payload = payload or {}
        op = payload.get("op", "weekly_check")

        if op == "weekly_check":
            expiries = upcoming_expiries(days_ahead=90)
            d = _load()
            seen = set(d.get("alerts_seen", []))
            new_alerts = 0
            for e in expiries:
                # Alert when crossing ALERT_DAYS thresholds
                tier_threshold = None
                for ad in ALERT_DAYS:
                    if e["days_until"] <= ad:
                        tier_threshold = ad
                        break
                if not tier_threshold:
                    continue
                key = f"{e['category']}|{e['type']}|{e['worker_name']}|{e['date']}|{tier_threshold}"
                if key in seen:
                    continue
                seen.add(key)
                self._emit("safety_alert", {
                    "category": e["category"], "type": e["type"],
                    "worker": e["worker_name"],
                    "days_until": e["days_until"],
                    "alert_tier": tier_threshold,
                    "law": e["art_lgs81"],
                })
                self.remember("todo",
                    f"🦺 [D.Lgs 81 {e['art_lgs81']}] Scadenza {e['type']} per "
                    f"{e['worker_name']} il {e['date']} (tra {e['days_until']}gg)",
                    importance=0.9 if e["days_until"] <= 7 else 0.7,
                    tags=["rspp", "safety", e["category"]])
                new_alerts += 1
            d["alerts_seen"] = list(seen)[-300:]
            _save(d)
            return {"ok": True, "expiries_in_90d": len(expiries),
                    "new_alerts": new_alerts, "next_5": expiries[:5]}

        if op == "list_expiries":
            return {"ok": True, "expiries":
                upcoming_expiries(days_ahead=int(payload.get("days", 90)))}

        if op == "add_worker":
            wid = add_worker(payload.get("name", "?"),
                              payload.get("role", "lavoratore"),
                              payload.get("risk_class", "medio"))
            return {"ok": True, "worker_id": wid}

        if op == "add_training":
            rec = add_training(
                worker_id=payload.get("worker_id", ""),
                training_type=payload.get("type", "formazione_base"),
                done_date=payload.get("done_date", date.today().isoformat()),
                hours=int(payload.get("hours", 0)),
                trainer=payload.get("trainer", ""),
                notes=payload.get("notes", ""),
            )
            self._emit("training_recorded", {"id": rec["id"]})
            return {"ok": True, "training": rec}

        if op == "add_checkup":
            rec = add_checkup(
                worker_id=payload.get("worker_id", ""),
                done_date=payload.get("done_date", date.today().isoformat()),
                next_due=payload.get("next_due"),
                doctor=payload.get("doctor", ""),
                outcome=payload.get("outcome", "idoneo"),
            )
            self._emit("checkup_recorded", {"id": rec["id"]})
            return {"ok": True, "checkup": rec}

        if op == "set_dvr":
            r = set_dvr(payload.get("last_revision", date.today().isoformat()),
                          payload.get("next_revision"))
            return {"ok": True, "dvr": r}

        if op == "status":
            d = _load()
            return {"ok": True,
                    "workers_count": len(d.get("workers", [])),
                    "trainings_count": len(d.get("trainings", [])),
                    "checkups_count": len(d.get("checkups", [])),
                    "dvr": d.get("dvr"),
                    "next_90d_expiries": len(upcoming_expiries(90))}

        return {"ok": False, "error": f"op sconosciuta: {op}",
                "available_ops": ["weekly_check", "list_expiries", "add_worker",
                                   "add_training", "add_checkup", "set_dvr", "status"]}


AGENT = RsppAgent()
