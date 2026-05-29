"""Workflow engine: esegue pipeline JSON dichiarative.

DSL minimale:
    {
        "id": "wf_xxx",
        "name": "...",
        "trigger": {"type": "manual" | "schedule" | "event", ...},
        "steps": [
            {"id": "s1", "type": "tool", "tool": "get_weather", "args": {}, "save_as": "w"},
            {"id": "s2", "type": "llm", "model": "haiku", "prompt": "...{{w}}...", "save_as": "out"},
            {"id": "s3", "type": "condition", "if": "{{out.count}} > 0", "then": "s4", "else": "end"},
            {"id": "s4", "type": "parallel", "branches": [[step,step], [step]]},
            {"id": "s5", "type": "foreach", "items": "{{list}}", "as": "x", "steps": [...]},
            {"id": "s6", "type": "wait", "seconds": 5}
        ]
    }

Persistenza: workflows/*.json (definizioni), stati di esecuzione in task_queue.
"""
import json
import os
import re
import time
import uuid
from pathlib import Path

import bus
import task_queue

ROOT = Path(__file__).parent
WORKFLOWS_DIR = ROOT / "workflows"
WORKFLOWS_DIR.mkdir(exist_ok=True)


# ============ Storage ============

def load_workflow(wf_id: str) -> dict:
    path = WORKFLOWS_DIR / f"{wf_id}.json"
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def save_workflow(wf: dict) -> str:
    if "id" not in wf:
        wf["id"] = "wf_" + uuid.uuid4().hex[:10]
    if "created_at" not in wf:
        wf["created_at"] = int(time.time())
    wf["updated_at"] = int(time.time())
    path = WORKFLOWS_DIR / f"{wf['id']}.json"
    tmp = str(path) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(wf, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    return wf["id"]


def list_workflows() -> list:
    out = []
    for p in WORKFLOWS_DIR.glob("*.json"):
        try:
            with open(p, "r", encoding="utf-8") as f:
                wf = json.load(f)
            out.append({
                "id": wf.get("id"), "name": wf.get("name"),
                "trigger": wf.get("trigger"), "enabled": wf.get("enabled", True),
                "created_at": wf.get("created_at"),
                "step_count": len(wf.get("steps", [])),
            })
        except Exception:
            pass
    return sorted(out, key=lambda x: x.get("created_at", 0), reverse=True)


def delete_workflow(wf_id: str) -> bool:
    path = WORKFLOWS_DIR / f"{wf_id}.json"
    if path.exists():
        try:
            path.unlink()
            return True
        except Exception:
            pass
    return False


# ============ Template variable expansion ============

_VAR_RE = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")


def _lookup(path: str, ctx: dict):
    """Resolve dotted path like 'a.b.c' or 'a.0.b' in ctx."""
    parts = path.split(".")
    cur = ctx
    for p in parts:
        if cur is None:
            return None
        if isinstance(cur, dict):
            cur = cur.get(p)
        elif isinstance(cur, list):
            try:
                cur = cur[int(p)]
            except (ValueError, IndexError):
                return None
        else:
            return None
    return cur


def render(template, ctx: dict):
    """Expand {{var}} in any string within a structure."""
    if isinstance(template, str):
        def replace(m):
            val = _lookup(m.group(1).strip(), ctx)
            if val is None:
                return ""
            if isinstance(val, (dict, list)):
                return json.dumps(val, ensure_ascii=False)
            return str(val)
        return _VAR_RE.sub(replace, template)
    if isinstance(template, dict):
        return {k: render(v, ctx) for k, v in template.items()}
    if isinstance(template, list):
        return [render(v, ctx) for v in template]
    return template


def _eval_condition(expr: str, ctx: dict) -> bool:
    """Eval a simple condition like '{{x}} > 0' or '{{name}} == "Amir"'.

    Variables are substituted as JSON literals so strings get quoted properly.
    """
    def replace(m):
        val = _lookup(m.group(1).strip(), ctx)
        if val is None:
            return "None"
        if isinstance(val, bool):
            return "True" if val else "False"
        if isinstance(val, (int, float)):
            return str(val)
        # Strings, dicts, lists → JSON-encoded (gives quoted strings)
        return json.dumps(val, ensure_ascii=False)
    rendered = _VAR_RE.sub(replace, expr) if isinstance(expr, str) else str(expr)
    try:
        return bool(eval(rendered, {"__builtins__": {}}, {"true": True, "false": False, "null": None}))
    except Exception:
        return False


# ============ Step executors ============

def _step_tool(step: dict, ctx: dict, emit=None) -> any:
    import tools as tool_registry
    name = step.get("tool")
    args = render(step.get("args", {}), ctx)
    if not name:
        return {"error": "no tool name"}
    return tool_registry.execute(name, args, emit=emit)


def _step_llm(step: dict, ctx: dict) -> any:
    import fast_brain
    prompt = render(step.get("prompt", ""), ctx)
    model_hint = step.get("model", "haiku")
    if model_hint == "haiku":
        if step.get("schema"):
            return fast_brain.fast_json(prompt, schema_hint=step.get("schema"))
        return fast_brain.fast_call(prompt)
    else:  # sonnet
        from brain import Brain
        b = Brain()
        return b.ask(prompt)


def _step_condition(step: dict, ctx: dict) -> dict:
    cond = step.get("if", "false")
    return {"matched": _eval_condition(cond, ctx)}


def _step_wait(step: dict, ctx: dict) -> dict:
    secs = int(step.get("seconds", 1))
    secs = min(secs, 60)  # cap at 1 min (longer waits should be schedule, not wait)
    time.sleep(secs)
    return {"waited": secs}


def _step_parallel(step: dict, ctx: dict, run_steps_fn) -> list:
    import concurrent.futures as _cf
    branches = step.get("branches", [])
    if not branches:
        return []
    out = [None] * len(branches)
    with _cf.ThreadPoolExecutor(max_workers=min(4, len(branches))) as ex:
        futs = [ex.submit(run_steps_fn, b, dict(ctx)) for b in branches]
        for i, f in enumerate(futs):
            try:
                out[i] = f.result()
            except Exception as e:
                out[i] = {"error": str(e)}
    return out


def _step_foreach(step: dict, ctx: dict, run_steps_fn) -> list:
    items_raw = render(step.get("items", ""), ctx)
    if isinstance(items_raw, str):
        try:
            items_raw = json.loads(items_raw)
        except Exception:
            items_raw = []
    if not isinstance(items_raw, list):
        return []
    out = []
    var = step.get("as", "item")
    inner_steps = step.get("steps", [])
    for x in items_raw[:20]:  # cap loops
        loop_ctx = dict(ctx)
        loop_ctx[var] = x
        out.append(run_steps_fn(inner_steps, loop_ctx))
    return out


# ============ Runner ============

def run_steps(steps: list, ctx: dict, emit=None) -> dict:
    """Execute a list of steps sequentially. Updates ctx with save_as values."""
    for step in steps:
        step_type = step.get("type", "tool")
        step_id = step.get("id", step_type)
        bus.publish(bus.Topics.WORKFLOW_STEP, {"step_id": step_id, "type": step_type})
        try:
            if step_type == "tool":
                result = _step_tool(step, ctx, emit=emit)
            elif step_type == "llm":
                result = _step_llm(step, ctx)
            elif step_type == "condition":
                result = _step_condition(step, ctx)
                if not result["matched"] and step.get("else"):
                    # skip ahead - simple: just mark and continue (else handling is implicit)
                    pass
            elif step_type == "wait":
                result = _step_wait(step, ctx)
            elif step_type == "parallel":
                result = _step_parallel(step, ctx, lambda s, c: run_steps(s, c, emit))
            elif step_type == "foreach":
                result = _step_foreach(step, ctx, lambda s, c: run_steps(s, c, emit))
            else:
                result = {"error": f"unknown step type: {step_type}"}

            save_as = step.get("save_as")
            if save_as:
                ctx[save_as] = result
            ctx[f"_last_{step_id}"] = result
        except Exception as e:
            ctx[f"_error_{step_id}"] = str(e)
            if step.get("on_error") == "abort":
                raise
            # else continue
    return ctx


def execute(wf_id: str, initial_ctx: dict = None, emit=None) -> dict:
    """Execute a workflow by id."""
    wf = load_workflow(wf_id)
    if not wf:
        return {"error": f"workflow {wf_id} not found"}
    if not wf.get("enabled", True):
        return {"error": "workflow disabled"}

    ctx = dict(initial_ctx or {})
    ctx["_workflow_id"] = wf_id
    ctx["_started_at"] = int(time.time())
    ctx.update(wf.get("context", {}))

    bus.publish(bus.Topics.WORKFLOW_STARTED, {"id": wf_id, "name": wf.get("name")})
    try:
        run_steps(wf.get("steps", []), ctx, emit=emit)
        bus.publish(bus.Topics.WORKFLOW_COMPLETED, {"id": wf_id, "ok": True})
        return {"ok": True, "ctx": {k: v for k, v in ctx.items() if not k.startswith("_")}}
    except Exception as e:
        bus.publish(bus.Topics.WORKFLOW_COMPLETED, {"id": wf_id, "ok": False, "error": str(e)})
        return {"ok": False, "error": str(e)}


# ============ Prompt → Workflow generation ============

WORKFLOW_DSL_DOC = """
Sei un esperto di automation. Genera un workflow JSON per Vega dato un obiettivo utente.

FORMATO JSON:
{
  "name": "nome breve",
  "trigger": {"type": "manual"} OPPURE {"type": "schedule", "cron": "* * * * *"} OPPURE {"type": "event", "event": "..."},
  "steps": [
    {"id": "s1", "type": "tool", "tool": "NOME_TOOL", "args": {...}, "save_as": "varname"},
    {"id": "s2", "type": "llm", "model": "haiku", "prompt": "testo con {{varname}}", "save_as": "out"},
    {"id": "s3", "type": "condition", "if": "{{out.count}} > 0"},
    {"id": "s4", "type": "foreach", "items": "{{list}}", "as": "x", "steps": [...]},
    {"id": "s5", "type": "parallel", "branches": [[step,step], [step]]}
  ]
}

TOOL DISPONIBILI (chiamate per nome, lo schema args e' standard):
- list_emails, summarize_inbox, send_email
- get_news, sports_news, get_weather, wikipedia
- list_todos, add_todo, save_note, remember_fact
- web_search, web_images, read_article_aloud
- windows_notify (title, message)
- analyze_screen, take_screenshot
- generate_image (prompt)
- system_info, set_volume, lock_pc

RISPONDI SOLO CON JSON VALIDO, NIENT'ALTRO.
"""


def create_from_prompt(user_goal: str) -> dict:
    """Use Haiku to generate a workflow JSON from natural language."""
    import fast_brain
    prompt = WORKFLOW_DSL_DOC + f"\n\nObiettivo utente: {user_goal}\n\nWorkflow JSON:"
    data = fast_brain.fast_json(prompt)
    if not data or "steps" not in data:
        return {"error": "Impossibile generare workflow"}
    # Normalize step IDs
    for i, step in enumerate(data.get("steps", [])):
        if "id" not in step:
            step["id"] = f"s{i+1}"
    data.setdefault("name", "workflow_generato")
    data["enabled"] = True
    data["source"] = "prompt"
    data["original_prompt"] = user_goal
    wf_id = save_workflow(data)
    return {"ok": True, "id": wf_id, "name": data["name"], "steps": len(data["steps"])}
