"""Tools for Vega to modify its own configuration via conversation."""
import memory

TOOLS = [
    {"name": "set_home_location", "description": "Salva citta' di residenza per meteo.",
     "input_schema": {"type": "object", "properties": {"location": {"type": "string"}}, "required": ["location"]}},
    {"name": "set_voice", "description": "Cambia voce. Opzioni: it-IT-DiegoNeural, it-IT-ElsaNeural, it-IT-IsabellaNeural, it-IT-GiuseppeNeural.",
     "input_schema": {"type": "object", "properties": {"voice_id": {"type": "string"}}, "required": ["voice_id"]}},
    {"name": "set_personality", "description": "Cambia personalita': friendly, stark (Iron Man), casual.",
     "input_schema": {"type": "object", "properties": {"style": {"type": "string", "enum": ["friendly", "stark", "casual"]}}, "required": ["style"]}},
    {"name": "set_mode", "description": "Modalita': general, developer, work.",
     "input_schema": {"type": "object", "properties": {"mode": {"type": "string", "enum": ["general", "developer", "work"]}}, "required": ["mode"]}},
    {"name": "toggle_startup_music", "description": "Musica all'avvio on/off.",
     "input_schema": {"type": "object", "properties": {"enabled": {"type": "boolean"}}, "required": ["enabled"]}},
    {"name": "add_instruction", "description": "Aggiunge regola personalizzata permanente (es. 'rispondi piu' breve').",
     "input_schema": {"type": "object", "properties": {"instruction": {"type": "string"}}, "required": ["instruction"]}},
    {"name": "list_instructions", "description": "Elenca regole personalizzate.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "remove_instruction", "description": "Rimuove regola all'indice 1-based.",
     "input_schema": {"type": "object", "properties": {"index": {"type": "integer"}}, "required": ["index"]}},
    {"name": "show_settings", "description": "Mostra impostazioni attuali.",
     "input_schema": {"type": "object", "properties": {}}},
]


def run(name, args):
    if name == "set_home_location":
        loc = args.get("location", "").strip()
        if not loc:
            return "Specifica una citta'."
        memory.set_preference("home_location", loc)
        return f"Memorizzato: la tua citta' e' {loc}. Da ora il meteo si riferisce a quel luogo."

    if name == "set_voice":
        v = args.get("voice_id", "").strip()
        if not v.startswith("it-IT-"):
            return "Voce non valida. Usa una voce italiana (es. it-IT-DiegoNeural)."
        memory.set_preference("voice", v)
        return f"Voce cambiata in {v}. Sentirai la differenza alla prossima risposta."

    if name == "set_personality":
        style = args.get("style", "friendly")
        memory.set_preference("personality", style)
        return f"Personalita' impostata su '{style}'."

    if name == "set_mode":
        m = args.get("mode", "general")
        memory.set_preference("mode", m)
        return f"Modalita' '{m}' attivata."

    if name == "toggle_startup_music":
        enabled = bool(args.get("enabled", True))
        memory.set_preference("startup_music", enabled)
        return "Musica avvio attivata." if enabled else "Musica avvio disattivata."

    if name == "add_instruction":
        text = args.get("instruction", "").strip()
        if not text:
            return "Istruzione vuota."
        memory.add_instruction(text)
        return f"Da ora seguiro' sempre questa istruzione: '{text}'"

    if name == "list_instructions":
        items = memory.get_instructions()
        if not items:
            return "Nessuna istruzione personalizzata."
        return "\n".join(f"{i+1}. {it['text']}" for i, it in enumerate(items))

    if name == "remove_instruction":
        idx = int(args.get("index", 1)) - 1
        memory.remove_instruction(idx)
        return "Istruzione rimossa."

    if name == "show_settings":
        p = memory.get_preferences()
        n_instr = len(memory.get_instructions())
        n_facts = len(memory.get_facts())
        return (f"Voce: {p.get('voice')}\n"
                f"Personalita': {p.get('personality')}\n"
                f"Modalita': {p.get('mode')}\n"
                f"Citta' (meteo): {p.get('home_location') or 'non impostata'}\n"
                f"Musica avvio: {'si' if p.get('startup_music') else 'no'}\n"
                f"Istruzioni personalizzate: {n_instr}\n"
                f"Fatti memorizzati su di te: {n_facts}")

    return f"Tool sconosciuto: {name}"
