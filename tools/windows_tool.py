"""Window management."""
try:
    import pygetwindow as gw
    _AVAIL = True
except Exception:
    _AVAIL = False

TOOLS = [
    {
        "name": "list_windows",
        "description": "Elenca le finestre aperte sul desktop.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "focus_window",
        "description": "Mette in primo piano una finestra per titolo (sottostringa).",
        "input_schema": {
            "type": "object",
            "properties": {"title": {"type": "string"}},
            "required": ["title"],
        },
    },
    {
        "name": "close_window",
        "description": "Chiude una finestra (per titolo).",
        "input_schema": {
            "type": "object",
            "properties": {"title": {"type": "string"}},
            "required": ["title"],
        },
    },
    {
        "name": "minimize_all",
        "description": "Minimizza tutte le finestre (mostra desktop).",
        "input_schema": {"type": "object", "properties": {}},
    },
]


def _find(title):
    if not _AVAIL:
        return []
    return [w for w in gw.getAllWindows() if w.title and title.lower() in w.title.lower()]


def run(name, args):
    if not _AVAIL:
        return "pygetwindow non disponibile."
    if name == "list_windows":
        wins = [w.title for w in gw.getAllWindows() if w.title]
        if not wins:
            return "Nessuna finestra aperta."
        return "\n".join(f"- {t}" for t in wins[:30])
    if name == "focus_window":
        wins = _find(args.get("title", ""))
        if not wins:
            return "Finestra non trovata."
        try:
            wins[0].activate()
            return f"Attivata: {wins[0].title}"
        except Exception as e:
            return f"Impossibile attivare: {e}"
    if name == "close_window":
        wins = _find(args.get("title", ""))
        if not wins:
            return "Finestra non trovata."
        try:
            wins[0].close()
            return f"Chiusa: {wins[0].title}"
        except Exception as e:
            return f"Impossibile chiudere: {e}"
    if name == "minimize_all":
        import subprocess
        subprocess.run(["powershell", "-Command", "(New-Object -ComObject shell.application).MinimizeAll()"], capture_output=True)
        return "Desktop mostrato."
    return "?"
