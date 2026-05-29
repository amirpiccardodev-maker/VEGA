"""Agentic loop con planning + reflection.

Usage:
  result = agent.plan_and_execute("organizzami un weekend a Lisbona col budget 500")

Phases:
  1. PLAN  - Haiku (cheap) writes a list of sub-tasks
  2. EXECUTE - per each sub-task, Sonnet (full power) runs it via Brain
  3. REFLECT - Haiku decides: done / iterate / give up
  4. SUMMARIZE - Haiku assembles the final answer from sub-results
"""
import json
import time

import fast_brain
from brain import Brain


MAX_STEPS = 5
MAX_REFLECTION_ITERATIONS = 2


def plan(goal: str, brain_history: list = None) -> list:
    """Return a list of subtask strings."""
    history_ctx = ""
    if brain_history:
        # Last few user msgs for context
        recent = [m for m in brain_history[-6:] if m.get("role") == "user"]
        if recent:
            history_ctx = "Contesto recente:\n" + "\n".join(
                f"- {m['content'][:200]}" if isinstance(m.get("content"), str) else ""
                for m in recent
            )

    prompt = (
        "Sei un agente che pianifica come affrontare un obiettivo complesso.\n"
        f"Obiettivo: {goal}\n\n{history_ctx}\n\n"
        "Spezza l'obiettivo in 2-5 sotto-task atomici, ognuno eseguibile come "
        "singola query a Vega. Sii concreto: ogni task deve essere una "
        "frase imperativa che il sistema possa processare (es. 'cerca info su X', "
        "'controlla meteo a Lisbona', 'trova foto di X').\n\n"
        "Rispondi SOLO con JSON valido: {\"steps\": [\"step1\", \"step2\", ...]}"
    )
    data = fast_brain.fast_json(prompt, schema_hint='{"steps": ["...", "..."]}')
    steps = data.get("steps", [])
    if not isinstance(steps, list):
        return []
    return [str(s)[:200] for s in steps if s][:MAX_STEPS]


def reflect(goal: str, results: list) -> dict:
    """Reflection: did we achieve the goal? Returns {done, next_action}."""
    results_text = "\n".join(f"- {r}" for r in results[-MAX_STEPS:])
    prompt = (
        f"Obiettivo originale: {goal}\n\n"
        f"Risultati ottenuti finora:\n{results_text}\n\n"
        "Abbiamo raggiunto l'obiettivo? Rispondi SOLO JSON: "
        '{"done": true/false, "next_step": "se non e\' done, una frase con il prossimo task", '
        '"summary": "se done, riassunto in italiano per l\'utente"}'
    )
    data = fast_brain.fast_json(prompt)
    return {
        "done": bool(data.get("done", False)),
        "next_step": str(data.get("next_step", ""))[:200],
        "summary": str(data.get("summary", ""))[:1000],
    }


def plan_and_execute(goal: str, brain: Brain = None, on_step=None) -> dict:
    """Run the full agentic loop.

    Returns: {goal, steps, results, final, success, duration_sec}
    """
    if brain is None:
        brain = Brain()
    started = time.time()

    steps = plan(goal, brain.history)
    if not steps:
        return {"goal": goal, "steps": [], "results": [],
                "final": "Non sono riuscito a pianificare. Riformula la richiesta.",
                "success": False, "duration_sec": 0}

    results = []
    if on_step: on_step("plan", steps)

    for i, step in enumerate(steps):
        if on_step: on_step("execute", f"[{i+1}/{len(steps)}] {step}")
        try:
            answer = brain.ask(step)
        except Exception as e:
            answer = f"ERRORE: {e}"
        results.append(f"{step} -> {answer[:300]}")

    # Reflection
    reflect_iter = 0
    while reflect_iter < MAX_REFLECTION_ITERATIONS:
        r = reflect(goal, results)
        if on_step: on_step("reflect", r)
        if r["done"]:
            break
        if not r["next_step"]:
            break
        # Execute the extra step
        try:
            answer = brain.ask(r["next_step"])
            results.append(f"{r['next_step']} -> {answer[:300]}")
        except Exception:
            break
        reflect_iter += 1

    final = r.get("summary") if r.get("done") else (
        "Ho eseguito tutti i passi ma il risultato potrebbe non essere completo. "
        "Risultati:\n" + "\n".join(results[-3:])
    )
    return {
        "goal": goal,
        "steps": steps,
        "results": results,
        "final": final,
        "success": r.get("done", False),
        "duration_sec": round(time.time() - started, 1),
    }
