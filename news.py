import feedparser
from config import NEWS_FEEDS


def fetch_news(per_source: int = 5) -> str:
    blocks = []
    for name, url in NEWS_FEEDS.items():
        try:
            feed = feedparser.parse(url)
            items = []
            for entry in feed.entries[:per_source]:
                title = entry.get("title", "").strip()
                if title:
                    items.append(f"- {title}")
            if items:
                blocks.append(f"=== {name} ===\n" + "\n".join(items))
        except Exception as e:
            blocks.append(f"=== {name} === (errore: {e})")
    return "\n\n".join(blocks) if blocks else "Nessuna notizia disponibile."
