"""Email Manager — smistamento + riassunto inbox + draft replies."""
import json
import time
from pathlib import Path

from .team_base import TeamAgent


ROOT = Path(__file__).parent.parent
DATA_FILE = ROOT / "data" / "email_inbox_state.json"
DATA_FILE.parent.mkdir(parents=True, exist_ok=True)


URGENT_KEYWORDS = ("urgente", "urgent", "asap", "subito", "entro oggi",
                    "scadenza", "deadline", "importante", "richiesto",
                    "fattura scaduta", "sollecito")
SPAM_KEYWORDS = ("offerta", "sconto", "promozione", "newsletter",
                  "unsubscribe", "marketing", "click here")


def _load() -> dict:
    if not DATA_FILE.exists():
        return {"last_summary": None, "last_check": 0, "categories": {}}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"last_summary": None, "last_check": 0, "categories": {}}


def _save(d: dict):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)


def _classify(subject: str, snippet: str = "") -> str:
    blob = f"{subject} {snippet}".lower()
    if any(k in blob for k in URGENT_KEYWORDS):
        return "urgent"
    if any(k in blob for k in SPAM_KEYWORDS):
        return "spam"
    if "newsletter" in blob or "notifica" in blob:
        return "info"
    return "normal"


class EmailManagerAgent(TeamAgent):
    name = "email_manager"
    tier = 2
    icon = "📧"
    description = "Smista inbox, classifica priorità, prepara bozze (no send auto)"
    model_pref = "haiku"
    schedule = "interval 30m"
    subscribes = []

    def run(self, payload):
        payload = payload or {}
        op = payload.get("op", "check")

        if op == "check":
            try:
                import tools as _tr
                raw = _tr.execute("list_emails", {"limit": 20})
            except Exception as e:
                return {"ok": False, "error": f"list_emails failed: {e}"}
            text = str(raw)
            lines = [l for l in text.split("\n") if l.strip()]
            categories = {"urgent": [], "normal": [], "info": [], "spam": []}
            for line in lines[:30]:
                cat = _classify(line)
                categories[cat].append(line[:200])
            d = _load()
            d["last_check"] = int(time.time())
            d["categories"] = {k: len(v) for k, v in categories.items()}
            _save(d)
            if categories["urgent"]:
                self._emit("urgent_mail", {"count": len(categories["urgent"])})
                for u in categories["urgent"][:3]:
                    self.remember("todo",
                        f"📧 Email urgente: {u[:200]}",
                        importance=0.85, tags=["email", "urgent"])
            self._emit("inbox_classified", {
                "urgent": len(categories["urgent"]),
                "normal": len(categories["normal"]),
                "info": len(categories["info"]),
                "spam": len(categories["spam"]),
            })
            return {"ok": True, "categories": {
                k: {"count": len(v), "sample": v[:3]}
                for k, v in categories.items()
            }}

        if op == "summarize":
            try:
                import tools as _tr
                summary = _tr.execute("summarize_inbox", {"limit": 15})
                d = _load()
                d["last_summary"] = {"ts": int(time.time()),
                                       "text": str(summary)[:1500]}
                _save(d)
                return {"ok": True, "summary": str(summary)[:1500]}
            except Exception as e:
                return {"ok": False, "error": str(e)}

        if op == "draft_reply":
            try:
                import tools as _tr
                draft = _tr.execute("compose_draft", {
                    "to": payload.get("to", ""),
                    "subject": "Re: " + payload.get("subject", ""),
                    "body": payload.get("hint", "(stesura automatica)"),
                })
                return {"ok": True, "draft": str(draft)}
            except Exception as e:
                return {"ok": False, "error": str(e)}

        if op == "status":
            return {"ok": True, "state": _load()}

        return {"ok": False, "error": f"op sconosciuta: {op}",
                "available_ops": ["check", "summarize", "draft_reply", "status"]}


AGENT = EmailManagerAgent()
