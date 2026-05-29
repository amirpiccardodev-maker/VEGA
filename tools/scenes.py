"""Smart scenes: 'modalita' che attivano molte cose insieme con un comando.

Esempi: 'modalita lavoro', 'modalita relax', 'modalita notte', 'modalita gaming'.
Ogni scena puo' eseguire: app, URL, settings, automazioni, comandi Vega.
"""
import json
from pathlib import Path

import memory

SCENES_FILE = Path(__file__).parent.parent / "scenes.json"


# Scene preconfigurate
DEFAULT_SCENES = {
    "lavoro": {
        "description": "Apre Outlook + Chrome + Slack, volume basso, modalita produttivita'",
        "actions": [
            {"type": "open_app", "target": "msedge"},
            {"type": "open_url", "target": "https://gmail.com"},
            {"type": "open_url", "target": "https://calendar.google.com"},
            {"type": "set_volume", "percent": 30},
            {"type": "set_personality", "style": "friendly"},
            {"type": "set_mode", "mode": "work"},
            {"type": "say", "text": "Modalita' lavoro attiva. Buon lavoro Amir."},
        ],
    },
    "relax": {
        "description": "Musica Radio Deejay, volume soft, voce calma",
        "actions": [
            {"type": "minimize_all"},
            {"type": "play_radio", "station": "Radio Deejay"},
            {"type": "set_volume", "percent": 40},
            {"type": "set_personality", "style": "casual"},
            {"type": "say", "text": "Modalita' relax. Goditi il momento."},
        ],
    },
    "notte": {
        "description": "Luminosita' bassa, silenzio, voce calma, no notifiche",
        "actions": [
            {"type": "set_brightness", "percent": 20},
            {"type": "set_volume", "percent": 15},
            {"type": "privacy_mode", "enabled": True},
            {"type": "say", "text": "Modalita' notte attiva. Buonanotte."},
        ],
    },
    "studio": {
        "description": "Solo browser e silenzio totale per concentrarsi",
        "actions": [
            {"type": "minimize_all"},
            {"type": "open_app", "target": "msedge"},
            {"type": "set_volume", "percent": 0},
            {"type": "set_personality", "style": "friendly"},
            {"type": "say", "text": "Modalita' studio attiva. Focus assoluto."},
        ],
    },
    "gaming": {
        "description": "Apre Steam, modalita game, full performance",
        "actions": [
            {"type": "open_app", "target": "steam"},
            {"type": "set_volume", "percent": 70},
            {"type": "minimize_all"},
            {"type": "say", "text": "Modalita' gaming pronta."},
        ],
    },
}


TOOLS = [
    {"name": "activate_scene",
     "description": "Attiva una scena/modalita' (lavoro, relax, notte, studio, gaming o personalizzata). Esegue molte azioni in sequenza.",
     "input_schema": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}},
    {"name": "list_scenes",
     "description": "Elenca tutte le scene/modalita' disponibili.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "save_scene",
     "description": "Crea/aggiorna una scena personalizzata con una lista di azioni.",
     "input_schema": {"type": "object", "properties": {
         "name": {"type": "string"},
         "description": {"type": "string"},
         "actions": {"type": "array", "items": {"type": "object"},
                     "description": "Lista azioni. Tipi: open_app, open_url, set_volume, set_brightness, minimize_all, play_radio, set_personality, set_mode, privacy_mode, say"},
     }, "required": ["name", "actions"]}},
    {"name": "delete_scene",
     "description": "Elimina una scena personalizzata.",
     "input_schema": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}},
]


def _load_scenes():
    if not SCENES_FILE.exists():
        return dict(DEFAULT_SCENES)
    try:
        with open(SCENES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        merged = dict(DEFAULT_SCENES)
        merged.update(data)
        return merged
    except Exception:
        return dict(DEFAULT_SCENES)


def _save_scenes(scenes):
    tmp = str(SCENES_FILE) + ".tmp"
    custom = {k: v for k, v in scenes.items() if k not in DEFAULT_SCENES or v != DEFAULT_SCENES.get(k)}
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(custom, f, ensure_ascii=False, indent=2)
    Path(tmp).replace(SCENES_FILE)


def _execute_action(action: dict) -> str:
    """Run one action via the tool registry."""
    import tools as tool_registry
    t = action.get("type", "")
    if t == "open_app":
        return tool_registry.execute("open_application", {"target": action.get("target", "")})
    if t == "open_url":
        return tool_registry.execute("open_application", {"target": action.get("target", "")})
    if t == "set_volume":
        return tool_registry.execute("set_volume", {"percent": action.get("percent", 50)})
    if t == "set_brightness":
        return tool_registry.execute("set_brightness", {"percent": action.get("percent", 50)})
    if t == "minimize_all":
        return tool_registry.execute("minimize_all", {})
    if t == "play_radio":
        return tool_registry.execute("play_radio", {"station": action.get("station", "Radio Deejay")})
    if t == "set_personality":
        return tool_registry.execute("set_personality", {"style": action.get("style", "friendly")})
    if t == "set_mode":
        return tool_registry.execute("set_mode", {"mode": action.get("mode", "general")})
    if t == "privacy_mode":
        return tool_registry.execute("privacy_mode", {"enabled": action.get("enabled", True)})
    if t == "say":
        return action.get("text", "")
    if t == "run_command":
        # Falls back to engine to run any natural command
        return f"[exec: {action.get('text','')}]"
    return f"[unknown action: {t}]"


def run(name, args):
    scenes = _load_scenes()

    if name == "activate_scene":
        sn = args.get("name", "").strip().lower()
        # Fuzzy match
        match = next((k for k in scenes if k == sn or sn in k or k in sn), None)
        if not match:
            return f"Scena '{sn}' non trovata. Disponibili: {', '.join(scenes.keys())}"
        scene = scenes[match]
        results = []
        for action in scene.get("actions", []):
            r = _execute_action(action)
            results.append(f"  {action.get('type')}: {r[:60]}")
        return f"Scena '{match}' attivata:\n" + "\n".join(results)

    if name == "list_scenes":
        if not scenes:
            return "Nessuna scena disponibile."
        return "\n".join(f"- {k}: {v.get('description', '')}" for k, v in scenes.items())

    if name == "save_scene":
        nm = args.get("name", "").strip().lower()
        if not nm:
            return "Nome scena richiesto."
        actions = args.get("actions", [])
        if not actions:
            return "Almeno una azione richiesta."
        scenes[nm] = {
            "description": args.get("description", ""),
            "actions": actions,
        }
        _save_scenes(scenes)
        return f"Scena '{nm}' salvata con {len(actions)} azioni."

    if name == "delete_scene":
        nm = args.get("name", "").strip().lower()
        if nm in DEFAULT_SCENES:
            return "Le scene predefinite non possono essere eliminate (puoi crearne una con lo stesso nome che le sovrascrive)."
        if nm in scenes:
            del scenes[nm]
            _save_scenes(scenes)
            return f"Scena '{nm}' eliminata."
        return f"'{nm}' non trovata."

    return "?"
