"""Privacy News Scout — Tier 3.

Daily 07:00: fetch Garante Privacy + Federprivacy + EDPB. Riassume.
Triggera DPO impact assessment se item è rilevante.
"""
import threading
import time

from .team_base import TeamAgent


FEEDS = [
    # Garante per la Protezione dei Dati Personali
    {"name": "Garante Privacy", "url": "https://www.garanteprivacy.it/temi/comunicati.rss", "tag": "garante"},
    {"name": "Garante - Provvedimenti", "url": "https://www.garanteprivacy.it/home/banche-dati.rss", "tag": "garante"},
    # Federprivacy
    {"name": "Federprivacy", "url": "https://www.federprivacy.org/rss/feed-news", "tag": "federprivacy"},
    # EDPB (Comitato Europeo)
    {"name": "EDPB", "url": "https://www.edpb.europa.eu/news-rss_en", "tag": "edpb"},
]


RELEVANCE_PROMPT = """Sei il Privacy News Scout. Dato un titolo+riassunto di una news
da fonte privacy ufficiale, valuta la rilevanza per un'utente che usa un assistente AI
personale con dati conservati localmente.

Output SOLO JSON:
{
  "relevance_score": 0.0..1.0,
  "category": "sanzione|faq|provvedimento|comunicato|nuova_normativa|altro",
  "summary_it": "max 200 char in italiano",
  "trigger_dpo_review": bool
}
"""


class PrivacyScoutAgent(TeamAgent):
    name = "privacy_scout"
    tier = 3
    icon = "📜"
    description = "Daily: Garante Privacy + Federprivacy + EDPB"
    model_pref = "haiku"
    schedule = "daily 07:00"

    def __init__(self):
        super().__init__()
        threading.Thread(target=self._loop, daemon=True,
                          name="privacy_scout_loop").start()

    def _loop(self):
        # First fetch 3 min after boot, then daily at 07:00
        time.sleep(180)
        while True:
            if self.is_enabled():
                try:
                    self.safe_run({"op": "fetch"})
                except Exception:
                    pass
            # Sleep until next 07:00 local
            now = time.localtime()
            secs_today = now.tm_hour * 3600 + now.tm_min * 60 + now.tm_sec
            target = 7 * 3600
            if secs_today < target:
                wait = target - secs_today
            else:
                wait = 24 * 3600 - secs_today + target
            time.sleep(wait)

    def _fetch_feed(self, feed: dict) -> list:
        try:
            from urllib.request import Request, urlopen
            req = Request(feed["url"], headers={"User-Agent": "Mozilla/5.0 Vega"})
            with urlopen(req, timeout=15) as r:
                raw = r.read()
        except Exception as e:
            self._emit("fetch_error", {"feed": feed["name"], "error": str(e)[:200]})
            return []
        try:
            import news_graph
            return news_graph._parse_rss(raw)
        except Exception:
            return []

    def fetch_all(self) -> dict:
        total_new = 0
        triggered_dpo = 0
        for feed in FEEDS:
            items = self._fetch_feed(feed)
            for it in items[:20]:
                # Score relevance via Haiku (cheap)
                blob = f"{it.get('title', '')}\n{it.get('summary', '')[:300]}"
                prompt = f"{RELEVANCE_PROMPT}\n\nNews:\n{blob}\n\nJSON:"
                rel = self.call_haiku_json(prompt) or {}
                score = float(rel.get("relevance_score", 0))
                if score < 0.3:
                    continue
                # Salva in news_graph
                try:
                    import memory_graph as mg
                    mg.add(
                        "news",
                        f"[{feed['name']} | {rel.get('category', 'altro')}] " +
                        (rel.get("summary_it") or it.get("title", ""))[:280] +
                        f"\nLink: {it.get('link', '')}",
                        importance=score,
                        source=f"scout.privacy:{feed['tag']}",
                        tags=["privacy_official", feed["tag"]],
                    )
                    total_new += 1
                except Exception:
                    pass
                # Trigger DPO review
                if rel.get("trigger_dpo_review") or score >= 0.7:
                    triggered_dpo += 1
                    try:
                        import bus
                        bus.publish("card", {
                            "type": "privacy_news",
                            "data": {
                                "title": f"📜 {feed['name']}: {rel.get('category', 'news')}",
                                "summary": rel.get("summary_it", "")[:300],
                                "link": it.get("link", ""),
                                "trigger_dpo": True,
                            },
                        })
                    except Exception:
                        pass
        self._emit("fetch_done", {"new_items": total_new, "dpo_triggers": triggered_dpo})
        return {"ok": True, "new_items": total_new, "dpo_triggers": triggered_dpo}

    def run(self, payload: dict) -> dict:
        op = payload.get("op", "fetch")
        if op == "fetch":
            return self.fetch_all()
        return {"ok": False, "error": f"op sconosciuta: {op}"}


AGENT = PrivacyScoutAgent()
