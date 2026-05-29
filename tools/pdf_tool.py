try:
    from pypdf import PdfReader
    _AVAIL = True
except ImportError:
    _AVAIL = False

TOOLS = [{
    "name": "read_pdf",
    "description": "Estrae il testo da un file PDF (max ~10k caratteri restituiti).",
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "pages": {"type": "string", "description": "Pagine (es. '1-5'). Vuoto = tutto"},
        },
        "required": ["path"],
    },
}]


def run(name, args):
    if not _AVAIL:
        return "pypdf non disponibile."
    path = args.get("path", "")
    pages = args.get("pages", "")
    try:
        reader = PdfReader(path)
    except Exception as e:
        return f"Impossibile aprire PDF: {e}"

    n = len(reader.pages)
    if pages:
        try:
            a, b = pages.split("-")
            start, end = int(a) - 1, int(b)
        except Exception:
            start, end = 0, n
    else:
        start, end = 0, n

    parts = []
    total = 0
    for i in range(start, min(end, n)):
        try:
            text = reader.pages[i].extract_text() or ""
        except Exception:
            text = ""
        parts.append(f"--- Pagina {i+1} ---\n{text}")
        total += len(text)
        if total > 10000:
            parts.append("[...troncato]")
            break
    return "\n\n".join(parts)
