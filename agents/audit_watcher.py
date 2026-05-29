"""Audit Watcher — Tier 1.

Verifica periodica integrità audit chain + report metriche mensili.
"""
import threading
import time
from pathlib import Path

from .team_base import TeamAgent


ROOT = Path(__file__).parent.parent
REPORTS_DIR = ROOT / "data" / "compliance_reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)


class AuditWatcherAgent(TeamAgent):
    name = "audit_watcher"
    tier = 1
    icon = "📋"
    description = "Verifica integrità audit log + report mensili"
    model_pref = "haiku"
    schedule = "interval 6h"

    def __init__(self):
        super().__init__()
        # Start periodic check
        threading.Thread(target=self._loop, daemon=True,
                          name="audit_watcher_loop").start()

    def _loop(self):
        time.sleep(60)  # wait for boot to settle
        while True:
            if self.is_enabled():
                try:
                    self.safe_run({"op": "verify"})
                except Exception:
                    pass
            time.sleep(6 * 3600)

    def verify(self) -> dict:
        try:
            import audit_log
            r = audit_log.verify_integrity()
        except Exception as e:
            return {"ok": False, "error": str(e)}
        if not r.get("ok"):
            # Alert critico via bus + card
            self._emit("integrity_broken", {"broken_at": r.get("broken_at")})
            try:
                import bus
                bus.publish("card", {
                    "type": "audit_alert",
                    "data": {
                        "title": "⚠️ AUDIT LOG MANOMESSO",
                        "broken_at": r.get("broken_at"),
                        "total_before_break": r.get("total"),
                        "action": "Indaga subito. Possibile compromissione.",
                    },
                })
            except Exception:
                pass
        else:
            self._emit("integrity_ok", {"total": r.get("total")})
        return r

    def monthly_report(self) -> dict:
        """Genera report mensile e lo salva."""
        try:
            import audit_log
            recent = audit_log.tail(n=2000)
        except Exception:
            recent = []
        from collections import Counter
        evt_count = Counter(r.get("event", "?") for r in recent)
        # Conta veto, incidenti, vulnerabilità
        dpo_vetos = sum(1 for r in recent
                          if r.get("event") == "dpo.preflight"
                          and (r.get("data", {}) or {}).get("verdict") == "deny")
        ciso_incidents = sum(1 for r in recent
                               if r.get("event") == "ciso.incident")
        shield_hits = evt_count.get("shield.injection", 0)
        net_blocked = evt_count.get("net.blocked", 0)
        canary_leaks = evt_count.get("output_filter.canary_leaked", 0)
        cve_detected = evt_count.get("cve.detected", 0)
        # Carica registro Art. 30
        try:
            from . import dpo
            reg = dpo._load_register()
            treatments_count = len(reg.get("treatments", []))
        except Exception:
            treatments_count = 0
        # Incidenti aperti
        try:
            from . import ciso
            open_incidents = len(ciso.AGENT.list_incidents(status="open"))
        except Exception:
            open_incidents = 0
        report = {
            "month": time.strftime("%Y-%m"),
            "generated_ts": int(time.time()),
            "metrics": {
                "audit_records_analyzed": len(recent),
                "dpo_vetoes": dpo_vetos,
                "ciso_incidents_recent": ciso_incidents,
                "shield_injections_caught": shield_hits,
                "net_outbound_blocked": net_blocked,
                "canary_leaks": canary_leaks,
                "cve_detected": cve_detected,
                "treatments_registered": treatments_count,
                "incidents_open_now": open_incidents,
            },
        }
        # Save
        import json
        fname = REPORTS_DIR / f"report_{report['month']}.json"
        try:
            with open(fname, "w", encoding="utf-8") as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
        self._emit("monthly_report", {"file": str(fname.name)})
        return report

    def run(self, payload: dict) -> dict:
        op = payload.get("op", "verify")
        if op == "verify":
            return {"ok": True, "result": self.verify()}
        if op == "monthly_report":
            return {"ok": True, "report": self.monthly_report()}
        return {"ok": False, "error": f"op sconosciuta: {op}"}


AGENT = AuditWatcherAgent()
