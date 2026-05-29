import wikipediaapi
import requests
from tools._shared import emit_card


def _get_lead_image(title: str) -> str:
    """Fetch the main image of a Wikipedia page via the REST API."""
    try:
        url = f"https://it.wikipedia.org/w/api.php"
        params = {
            "action": "query",
            "prop": "pageimages",
            "format": "json",
            "piprop": "original|thumbnail",
            "pithumbsize": 600,
            "titles": title,
        }
        r = requests.get(url, params=params, timeout=6,
                         headers={"User-Agent": "VegaPersonal/1.0"})
        data = r.json()
        pages = data.get("query", {}).get("pages", {})
        for pid, page in pages.items():
            thumb = page.get("thumbnail", {}).get("source")
            if thumb:
                return thumb
            orig = page.get("original", {}).get("source")
            if orig:
                return orig
    except Exception:
        pass
    return ""

TOOLS = [{
    "name": "wikipedia",
    "description": "Cerca e riassume un argomento su Wikipedia (italiano).",
    "input_schema": {
        "type": "object",
        "properties": {
            "topic": {"type": "string", "description": "Argomento o nome da cercare"},
            "sentences": {"type": "integer", "description": "Lunghezza riassunto (default 4)"},
        },
        "required": ["topic"],
    },
}]


def run(name, args):
    topic = args.get("topic", "").strip()
    sents = int(args.get("sentences", 4))
    if not topic:
        return "Specifica un argomento."
    wiki = wikipediaapi.Wikipedia(language="it", user_agent="VegaPersonal/1.0")
    page = wiki.page(topic)
    if not page.exists():
        return f"Nessuna pagina Wikipedia trovata per '{topic}'."
    summary = page.summary
    parts = summary.split(". ")
    short = ". ".join(parts[:sents]).strip()
    if short and not short.endswith("."):
        short += "."
    image = _get_lead_image(page.title)
    emit_card("wikipedia", {
        "title": page.title,
        "summary": short,
        "url": page.fullurl,
        "image": image,
    })
    return f"{page.title}\n\n{short}\n\nFonte: {page.fullurl}"
