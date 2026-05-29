import os
import base64
import tempfile
from datetime import datetime

try:
    import pyautogui
    _AVAIL = True
except ImportError:
    _AVAIL = False

TOOLS = [{
    "name": "take_screenshot",
    "description": "Cattura uno screenshot dello schermo e lo salva. Usalo se l'utente chiede 'fai screenshot' o 'guarda lo schermo'.",
    "input_schema": {
        "type": "object",
        "properties": {
            "save_path": {"type": "string", "description": "Percorso opzionale per salvare"},
        },
    },
}]


def run(name, args):
    if not _AVAIL:
        return "pyautogui non disponibile. Installa con: pip install pyautogui"
    path = args.get("save_path", "")
    if not path:
        path = os.path.join(tempfile.gettempdir(), f"vega_shot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
    img = pyautogui.screenshot()
    img.save(path)
    return f"Screenshot salvato in: {path}"
