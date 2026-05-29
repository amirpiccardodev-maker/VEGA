"""Sport: feed RSS ANSA Sport per risultati e notizie sportive italiane."""
import feedparser

TOOLS = [{
    "name": "sports_news",
    "description": "Notizie sportive del giorno (ANSA Sport).",
    "input_schema": {
        "type": "object",
        "properties": {
            "max_items": {"type": "integer", "description": "Default 6"},
        },
    },
}]


def run(name, args):
    n = int(args.get("max_items", 6))
    try:
        feed = feedparser.parse("https://www.ansa.it/sito/notizie/sport/sport_rss.xml")
        items = feed.entries[:n]
    except Exception as e:
        return f"Errore: {e}"
    if not items:
        return "Nessuna notizia sportiva."
    return "\n".join(f"- {e.get('title','')}" for e in items)
