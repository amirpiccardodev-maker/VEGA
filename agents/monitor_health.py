"""Health Monitor — CPU/RAM/disk + uptime + errori sistema."""
import time

from .monitor_base import MonitorAgent


class HealthMonitorAgent(MonitorAgent):
    name = "health_monitor"
    subsystem_name = "health"
    icon = "🏥"
    description = "Monitor salute sistema: CPU, RAM, disco, uptime, errori per ora."
    model_pref = "haiku"
    actions = [
        {"name": "system_check", "description": "Check completo sistema"},
        {"name": "error_rate", "description": "Tasso errori ultime 24h"},
        {"name": "ws_clients", "description": "Numero client WebSocket connessi"},
    ]

    def __init__(self):
        super().__init__()
        self._boot_ts = time.time()

    def _snapshot(self):
        out = {"uptime_sec": int(time.time() - self._boot_ts)}
        try:
            import psutil
            out["cpu_pct"] = psutil.cpu_percent(interval=0.1)
            mem = psutil.virtual_memory()
            out["ram"] = {"used_pct": mem.percent,
                           "used_gb": round(mem.used / 1024**3, 1),
                           "total_gb": round(mem.total / 1024**3, 1)}
            disk = psutil.disk_usage("/")
            out["disk"] = {"used_pct": disk.percent,
                            "free_gb": round(disk.free / 1024**3, 1)}
            # Process memory
            proc = psutil.Process()
            out["vega_mem_mb"] = round(proc.memory_info().rss / 1024**2, 1)
        except Exception as e:
            out["psutil_error"] = str(e)[:80]
        # Errors last hour
        try:
            import bus
            recent = bus.history()
            now = time.time()
            hour_ago = (now - 3600) * 1000  # ms
            errors_last_hour = sum(1 for e in recent
                                     if e.get("topic", "").startswith("error")
                                     and e.get("ts_ms", 0) > hour_ago)
            out["errors_last_hour"] = errors_last_hour
        except Exception:
            pass
        return out

    def _diagnose(self):
        snap = self._snapshot()
        snap["alerts"] = []
        if snap.get("cpu_pct", 0) > 80:
            snap["alerts"].append("⚠ CPU >80%")
        if snap.get("ram", {}).get("used_pct", 0) > 85:
            snap["alerts"].append("⚠ RAM >85%")
        if snap.get("disk", {}).get("used_pct", 0) > 90:
            snap["alerts"].append("⚠ Disco >90%")
        if snap.get("errors_last_hour", 0) > 20:
            snap["alerts"].append(f"⚠ {snap['errors_last_hour']} errori nell'ultima ora")
        uptime_h = snap["uptime_sec"] / 3600
        if uptime_h > 168:  # 1 week
            snap["alerts"].append("ℹ Uptime >1 settimana: considera riavvio per refresh memoria")
        return snap

    def _do_action(self, name, args=None):
        if name == "system_check":
            return {"ok": True, "snapshot": self._snapshot()}
        if name == "error_rate":
            try:
                import bus
                recent = bus.history()
                from collections import Counter
                topics = Counter(e.get("topic", "?") for e in recent
                                  if "error" in e.get("topic", ""))
                return {"ok": True, "errors_by_topic": dict(topics)}
            except Exception as e:
                return {"ok": False, "error": str(e)}
        if name == "ws_clients":
            try:
                # access via server module if available
                import server
                count = len(getattr(server, "_clients", []))
                return {"ok": True, "ws_clients": count}
            except Exception:
                return {"ok": True, "ws_clients": "unknown"}
        return super()._do_action(name, args)


AGENT = HealthMonitorAgent()
