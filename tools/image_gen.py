"""Image generation via Pollinations.ai (free, no API key, unlimited).

Builds a URL that Pollinations serves directly as an image. Falls back to
returning the URL for the UI to display. No bytes downloaded server-side.
"""
import urllib.parse
import random
import requests

from tools._shared import emit_card


TOOLS = [{
    "name": "generate_image",
    "description": "Genera un'immagine da una descrizione testuale. Gratis, locale via Pollinations. Usalo quando l'utente dice 'crea un'immagine di X', 'genera una foto di X', 'disegnami X'.",
    "input_schema": {
        "type": "object",
        "properties": {
            "prompt": {"type": "string", "description": "Descrizione dell'immagine (anche in italiano)"},
            "style": {"type": "string", "description": "Es. 'realistic', 'anime', 'painting', 'cyberpunk' (opzionale)"},
            "width": {"type": "integer", "description": "Default 1024"},
            "height": {"type": "integer", "description": "Default 1024"},
        },
        "required": ["prompt"],
    },
}]


def _build_url(prompt: str, width: int, height: int, seed: int, model: str = "flux"):
    p = urllib.parse.quote(prompt)
    return (f"https://image.pollinations.ai/prompt/{p}"
            f"?width={width}&height={height}&seed={seed}&model={model}&nologo=true&enhance=true")


def run(name, args):
    if name != "generate_image":
        return "?"
    prompt = args.get("prompt", "").strip()
    if not prompt:
        return "Specifica una descrizione."
    style = args.get("style", "").strip()
    if style:
        full_prompt = f"{prompt}, {style} style, high quality, detailed"
    else:
        full_prompt = f"{prompt}, high quality, detailed"

    width = max(256, min(int(args.get("width", 1024)), 2048))
    height = max(256, min(int(args.get("height", 1024)), 2048))
    seed = random.randint(1, 999999)

    url = _build_url(full_prompt, width, height, seed)

    # Emit the URL immediately. Browser handles loading + retries.
    # (Doing HEAD/GET here would add 5-30s of latency before user sees anything.)
    emit_card("image", {
        "url": url,
        "prompt": prompt,
        "style": style,
        "width": width,
        "height": height,
        "seed": seed,
    })

    return f"Immagine richiesta: {prompt[:80]}. Apparira' nella card."
