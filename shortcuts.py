"""Fast paths: answer/execute common queries locally without calling Claude.
Saves ~100% of tokens for these queries and is instant.

Some shortcuts call tool_registry.execute() directly so cards/visuals still
appear, but no Claude API call is made.
"""
import re
import random
import subprocess
import os
from datetime import datetime

# emit callback (set by engine before try_match)
_emit_fn = None


def set_emit(fn):
    global _emit_fn
    _emit_fn = fn


def _call_tool(tool_name: str, args: dict = None):
    """Call a tool directly via the registry (no Claude). Returns the result string."""
    import tools as tool_registry
    return tool_registry.execute(tool_name, args or {}, emit=_emit_fn)


GIORNI = ["lunedi", "martedi", "mercoledi", "giovedi", "venerdi", "sabato", "domenica"]
MESI = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
        "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"]


def _now_phrase() -> str:
    n = datetime.now()
    return f"Sono le {n.hour} e {n.minute:02d} di {GIORNI[n.weekday()]} {n.day} {MESI[n.month-1]}."


def _date_phrase() -> str:
    n = datetime.now()
    return f"Oggi e' {GIORNI[n.weekday()]} {n.day} {MESI[n.month-1]} {n.year}."


def _volume_set(pct: int) -> str:
    try:
        import tools.pc_control as pc
        return pc.run("set_volume", {"percent": pct})
    except Exception as e:
        return f"Volume non disponibile: {e}"


def _volume_get() -> str:
    try:
        import tools.pc_control as pc
        return pc.run("get_volume", {})
    except Exception:
        return "Volume non disponibile."


def _mute(b: bool) -> str:
    try:
        import tools.pc_control as pc
        return pc.run("mute_audio", {"mute": b})
    except Exception:
        return "Non riesco."


def _lock_pc() -> str:
    try:
        os.system("rundll32.exe user32.dll,LockWorkStation")
        return "PC bloccato."
    except Exception:
        return "Non riesco a bloccare."


def _shutdown_pc(action="shutdown", delay=60) -> str:
    try:
        if action == "cancel":
            subprocess.run(["shutdown", "/a"], capture_output=True)
            return "Spegnimento annullato."
        flag = "/s" if action == "shutdown" else "/r"
        subprocess.Popen(["shutdown", flag, "/t", str(delay)])
        verb = "Spegnimento" if action == "shutdown" else "Riavvio"
        return f"{verb} in {delay} secondi."
    except Exception:
        return "Operazione non disponibile."


def _open_app(name: str) -> str:
    try:
        import tools.apps as apps
        return apps.run("open_application", {"target": name})
    except Exception:
        return "App non trovata."


def _screenshot() -> str:
    try:
        import tools.screenshot as s
        return s.run("take_screenshot", {})
    except Exception:
        return "Screenshot non disponibile."


def _minimize_all() -> str:
    try:
        import tools.windows_tool as w
        return w.run("minimize_all", {})
    except Exception:
        return "Operazione non disponibile."


def _vol_match(m):
    s = m.group(0).lower()
    n = re.search(r"\d+", s)
    return _volume_set(int(n.group(0))) if n else _volume_get()


PATTERNS = [
    # Time
    (re.compile(r"^(che\s+ore\s+sono|che\s+ora\s+(e'|e|è)|dimmi\s+l'?ora|che\s+ora\s+fa|orario)[\.\?!]?$", re.I),
     lambda m: _now_phrase()),
    (re.compile(r"^(che\s+giorno\s+(e'|e|è)|che\s+(giorno|data)\s+(siamo|fa)|data)[\.\?!]?$", re.I),
     lambda m: _date_phrase()),

    # Politeness
    (re.compile(r"^(grazie|grazie\s+vega)[\.\!]?$", re.I),
     lambda m: random.choice(["Prego.", "Figurati.", "Quando vuoi."])),
    (re.compile(r"^(ciao|salve|ehi)\s*(vega)?[\.\!]?$", re.I),
     lambda m: random.choice(["Ciao Amir.", "Salve.", "Eccomi."])),
    (re.compile(r"^(va\s+bene|ok|d'accordo|perfetto)[\.\!]?$", re.I),
     lambda m: random.choice(["Tutto chiaro.", "Capito.", "Ricevuto."])),
    (re.compile(r"^(buongiorno|buon\s+giorno)\s*(vega)?[\.\!]?$", re.I),
     lambda m: f"Buongiorno Amir. {_now_phrase()}"),
    (re.compile(r"^buona\s*sera\s*(vega)?[\.\!]?$", re.I),
     lambda m: f"Buonasera Amir. {_now_phrase()}"),
    (re.compile(r"^buona?\s*notte\s*(vega)?[\.\!]?$", re.I),
     lambda m: "Buonanotte, Amir."),
    (re.compile(r"^(come\s+(stai|va)|tutto\s+bene)[\.\?!]?$", re.I),
     lambda m: random.choice([
         "Tutto operativo, grazie. Tu?",
         "Sistemi al massimo. Lei come sta?",
         "Sto bene, Amir.",
     ])),

    # Volume
    (re.compile(r"^(metti|imposta|porta)\s+(il\s+)?volume\s+(al?\s+)?(\d+)\s*%?[\.!]?$", re.I),
     lambda m: _volume_set(int(m.group(4)))),
    (re.compile(r"^volume\s+(al?\s+)?(\d+)\s*%?[\.!]?$", re.I),
     lambda m: _volume_set(int(m.group(2)))),
    (re.compile(r"^(che\s+)?volume\s+(c'?e'?|ho|attuale)[\.\?!]?$", re.I),
     lambda m: _volume_get()),
    (re.compile(r"^(alza|aumenta)\s+(il\s+)?volume[\.!]?$", re.I),
     lambda m: _volume_set(80)),
    (re.compile(r"^(abbassa|diminuisci)\s+(il\s+)?volume[\.!]?$", re.I),
     lambda m: _volume_set(30)),
    (re.compile(r"^(muta|silenzia|togli\s+l'?audio)[\.!]?$", re.I),
     lambda m: _mute(True)),
    (re.compile(r"^(smuta|riattiva\s+l'?audio)[\.!]?$", re.I),
     lambda m: _mute(False)),

    # PC control
    (re.compile(r"^(blocca|chiudi)\s+(il\s+)?pc[\.!]?$", re.I),
     lambda m: _lock_pc()),
    (re.compile(r"^spegni\s+(il\s+)?pc(\s+tra\s+(\d+)\s*(minut|secondi|sec|min|m)?)?[\.!]?$", re.I),
     lambda m: _shutdown_pc("shutdown", int(m.group(3) or 60) * (60 if (m.group(4) or "").startswith("min") else 1))),
    (re.compile(r"^riavvia\s+(il\s+)?pc[\.!]?$", re.I),
     lambda m: _shutdown_pc("restart", 30)),
    (re.compile(r"^annulla\s+(lo\s+)?spegnimento[\.!]?$", re.I),
     lambda m: _shutdown_pc("cancel")),

    # Apps
    (re.compile(r"^apri\s+(chrome|edge|firefox|spotify|notepad|calcolatrice|paint|cmd|powershell|word|excel|outlook|telegram|whatsapp|vscode|code)[\.!]?$", re.I),
     lambda m: _open_app(m.group(1))),

    # System
    (re.compile(r"^(fai|fammi)\s+(uno\s+)?screenshot[\.!]?$", re.I),
     lambda m: _screenshot()),
    (re.compile(r"^(mostra|vai\s+al?)\s+(il\s+)?desktop[\.!]?$", re.I),
     lambda m: _minimize_all()),
    (re.compile(r"^(minimizza|nascondi)\s+(tutto|le\s+finestre)[\.!]?$", re.I),
     lambda m: _minimize_all()),

    # === DIRECT TOOL SHORTCUTS (bypass Claude, save tokens, instant) ===
    # Weather
    (re.compile(r"^(che\s+tempo\s+fa|che\s+meteo\s+(c'?e'?|fa)|dimmi\s+il\s+meteo|com'?e'?\s+il\s+tempo|meteo)\s*(oggi)?[\.\?!]?$", re.I),
     lambda m: _call_tool("get_weather", {})),
    (re.compile(r"^(meteo|tempo)\s+(di\s+)?(domani|dopodomani)[\.\?!]?$", re.I),
     lambda m: _call_tool("get_weather", {"days": 2 if "dopodom" in m.group(0).lower() else 1})),

    # News
    (re.compile(r"^(dimmi|dammi|leggi(mi)?)\s+(le\s+)?notizie\s*(di\s+oggi|principali|importanti|del\s+giorno)?[\.!]?$", re.I),
     lambda m: _call_tool("get_news", {})),
    (re.compile(r"^(rassegna\s+stampa|le\s+notizie)[\.!]?$", re.I),
     lambda m: _call_tool("get_news", {})),

    # Sports news
    (re.compile(r"^(notizie\s+)?sport(ive)?(\s+di\s+oggi)?[\.!]?$", re.I),
     lambda m: _call_tool("sports_news", {})),
    (re.compile(r"^come\s+(va|sta)\s+lo\s+sport[\.\?!]?$", re.I),
     lambda m: _call_tool("sports_news", {})),

    # Email
    (re.compile(r"^(leggi(mi)?\s+)?(le\s+)?email(\s+(piu'?\s+)?recenti)?[\.!]?$", re.I),
     lambda m: _call_tool("list_emails", {"limit": 10})),
    (re.compile(r"^(leggi(mi)?\s+)?(le\s+)?mail(\s+(piu'?\s+)?recenti)?[\.!]?$", re.I),
     lambda m: _call_tool("list_emails", {"limit": 10})),
    (re.compile(r"^(controlla|hai)\s+(la\s+)?(mia\s+)?posta[\.\?!]?$", re.I),
     lambda m: _call_tool("list_emails", {"limit": 10})),
    (re.compile(r"^(riassumi\s+(le\s+)?(mie\s+)?(mail|email)|riassunto\s+(mail|email|posta))[\.!]?$", re.I),
     lambda m: _call_tool("summarize_inbox", {"limit": 15})),

    # System info
    (re.compile(r"^(come\s+va\s+(il\s+)?(sistema|pc)|stato\s+(sistema|pc)|info\s+sistema)[\.\?!]?$", re.I),
     lambda m: _call_tool("system_info", {})),
    (re.compile(r"^(quanto\s+(cpu|ram|memoria)\s+(uso|sto\s+usando)|cpu\s+attuale)[\.\?!]?$", re.I),
     lambda m: _call_tool("system_info", {})),

    # Settings
    (re.compile(r"^(mostra(mi)?\s+)?(le\s+)?(tue\s+)?impostazioni[\.!]?$", re.I),
     lambda m: _call_tool("show_settings", {})),
    (re.compile(r"^cosa\s+sai\s+di\s+me[\.\?!]?$", re.I),
     lambda m: _call_tool("list_facts", {})),

    # TODO / notes
    (re.compile(r"^(lista|elenca|mostra(mi)?)\s+(le\s+)?(mie\s+)?(cose\s+da\s+fare|todo|attivita')[\.!]?$", re.I),
     lambda m: _call_tool("list_todos", {})),
    (re.compile(r"^(che\s+cose\s+(devo|ho\s+da)\s+fare|cosa\s+devo\s+fare)[\.\?!]?$", re.I),
     lambda m: _call_tool("list_todos", {})),
    (re.compile(r"^(lista|elenca|mostra(mi)?)\s+(le\s+)?(mie\s+)?note[\.!]?$", re.I),
     lambda m: _call_tool("list_notes", {})),
]


def try_match(text: str):
    if not text:
        return None
    cleaned = text.strip().lower()
    for pat, handler in PATTERNS:
        m = pat.match(cleaned)
        if m:
            try:
                return handler(m)
            except Exception:
                return None
    return None
