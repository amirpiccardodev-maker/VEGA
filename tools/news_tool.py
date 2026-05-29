import re
import json
import pathlib
import feedparser
import requests
from concurrent.futures import ThreadPoolExecutor
from tools._shared import emit_card

def _load_feeds() -> dict:
    """Legge news_feeds.json e restituisce {nome: url}."""
    path = pathlib.Path(__file__).parent.parent / "news_feeds.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {f["name"]: f["url"] for f in data.get("feeds", [])}
    except Exception:
        return {}

NEWS_FEEDS = _load_feeds()


def _fetch_og_image(url: str) -> str:
    """Fetch the og:image meta tag from an article page. Returns "" on failure."""
    if not url:
        return ""
    try:
        r = requests.get(url, timeout=4, headers={"User-Agent": "Mozilla/5.0 VegaBot"})
        if r.status_code >= 400:
            return ""
        # Parse only the head (faster) - look for og:image
        head = r.text[:30000]
        m = re.search(r'<meta\s+property=["\']og:image["\']\s+content=["\']([^"\']+)', head, re.I)
        if m:
            return m.group(1)
        m = re.search(r'<meta\s+name=["\']twitter:image["\']\s+content=["\']([^"\']+)', head, re.I)
        if m:
            return m.group(1)
    except Exception:
        pass
    return ""


def _extract_image(entry) -> str:
    """Pull image URL from various RSS conventions (no extra HTTP needed)."""
    # 1) media:content
    media = getattr(entry, "media_content", None)
    if media:
        for m in media:
            url = m.get("url") if isinstance(m, dict) else None
            if url and re.search(r"\.(jpg|jpeg|png|webp|gif)", url, re.I):
                return url
            if url:
                return url
    # 2) media:thumbnail
    thumbs = getattr(entry, "media_thumbnail", None)
    if thumbs:
        for t in thumbs:
            url = t.get("url") if isinstance(t, dict) else None
            if url:
                return url
    # 3) enclosures
    encs = getattr(entry, "enclosures", None) or []
    for e in encs:
        href = getattr(e, "href", None) or (e.get("href") if isinstance(e, dict) else None)
        type_ = getattr(e, "type", None) or (e.get("type") if isinstance(e, dict) else "")
        if href and (type_.startswith("image") or re.search(r"\.(jpg|jpeg|png|webp|gif)", href, re.I)):
            return href
    # 4) image tag at top-level (rare)
    img = getattr(entry, "image", None)
    if img:
        if isinstance(img, dict):
            url = img.get("href") or img.get("url")
            if url:
                return url
        elif isinstance(img, str):
            return img
    # 5) parse from summary HTML
    summary = entry.get("summary", "") or entry.get("description", "")
    m = re.search(r'<img[^>]+src=[\"\'](https?://[^\"\']+)[\"\']', summary)
    if m:
        return m.group(1)
    return ""

TOOLS = [{
    "name": "get_news",
    "description": ("[LIVE FETCH] Scarica notizie FRESCHE dalle testate italiane "
                    "(ANSA, Repubblica, Corriere, Sole24Ore) — network call (~2s). "
                    "USA SE: l'utente chiede 'ultime', 'fresche', 'di oggi', o serve "
                    "panoramica generale. Per ricerca su argomento specifico già "
                    "indicizzato localmente usa ask_recent_news (più veloce)."),
    "input_schema": {
        "type": "object",
        "properties": {
            "per_source": {"type": "integer", "description": "Titoli per testata (default 5)"},
            "source": {"type": "string", "description": "Limita a una sola testata (es. ANSA)"},
        },
    },
}]


def run(name, args):
    per_source = int(args.get("per_source", 5))
    only_source = args.get("source")
    blocks = []
    card_items = []
    for src_name, url in NEWS_FEEDS.items():
        if only_source and only_source.lower() not in src_name.lower():
            continue
        try:
            feed = feedparser.parse(url)
            items = []
            for entry in feed.entries[:per_source]:
                title = entry.get("title", "").strip()
                summary_raw = entry.get("summary", "").strip()
                # Strip HTML for textual summary
                summary = re.sub(r"<[^>]+>", "", summary_raw).strip()
                link = entry.get("link", "")
                image = _extract_image(entry)
                if title:
                    if summary:
                        items.append(f"- {title}\n  {summary[:200]}")
                    else:
                        items.append(f"- {title}")
                    card_items.append({
                        "source": src_name,
                        "title": title,
                        "summary": summary[:160],
                        "link": link,
                        "image": image,
                    })
            if items:
                blocks.append(f"=== {src_name} ===\n" + "\n".join(items))
        except Exception as e:
            blocks.append(f"=== {src_name} === (errore: {e})")
    if card_items:
        # Fetch og:image in parallel for items that have no image yet (ANSA, Repubblica)
        missing = [i for i, it in enumerate(card_items[:8]) if not it.get("image") and it.get("link")]
        if missing:
            with ThreadPoolExecutor(max_workers=6) as ex:
                imgs = list(ex.map(lambda i: _fetch_og_image(card_items[i]["link"]), missing))
            for i, img in zip(missing, imgs):
                if img:
                    card_items[i]["image"] = img
        emit_card("news", {"items": card_items[:8]})
    return "\n\n".join(blocks) if blocks else "Nessuna notizia."
