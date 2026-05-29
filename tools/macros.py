"""Macro recorder + custom aliases.

Macro: registra una sequenza di comandi e li replica con 'esegui macro X'.
Alias: 'quando dico X, fai Y' - shortcut completamente personali.
"""
import json
from pathlib import Path

MACROS_FILE = Path(__file__).parent.parent / "macros.json"


TOOLS = [
    {"name": "record_macro_start",
     "description": "Inizia la registrazione di una macro. I prossimi comandi tu dirai verranno salvati.",
     "input_schema": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}},
    {"name": "record_macro_stop",
     "description": "Ferma la registrazione e salva la macro.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "save_macro",
     "description": "Salva una macro con nome e lista di comandi pre-definita.",
     "input_schema": {"type": "object", "properties": {
         "name": {"type": "string"},
         "commands": {"type": "array", "items": {"type": "string"}},
     }, "required": ["name", "commands"]}},
    {"name": "run_macro",
     "description": "Esegue una macro salvata: lancia tutti i comandi in sequenza.",
     "input_schema": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}},
    {"name": "list_macros",
     "description": "Elenca tutte le macro salvate.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "delete_macro",
     "description": "Elimina una macro.",
     "input_schema": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}},
    {"name": "set_alias",
     "description": "Crea un alias: quando dici 'trigger_phrase', Vega esegue 'expanded_command'. Es: trigger='apri ufficio', expanded='attiva modalita lavoro e dimmi le mail'.",
     "input_schema": {"type": "object", "properties": {
         "trigger": {"type": "string"},
         "expanded": {"type": "string"},
     }, "required": ["trigger", "expanded"]}},
    {"name": "list_aliases",
     "description": "Elenca alias personalizzati.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "delete_alias",
     "description": "Elimina un alias per trigger.",
     "input_schema": {"type": "object", "properties": {"trigger": {"type": "string"}}, "required": ["trigger"]}},
]


def _load():
    if not MACROS_FILE.exists():
        return {"macros": {}, "aliases": {}, "recording": None, "buffer": []}
    try:
        with open(MACROS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        data.setdefault("macros", {})
        data.setdefault("aliases", {})
        data.setdefault("recording", None)
        data.setdefault("buffer", [])
        return data
    except Exception:
        return {"macros": {}, "aliases": {}, "recording": None, "buffer": []}


def _save(data):
    tmp = str(MACROS_FILE) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    Path(tmp).replace(MACROS_FILE)


# Public hook used by engine to capture commands during recording
def capture_command_if_recording(command: str):
    data = _load()
    if data["recording"]:
        data["buffer"].append(command)
        _save(data)


def get_alias_expansion(text: str):
    """Returns expanded command if text matches an alias trigger, else None."""
    data = _load()
    low = text.lower().strip()
    for trigger, expanded in data["aliases"].items():
        if trigger.lower() == low:
            return expanded
    return None


def run(name, args):
    data = _load()

    if name == "record_macro_start":
        nm = args.get("name", "").strip()
        if not nm:
            return "Nome macro richiesto."
        data["recording"] = nm
        data["buffer"] = []
        _save(data)
        return f"Registrazione macro '{nm}' AVVIATA. Dimmi i comandi che vuoi salvare, poi di' 'ferma registrazione macro'."

    if name == "record_macro_stop":
        if not data["recording"]:
            return "Non sto registrando."
        nm = data["recording"]
        commands = data["buffer"]
        if not commands:
            data["recording"] = None
            data["buffer"] = []
            _save(data)
            return "Macro vuota, registrazione annullata."
        data["macros"][nm] = commands
        data["recording"] = None
        data["buffer"] = []
        _save(data)
        return f"Macro '{nm}' salvata con {len(commands)} comandi: {commands}"

    if name == "save_macro":
        nm = args.get("name", "").strip()
        cmds = args.get("commands", [])
        if not nm or not cmds:
            return "Nome e lista comandi richiesti."
        data["macros"][nm] = cmds
        _save(data)
        return f"Macro '{nm}' salvata."

    if name == "run_macro":
        nm = args.get("name", "").strip().lower()
        match = next((k for k in data["macros"] if k.lower() == nm), None)
        if not match:
            return f"Macro '{nm}' non trovata."
        commands = data["macros"][match]
        return f"Eseguo macro '{match}': {len(commands)} comandi:\n" + "\n".join(f"- {c}" for c in commands) + "\n[NOTA: i comandi verranno eseguiti uno dopo l'altro dall'engine]"

    if name == "list_macros":
        if not data["macros"]:
            return "Nessuna macro salvata."
        out = []
        for nm, cmds in data["macros"].items():
            out.append(f"- {nm}: {len(cmds)} comandi")
        return "\n".join(out)

    if name == "delete_macro":
        nm = args.get("name", "").strip()
        if nm in data["macros"]:
            del data["macros"][nm]
            _save(data)
            return f"Macro '{nm}' eliminata."
        return f"'{nm}' non trovata."

    if name == "set_alias":
        trig = args.get("trigger", "").strip()
        exp = args.get("expanded", "").strip()
        if not trig or not exp:
            return "Trigger e expanded richiesti."
        data["aliases"][trig] = exp
        _save(data)
        return f"Alias creato: '{trig}' -> '{exp}'"

    if name == "list_aliases":
        if not data["aliases"]:
            return "Nessun alias."
        return "\n".join(f"- '{t}' -> '{e}'" for t, e in data["aliases"].items())

    if name == "delete_alias":
        trig = args.get("trigger", "").strip()
        if trig in data["aliases"]:
            del data["aliases"][trig]
            _save(data)
            return f"Alias '{trig}' eliminato."
        return f"'{trig}' non trovato."

    return "?"
