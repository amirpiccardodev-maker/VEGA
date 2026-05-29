"""Continuous news ingestion → searchable knowledge graph.

Poll RSS feeds ogni N minuti, dedup via hash url, embedding del titolo+summary,
salvataggio in memory_graph kind='news'. La search a posteriori funziona già
via memory_graph.search() perché embedding-based.

Feeds configurabili in news_feeds.json (creato se manca con default IT).
"""
import json
import threading
import time
import hashlib
from pathlib import Path
from urllib.request import urlopen, Request

import bus


ROOT = Path(__file__).parent
FEEDS_FILE = ROOT / "news_feeds.json"
POLL_INTERVAL_SEC = 30 * 60   # 30 min
USER_AGENT = "Mozilla/5.0 Vega/1.0"

DEFAULT_FEEDS = [
    {"name": "ANSA Top", "url": "https://www.ansa.it/sito/ansait_rss.xml", "lang": "it"},
    {"name": "Repubblica HP", "url": "https://www.repubblica.it/rss/homepage/rss2.0.xml", "lang": "it"},
    {"name": "Il Post", "url": "https://www.ilpost.it/feed/", "lang": "it"},
    {"name": "HN", "url": "https://news.ycombinator.com/rss", "lang": "en"},
    {"name": "BBC World", "url": "http://feeds.bbci.co.uk/news/world/rss.xml", "lang": "en"},
]

_started = False
_seen_hashes = set()  # de-dup across cycles


def _load_feeds():
    if not FEEDS_FILE.exists():
        with open(FEEDS_FILE, "w", encoding="utf-8") as f:
            json.dump({"feeds": DEFAULT_FEEDS}, f, ensure_ascii=False, indent=2)
        return DEFAULT_FEEDS
    try:
        with open(FEEDS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("feeds", DEFAULT_FEEDS)
    except Exception:
        return DEFAULT_FEEDS


def _parse_rss(xml_bytes: bytes) -> list:
    """Minimal RSS/Atom parser via stdlib. Returns list of {title, link, summary}."""
    import xml.etree.ElementTree as ET
    items = []
    try:
        root = ET.fromstring(xml_bytes)
    except Exception:
        return items
    # RSS 2.0: channel/item
    for it in root.iter():
        tag = it.tag.split("}")[-1]
        if tag in ("item", "entry"):
            title, link, summary = "", "", ""
            for child in it:
                ctag = child.tag.split("}")[-1]
                if ctag == "title":
                    title = (child.text or "").strip()
                elif ctag == "link":
                    link = (child.attrib.get("href") or child.text or "").strip()
                elif ctag in ("summary", "description"):
                    summary = (child.text or "").strip()
            if title:
                items.append({"title": title, "link": link, "summary": summary[:500]})
    return items


def _fetch_feed(feed: dict) -> list:
    try:
        req = Request(feed["url"], headers={"User-Agent": USER_AGENT})
        with urlopen(req, timeout=10) as r:
            return _parse_rss(r.read())
    except Exception as e:
        bus.publish("news.fetch_error", {"feed": feed.get("name"), "error": str(e)[:200]})
        return []


def _ingest_one(feed: dict):
    items = _fetch_feed(feed)
    added = 0
    for it in items[:30]:  # cap per feed per cycle
        h = hashlib.md5((it["link"] or it["title"]).encode("utf-8")).hexdigest()[:16]
        if h in _seen_hashes:
            continue
        _seen_hashes.add(h)
        try:
            import memory_graph as mg
            content = f"[{feed['name']}] {it['title']}"
            if it.get("summary"):
                content += f"\n{it['summary']}"
            mg.add("news", content, importance=0.4, source=f"rss:{feed['name']}",
                   meta={"link": it.get("link"), "lang": feed.get("lang", "it")})
            added += 1
        except Exception:
            pass
    return added


def _cycle():
    feeds = _load_feeds()
    total = 0
    for f in feeds:
        try:
            total += _ingest_one(f)
        except Exception as e:
            bus.publish("error.occurred", {"source": "news_graph", "error": str(e)})
    if total:
        bus.publish("news.ingested", {"count": total})


def _loop():
    # First ingestion ~20s after boot (don't slow startup)
    time.sleep(20)
    while True:
        try:
            _cycle()
        except Exception as e:
            bus.publish("error.occurred", {"source": "news_graph", "error": str(e)})
        time.sleep(POLL_INTERVAL_SEC)


def start():
    global _started
    if _started:
        return
    _started = True
    threading.Thread(target=_loop, daemon=True, name="news_graph").start()
    bus.publish("news_graph.started", {})


def search_recent(query: str, top_k: int = 5) -> list:
    """Cerca tra le news ingerite. Wrapper su memory_graph."""
    try:
        import memory_graph as mg
        return mg.search(query, kinds=["news"], top_k=top_k, min_similarity=0.25)
    except Exception:
        return []
