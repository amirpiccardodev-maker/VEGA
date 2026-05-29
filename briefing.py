"""Morning Briefing aggregator.

Mega-card mostrata alla prima apertura del giorno. Aggrega:
  - Top news privacy + cyber (dalle ultime 24h)
  - Incident NIS2 aperti
  - Proposte Innovator pendenti
  - Meteo (se home_location configurato)
  - Compliance score (audit watcher last report)

API:
    build_morning_briefing() -> dict (payload card)
    should_show_today(client_id) -> bool   # dedup per giorno
"""
import json
import time
from pathlib import Path


ROOT = Path(__file__).parent
DATA_FILE = ROOT / "data" / "briefing_shown.json"
DATA_FILE.parent.mkdir(parents=True, exist_ok=True)


def _today_key() -> str:
    return time.strftime("%Y-%m-%d")


def should_show_today(client_id: str = "default") -> bool:
    """True se non abbiamo ancora mostrato il briefing oggi per questo client."""
    try:
        if not DATA_FILE.exists():
            return True
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            d = json.load(f)
        return d.get(client_id) != _today_key()
    except Exception:
        return True


def mark_shown(client_id: str = "default"):
    try:
        d = {}
        if DATA_FILE.exists():
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                d = json.load(f)
        d[client_id] = _today_key()
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _top_news(tag: str, limit: int) -> list:
    """Cerca news recenti con tag specifico (privacy_official / cyber_official)."""
    try:
        import memory_graph as mg
        # Cerca con query empty filtrata per kind/tags non è supportato direttamente
        # quindi prendiamo by kind e filtriamo per tag
        items = mg.search(tag.replace("_", " "), kinds=["news"], top_k=20)
        out = []
        for it in items:
            tags = it.get("tags") or []
            if isinstance(tags, str):
                # tags can be JSON string in sqlite
                try:
                    tags = json.loads(tags)
                except Exception:
                    tags = [tags]
            if tag in tags:
                out.append({
                    "content": it.get("content", "")[:280],
                    "importance": it.get("importance", 0),
                    "created_ts": it.get("created_ts"),
                })
            if len(out) >= limit:
                break
        return out
    except Exception:
        return []


def _open_incidents() -> list:
    try:
        from agents import ciso
        all_inc = ciso.AGENT.list_incidents(status="open")
        return [
            {
                "id": i["id"],
                "classification": i.get("classification"),
                "title": i.get("title", "")[:200],
                "discovered_at": i.get("discovered_at"),
                "notification_required": i.get("nis2_notification_required"),
                "notification_deadline_hours": i.get("notification_deadline_hours"),
            }
            for i in all_inc[:5]
        ]
    except Exception:
        return []


def _pending_proposals() -> list:
    """Proposte Innovator non ancora processate (kind=instruction tag=innovation)."""
    try:
        import memory_graph as mg
        items = mg.search("proposta feature innovazione", kinds=["instruction"], top_k=10)
        return [
            {"content": it.get("content", "")[:300], "importance": it.get("importance", 0)}
            for it in items[:3]
        ]
    except Exception:
        return []


def _weather():
    try:
        import tools as tr
        cards_captured = []
        def emit(event, payload):
            if event == "card":
                cards_captured.append(payload)
        # Get weather (uses home_location)
        tr.execute("get_weather", {}, emit=emit)
        if cards_captured:
            return cards_captured[0].get("data", {})
    except Exception:
        pass
    return None


def _compliance_summary():
    """Ultimo report mensile + stato veloce."""
    try:
        from agents import audit_watcher
        report = audit_watcher.AGENT.monthly_report()
        m = (report or {}).get("metrics", {})
        return {
            "dpo_vetoes": m.get("dpo_vetoes", 0),
            "incidents_open": m.get("incidents_open_now", 0),
            "shield_injections": m.get("shield_injections_caught", 0),
            "canary_leaks": m.get("canary_leaks", 0),
            "audit_records": m.get("audit_records_analyzed", 0),
        }
    except Exception:
        return {}


def build_morning_briefing() -> dict:
    """Compose the briefing payload (dict, ready to emit as card)."""
    return {
        "type": "morning_briefing",
        "data": {
            "title": f"☀️ Buongiorno — Briefing {time.strftime('%A %d %B', time.localtime())}",
            "generated_at": int(time.time()),
            "privacy_news": _top_news("privacy_official", limit=3),
            "cyber_news": _top_news("cyber_official", limit=3),
            "open_incidents": _open_incidents(),
            "pending_proposals": _pending_proposals(),
            "weather": _weather(),
            "compliance": _compliance_summary(),
        },
    }
