"""Market Scout — Tier 3.

Weekly: HackerNews, ProductHunt, ANSA economia. Alimenta Marketing Agent.
"""
import threading
import time

from .team_base import TeamAgent


FEEDS = [
    {"name": "Hacker News Top", "url": "https://news.ycombinator.com/rss", "tag": "hn"},
    {"name": "ProductHunt", "url": "https://www.producthunt.com/feed", "tag": "ph"},
    {"name": "ANSA Economia", "url": "https://www.ansa.it/sito/notizie/economia/economia_rss.xml", "tag": "ansa_eco"},
]


class MarketScoutAgent(TeamAgent):
    name = "market_scout"
    tier = 3
    icon = "📈"
    description = "Weekly: trend tech + business + economia"
    model_pref = "haiku"
    schedule = "weekly Monday 08:00"

    def __init__(self):
        super().__init__()
        threading.Thread(target=self._loop, daemon=True,
                          name="market_scout_loop").start()

    def _loop(self):
        time.sleep(420)
        while True:
            if self.is_enabled():
                try:
                    self.safe_run({"op": "fetch"})
                except Exception:
                    pass
            time.sleep(7 * 24 * 3600)

    def fetch_all(self) -> dict:
        total_new = 0
        for feed in FEEDS:
            try:
                from urllib.request import Request, urlopen
                req = Request(feed["url"], headers={"User-Agent": "Mozilla/5.0 Vega"})
                with urlopen(req, timeout=15) as r:
                    raw = r.read()
                import news_graph
                items = news_graph._parse_rss(raw)
            except Exception:
                continue
            for it in items[:15]:
                try:
                    import memory_graph as mg
                    mg.add(
                        "news",
                        f"[{feed['name']}] {it.get('title', '')}\n{it.get('summary', '')[:300]}",
                        importance=0.3,
                        source=f"scout.market:{feed['tag']}",
                        tags=["market_trends", feed["tag"]],
                    )
                    total_new += 1
                except Exception:
                    pass
        self._emit("fetch_done", {"new_items": total_new})
        return {"ok": True, "new_items": total_new}

    def run(self, payload: dict) -> dict:
        if payload.get("op", "fetch") == "fetch":
            return self.fetch_all()
        return {"ok": False, "error": "op sconosciuta"}


AGENT = MarketScoutAgent()
