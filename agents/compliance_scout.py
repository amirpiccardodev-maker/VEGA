"""Monitora Agenzia Entrate, INPS, INAIL, MEF per nuove norme fiscali/contributi."""
import json
import time
from .team_base import TeamAgent


class ComplianceScoutAgent(TeamAgent):
    name = "compliance_scout"
    tier = 3
    icon = "🏛"
    description = "Monitora Agenzia Entrate, INPS, INAIL, MEF per nuove norme fiscali/contributi."
    model_pref = "haiku"
    schedule = 'daily 07:30'
    subscribes = []

    def run(self, payload):
        if not self.is_enabled():
            return {"ok": False, "error": "agent disabled"}

        action = payload.get("action", "scan")

        if action == "scan":
            agencies = ["agenziaentrate.gov.it", "inps.it", "inail.it", "mef.gov.it"]
            prompt = f"Analizza le ultime novità fiscali e contributive da questi enti: {', '.join(agencies)}. Identifica solo norme rilevanti per studi professionali."
            findings = self.call_haiku(prompt)
            self.remember("compliance_scan", findings, importance=0.8)
            self._emit("scan_complete", {"agencies": len(agencies), "findings_len": len(findings)})
            return {"ok": True, "findings": findings}

        elif action == "assess":
            norm = payload.get("norm", "")
            if not norm:
                return {"ok": False, "error": "norm required"}
            ctx = self.search_memory("compliance norme", top_k=3)
            prompt = f"Norma: {norm}. Contesto precedente: {' | '.join(c.get('content','')[:100] for c in ctx)}. Indica: 1) Impatto operativo, 2) Se richiede azione immediata (sì/no), 3) Scadenze."
            analysis = self.call_haiku(prompt)
            self.remember("compliance_assessment", norm + " -> " + analysis[:150], importance=0.7)
            self._emit("assessment_done", {"norm_len": len(norm)})
            return {"ok": True, "assessment": analysis}

        return {"ok": False, "error": "action non riconosciuta"}


AGENT = ComplianceScoutAgent()
