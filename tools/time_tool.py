import threading
from datetime import datetime, timedelta

TOOLS = [
    {"name": "get_time", "description": "Data e ora attuale.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "set_timer", "description": "Timer con notifica vocale a tempo scaduto.",
     "input_schema": {"type": "object", "properties": {"seconds": {"type": "integer"}, "label": {"type": "string"}}, "required": ["seconds"]}},
    {"name": "set_reminder", "description": "Promemoria per data/ora. 'when' accetta ISO datetime o '+1h', '+30min', '+2d'.",
     "input_schema": {"type": "object", "properties": {"text": {"type": "string"}, "when": {"type": "string"}}, "required": ["text", "when"]}},
]

_timer_callbacks = []  # populated by engine


def register_timer_callback(fn):
    _timer_callbacks.append(fn)


def _parse_when(s: str) -> datetime:
    s = s.strip()
    if s.startswith("+"):
        num = ""
        unit = ""
        for c in s[1:]:
            if c.isdigit():
                num += c
            else:
                unit += c
        n = int(num or "0")
        unit = unit.lower().strip()
        now = datetime.now()
        if unit.startswith("s"): return now + timedelta(seconds=n)
        if unit.startswith("min") or unit == "m": return now + timedelta(minutes=n)
        if unit.startswith("h"): return now + timedelta(hours=n)
        if unit.startswith("d") or unit.startswith("g"): return now + timedelta(days=n)
        return now + timedelta(minutes=n)
    return datetime.fromisoformat(s)


def run(name, args):
    if name == "get_time":
        now = datetime.now()
        giorni = ["lunedi", "martedi", "mercoledi", "giovedi", "venerdi", "sabato", "domenica"]
        mesi = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
                "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"]
        return f"{giorni[now.weekday()].capitalize()} {now.day} {mesi[now.month-1]} {now.year}, ore {now.strftime('%H:%M')}"

    if name == "set_timer":
        secs = int(args.get("seconds", 60))
        label = args.get("label", "")
        def fire():
            for cb in _timer_callbacks:
                try:
                    cb(label or "Timer", secs)
                except Exception:
                    pass
        threading.Timer(secs, fire).start()
        mins = secs // 60
        if mins:
            return f"Timer impostato per {mins} minuti ({label or 'senza etichetta'})."
        return f"Timer impostato per {secs} secondi."

    if name == "set_reminder":
        from memory import add_reminder
        text = args.get("text", "")
        when_str = args.get("when", "")
        try:
            when = _parse_when(when_str)
        except Exception as e:
            return f"Formato data/ora non valido: {e}"
        add_reminder(text, when.isoformat())
        return f"Promemoria salvato: '{text}' per il {when.strftime('%d/%m/%Y %H:%M')}"

    return f"Tool sconosciuto: {name}"
