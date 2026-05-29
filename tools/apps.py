import os
import subprocess
import shutil
import webbrowser

TOOLS = [{
    "name": "open_application",
    "description": "Apre un'applicazione o un sito web sul PC. Esempi: 'spotify', 'vscode', 'chrome', 'notepad', oppure URL completo.",
    "input_schema": {
        "type": "object",
        "properties": {
            "target": {"type": "string", "description": "Nome app o URL"},
        },
        "required": ["target"],
    },
}]


_KNOWN = {
    "vscode": "code",
    "code": "code",
    "chrome": "chrome",
    "edge": "msedge",
    "firefox": "firefox",
    "spotify": "spotify",
    "notepad": "notepad",
    "calc": "calc",
    "calcolatrice": "calc",
    "calculator": "calc",
    "explorer": "explorer",
    "esplora": "explorer",
    "cmd": "cmd",
    "powershell": "powershell",
    "paint": "mspaint",
    "word": "winword",
    "excel": "excel",
    "outlook": "outlook",
    "telegram": "telegram",
    "whatsapp": "whatsapp",
}


def run(name, args):
    target = args.get("target", "").strip()
    if not target:
        return "Specifica cosa aprire."
    if target.startswith(("http://", "https://", "www.")):
        url = target if target.startswith("http") else "https://" + target
        webbrowser.open(url)
        return f"Aperto: {url}"

    low = target.lower()
    exe = _KNOWN.get(low, low)
    if shutil.which(exe):
        subprocess.Popen([exe], shell=False)
        return f"Avviato: {target}"
    try:
        os.startfile(exe)
        return f"Avviato: {target}"
    except Exception as e:
        return f"Non sono riuscito a aprire '{target}': {e}"
