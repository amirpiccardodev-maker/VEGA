"""Privacy and security controls accessible via voice/chat."""
import security
import memory

TOOLS = [
    {"name": "privacy_mode", "description": "Attiva o disattiva la modalita' privata (no logging conversazioni).",
     "input_schema": {"type": "object", "properties": {"enabled": {"type": "boolean"}}, "required": ["enabled"]}},
    {"name": "security_status", "description": "Mostra lo stato della sicurezza: privacy, PIN, cifratura memoria.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "set_pin", "description": "Imposta o cambia il PIN per azioni critiche (min 4 cifre). Es: 'imposta PIN 1234'.",
     "input_schema": {"type": "object", "properties": {"pin": {"type": "string"}}, "required": ["pin"]}},
    {"name": "remove_pin", "description": "Rimuove il PIN. Richiede conferma vocale.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "clear_conversation_log", "description": "Cancella la cronologia conversazioni salvata (irreversibile).",
     "input_schema": {"type": "object", "properties": {"confirm": {"type": "boolean"}}, "required": ["confirm"]}},
]


def run(name, args):
    if name == "privacy_mode":
        enabled = bool(args.get("enabled", True))
        security.set_privacy_mode(enabled)
        # Persist preference too
        memory.set_preference("privacy_mode", enabled)
        if enabled:
            return ("Modalita' privata ATTIVA. Da ora le conversazioni non vengono "
                    "loggate, i fatti non vengono salvati automaticamente, i log "
                    "mascherano segreti.")
        return "Modalita' privata disattivata. Logging conversazioni ripreso."

    if name == "security_status":
        st = security.get_security_status()
        env_status = st["env_check"]["status"]
        lines = [
            f"Privacy mode: {'ATTIVA' if st['privacy_mode'] else 'spenta'}",
            f"PIN protezione: {'impostato' if st['pin_set'] else 'NON impostato'}",
            f"Cifratura memoria: {'ATTIVA' if st['encryption_active'] else 'non attiva'}",
            f"File .env: {env_status}",
            f"Istruzioni personalizzate: {st['instructions_count']}",
        ]
        return "\n".join(lines)

    if name == "set_pin":
        pin = str(args.get("pin", "")).strip()
        if not pin.isdigit() or len(pin) < 4:
            return "Il PIN deve essere di almeno 4 cifre numeriche."
        ok = security.set_pin(pin)
        if ok:
            return f"PIN impostato. Verra' richiesto per azioni critiche (spegnimento PC, invio email, ecc.)."
        return "Impossibile impostare il PIN."

    if name == "remove_pin":
        memory.set_preference("pin_hash", "")
        security.revoke_pin_session()
        return "PIN rimosso. Azioni critiche non saranno piu' protette."

    if name == "clear_conversation_log":
        if not args.get("confirm"):
            return "Per confermare di' 'conferma cancellazione cronologia'."
        def m(d):
            d["conversation_log"] = []
        memory.update(m)
        return "Cronologia conversazioni cancellata."

    return "?"
