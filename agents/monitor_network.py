"""Network Monitor — net_guard outbound + connections + DNS."""
from .monitor_base import MonitorAgent


class NetworkMonitorAgent(MonitorAgent):
    name = "network_monitor"
    subsystem_name = "network"
    icon = "🌐"
    description = "Monitor connessioni esterne: chi chiama chi, outbound log, allowlist."
    model_pref = "haiku"
    actions = [
        {"name": "recent_outbound", "description": "Ultimi 100 outbound logged"},
        {"name": "set_strict", "description": "Attiva modalità strict (blocca non allowlisted)"},
        {"name": "set_observe", "description": "Modalità observe (log ma non blocca)"},
        {"name": "blocked_count", "description": "Quanti host bloccati"},
    ]

    def _snapshot(self):
        out = {}
        try:
            import net_guard
            out["net_guard"] = net_guard.status()
        except Exception:
            pass
        try:
            import web_push
            out["web_push"] = web_push.stats()
        except Exception:
            pass
        return out

    def _diagnose(self):
        snap = self._snapshot()
        snap["analysis"] = []
        ng = snap.get("net_guard", {})
        if ng.get("mode") == "observe":
            snap["analysis"].append("ℹ Net guard in OBSERVE: logga ma non blocca")
        # Recent outbound histogram
        try:
            import net_guard
            recent = net_guard.recent_outbound(limit=200)
            hosts = {}
            blocked = 0
            for e in recent:
                h = e.get("host", "?")
                hosts[h] = hosts.get(h, 0) + 1
                if not e.get("allowed"):
                    blocked += 1
            top = sorted(hosts.items(), key=lambda x: -x[1])[:10]
            snap["top_hosts_recent"] = top
            snap["blocked_recent"] = blocked
        except Exception:
            pass
        return snap

    def _do_action(self, name, args=None):
        if name == "recent_outbound":
            try:
                import net_guard
                return {"ok": True, "events": net_guard.recent_outbound(limit=100)}
            except Exception as e:
                return {"ok": False, "error": str(e)}
        if name == "set_strict":
            try:
                import net_guard
                return {"ok": net_guard.set_mode("strict"), "mode": "strict"}
            except Exception as e:
                return {"ok": False, "error": str(e)}
        if name == "set_observe":
            try:
                import net_guard
                return {"ok": net_guard.set_mode("observe"), "mode": "observe"}
            except Exception as e:
                return {"ok": False, "error": str(e)}
        if name == "blocked_count":
            try:
                import net_guard
                recent = net_guard.recent_outbound(limit=1000)
                blocked = sum(1 for e in recent if not e.get("allowed"))
                return {"ok": True, "blocked_in_last_1000": blocked}
            except Exception as e:
                return {"ok": False, "error": str(e)}
        return super()._do_action(name, args)


AGENT = NetworkMonitorAgent()
