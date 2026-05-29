"""Volume, brightness, shutdown, lock - all heavy imports are lazy."""
import os
import subprocess


TOOLS = [
    {
        "name": "set_volume",
        "description": "Imposta volume sistema in percentuale (0-100).",
        "input_schema": {
            "type": "object",
            "properties": {"percent": {"type": "integer"}},
            "required": ["percent"],
        },
    },
    {
        "name": "get_volume",
        "description": "Volume attuale del sistema.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "mute_audio",
        "description": "Muta o smuta audio sistema.",
        "input_schema": {
            "type": "object",
            "properties": {"mute": {"type": "boolean"}},
            "required": ["mute"],
        },
    },
    {
        "name": "set_brightness",
        "description": "Imposta luminosita' schermo in percentuale (0-100).",
        "input_schema": {
            "type": "object",
            "properties": {"percent": {"type": "integer"}},
            "required": ["percent"],
        },
    },
    {
        "name": "lock_pc",
        "description": "Blocca il PC.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "shutdown_pc",
        "description": "Spegne o riavvia il PC. Default delay 30 secondi (annullabile).",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["shutdown", "restart", "cancel"]},
                "delay_seconds": {"type": "integer", "description": "Default 30"},
            },
            "required": ["action"],
        },
    },
]


def _get_endpoint():
    # lazy import: pycaw is heavy
    from ctypes import cast, POINTER
    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    devices = AudioUtilities.GetSpeakers()
    interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    return cast(interface, POINTER(IAudioEndpointVolume))


def run(name, args):
    if name == "set_volume":
        try:
            pct = max(0, min(100, int(args.get("percent", 50))))
            ep = _get_endpoint()
            ep.SetMasterVolumeLevelScalar(pct / 100, None)
            return f"Volume impostato al {pct}%."
        except Exception as e:
            return f"Controllo audio non disponibile: {e}"

    if name == "get_volume":
        try:
            ep = _get_endpoint()
            v = ep.GetMasterVolumeLevelScalar()
            muted = ep.GetMute()
            return f"Volume: {int(v * 100)}% {'(mutato)' if muted else ''}".strip()
        except Exception as e:
            return f"Controllo audio non disponibile: {e}"

    if name == "mute_audio":
        try:
            ep = _get_endpoint()
            ep.SetMute(bool(args.get("mute", True)), None)
            return "Audio mutato." if args.get("mute") else "Audio attivato."
        except Exception as e:
            return f"Controllo audio non disponibile: {e}"

    if name == "set_brightness":
        try:
            import screen_brightness_control as sbc
        except Exception:
            return "Controllo luminosita' non disponibile."
        pct = max(0, min(100, int(args.get("percent", 50))))
        try:
            sbc.set_brightness(pct)
            return f"Luminosita' al {pct}%."
        except Exception as e:
            return f"Impossibile impostare luminosita': {e}"

    if name == "lock_pc":
        os.system("rundll32.exe user32.dll,LockWorkStation")
        return "PC bloccato."

    if name == "shutdown_pc":
        action = args.get("action")
        delay = int(args.get("delay_seconds", 30))
        if action == "cancel":
            subprocess.run(["shutdown", "/a"], capture_output=True)
            return "Spegnimento annullato."
        if action == "shutdown":
            subprocess.Popen(["shutdown", "/s", "/t", str(delay)])
            return f"Spegnimento tra {delay} secondi."
        if action == "restart":
            subprocess.Popen(["shutdown", "/r", "/t", str(delay)])
            return f"Riavvio tra {delay} secondi."
        return "Azione non valida."

    return f"Tool sconosciuto: {name}"
