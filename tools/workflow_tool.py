"""Tool per creare e gestire workflow autonomi (Sprint C)."""

TOOLS = [
    {"name": "create_workflow",
     "description": (
         "Crea un workflow autonomo da una descrizione naturale. Usalo quando l'utente "
         "vuole automazioni complesse multi-step (es. 'ogni volta che ricevo email "
         "urgenti, riassumile, estrai task, manda notifica'). Il workflow viene salvato "
         "e puo' essere eseguito a richiesta o secondo trigger."
     ),
     "input_schema": {"type": "object", "properties": {
         "goal": {"type": "string", "description": "Descrizione completa di cosa il workflow deve fare"},
     }, "required": ["goal"]}},
    {"name": "list_workflows",
     "description": "Elenca tutti i workflow esistenti.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "run_workflow",
     "description": "Esegue un workflow per nome o ID.",
     "input_schema": {"type": "object", "properties": {
         "id_or_name": {"type": "string"},
     }, "required": ["id_or_name"]}},
    {"name": "delete_workflow",
     "description": "Elimina un workflow.",
     "input_schema": {"type": "object", "properties": {
         "id_or_name": {"type": "string"},
     }, "required": ["id_or_name"]}},
]


def _find(id_or_name: str):
    import workflow_engine
    wf = workflow_engine.load_workflow(id_or_name)
    if wf:
        return wf
    # Try by name
    for w in workflow_engine.list_workflows():
        if w.get("name", "").lower() == id_or_name.lower():
            return workflow_engine.load_workflow(w["id"])
    return None


def run(name, args):
    import workflow_engine

    if name == "create_workflow":
        goal = args.get("goal", "").strip()
        if not goal:
            return "Specifica un obiettivo."
        result = workflow_engine.create_from_prompt(goal)
        if result.get("error"):
            return f"Errore: {result['error']}"
        return (f"Workflow '{result['name']}' creato (id: {result['id']}) "
                f"con {result['steps']} step. Puoi eseguirlo con 'esegui workflow {result['name']}'.")

    if name == "list_workflows":
        items = workflow_engine.list_workflows()
        if not items:
            return "Nessun workflow definito."
        out = []
        for w in items:
            trigger = w.get("trigger", {}).get("type", "manual")
            enabled = "attivo" if w.get("enabled", True) else "disattivato"
            out.append(f"- {w['name']} (id: {w['id']}, {w['step_count']} step, trigger: {trigger}, {enabled})")
        return "\n".join(out)

    if name == "run_workflow":
        target = args.get("id_or_name", "").strip()
        wf = _find(target)
        if not wf:
            return f"Workflow '{target}' non trovato."
        result = workflow_engine.execute(wf["id"])
        if result.get("ok"):
            return f"Workflow '{wf.get('name')}' eseguito con successo."
        return f"Errore esecuzione: {result.get('error')}"

    if name == "delete_workflow":
        target = args.get("id_or_name", "").strip()
        wf = _find(target)
        if not wf:
            return f"Workflow '{target}' non trovato."
        ok = workflow_engine.delete_workflow(wf["id"])
        return f"Workflow '{wf.get('name')}' eliminato." if ok else "Errore eliminazione."

    return "?"
