"""Vision: take a screenshot and let Claude see it (lazy import pyautogui)."""

TOOLS = [{
    "name": "analyze_screen",
    "description": "Cattura uno screenshot dello schermo attuale e lo passa al modello per analisi visiva. Usalo quando l'utente chiede 'guarda lo schermo', 'cosa vedi', 'descrivimi quello che e' aperto', oppure quando serve sapere cosa c'e' a video.",
    "input_schema": {
        "type": "object",
        "properties": {
            "region": {"type": "string", "description": "'full' (default), 'left', 'right', 'top', 'bottom'"},
        },
    },
}, {
    "name": "analyze_image",
    "description": "Carica un'immagine da un file path locale e la passa al modello per analisi visiva. Usalo quando l'utente trascina un'immagine, chiede 'guarda questa foto', 'cosa c'e' in questa immagine', oppure dopo che un'immagine e' stata generata e serve descriverla.",
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Percorso assoluto del file immagine (PNG/JPG/JPEG/GIF/WEBP/BMP)."},
        },
        "required": ["path"],
    },
}]


def run(name, args):
    import base64
    import io
    if name == "analyze_image":
        return _analyze_image_file(args)
    try:
        import pyautogui
    except Exception:
        return "pyautogui non disponibile."
    region = args.get("region", "full")
    img = pyautogui.screenshot()
    w, h = img.size
    if region == "left":
        img = img.crop((0, 0, w // 2, h))
    elif region == "right":
        img = img.crop((w // 2, 0, w, h))
    elif region == "top":
        img = img.crop((0, 0, w, h // 2))
    elif region == "bottom":
        img = img.crop((0, h // 2, w, h))

    max_dim = 1568
    if max(img.size) > max_dim:
        ratio = max_dim / max(img.size)
        img = img.resize((int(img.size[0] * ratio), int(img.size[1] * ratio)))

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")

    return [
        {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": b64}},
        {"type": "text", "text": "Screenshot dello schermo allegato qui sopra."},
    ]


def _analyze_image_file(args):
    """Load an image file from disk and return it as an image content block."""
    import base64
    import io
    import os
    path = (args or {}).get("path", "").strip().strip('"').strip("'")
    if not path or not os.path.exists(path):
        return f"Immagine non trovata: {path}"
    ext = os.path.splitext(path)[1].lower()
    mime_map = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
                ".gif": "image/gif", ".webp": "image/webp", ".bmp": "image/png"}
    media_type = mime_map.get(ext, "image/png")
    try:
        from PIL import Image
        img = Image.open(path)
        # Normalize: convert to RGB if needed, downsize if too large
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGB")
        max_dim = 1568
        if max(img.size) > max_dim:
            ratio = max_dim / max(img.size)
            img = img.resize((int(img.size[0] * ratio), int(img.size[1] * ratio)))
        buf = io.BytesIO()
        # Always re-encode to PNG/JPEG depending on alpha
        if img.mode == "RGBA":
            img.save(buf, format="PNG", optimize=True)
            media_type = "image/png"
        else:
            img.save(buf, format="JPEG", quality=85, optimize=True)
            media_type = "image/jpeg"
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception as e:
        return f"Errore lettura immagine: {e}"

    fname = os.path.basename(path)
    return [
        {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64}},
        {"type": "text", "text": f"Immagine '{fname}' allegata sopra. Descrivila/analizzala."},
    ]
