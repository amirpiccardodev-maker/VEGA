"""Web advanced: article reader, YouTube transcript, podcast generation."""
import os
import re
import asyncio
import tempfile

import requests
from bs4 import BeautifulSoup

from tools._shared import emit_card


TOOLS = [
    {"name": "read_article_aloud",
     "description": "Carica un articolo da un URL e Vega lo legge ad alta voce + lo riassume.",
     "input_schema": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}},
    {"name": "youtube_transcript",
     "description": "Estrae il transcript di un video YouTube e lo riassume.",
     "input_schema": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}},
    {"name": "generate_podcast",
     "description": "Genera un file MP3 (audio podcast) da un testo lungo, salvato in assets/podcasts/.",
     "input_schema": {"type": "object", "properties": {
         "text": {"type": "string"},
         "title": {"type": "string"},
     }, "required": ["text"]}},
]


def _fetch_article(url: str) -> dict:
    """Fetch a URL, extract main text + title + image."""
    try:
        r = requests.get(url, timeout=12, headers={"User-Agent": "Mozilla/5.0 VegaBot"})
        r.raise_for_status()
    except Exception as e:
        return {"error": str(e)}
    soup = BeautifulSoup(r.text, "html.parser")
    # Title
    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string.strip()
    og_title = soup.find("meta", property="og:title")
    if og_title and og_title.get("content"):
        title = og_title["content"].strip()
    # Image
    image = ""
    og_image = soup.find("meta", property="og:image")
    if og_image and og_image.get("content"):
        image = og_image["content"]
    # Main content - remove noise
    for tag in soup(["script", "style", "nav", "header", "footer", "aside", "form", "noscript"]):
        tag.decompose()
    # Try common article selectors
    article = soup.find("article") or soup.find("main") or soup.body
    if article:
        text = article.get_text(separator="\n", strip=True)
    else:
        text = soup.get_text(separator="\n", strip=True)
    # Clean
    lines = [ln.strip() for ln in text.split("\n") if len(ln.strip()) > 30]
    return {"title": title, "image": image, "text": "\n".join(lines)[:8000], "url": url}


def _extract_video_id(url: str) -> str:
    """Extract YouTube video ID from various URL formats."""
    patterns = [
        r"v=([a-zA-Z0-9_-]{11})",
        r"youtu\.be/([a-zA-Z0-9_-]{11})",
        r"youtube\.com/embed/([a-zA-Z0-9_-]{11})",
        r"youtube\.com/shorts/([a-zA-Z0-9_-]{11})",
    ]
    for pat in patterns:
        m = re.search(pat, url)
        if m:
            return m.group(1)
    return ""


def run(name, args):
    if name == "read_article_aloud":
        url = args.get("url", "").strip()
        if not url:
            return "Specifica un URL."
        data = _fetch_article(url)
        if data.get("error"):
            return f"Errore lettura URL: {data['error']}"
        # Emit a card so the user sees the article
        emit_card("wikipedia", {
            "title": data.get("title", "Articolo"),
            "summary": data.get("text", "")[:600],
            "url": data.get("url"),
            "image": data.get("image", ""),
        })
        return f"Titolo: {data.get('title')}\n\n{data.get('text', '')[:3500]}"

    if name == "youtube_transcript":
        url = args.get("url", "").strip()
        vid = _extract_video_id(url)
        if not vid:
            return "URL YouTube non valido."
        try:
            from youtube_transcript_api import YouTubeTranscriptApi
        except Exception:
            return "youtube-transcript-api non disponibile."
        # Try italian first, then english, then any
        for lang in [["it"], ["en"], None]:
            try:
                if lang:
                    transcript = YouTubeTranscriptApi.get_transcript(vid, languages=lang)
                else:
                    transcript = YouTubeTranscriptApi.get_transcript(vid)
                break
            except Exception:
                transcript = None
        if not transcript:
            return "Trascrizione non disponibile per questo video."
        text = " ".join(t.get("text", "") for t in transcript)
        # Truncate to keep tokens reasonable
        text = text[:6000]
        emit_card("wikipedia", {
            "title": f"YouTube · {vid}",
            "summary": text[:600],
            "url": f"https://www.youtube.com/watch?v={vid}",
        })
        return text

    if name == "generate_podcast":
        text = args.get("text", "")
        title = args.get("title", "podcast").strip().replace(" ", "_") or "podcast"
        if not text:
            return "Testo richiesto."
        # Use TTS to generate audio
        from datetime import datetime
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe = re.sub(r"[^a-zA-Z0-9_-]", "", title)[:30]
        out_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "podcasts")
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, f"{safe}_{ts}.mp3")
        try:
            import tts as tts_mod
            tts_mod.synthesize(text[:30000], out_path)  # cap to ~30k chars
        except Exception as e:
            return f"Errore generazione podcast: {e}"
        size_mb = os.path.getsize(out_path) / 1e6
        emit_card("wikipedia", {
            "title": f"Podcast: {title}",
            "summary": f"Generato MP3 di {size_mb:.1f} MB. Salvato in:\n{out_path}",
            "url": f"/assets/podcasts/{safe}_{ts}.mp3",
        })
        return f"Podcast salvato in {out_path} ({size_mb:.1f} MB)."

    return "?"
