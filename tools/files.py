import os
import fnmatch
from pathlib import Path

TOOLS = [{
    "name": "find_files",
    "description": "Cerca file per nome o pattern nelle cartelle utente comuni (Desktop, Documenti, Download). Restituisce massimo 20 risultati.",
    "input_schema": {
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "Nome o pattern (es. 'budget*', '*.pdf')"},
            "root": {"type": "string", "description": "Cartella opzionale (default: cartelle utente)"},
        },
        "required": ["pattern"],
    },
}]


def _roots():
    home = Path.home()
    return [home / "Desktop", home / "Documents", home / "Documenti", home / "Downloads", home / "Download"]


def run(name, args):
    pattern = args.get("pattern", "").strip()
    if "*" not in pattern and "?" not in pattern:
        pattern = f"*{pattern}*"
    roots = [Path(args["root"])] if args.get("root") else _roots()
    matches = []
    for root in roots:
        if not root.exists():
            continue
        for dirpath, _, filenames in os.walk(root):
            for fn in filenames:
                if fnmatch.fnmatch(fn.lower(), pattern.lower()):
                    matches.append(os.path.join(dirpath, fn))
                    if len(matches) >= 20:
                        break
            if len(matches) >= 20:
                break
        if len(matches) >= 20:
            break
    if not matches:
        return "Nessun file trovato."
    return "\n".join(matches)
