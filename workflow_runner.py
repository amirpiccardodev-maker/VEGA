"""Workflow runner — orchestra agenti del team in pipeline coordinata.

Carica i workflow definiti nei template (es. consulting.json) e li esegue
chiamando il giusto agente per ogni step con il payload appropriato.

API:
    list_workflows(template_id=None) -> list
    run(workflow_name, payload_overrides={}) -> dict (con tutti gli step results)
"""
import json
import time
import uuid
from pathlib import Path

import bus


ROOT = Path(__file__).parent
TEMPLATES_DIR = ROOT / "data" / "agent_templates"
RUNS_DIR = ROOT / "data" / "workflow_runs"
RUNS_DIR.mkdir(parents=True, exist_ok=True)


def _load_all_templates() -> list:
    out = []
    if not TEMPLATES_DIR.exists():
        return out
    for p in TEMPLATES_DIR.glob("*.json"):
        try:
            with open(p, "r", encoding="utf-8") as f:
                out.append(json.load(f))
        except Exception:
            pass
    return out


def list_workflows(template_id: str = None) -> list:
    """Lista tutti i workflow disponibili in tutti i template."""
    out = []
    for t in _load_all_templates():
        if template_id and t.get("id") != template_id:
            continue
        for wf in t.get("workflows", []):
            out.append({
                "template_id": t.get("id"),
                "name": wf.get("name"),
                "description": wf.get("description"),
                "trigger": wf.get("trigger"),
                "steps_count": len(wf.get("steps", [])),
            })
    return out


def get_workflow(workflow_name: str) -> dict:
    """Find a workflow definition by name."""
    for t in _load_all_templates():
        for wf in t.get("workflows", []):
            if wf.get("name") == workflow_name:
                return wf
    return None


def _build_step_payload(step: dict, shared_ctx: dict) -> dict:
    """Build the payload to pass to an agent for this step.

    Combines:
      - step.action → maps to op (es. 'welcome_kit' → op='welcome_kit')
      - shared_ctx (cliente, progetto ecc.)
      - step.payload (override esplicito)
    """
    payload = dict(shared_ctx)
    payload["op"] = step.get("action", "default")
    if "payload" in step:
        payload.update(step["payload"])
    return payload


def run(workflow_name: str, payload_overrides: dict = None) -> dict:
    """Esegue un workflow step-by-step, chiamando ogni agente in sequenza."""
    wf = get_workflow(workflow_name)
    if not wf:
        return {"ok": False, "error": f"workflow '{workflow_name}' non trovato"}

    run_id = f"wfrun_{uuid.uuid4().hex[:8]}"
    started = time.time()
    shared_ctx = dict(payload_overrides or {})

    bus.publish("workflow.started", {
        "run_id": run_id, "workflow": workflow_name,
        "steps": len(wf.get("steps", [])),
    })

    # Import agents registry
    try:
        from agents import team_registry
        team_registry._load_all()
    except Exception as e:
        return {"ok": False, "error": f"team_registry load failed: {e}"}

    step_results = []
    success_count = 0
    for i, step in enumerate(wf.get("steps", [])):
        agent_name = step.get("agent")
        action = step.get("action", "default")
        agent = team_registry.get(agent_name)
        step_meta = {
            "index": i,
            "agent": agent_name,
            "action": action,
            "started_at": int(time.time()),
        }
        bus.publish("workflow.step_started", {
            "run_id": run_id, **step_meta,
        })
        if not agent:
            step_meta.update({"ok": False, "error": f"agente '{agent_name}' non trovato"})
            step_results.append(step_meta)
            continue
        if not agent.is_enabled():
            step_meta.update({"ok": False, "error": f"agente '{agent_name}' disabilitato"})
            step_results.append(step_meta)
            continue
        # Build payload from shared context
        payload = _build_step_payload(step, shared_ctx)
        # Execute
        try:
            result = agent.safe_run(payload)
        except Exception as e:
            result = {"ok": False, "error": str(e)}
        step_meta.update({
            "ok": bool(result.get("ok")) if isinstance(result, dict) else False,
            "duration_ms": int((time.time() - step_meta["started_at"]) * 1000),
            "result_preview": str(result)[:300] if result else "",
        })
        step_results.append(step_meta)
        if step_meta["ok"]:
            success_count += 1
        # Merge result into shared context for next step (es. client_id, lead_id)
        if isinstance(result, dict):
            for k in ("client", "client_id", "lead_id", "invoice_id",
                      "project", "project_id"):
                if k in result and k not in shared_ctx:
                    shared_ctx[k] = result[k]
        bus.publish("workflow.step_finished", {
            "run_id": run_id, "step": i, "ok": step_meta["ok"],
        })

    duration = round(time.time() - started, 2)
    report = {
        "ok": success_count == len(step_results),
        "run_id": run_id,
        "workflow": workflow_name,
        "started_at": int(started),
        "duration_sec": duration,
        "steps_total": len(step_results),
        "steps_succeeded": success_count,
        "steps": step_results,
        "shared_context": shared_ctx,
    }
    # Persist
    try:
        with open(RUNS_DIR / f"{run_id}.json", "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

    bus.publish("workflow.finished", {
        "run_id": run_id, "workflow": workflow_name,
        "ok": report["ok"], "duration_sec": duration,
    })

    # UI card with outcome
    try:
        bus.publish("card", {
            "type": "workflow_result",
            "data": {
                "title": f"🔄 Workflow: {workflow_name}",
                "ok": report["ok"],
                "steps": [{"agent": s["agent"], "action": s["action"],
                            "ok": s["ok"]} for s in step_results],
                "duration_sec": duration,
            },
        })
    except Exception:
        pass

    return report


def list_recent_runs(limit: int = 20) -> list:
    out = []
    for p in sorted(RUNS_DIR.glob("wfrun_*.json"),
                     key=lambda x: x.stat().st_mtime, reverse=True)[:limit]:
        try:
            with open(p, "r", encoding="utf-8") as f:
                r = json.load(f)
            out.append({
                "run_id": r.get("run_id"),
                "workflow": r.get("workflow"),
                "ok": r.get("ok"),
                "duration_sec": r.get("duration_sec"),
                "started_at": r.get("started_at"),
                "steps_succeeded": r.get("steps_succeeded"),
                "steps_total": r.get("steps_total"),
            })
        except Exception:
            pass
    return out


def get_run(run_id: str) -> dict:
    p = RUNS_DIR / f"{run_id}.json"
    if not p.exists():
        return {"error": "run non trovato"}
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        return {"error": str(e)}
