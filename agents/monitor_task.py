"""Task Monitor — task_queue, workflows, agent fabric long-horizon, automazioni."""
from .monitor_base import MonitorAgent


class TaskMonitorAgent(MonitorAgent):
    name = "task_monitor"
    subsystem_name = "tasks"
    icon = "🗂"
    description = "Monitor task queue SQLite, workflow attivi, automazioni schedulate."
    model_pref = "haiku"
    actions = [
        {"name": "list_pending", "description": "Lista task pending"},
        {"name": "list_workflows", "description": "Lista workflow definiti"},
        {"name": "list_automations", "description": "Lista automazioni schedulate"},
        {"name": "stuck_recovery", "description": "Recupera task bloccati"},
    ]

    def _snapshot(self):
        out = {}
        try:
            import task_queue
            out["queue"] = task_queue.stats()
        except Exception:
            pass
        try:
            import workflow_engine
            wfs = workflow_engine.list_workflows()
            out["workflows"] = {"count": len(wfs), "enabled":
                                  sum(1 for w in wfs if w.get("enabled"))}
        except Exception:
            pass
        try:
            import automations
            items = automations.list_all()
            out["automations"] = {
                "count": len(items),
                "enabled": sum(1 for i in items if i.get("enabled")),
            }
        except Exception:
            pass
        return out

    def _diagnose(self):
        snap = self._snapshot()
        snap["analysis"] = []
        q = snap.get("queue", {})
        if q.get("pending", 0) > 50:
            snap["analysis"].append(f"⚠ {q['pending']} task pending: worker sottodimensionato?")
        if q.get("dlq", 0) > 0:
            snap["analysis"].append(f"⚠ {q['dlq']} task in DLQ: errori ricorrenti")
        return snap

    def _do_action(self, name, args=None):
        if name == "list_pending":
            try:
                import task_queue
                # task_queue API ha get_task ma non list pending direttamente
                stats = task_queue.stats()
                return {"ok": True, "stats": stats}
            except Exception as e:
                return {"ok": False, "error": str(e)}
        if name == "list_workflows":
            try:
                import workflow_engine
                return {"ok": True, "workflows": workflow_engine.list_workflows()}
            except Exception as e:
                return {"ok": False, "error": str(e)}
        if name == "list_automations":
            try:
                import automations
                return {"ok": True, "automations": automations.list_all()}
            except Exception as e:
                return {"ok": False, "error": str(e)}
        if name == "stuck_recovery":
            try:
                import task_queue
                if hasattr(task_queue, "stuck_recovery"):
                    n = task_queue.stuck_recovery()
                    return {"ok": True, "recovered": n}
            except Exception as e:
                return {"ok": False, "error": str(e)}
            return {"ok": False, "error": "stuck_recovery non disponibile"}
        return super()._do_action(name, args)


AGENT = TaskMonitorAgent()
