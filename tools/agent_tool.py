"""Tool per invocare il fabric multi-agent (Planner/Executor/Verifier)."""


TOOLS = [{
    "name": "agent_run",
    "description": (
        "Esegue un obiettivo complesso multi-step come agente autonomo con planning + reflection. "
        "Usalo per: 'organizzami un weekend a X', 'gestisci l'onboarding cliente', "
        "'prepara una presentazione su X', 'analizza queste 3 cose e fammi un riassunto'."
    ),
    "input_schema": {"type": "object", "properties": {
        "goal": {"type": "string"},
    }, "required": ["goal"]},
}]


def run(name, args):
    goal = args.get("goal", "").strip()
    if not goal:
        return "Specifica un obiettivo."
    try:
        import agent_fabric
        events = []
        def on_event(phase, payload):
            events.append((phase, str(payload)[:80]))
        result = agent_fabric.run(goal, on_event=on_event)
        out = [f"OBIETTIVO: {goal}", ""]
        out.append(f"STEP ESEGUITI: {result.get('steps_executed', 0)}")
        out.append(f"DURATA: {result.get('duration_sec', 0)}s")
        out.append("")
        out.append("RISULTATO:")
        out.append(result.get("summary", ""))
        return "\n".join(out)
    except Exception as e:
        return f"Errore agent fabric: {e}"
