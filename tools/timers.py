"""Multi-timer system: create, list, stop, rename, query by name.

Timers are stored in memory.json so they survive Vega restarts.
A background thread in engine watches them and emits notifications on expiry.
No persistent UI - everything voice/chat-controlled.
"""
import re
import threading
import time as _time
from datetime import datetime, timedelta

import memory

TOOLS = [
    {"name": "timer_create",
     "description": "Crea un nuovo timer con nome. Es: 'imposta timer pasta 8 minuti', 'timer riunione 25 minuti'.",
     "input_schema": {"type": "object", "properties": {
         "name": {"type": "string", "description": "Nome del timer (es. pasta, riunione)"},
         "seconds": {"type": "integer"},
     }, "required": ["name", "seconds"]}},
    {"name": "timer_list",
     "description": "Elenca tutti i timer attivi con tempo rimanente.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "timer_stop",
     "description": "Ferma e rimuove un timer per nome.",
     "input_schema": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}},
    {"name": "timer_rename",
     "description": "Rinomina un timer.",
     "input_schema": {"type": "object", "properties": {
         "old_name": {"type": "string"},
         "new_name": {"type": "string"},
     }, "required": ["old_name", "new_name"]}},
    {"name": "timer_query",
     "description": "Quanto manca a un timer specifico.",
     "input_schema": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}},
    {"name": "timer_stop_all",
     "description": "Ferma tutti i timer.",
     "input_schema": {"type": "object", "properties": {}}},
]


def _get_timers() -> dict:
    return memory.get_all().get("timers", {})


def _save_timers(timers: dict):
    def m(d):
        d["timers"] = timers
    memory.update(m)


def _fmt_remaining(secs: int) -> str:
    if secs < 60:
        return f"{secs} secondi"
    m = secs // 60
    s = secs % 60
    if s:
        return f"{m} minuti e {s} secondi"
    return f"{m} minuti"


def run(name, args):
    timers = _get_timers()

    if name == "timer_create":
        tname = args.get("name", "").strip().lower()
        secs = int(args.get("seconds", 0))
        if not tname or secs <= 0:
            return "Specifica nome e secondi validi."
        # Find unique name if duplicate
        original = tname
        i = 2
        while tname in timers:
            tname = f"{original} {i}"
            i += 1
        end = (datetime.now() + timedelta(seconds=secs)).isoformat()
        timers[tname] = {"end": end, "fired": False, "duration": secs,
                         "created": datetime.now().isoformat()}
        _save_timers(timers)
        return f"Timer '{tname}' impostato per {_fmt_remaining(secs)}."

    if name == "timer_list":
        if not timers:
            return "Nessun timer attivo."
        out = []
        now = datetime.now()
        for tn, t in timers.items():
            try:
                end = datetime.fromisoformat(t["end"])
                remaining = int((end - now).total_seconds())
                if remaining > 0:
                    out.append(f"- {tn}: {_fmt_remaining(remaining)} rimanenti")
                else:
                    out.append(f"- {tn}: SCADUTO")
            except Exception:
                pass
        return "\n".join(out) if out else "Nessun timer attivo."

    if name == "timer_stop":
        tname = args.get("name", "").strip().lower()
        # Fuzzy match
        match = next((k for k in timers if k == tname or tname in k), None)
        if not match:
            return f"Timer '{tname}' non trovato."
        del timers[match]
        _save_timers(timers)
        return f"Timer '{match}' fermato."

    if name == "timer_stop_all":
        n = len(timers)
        _save_timers({})
        return f"Fermati {n} timer."

    if name == "timer_rename":
        old = args.get("old_name", "").strip().lower()
        new = args.get("new_name", "").strip().lower()
        match = next((k for k in timers if k == old or old in k), None)
        if not match:
            return f"Timer '{old}' non trovato."
        if not new:
            return "Nome nuovo invalido."
        if new in timers:
            return f"Esiste gia' un timer chiamato '{new}'."
        timers[new] = timers.pop(match)
        _save_timers(timers)
        return f"Timer '{match}' rinominato in '{new}'."

    if name == "timer_query":
        tname = args.get("name", "").strip().lower()
        match = next((k for k in timers if k == tname or tname in k), None)
        if not match:
            return f"Timer '{tname}' non trovato."
        try:
            end = datetime.fromisoformat(timers[match]["end"])
            remaining = int((end - datetime.now()).total_seconds())
            if remaining > 0:
                return f"Timer '{match}': {_fmt_remaining(remaining)} rimanenti."
            return f"Timer '{match}' gia' scaduto."
        except Exception:
            return f"Errore lettura timer '{match}'."

    return "?"


# ===== Engine integration =====
# Background scanner that fires notifications when timers expire.

def check_expired_timers(notify_callback):
    """Called periodically by the engine. notify_callback(msg) when one expires."""
    timers = _get_timers()
    now = datetime.now()
    changed = False
    for tn, t in list(timers.items()):
        if t.get("fired"):
            continue
        try:
            end = datetime.fromisoformat(t["end"])
            if now >= end:
                notify_callback(f"Timer '{tn}' scaduto.")
                # Remove the timer entirely (no clutter)
                del timers[tn]
                changed = True
        except Exception:
            pass
    if changed:
        _save_timers(timers)
