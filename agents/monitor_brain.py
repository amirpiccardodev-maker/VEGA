"""Brain Monitor — osserva Anthropic API usage + Ollama + cache hit rate."""
from .monitor_base import MonitorAgent


class BrainMonitorAgent(MonitorAgent):
    name = "brain_monitor"
    subsystem_name = "brain"
    icon = "🧠"
    description = "Monitor cervelli AI (Sonnet, Haiku, Ollama). Token, cache, latency."
    model_pref = "haiku"
    actions = [
        {"name": "clear_history", "description": "Pulisce history conversazione in memoria"},
        {"name": "clear_tool_cache", "description": "Svuota cache risultati tool"},
        {"name": "rotate_provider", "description": "Forza switch a Ollama (se disponibile)"},
    ]

    def _snapshot(self):
        out = {}
        # Token usage
        try:
            import memory
            usage = memory.get_usage_stats()
            out["tokens"] = usage
        except Exception as e:
            out["tokens_error"] = str(e)[:80]
        # Cache hit
        try:
            import tool_cache
            out["tool_cache"] = tool_cache.stats()
        except Exception:
            pass
        # Ollama
        try:
            import local_brain
            out["ollama"] = {
                "available": local_brain.is_available(),
                "current_model": local_brain.get_model(),
            }
        except Exception:
            out["ollama"] = {"available": False}
        return out

    def _diagnose(self):
        snap = self._snapshot()
        # Cost estimate from token usage
        try:
            import memory
            usage = memory.get_usage_stats() or {}
            input_t = usage.get("input_tokens_total", 0)
            output_t = usage.get("output_tokens_total", 0)
            # Sonnet 4.5 pricing approx
            cost_in = input_t * 3.0 / 1_000_000
            cost_out = output_t * 15.0 / 1_000_000
            snap["estimated_cost_usd"] = round(cost_in + cost_out, 2)
        except Exception:
            pass
        return snap

    def _do_action(self, name, args=None):
        if name == "clear_history":
            return {"ok": False, "error": "history clear non implementato (richiede engine ref)"}
        if name == "clear_tool_cache":
            try:
                import tool_cache
                tool_cache.clear() if hasattr(tool_cache, "clear") else tool_cache.invalidate()
                return {"ok": True, "msg": "cache pulita"}
            except Exception as e:
                return {"ok": False, "error": str(e)}
        if name == "rotate_provider":
            try:
                import memory
                memory.set_preference("local_brain_enabled", True)
                return {"ok": True, "msg": "local brain abilitato; ricarica per applicare"}
            except Exception as e:
                return {"ok": False, "error": str(e)}
        return super()._do_action(name, args)


AGENT = BrainMonitorAgent()
