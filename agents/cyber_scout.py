"""Cyber News Scout — Tier 3.

Daily: CSIRT Italia + ENISA + CISA KEV. Triggera CISO se CVE rilevanti
toccano dipendenze rilevate dal cve_scanner.
"""
import threading
import time

from .team_base import TeamAgent


FEEDS = [
    {"name": "CSIRT Italia", "url": "https://www.csirt.gov.it/contenuti/rss/news.rss", "tag": "csirt_it"},
    {"name": "CISA Alerts", "url": "https://www.cisa.gov/news-events/cybersecurity-advisories/all.xml", "tag": "cisa"},
    {"name": "ENISA News", "url": "https://www.enisa.europa.eu/news/rss-feed", "tag": "enisa"},
    {"name": "ACN", "url": "https://www.acn.gov.it/portale/rss", "tag": "acn"},
]


class CyberScoutAgent(TeamAgent):
    name = "cyber_scout"
    tier = 3
    icon = "🛡"
    description = "Daily: CSIRT Italia, CISA, ENISA, ACN"
    model_pref = "haiku"
    schedule = "daily 07:15"

    def __init__(self):
        super().__init__()
        threading.Thread(target=self._loop, daemon=True,
                          name="cyber_scout_loop").start()

    def _loop(self):
        time.sleep(240)
        while True:
            if self.is_enabled():
                try:
                    self.safe_run({"op": "fetch"})
                except Exception:
                    pass
            now = time.localtime()
            secs_today = now.tm_hour * 3600 + now.tm_min * 60 + now.tm_sec
            target = 7 * 3600 + 15 * 60
            wait = (target - secs_today) if secs_today < target else (24 * 3600 - secs_today + target)
            time.sleep(wait)

    def fetch_all(self) -> dict:
        total_new = 0
        ciso_triggers = 0
        for feed in FEEDS:
            try:
                from urllib.request import Request, urlopen
                req = Request(feed["url"], headers={"User-Agent": "Mozilla/5.0 Vega"})
                with urlopen(req, timeout=15) as r:
                    raw = r.read()
                import news_graph
                items = news_graph._parse_rss(raw)
            except Exception as e:
                self._emit("fetch_error", {"feed": feed["name"], "error": str(e)[:200]})
                continue
            for it in items[:20]:
                title = it.get("title", "")
                # Quick keyword filter for relevance
                low = (title + " " + it.get("summary", "")).lower()
                is_critical = any(kw in low for kw in
                                    ["critical", "critica", "rce", "exploit",
                                     "0-day", "zero day", "actively exploited",
                                     "ransomware", "data breach"])
                try:
                    import memory_graph as mg
                    mg.add(
                        "news",
                        f"[{feed['name']}] {title}\n{it.get('summary', '')[:300]}\nLink: {it.get('link', '')}",
                        importance=0.7 if is_critical else 0.4,
                        source=f"scout.cyber:{feed['tag']}",
                        tags=["cyber_official", feed["tag"]] + (["critical"] if is_critical else []),
                    )
                    total_new += 1
                except Exception:
                    pass
                if is_critical:
                    ciso_triggers += 1
                    try:
                        import bus
                        bus.publish("cyber.threat_alert", {
                            "feed": feed["name"], "title": title[:200],
                            "link": it.get("link", ""),
                        })
                        bus.publish("card", {
                            "type": "cyber_news",
                            "data": {
                                "title": f"🛡 {feed['name']}: avviso critico",
                                "summary": title[:280],
                                "link": it.get("link", ""),
                                "critical": True,
                            },
                        })
                    except Exception:
                        pass
        self._emit("fetch_done", {"new_items": total_new, "critical": ciso_triggers})
        return {"ok": True, "new_items": total_new, "critical_alerts": ciso_triggers}

    def run(self, payload: dict) -> dict:
        op = payload.get("op", "fetch")
        if op == "fetch":
            return self.fetch_all()
        return {"ok": False, "error": f"op sconosciuta: {op}"}


AGENT = CyberScoutAgent()
