"""Dispatch function for task_queue worker.

Knows how to execute different task types:
  - tool_call          -> tools.execute(name, args)
  - llm_call           -> brain.ask(prompt)  or  fast_brain.fast_call
  - workflow_step      -> workflow_engine step
  - automation         -> engine.run_automation_command
  - agent_subgoal      -> agent_fabric.run for one sub-goal
"""
import json

import bus


def dispatch(task: dict):
    """Called by worker on each task. Returns result (any) or raises."""
    task_type = task["type"]
    try:
        payload = json.loads(task["payload"])
    except Exception:
        payload = {}

    if task_type == "tool_call":
        import tools as tool_registry
        name = payload.get("tool")
        args = payload.get("args", {})
        return tool_registry.execute(name, args)

    if task_type == "llm_call":
        prompt = payload.get("prompt", "")
        model = payload.get("model", "haiku")
        if model == "haiku":
            import fast_brain
            return fast_brain.fast_call(prompt)
        else:
            from brain import Brain
            b = Brain()
            return b.ask(prompt)

    if task_type == "workflow_run":
        import workflow_engine
        wf_id = payload.get("workflow_id")
        return workflow_engine.execute(wf_id, payload.get("ctx", {}))

    if task_type == "automation":
        # Trigger via global engine reference if set
        import sys
        eng = getattr(sys.modules.get("server"), "engine", None)
        if eng:
            cmd = payload.get("command", "")
            mode = payload.get("mode", "voice")
            eng.run_automation_command(cmd, mode, payload.get("name", "task"))
            return {"queued": True}
        return {"error": "no engine"}

    if task_type == "agent_subgoal":
        import agent_fabric
        return agent_fabric.run(payload.get("goal", ""))

    return {"error": f"unknown task type: {task_type}"}
