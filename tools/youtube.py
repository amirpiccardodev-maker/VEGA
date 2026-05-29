"""YouTube: search and open videos."""
import webbrowser
import urllib.parse
import requests
import re

TOOLS = [
    {
        "name": "youtube_search",
        "description": "Cerca video su YouTube e restituisce i primi risultati con titolo e link.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "max_results": {"type": "integer"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "youtube_play",
        "description": "Apre direttamente il primo video YouTube corrispondente alla ricerca nel browser.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
]


def _search(query: str, n: int = 5):
    url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote(query)
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "it-IT"}, timeout=10)
    except Exception:
        return []
    ids = re.findall(r'"videoId":"([a-zA-Z0-9_-]{11})"', r.text)
    titles = re.findall(r'"title":\{"runs":\[\{"text":"([^"]+)"', r.text)
    seen = set()
    out = []
    for vid, title in zip(ids, titles):
        if vid in seen:
            continue
        seen.add(vid)
        out.append({"id": vid, "title": title, "url": f"https://www.youtube.com/watch?v={vid}"})
        if len(out) >= n:
            break
    return out


def run(name, args):
    if name == "youtube_search":
        q = args.get("query", "")
        n = int(args.get("max_results", 5))
        results = _search(q, n)
        if not results:
            return "Nessun risultato."
        return "\n".join(f"{i+1}. {r['title']}\n   {r['url']}" for i, r in enumerate(results))

    if name == "youtube_play":
        q = args.get("query", "")
        results = _search(q, 1)
        if not results:
            return "Nessun video trovato."
        webbrowser.open(results[0]["url"])
        return f"Aperto: {results[0]['title']}"

    return "?"
