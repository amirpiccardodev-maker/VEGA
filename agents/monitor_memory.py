"""Memory Monitor — memory_graph + Mem0 + RAG docs."""
from .monitor_base import MonitorAgent


class MemoryMonitorAgent(MonitorAgent):
    name = "memory_monitor"
    subsystem_name = "memory"
    icon = "💾"
    description = "Monitor memorie: memory_graph SQLite, Mem0 episodic, RAG docs."
    model_pref = "haiku"
    actions = [
        {"name": "stats_detail", "description": "Statistiche dettagliate per kind"},
        {"name": "prune_low_importance", "description": "Cancella record con importance<0.3"},
        {"name": "list_canaries", "description": "Lista honeypot canary attivi"},
        {"name": "rotate_canaries", "description": "Ruota canary (nuovi)"},
    ]

    def _snapshot(self):
        out = {}
        try:
            import memory_graph as mg
            out["graph"] = mg.stats()
        except Exception as e:
            out["graph_error"] = str(e)[:80]
        try:
            import episodic_memory as em
            out["mem0"] = em.stats()
        except Exception:
            out["mem0"] = {"available": False}
        try:
            import honeypot
            out["honeypot"] = honeypot.stats()
        except Exception:
            pass
        return out

    def _diagnose(self):
        snap = self._snapshot()
        snap["analysis"] = []
        graph = snap.get("graph", {})
        if isinstance(graph, dict):
            total = graph.get("total", 0)
            if total > 10000:
                snap["analysis"].append("memory_graph >10k records: considera pruning")
            kinds_count = {k: v for k, v in graph.items() if k != "total"}
            top = sorted(kinds_count.items(), key=lambda x: -x[1])[:3]
            snap["top_kinds"] = top
        mem0 = snap.get("mem0", {})
        if mem0.get("total", 0) > 500:
            snap["analysis"].append("Mem0 >500 episodi: ottime continuità ma ricarica più lenta")
        return snap

    def _do_action(self, name, args=None):
        if name == "stats_detail":
            return {"ok": True, "snapshot": self._snapshot()}
        if name == "prune_low_importance":
            try:
                import memory_graph as mg
                if hasattr(mg, "prune"):
                    n = mg.prune(min_importance=0.3)
                    return {"ok": True, "pruned": n}
            except Exception as e:
                return {"ok": False, "error": str(e)}
            return {"ok": False, "error": "prune non disponibile"}
        if name == "list_canaries":
            try:
                import honeypot
                cs = honeypot.get_active_canaries()
                return {"ok": True, "count": len(cs),
                        "canaries": [{"id": c["id"], "kind": c["kind"]} for c in cs]}
            except Exception as e:
                return {"ok": False, "error": str(e)}
        if name == "rotate_canaries":
            try:
                import honeypot
                honeypot.rotate_canaries()
                return {"ok": True, "msg": "canary ruotati"}
            except Exception as e:
                return {"ok": False, "error": str(e)}
        return super()._do_action(name, args)


AGENT = MemoryMonitorAgent()
