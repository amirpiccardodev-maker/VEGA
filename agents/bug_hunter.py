"""Bug Hunter — Tier 2.

Estende self_healing: aggrega errori, propone fix, schedule check ogni 4h.
"""
import threading
import time

from .team_base import TeamAgent


class BugHunterAgent(TeamAgent):
    name = "bug_hunter"
    tier = 2
    icon = "🐛"
    description = "Aggrega errori, propone fix, monitora salute sistema"
    model_pref = "haiku"
    schedule = "interval 4h"
    subscribes = ["error.occurred"]

    def __init__(self):
        super().__init__()
        threading.Thread(target=self._loop, daemon=True,
                          name="bug_hunter_loop").start()

    def _loop(self):
        time.sleep(90)
        while True:
            if self.is_enabled():
                try:
                    self.safe_run({"op": "scan"})
                except Exception:
                    pass
            time.sleep(4 * 3600)

    def on_event(self, event):
        """Ogni 5 errori in 5 min triggera scan."""
        # Delega al modulo self_healing che ha già ring buffer
        try:
            import self_healing
            self_healing._on_error(event)
        except Exception:
            pass

    def scan(self) -> dict:
        try:
            import self_healing
            self_healing._analyze_once()
            return {"ok": True, "stats": self_healing.stats()}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def health_check(self) -> dict:
        """Quick health snapshot."""
        report = {}
        try:
            import task_queue
            report["task_queue"] = task_queue.stats()
        except Exception as e:
            report["task_queue"] = {"error": str(e)}
        try:
            import memory_graph as mg
            report["memory_graph"] = mg.stats()
        except Exception as e:
            report["memory_graph"] = {"error": str(e)}
        try:
            import bus
            report["bus_history_count"] = len(bus.history()[-50:])
        except Exception:
            pass
        return report

    def run(self, payload: dict) -> dict:
        op = payload.get("op", "scan")
        if op == "scan":
            return self.scan()
        if op == "health":
            return {"ok": True, "health": self.health_check()}
        return {"ok": False, "error": f"op sconosciuta: {op}"}


AGENT = BugHunterAgent()
