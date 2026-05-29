"""Web search + page reader."""
import requests
from bs4 import BeautifulSoup

try:
    from duckduckgo_search import DDGS
    _DDG = True
except Exception:
    _DDG = False


TOOLS = [
    {
        "name": "web_search",
        "description": "Cerca sul web (DuckDuckGo). Restituisce i primi risultati con titolo e snippet.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "max_results": {"type": "integer", "description": "Default 5"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "read_webpage",
        "description": "Scarica una pagina web e restituisce il testo principale (max ~6000 caratteri).",
        "input_schema": {
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "required": ["url"],
        },
    },
]


def run(name, args):
    if name == "web_search":
        if not _DDG:
            return "duckduckgo_search non disponibile."
        q = args.get("query", "")
        n = int(args.get("max_results", 5))
        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(q, max_results=n, region="it-it"))
        except Exception as e:
            return f"Ricerca fallita: {e}"
        if not results:
            return "Nessun risultato."
        out = []
        for i, r in enumerate(results, 1):
            out.append(f"{i}. {r.get('title','')}\n   {r.get('body','')[:200]}\n   {r.get('href','')}")
        return "\n\n".join(out)

    if name == "read_webpage":
        url = args.get("url", "").strip()
        if not url.startswith("http"):
            url = "https://" + url
        try:
            r = requests.get(url, timeout=12, headers={"User-Agent": "Mozilla/5.0 VegaBot"})
            r.raise_for_status()
        except Exception as e:
            return f"Errore: {e}"
        soup = BeautifulSoup(r.text, "html.parser")
        for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        lines = [ln for ln in text.split("\n") if len(ln.strip()) > 20]
        clean = "\n".join(lines)[:6000]
        title = soup.title.string.strip() if soup.title and soup.title.string else url
        return f"{title}\n{url}\n\n{clean}"

    return "?"
