"""Local music library: scan and play mp3/wav/flac/ogg."""
import os
import random
from pathlib import Path
from playsound3 import playsound

TOOLS = [
    {
        "name": "list_music",
        "description": "Elenca i brani musicali nella libreria locale (cartella Musica e Downloads).",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Filtra per nome (opzionale)"},
                "max_results": {"type": "integer"},
            },
        },
    },
    {
        "name": "play_music_track",
        "description": "Riproduce un brano specifico dalla libreria. Indicagli il nome (anche parziale) oppure 'random'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Nome brano (anche parziale) o 'random' per casuale"},
            },
            "required": ["name"],
        },
    },
    {
        "name": "stop_music_track",
        "description": "Ferma la riproduzione musicale corrente.",
        "input_schema": {"type": "object", "properties": {}},
    },
]


_current_sound = None


def _music_dirs():
    home = Path.home()
    return [home / "Music", home / "Musica", home / "Downloads"]


def _scan(query: str = "", limit: int = 50):
    exts = (".mp3", ".wav", ".flac", ".ogg", ".m4a")
    matches = []
    q = query.lower()
    for d in _music_dirs():
        if not d.exists():
            continue
        for path in d.rglob("*"):
            if path.is_file() and path.suffix.lower() in exts:
                if not q or q in path.stem.lower():
                    matches.append(path)
                    if len(matches) >= limit:
                        return matches
    return matches


def run(name, args):
    global _current_sound

    if name == "list_music":
        q = args.get("query", "")
        n = int(args.get("max_results", 20))
        files = _scan(q, n)
        if not files:
            return "Nessun brano trovato nella libreria."
        return "\n".join(f"- {f.stem}" for f in files[:n])

    if name == "play_music_track":
        try:
            if _current_sound and _current_sound.is_alive():
                _current_sound.stop()
        except Exception:
            pass
        name_q = args.get("name", "").strip()
        if name_q.lower() in ("random", "casuale", "qualcosa"):
            files = _scan("", 100)
            if not files:
                return "Libreria vuota."
            chosen = random.choice(files)
        else:
            files = _scan(name_q, 5)
            if not files:
                return f"Nessun brano corrisponde a '{name_q}'."
            chosen = files[0]
        try:
            _current_sound = playsound(str(chosen), block=False)
            return f"In riproduzione: {chosen.stem}"
        except Exception as e:
            return f"Errore: {e}"

    if name == "stop_music_track":
        try:
            if _current_sound:
                _current_sound.stop()
                _current_sound = None
                return "Musica fermata."
        except Exception:
            pass
        return "Nessuna musica in riproduzione."

    return "?"
