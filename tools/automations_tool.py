"""Tool per creare, gestire ed eseguire automazioni/agenti tramite voce/chat."""
import re
from datetime import datetime

import automations


TOOLS = [
    {
        "name": "create_automation",
        "description": (
            "Crea o aggiorna un'automazione che Vega esegue da solo a orari/intervalli prefissati. "
            "Esempi di chiamata: "
            "name='briefing mattutino', schedule='daily 08:00', command='dimmi meteo, news e mail importanti'. "
            "name='controllo mail', schedule='interval 2h', command='riassumi le mie email recenti'. "
            "name='promemoria sport', schedule='weekday 18:30', command='ricordami di andare in palestra'. "
            "SCHEDULE FORMATS: "
            "'daily HH:MM' (ogni giorno), 'weekday HH:MM' (lun-ven), 'weekend HH:MM' (sab-dom), "
            "'mon HH:MM' (anche tue/wed/thu/fri/sat/sun o lun/mar/mer/gio/ven/sab/dom), "
            "'interval Xm' (ogni X minuti), 'interval Xh' (ogni X ore), "
            "'once 2026-05-22T18:00' (una sola volta). "
            "MODES: 'voice' = parla ad alta voce (default), 'card' = solo card visiva, 'silent' = solo toast."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Nome unico dell'automazione"},
                "schedule": {"type": "string"},
                "command": {"type": "string", "description": "Comando in linguaggio naturale che Vega eseguira'"},
                "mode": {"type": "string", "enum": ["voice", "card", "silent"]},
                "enabled": {"type": "boolean"},
            },
            "required": ["name", "schedule", "command"],
        },
    },
    {
        "name": "list_automations",
        "description": "Elenca tutte le automazioni esistenti con stato.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "delete_automation",
        "description": "Elimina una automazione per nome.",
        "input_schema": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
    },
    {
        "name": "toggle_automation",
        "description": "Attiva o disattiva una automazione (la mantiene salvata, ma in pausa).",
        "input_schema": {"type": "object", "properties": {
            "name": {"type": "string"}, "enabled": {"type": "boolean"},
        }, "required": ["name", "enabled"]},
    },
    {
        "name": "run_automation_now",
        "description": "Esegue immediatamente una automazione per nome (utile per test).",
        "input_schema": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
    },
]


def _validate_schedule(s: str) -> bool:
    s = s.strip().lower()
    if s.startswith("once "):
        try:
            datetime.fromisoformat(s[5:].strip())
            return True
        except Exception:
            return False
    if s.startswith("interval "):
        rest = s[9:].strip()
        return bool(re.match(r"^\d+[mh]?$", rest))
    parts = s.split(" ")
    if len(parts) != 2:
        return False
    kind, time_str = parts
    if not re.match(r"^\d{1,2}:\d{2}$", time_str):
        return False
    valid_kinds = {"daily", "weekday", "weekend",
                   "mon", "tue", "wed", "thu", "fri", "sat", "sun",
                   "lun", "mar", "mer", "gio", "ven", "sab", "dom"}
    return kind in valid_kinds


def run(name, args):
    if name == "create_automation":
        nm = args.get("name", "").strip()
        sched = args.get("schedule", "").strip()
        cmd = args.get("command", "").strip()
        mode = args.get("mode", "voice")
        enabled = bool(args.get("enabled", True))
        if not nm:
            return "Nome automazione richiesto."
        if not _validate_schedule(sched):
            return (f"Schedule non valido: '{sched}'. Esempi validi: "
                    "'daily 08:00', 'weekday 18:30', 'interval 30m', 'interval 2h'.")
        if not cmd:
            return "Comando richiesto."
        if mode not in ("voice", "card", "silent"):
            mode = "voice"
        automations.upsert({
            "name": nm,
            "schedule": sched,
            "command": cmd,
            "mode": mode,
            "enabled": enabled,
            "created": datetime.now().isoformat(),
        })
        return f"Automazione '{nm}' creata. Trigger: {sched}. Modalita': {mode}."

    if name == "list_automations":
        items = automations.list_all()
        if not items:
            return "Nessuna automazione configurata."
        out = []
        for it in items:
            status = "attiva" if it.get("enabled", True) else "in pausa"
            last = it.get("last_run", "mai")
            if last != "mai":
                try:
                    last = datetime.fromisoformat(last).strftime("%d/%m %H:%M")
                except Exception:
                    pass
            out.append(f"- {it['name']} | {it['schedule']} | {status} | ultima: {last}")
            out.append(f"  comando: {it['command'][:80]}")
        return "\n".join(out)

    if name == "delete_automation":
        nm = args.get("name", "").strip()
        ok = automations.delete(nm)
        return f"Automazione '{nm}' eliminata." if ok else f"'{nm}' non trovata."

    if name == "toggle_automation":
        nm = args.get("name", "").strip()
        enabled = bool(args.get("enabled", True))
        ok = automations.set_enabled(nm, enabled)
        if not ok:
            return f"'{nm}' non trovata."
        return f"'{nm}' {'attivata' if enabled else 'disattivata'}."

    if name == "run_automation_now":
        nm = args.get("name", "").strip()
        item = automations.find(nm)
        if not item:
            return f"'{nm}' non trovata."
        automations._execute(item)
        return f"Eseguo '{nm}' ora."

    return "?"
