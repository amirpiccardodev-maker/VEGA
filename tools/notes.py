import memory

TOOLS = [
    {"name": "save_note", "description": "Salva una nota.",
     "input_schema": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}},
    {"name": "list_notes", "description": "Elenca le note salvate.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "add_todo", "description": "Aggiunge un todo.",
     "input_schema": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}},
    {"name": "list_todos", "description": "Elenca todo aperti.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "complete_todo", "description": "Segna come completato (indice 1-based).",
     "input_schema": {"type": "object", "properties": {"index": {"type": "integer"}}, "required": ["index"]}},
    {"name": "remember_fact", "description": "Memorizza un fatto sull'utente a lungo termine.",
     "input_schema": {"type": "object", "properties": {"fact": {"type": "string"}}, "required": ["fact"]}},
    {"name": "list_facts", "description": "Elenca i fatti memorizzati sull'utente.",
     "input_schema": {"type": "object", "properties": {}}},
]


def run(name, args):
    if name == "save_note":
        memory.add_note(args.get("text", ""))
        return "Nota salvata."
    if name == "list_notes":
        items = memory.get_notes()
        if not items:
            return "Nessuna nota."
        return "\n".join(f"- {n['text']}" for n in items[-20:])
    if name == "add_todo":
        memory.add_todo(args.get("text", ""))
        return "Aggiunto."
    if name == "list_todos":
        items = memory.get_todos()
        if not items:
            return "Nessuna attivita' aperta."
        return "\n".join(f"{i+1}. {t['text']}" for i, t in enumerate(items))
    if name == "complete_todo":
        idx = int(args.get("index", 1)) - 1
        memory.complete_todo(idx)
        return "Completata."
    if name == "remember_fact":
        memory.add_fact(args.get("fact", ""))
        return "Memorizzato."
    if name == "list_facts":
        items = memory.get_facts()
        if not items:
            return "Non ricordo nulla di particolare."
        return "\n".join(f"- {f['text']}" for f in items)
    return "?"
