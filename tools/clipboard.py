try:
    import pyperclip
    _AVAIL = True
except ImportError:
    _AVAIL = False

TOOLS = [
    {
        "name": "read_clipboard",
        "description": "Legge il contenuto attuale degli appunti (clipboard).",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "write_clipboard",
        "description": "Scrive un testo negli appunti.",
        "input_schema": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
    },
]


def run(name, args):
    if not _AVAIL:
        return "pyperclip non disponibile."
    if name == "read_clipboard":
        c = pyperclip.paste()
        return c if c else "Appunti vuoti."
    if name == "write_clipboard":
        pyperclip.copy(args.get("text", ""))
        return "Copiato negli appunti."
    return "?"
