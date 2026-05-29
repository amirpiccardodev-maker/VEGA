"""Agent fabric: Planner / Executor / Verifier orchestration.

Per task complessi multi-step dove serve pianificare prima di eseguire.

Flusso:
    user_goal -> Planner (Sonnet, capability-aware) -> JSON plan
              -> Executor (Haiku per ogni step) -> step results
              -> Verifier (Haiku) -> done? next? retry?
              -> Final answer (Sonnet) -> user

Stato persistente via task_queue: ogni step e' un task con parent workflow_id.
Re-pianifica fino a MAX_REPLANS volte se verifier dice "non bene".
"""
import json
import time
import uuid

import fast_brain
import bus


MAX_PLAN_STEPS = 6
MAX_REPLANS = 2


PLANNER_SYSTEM = """Sei un AGENT PLANNER. Decomposi obiettivi complessi in step atomici eseguibili.

Output JSON:
{
  "plan": [
    {"id": "s1", "action": "descrizione concreta di cosa fare", "agent": "email|travel|code|desktop|generic"},
    ...
  ],
  "reasoning": "breve spiegazione del piano"
}

Regole:
- Max 6 step
- Ogni step deve essere atomic (1 azione chiara)
- Usa l'agent appropriato:
  - email: tutto su gmail
  - travel: itinerari, meteo, immagini posti
  - code: dati, analisi, calcoli
  - desktop: app, file, sistema PC
  - generic: tutto il resto (info, ricerche, scrittura)
- Pensa al risultato finale: cosa deve avere l'utente alla fine?
"""


VERIFIER_SYSTEM = """Sei un VERIFIER. Valuti se un piano agentico ha raggiunto l'obiettivo.

Output JSON:
{
  "done": true/false,
  "quality": 0.0-1.0,
  "issues": ["..."],
  "next_action": "se non done, cosa fare ora",
  "summary": "se done, riassunto in italiano per l'utente"
}
"""


def plan(goal: str, context: dict = None) -> dict:
    """Generate a plan for the goal. Uses Haiku for cost (Sonnet only on hard goals)."""
    ctx_str = ""
    if context:
        ctx_str = "\nContesto: " + json.dumps(context, ensure_ascii=False)[:500]
    prompt = f"{PLANNER_SYSTEM}\n\nObiettivo: {goal}{ctx_str}\n\nGenera il piano JSON:"
    result = fast_brain.fast_json(prompt)
    if not result or "plan" not in result:
        return {"plan": [], "reasoning": "Impossibile pianificare"}
    # Normalize
    for i, step in enumerate(result.get("plan", [])):
        if "id" not in step:
            step["id"] = f"s{i+1}"
        if "agent" not in step:
            step["agent"] = "generic"
    bus.publish(bus.Topics.AGENT_PLAN, {"goal": goal, "steps": len(result.get("plan", []))})
    return result


def execute_step(step: dict, shared_state: dict) -> dict:
    """Execute one step via the appropriate agent (which boils down to a Brain call)."""
    from agents import load_agent
    agent_name = step.get("agent", "generic")
    action = step.get("action", "")
    agent = load_agent(agent_name)
    bus.publish(bus.Topics.AGENT_EXECUTE, {"step": step.get("id"), "agent": agent_name})
    try:
        result = agent.run(action, shared_state)
        return {"id": step["id"], "ok": True, "output": result}
    except Exception as e:
        return {"id": step["id"], "ok": False, "error": str(e)}


def verify(goal: str, results: list) -> dict:
    """Reflect on what was achieved."""
    results_text = "\n".join(f"- Step {r['id']}: {'OK' if r.get('ok') else 'FAIL'} - {str(r.get('output', r.get('error', '')))[:300]}"
                              for r in results)
    prompt = (
        f"{VERIFIER_SYSTEM}\n\n"
        f"Obiettivo utente: {goal}\n\n"
        f"Risultati ottenuti:\n{results_text}\n\nJSON:"
    )
    result = fast_brain.fast_json(prompt)
    bus.publish(bus.Topics.AGENT_REFLECT, result)
    return result or {"done": False, "summary": "Verifica fallita"}


def run_long_horizon(goal: str, max_minutes: int = 60, on_event=None,
                       persistent: bool = True) -> dict:
    """Long-horizon variant: persiste ogni step nel task_queue come parent_id
    workflow, può essere ripreso dopo crash. Cap a max_minutes (default 60).
    Re-plan dopo ogni fase di verifica fino a deadline."""
    import time as _t
    started = _t.time()
    deadline = started + max_minutes * 60
    workflow_id = f"lh_{int(started)}"

    if persistent:
        try:
            import task_queue
            task_queue.enqueue("long_horizon_root", {"goal": goal, "wf_id": workflow_id},
                               dedup_key=workflow_id)
        except Exception:
            pass

    if on_event:
        on_event("long_horizon_started", {"goal": goal, "wf_id": workflow_id,
                                            "max_minutes": max_minutes})

    all_results = []
    shared_state = {}
    cycle = 0
    current_goal = goal
    while _t.time() < deadline and cycle < 20:
        cycle += 1
        if on_event:
            on_event("cycle_start", {"cycle": cycle, "remaining_sec":
                                      int(deadline - _t.time())})

        plan_obj = plan(current_goal, context={"previous": all_results[-3:]} if all_results else None)
        if not plan_obj.get("plan"):
            break
        if on_event:
            on_event("plan", plan_obj)

        for step in plan_obj["plan"]:
            if _t.time() >= deadline:
                break
            if on_event:
                on_event("executing", step)
            res = execute_step(step, shared_state)
            all_results.append(res)
            shared_state[step["id"]] = res.get("output")
            if persistent:
                try:
                    import task_queue
                    task_queue.enqueue("long_horizon_step",
                                       {"wf_id": workflow_id, "step": step,
                                        "result": res},
                                       parent_id=workflow_id)
                except Exception:
                    pass
            if on_event:
                on_event("step_done", res)

        v = verify(goal, all_results)
        if on_event:
            on_event("verified", v)
        if v.get("done") and v.get("quality", 0) >= 0.75:
            return {
                "ok": True,
                "wf_id": workflow_id,
                "summary": v.get("summary", "Completato."),
                "steps_executed": len(all_results),
                "cycles": cycle,
                "duration_sec": round(_t.time() - started, 1),
            }
        # Re-plan on next iteration with verifier feedback
        nxt = v.get("next_action", "")
        if not nxt:
            break
        current_goal = nxt

    return {
        "ok": False,
        "wf_id": workflow_id,
        "summary": f"Tempo o cicli esauriti dopo {cycle} cicli, {len(all_results)} step.\n" +
                   "Ultimi risultati:\n" +
                   "\n".join(f"- {str(r.get('output', r.get('error', '')))[:200]}" for r in all_results[-3:]),
        "steps_executed": len(all_results),
        "cycles": cycle,
        "duration_sec": round(_t.time() - started, 1),
    }


def run(goal: str, on_event=None) -> dict:
    """Full planner-executor-verifier loop. Returns final summary."""
    started = time.time()
    replan_count = 0
    all_results = []
    shared_state = {}

    current_plan = plan(goal)
    if not current_plan.get("plan"):
        return {"ok": False, "summary": "Non sono riuscito a pianificare l'obiettivo."}

    if on_event: on_event("plan", current_plan)

    while replan_count <= MAX_REPLANS:
        # Execute all steps in plan
        for step in current_plan["plan"]:
            if on_event: on_event("executing", step)
            res = execute_step(step, shared_state)
            all_results.append(res)
            shared_state[step["id"]] = res.get("output")
            if on_event: on_event("step_done", res)

        # Verify
        v = verify(goal, all_results)
        if on_event: on_event("verified", v)

        if v.get("done"):
            return {
                "ok": True,
                "summary": v.get("summary", "Completato."),
                "steps_executed": len(all_results),
                "duration_sec": round(time.time() - started, 1),
            }

        # Try to re-plan
        replan_count += 1
        if replan_count > MAX_REPLANS:
            break
        next_action = v.get("next_action", "")
        if not next_action:
            break
        current_plan = plan(next_action, context={"previous_results": all_results[-3:]})
        if not current_plan.get("plan"):
            break

    return {
        "ok": False,
        "summary": "Ho fatto del mio meglio ma non ho raggiunto pienamente l'obiettivo.\n" +
                   "\n".join(f"- {r.get('output', r.get('error'))[:200]}" for r in all_results[-3:]),
        "steps_executed": len(all_results),
        "duration_sec": round(time.time() - started, 1),
    }
