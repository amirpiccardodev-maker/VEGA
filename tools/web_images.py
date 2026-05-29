"""Cerca foto REALI sul web tramite DuckDuckGo image search (gratis, no key)."""
from tools._shared import emit_card

try:
    from duckduckgo_search import DDGS
    _AVAIL = True
except Exception:
    _AVAIL = False


TOOLS = [{
    "name": "web_images",
    "description": "Cerca FOTO REALI sul web. Usalo quando l'utente vuole vedere foto di posti, persone famose, oggetti, eventi (es. 'mostrami foto di Roma', 'foto del Colosseo', 'come e' fatto il Burj Khalifa'). Per immagini AI-generate usa generate_image invece.",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Cosa cercare (es. 'Tour Eiffel di notte', 'spiagge Sardegna')"},
            "max_results": {"type": "integer", "description": "Default 6, max 10"},
        },
        "required": ["query"],
    },
}]


def run(name, args):
    if not _AVAIL:
        return "Ricerca immagini non disponibile."
    q = args.get("query", "").strip()
    n = max(3, min(int(args.get("max_results", 6)), 10))
    if not q:
        return "Specifica cosa cercare."
    try:
        with DDGS() as ddgs:
            results = list(ddgs.images(q, max_results=n, region="it-it", safesearch="moderate"))
    except Exception as e:
        return f"Ricerca immagini fallita: {e}"
    if not results:
        return "Nessuna immagine trovata."

    items = []
    for r in results:
        url = r.get("image") or r.get("thumbnail")
        if not url:
            continue
        items.append({
            "url": url,
            "title": (r.get("title") or "")[:80],
            "source": r.get("source") or "",
            "page": r.get("url") or "",
        })

    if items:
        emit_card("gallery", {"query": q, "items": items[:n]})

    return f"Trovate {len(items)} immagini per '{q}'. Mostrate nella galleria."
