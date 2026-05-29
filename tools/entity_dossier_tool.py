"""Tool: ottieni un dossier completo su una persona/azienda/argomento."""

TOOLS = [{
    "name": "ask_about_entity",
    "description": (
        "Recupera TUTTE le informazioni memorizzate su una persona, azienda, "
        "progetto o argomento (es. 'Marco', 'Libreria Islamica', 'progetto X'). "
        "Restituisce dossier raggruppato per tipo (fatti, note, todo, conversazioni) "
        "con most_recent e most_important. Usalo quando l'utente chiede 'cosa "
        "ricordi di X', 'parlami di Y', 'dossier su Z'."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "entity": {"type": "string", "description": "Nome dell'entità."},
            "max_results": {"type": "integer", "description": "Default 30."},
        },
        "required": ["entity"],
    },
}]


def run(name, args):
    import memory_graph as mg
    entity = (args or {}).get("entity", "").strip()
    if not entity:
        return "Specifica un nome di entità."
    max_results = int((args or {}).get("max_results", 30))
    dossier = mg.cluster_by_entity(entity, max_results=max_results)
    if dossier["total"] == 0:
        return (f"Nessuna informazione memorizzata su '{entity}'. "
                f"Se l'utente sta fornendo dettagli ORA, memorizzali con remember_fact.")
    # Format output
    out = [f"Dossier su '{entity}' — {dossier['total']} record trovati"]
    out.append(f"\nPer tipo:")
    for kind, items in dossier["by_kind"].items():
        out.append(f"  - {kind}: {len(items)} record")
    out.append(f"\nPiù recenti:")
    for h in dossier["most_recent"][:5]:
        out.append(f"  • [{h['kind']}] {h.get('content', '')[:180]}")
    out.append(f"\nPiù rilevanti (peso × freschezza):")
    for h in dossier["most_important"][:3]:
        out.append(f"  • [{h['kind']}] {h.get('content', '')[:180]}")
    return "\n".join(out)
