"""Monitora Ispettorato Lavoro, INAIL, accordi Stato-Regioni formazione."""
import json
import time
from .team_base import TeamAgent


class SafetyScoutAgent(TeamAgent):
    name = "safety_scout"
    tier = 3
    icon = "🦺"
    description = "Monitora Ispettorato Lavoro, INAIL, accordi Stato-Regioni formazione."
    model_pref = "haiku"
    schedule = 'daily 07:45'
    subscribes = []

    def run(self, payload):
        if not self.is_enabled():
            return {"ok": False, "error": "agent disabled"}

        action = payload.get("action", "monitor")

        if action == "monitor":
            ctx = self.search_memory("normative sicurezza lavoro INAIL formazione", top_k=5)
            prompt = f"Analizza queste fonti su sicurezza lavoro e identifica: 1) modifiche D.Lgs 81/2008 2) aggiornamenti formazione obbligatoria 3) accordi Stato-Regioni. Sorgenti: {' | '.join(c.get('content', '')[:150] for c in ctx)}"
            analysis = self.call_haiku(prompt)
            self.remember("safety_alert", analysis, importance=0.8)
            self._emit("safety_change", {"analysis": analysis[:300]})
            return {"ok": True, "action": "monitor", "findings": analysis}

        elif action == "alert_rspp":
            findings = payload.get("findings", "")
            prompt = f"Valuta impact per RSPP (Responsabile SPP): {findings}. Rischio alto? Necessario assessment?"
            assessment = self.call_haiku(prompt)
            self.remember("rspp_task", assessment, importance=0.9)
            self._emit("rspp_notification", {"assessment": assessment})
            return {"ok": True, "action": "alert_rspp", "assessment": assessment}

        return {"ok": False, "error": "action non riconosciuta"}


AGENT = SafetyScoutAgent()
