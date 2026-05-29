"""Admin agent — fatturazione + scadenze fiscali italiane reali."""
import json
import time
from datetime import date, timedelta
from pathlib import Path

from .team_base import TeamAgent


ROOT = Path(__file__).parent.parent
DATA_FILE = ROOT / "data" / "admin_invoices.json"
DATA_FILE.parent.mkdir(parents=True, exist_ok=True)


def _load() -> dict:
    if not DATA_FILE.exists():
        return {"invoices": [], "deadlines_seen": []}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"invoices": [], "deadlines_seen": []}


def _save(d: dict):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)


def _annual_deadlines(year: int) -> list:
    return [
        {"name": "Diritto camerale", "date": date(year, 6, 16), "category": "annual"},
        {"name": "Redditi PF (saldo + 1° acconto)", "date": date(year, 6, 30), "category": "annual"},
        {"name": "Redditi PF (con maggiorazione 0.4%)", "date": date(year, 7, 30), "category": "annual"},
        {"name": "2° acconto IRPEF/IRES", "date": date(year, 11, 30), "category": "annual"},
        {"name": "Dichiarazione IVA annuale", "date": date(year + 1, 4, 30), "category": "annual"},
    ]


def _lipe_deadlines(year: int) -> list:
    return [
        {"name": "LIPE Q1", "date": date(year, 5, 31), "category": "lipe"},
        {"name": "LIPE Q2", "date": date(year, 9, 16), "category": "lipe"},
        {"name": "LIPE Q3", "date": date(year, 11, 30), "category": "lipe"},
        {"name": "LIPE Q4", "date": date(year + 1, 2, 28), "category": "lipe"},
    ]


def upcoming_deadlines(days_ahead: int = 60) -> list:
    today = date.today()
    horizon = today + timedelta(days=days_ahead)
    out = []
    for offset in range(0, 3):
        m = today.month + offset
        y = today.year
        while m > 12:
            m -= 12
            y += 1
        f24 = date(y, m, 16)
        if today <= f24 <= horizon:
            out.append({"name": f"F24 {f24.strftime('%B %Y')}",
                         "date": f24, "category": "f24_monthly"})
    iva_dates = [date(today.year, 5, 16), date(today.year, 8, 20),
                  date(today.year, 11, 16), date(today.year + 1, 3, 16)]
    for d in iva_dates:
        if today <= d <= horizon:
            out.append({"name": "Liquidazione IVA trimestrale",
                         "date": d, "category": "iva_trim"})
    for d in _annual_deadlines(today.year) + _lipe_deadlines(today.year):
        if today <= d["date"] <= horizon:
            out.append(d)
    out.sort(key=lambda x: x["date"])
    for d in out:
        d["date_iso"] = d["date"].isoformat()
        d["days_until"] = (d["date"] - today).days
        d.pop("date", None)
    return out


def overdue_invoices() -> list:
    today = date.today()
    out = []
    for inv in _load().get("invoices", []):
        if inv.get("paid"):
            continue
        try:
            due = date.fromisoformat(inv["payment_due"])
        except Exception:
            continue
        if due < today:
            inv["days_overdue"] = (today - due).days
            out.append(inv)
    out.sort(key=lambda x: -x.get("days_overdue", 0))
    return out


def monthly_summary(year: int = None, month: int = None) -> dict:
    today = date.today()
    y = year or today.year
    m = month or today.month
    billed = paid = outstanding = 0.0
    count = 0
    for inv in _load().get("invoices", []):
        try:
            issue = date.fromisoformat(inv["issue_date"])
        except Exception:
            continue
        if issue.year == y and issue.month == m:
            billed += inv.get("amount", 0)
            count += 1
            if inv.get("paid"):
                paid += inv.get("amount", 0)
            else:
                outstanding += inv.get("amount", 0)
    return {"year": y, "month": m, "invoices_count": count,
            "billed": round(billed, 2), "paid": round(paid, 2),
            "outstanding": round(outstanding, 2)}


class AdminAgent(TeamAgent):
    name = "admin"
    tier = 2
    icon = "💰"
    description = "Fatturazione + scadenze fiscali italiane (F24/IVA/LIPE/redditi)"
    model_pref = "haiku"
    schedule = "daily 08:00"
    subscribes = []

    def run(self, payload):
        payload = payload or {}
        op = payload.get("op", "daily_check")

        if op == "daily_check":
            deadlines = upcoming_deadlines(days_ahead=14)
            d = _load()
            seen = set(d.get("deadlines_seen", []))
            alerts = 0
            for dl in deadlines:
                key = f"{dl['name']}|{dl['date_iso']}"
                if key in seen or dl["days_until"] > 7:
                    continue
                seen.add(key)
                self._emit("deadline_alert", {"name": dl["name"],
                                               "days_until": dl["days_until"]})
                self.remember("todo",
                    f"⏰ Scadenza fiscale: {dl['name']} il {dl['date_iso']} "
                    f"(tra {dl['days_until']} giorni)",
                    importance=0.85, tags=["admin", "fiscal"])
                alerts += 1
            d["deadlines_seen"] = list(seen)[-200:]
            _save(d)
            overdue = overdue_invoices()
            for inv in overdue[:5]:
                self.remember("todo",
                    f"💰 Fattura {inv['number']} a {inv['client']} scaduta da "
                    f"{inv['days_overdue']}gg (€{inv['amount']:.2f})",
                    importance=0.9, tags=["admin", "overdue"])
            return {"ok": True, "deadlines_count": len(deadlines),
                    "next_3": deadlines[:3], "overdue_count": len(overdue),
                    "alerts_emitted": alerts}

        if op == "list_deadlines":
            return {"ok": True, "deadlines":
                upcoming_deadlines(days_ahead=int(payload.get("days", 60)))}

        if op == "add_invoice":
            d = _load()
            inv = {
                "id": f"inv_{int(time.time())}",
                "number": payload.get("number") or
                          f"{date.today().year}/{len(d['invoices'])+1:04d}",
                "client": payload.get("client", "Cliente"),
                "amount": float(payload.get("amount", 0)),
                "issue_date": payload.get("issue_date") or date.today().isoformat(),
                "payment_due": payload.get("payment_due") or
                                (date.today() + timedelta(days=30)).isoformat(),
                "paid": False,
                "notes": payload.get("notes", ""),
                "created_ts": int(time.time()),
            }
            d["invoices"].append(inv)
            _save(d)
            self._emit("invoice_added", {"id": inv["id"], "client": inv["client"]})
            return {"ok": True, "invoice": inv}

        if op == "mark_paid":
            iid = payload.get("invoice_id", "")
            d = _load()
            for inv in d["invoices"]:
                if inv["id"] == iid:
                    inv["paid"] = True
                    inv["paid_date"] = payload.get("paid_date") or date.today().isoformat()
                    _save(d)
                    return {"ok": True, "invoice": inv}
            return {"ok": False, "error": "fattura non trovata"}

        if op == "overdue":
            return {"ok": True, "overdue": overdue_invoices()}

        if op == "monthly_summary":
            return {"ok": True, "summary": monthly_summary(
                year=payload.get("year"), month=payload.get("month"))}

        if op == "create_invoice_template":
            client = payload.get("client", "Cliente")
            self.remember("instruction",
                f"Template fatturazione attivo per cliente: {client}",
                importance=0.5, tags=["admin", "client_template"])
            return {"ok": True, "client": client, "template_created": True}

        if op == "generate_invoices":
            return {"ok": True, "summary": monthly_summary()}

        return {"ok": False, "error": f"op sconosciuta: {op}",
                "available_ops": ["daily_check", "list_deadlines", "add_invoice",
                                   "mark_paid", "overdue", "monthly_summary",
                                   "create_invoice_template", "generate_invoices"]}


AGENT = AdminAgent()
