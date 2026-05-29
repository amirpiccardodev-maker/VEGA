"""Workspace profiles: open/close sets of apps/URLs with one command."""
import os
import json
import subprocess
import shutil
import webbrowser
from pathlib import Path

WORKSPACES_FILE = Path(__file__).parent.parent / "workspaces.json"

# Default profiles - user can edit workspaces.json to add more
_DEFAULT_PROFILES = {
    "lavoro": {
        "description": "Apre VSCode, browser, posta",
        "apps": ["code", "msedge"],
        "urls": ["https://gmail.com", "https://calendar.google.com"],
    },
    "studio": {
        "description": "Apre browser e cancelleria digitale",
        "apps": ["notepad"],
        "urls": ["https://duckduckgo.com", "https://en.wikipedia.org"],
    },
    "musica": {
        "description": "Apre Spotify",
        "apps": ["spotify"],
        "urls": [],
    },
    "intrattenimento": {
        "description": "YouTube e Netflix",
        "apps": [],
        "urls": ["https://youtube.com", "https://netflix.com"],
    },
    "sviluppatore": {
        "description": "VSCode + GitHub + StackOverflow",
        "apps": ["code"],
        "urls": ["https://github.com", "https://stackoverflow.com"],
    },
}

TOOLS = [
    {
        "name": "list_workspaces",
        "description": "Elenca i profili workspace disponibili (insiemi di app/siti da aprire insieme).",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "activate_workspace",
        "description": "Attiva un profilo workspace: apre tutte le app e i siti del profilo in un colpo solo. Profili: lavoro, studio, musica, intrattenimento, sviluppatore (o quelli personalizzati).",
        "input_schema": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
    },
    {
        "name": "save_workspace",
        "description": "Crea un nuovo profilo workspace o ne aggiorna uno.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "description": {"type": "string"},
                "apps": {"type": "array", "items": {"type": "string"}, "description": "Nomi eseguibili (es. code, chrome)"},
                "urls": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["name"],
        },
    },
]


def _load():
    if WORKSPACES_FILE.exists():
        try:
            with open(WORKSPACES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return dict(_DEFAULT_PROFILES)


def _save(data):
    with open(WORKSPACES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def run(name, args):
    profiles = _load()

    if name == "list_workspaces":
        if not profiles:
            return "Nessun profilo."
        return "\n".join(f"- {n}: {p.get('description','')}" for n, p in profiles.items())

    if name == "activate_workspace":
        target = args.get("name", "").strip().lower()
        # fuzzy match
        match = None
        for k in profiles:
            if k.lower() == target or target in k.lower():
                match = k
                break
        if not match:
            return f"Profilo '{target}' non trovato. Disponibili: {', '.join(profiles.keys())}"
        p = profiles[match]
        opened = []
        for app in p.get("apps", []):
            try:
                if shutil.which(app):
                    subprocess.Popen([app])
                    opened.append(app)
                else:
                    os.startfile(app)
                    opened.append(app)
            except Exception:
                pass
        for url in p.get("urls", []):
            try:
                webbrowser.open(url)
                opened.append(url)
            except Exception:
                pass
        return f"Profilo '{match}' attivato: {len(opened)} elementi aperti."

    if name == "save_workspace":
        n = args.get("name", "").strip()
        if not n:
            return "Nome profilo richiesto."
        profiles[n] = {
            "description": args.get("description", ""),
            "apps": args.get("apps", []),
            "urls": args.get("urls", []),
        }
        _save(profiles)
        return f"Profilo '{n}' salvato."

    return "?"
