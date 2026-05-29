"""Base class per gli agenti del Team (Tier 0-3).

Differenze rispetto ad agents/base.py (worker classici email/code/desktop):
  - lifecycle: enabled/paused/disabled
  - schedule (cron-like via automations) opzionale
  - subscribe a bus events automaticamente
  - emit messages strutturati su bus topic "team.<from>.<kind>"
  - shared state via memory_graph + namespacing

Ogni agente concreto eredita e implementa run(payload) e (opzionale) on_event.
"""
import threading
import time
import uuid


class TeamAgent:
    name: str = "unnamed"
    tier: int = 2                 # 0 governance | 1 compliance | 2 operations | 3 intelligence
    icon: str = "🤖"
    description: str = ""
    model_pref: str = "haiku"     # "haiku" | "sonnet" | "local"
    subscribes: list = []         # bus topics
    schedule: str = None          # crontab-like "daily 07:00", "interval 4h"

    def __init__(self):
        self._enabled = True
        self._last_activity_ts = 0
        self._task_count = 0
        self._lock = threading.Lock()
        self._wire_subscriptions()

    # --- lifecycle ---
    def enable(self):
        with self._lock:
            self._enabled = True
            self._touch()
        self._emit("lifecycle", {"state": "enabled"})

    def disable(self):
        with self._lock:
            self._enabled = False
        self._emit("lifecycle", {"state": "disabled"})

    def is_enabled(self) -> bool:
        return self._enabled

    def status(self) -> dict:
        return {
            "name": self.name,
            "tier": self.tier,
            "icon": self.icon,
            "description": self.description,
            "enabled": self._enabled,
            "last_activity_ts": self._last_activity_ts,
            "task_count": self._task_count,
            "model_pref": self.model_pref,
            "schedule": self.schedule,
        }

    # --- bus wiring ---
    def _wire_subscriptions(self):
        try:
            import bus
            for topic in self.subscribes:
                bus.subscribe(topic, self._dispatch)
        except Exception:
            pass

    def _dispatch(self, event):
        if not self._enabled:
            return
        try:
            self.on_event(event)
            self._touch()
        except Exception as e:
            self._emit("error", {"error": str(e)})

    def on_event(self, event):
        """Override to react to subscribed bus events."""
        pass

    # --- main entry ---
    def run(self, payload: dict = None) -> dict:
        """Override. Main work entry. Returns result dict."""
        return {"ok": False, "error": "not implemented"}

    def safe_run(self, payload: dict = None) -> dict:
        """Wraps run() with enabled check + audit + emit."""
        if not self._enabled:
            return {"ok": False, "error": "agent disabled"}
        run_id = "rn_" + uuid.uuid4().hex[:8]
        self._emit("run_start", {"run_id": run_id, "payload_preview":
                                  str(payload)[:200] if payload else ""})
        started = time.time()
        try:
            result = self.run(payload or {})
        except Exception as e:
            result = {"ok": False, "error": str(e)}
        duration = round(time.time() - started, 2)
        self._task_count += 1
        self._touch()
        self._emit("run_end", {"run_id": run_id, "duration_sec": duration,
                                 "ok": result.get("ok", False)})
        try:
            import audit_log
            audit_log.log(f"team.{self.name}.run",
                          {"run_id": run_id, "duration_sec": duration,
                           "ok": result.get("ok", False)})
        except Exception:
            pass
        return result

    # --- utilities ---
    def _touch(self):
        self._last_activity_ts = int(time.time())

    def _emit(self, kind: str, data: dict):
        """Emit a structured message on the bus, for UI live view + audit."""
        try:
            import bus
            bus.publish("team.message", {
                "ts": int(time.time() * 1000),
                "from": f"agent.{self.name}",
                "kind": kind,
                "data": data,
            })
        except Exception:
            pass

    def call_haiku(self, prompt: str) -> str:
        """Shortcut for Haiku."""
        try:
            import fast_brain
            return (fast_brain.fast_call(prompt) or "").strip()
        except Exception as e:
            return f"(LLM error: {e})"

    def call_haiku_json(self, prompt: str, schema: dict = None) -> dict:
        try:
            import fast_brain
            return fast_brain.fast_json(prompt, schema_hint=schema) or {}
        except Exception as e:
            return {"error": str(e)}

    def remember(self, kind: str, content: str, importance: float = 0.5,
                  tags: list = None):
        """Persist a fact/note into memory_graph, namespaced by agent."""
        try:
            import memory_graph as mg
            mg.add(kind, content, importance=importance,
                   source=f"agent.{self.name}",
                   tags=(tags or []) + [f"agent:{self.name}"])
        except Exception:
            pass

    def search_memory(self, query: str, kinds: list = None, top_k: int = 5):
        try:
            import memory_graph as mg
            return mg.search(query, kinds=kinds, top_k=top_k)
        except Exception:
            return []

    # ============ HIERARCHY & COLLABORATION ============

    def hierarchy_info(self) -> dict:
        """Return this agent's position in the org chart."""
        return _hierarchy_for(self.name)

    def superior(self) -> str:
        """Return name of superior agent or None."""
        return self.hierarchy_info().get("superior")

    def subordinates(self) -> list:
        """List of agent names this agent can delegate to."""
        return self.hierarchy_info().get("subordinates", [])

    def can_veto_tool(self, tool_name: str) -> bool:
        """Check if this agent has veto power on a specific tool."""
        info = self.hierarchy_info()
        if not info.get("can_veto"):
            return False
        scope = info.get("veto_scope", [])
        return tool_name in scope or "any_personal_data_op" in scope

    def delegate(self, target: str, payload: dict, timeout_sec: float = 30) -> dict:
        """Call another agent. Records the delegation in audit_log.

        Returns dict: {ok, result, target, duration_sec}
        """
        import time as _time
        try:
            from . import team_registry
        except Exception:
            return {"ok": False, "error": "team_registry unavailable"}
        target_agent = team_registry.get(target)
        if not target_agent:
            return {"ok": False, "error": f"target '{target}' not found"}
        # Authorization check: can this agent delegate to target?
        my_subs = self.subordinates()
        if my_subs and target not in my_subs:
            self._emit("unauthorized_delegate", {"target": target,
                                                   "my_subs_count": len(my_subs)})
            # Allow soft-delegate (audit but proceed) for now
        self._emit("delegate", {"target": target,
                                  "payload_preview": str(payload)[:200]})
        start = _time.time()
        try:
            result = target_agent.safe_run(payload)
        except Exception as e:
            result = {"ok": False, "error": str(e)}
        duration = round(_time.time() - start, 2)
        try:
            import audit_log
            audit_log.log("team.delegation", {
                "from": self.name, "to": target,
                "ok": bool(result.get("ok")) if isinstance(result, dict) else False,
                "duration_sec": duration,
            })
        except Exception:
            pass
        return {"ok": True, "result": result, "target": target,
                "duration_sec": duration}

    def report_to_superior(self, kind: str, data: dict):
        """Bubble up a notification to the superior in the chain."""
        sup_name = self.superior()
        if not sup_name:
            return
        try:
            from . import team_registry
            sup = team_registry.get(sup_name)
            if sup is None:
                return
            sup._dispatch({"topic": f"report_from_{self.name}",
                           "payload": {"kind": kind, "data": data,
                                        "from": self.name}})
        except Exception:
            pass

    # ============ ACTIONS REGISTRY ============
    # Each agent declares its callable actions (for UI + delegation).

    def list_actions(self) -> list:
        """Returns list of {name, description, args_schema}.
        Subclasses override to expose specific actions."""
        if hasattr(self, "_actions_cache"):
            return self._actions_cache
        actions = self._declare_actions()
        self._actions_cache = actions
        return actions

    def _declare_actions(self) -> list:
        """Default: introspect run() ops by trying with empty payload.
        Subclasses should override with explicit declaration."""
        return [{"name": "default", "description": self.description, "args_schema": {}}]

    def execute_action(self, action_name: str, args: dict = None) -> dict:
        """Run a named action with args."""
        payload = dict(args or {})
        payload["op"] = action_name
        return self.safe_run(payload)

    # ============ DASHBOARD DATA ============

    def dashboard_data(self) -> dict:
        """Return a snapshot for UI dashboard. Subclasses can override."""
        return {
            "name": self.name,
            "tier": self.tier,
            "icon": self.icon,
            "description": self.description,
            "enabled": self._enabled,
            "task_count": self._task_count,
            "last_activity_ts": self._last_activity_ts,
            "model_pref": self.model_pref,
            "schedule": self.schedule,
            "hierarchy": self.hierarchy_info(),
            "actions": self.list_actions(),
        }


# ============ Hierarchy data loader (module-level) ============
_hierarchy_cache = None


def _load_hierarchy() -> dict:
    global _hierarchy_cache
    if _hierarchy_cache is not None:
        return _hierarchy_cache
    import json
    from pathlib import Path
    p = Path(__file__).parent.parent / "data" / "hierarchy.json"
    if not p.exists():
        _hierarchy_cache = {}
        return {}
    try:
        with open(p, "r", encoding="utf-8") as f:
            _hierarchy_cache = json.load(f)
    except Exception:
        _hierarchy_cache = {}
    return _hierarchy_cache


def _hierarchy_for(agent_name: str) -> dict:
    return _load_hierarchy().get(agent_name, {})


def reload_hierarchy():
    global _hierarchy_cache
    _hierarchy_cache = None
