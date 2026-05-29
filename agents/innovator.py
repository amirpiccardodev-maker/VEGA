"""Innovator Agent — Tier 2.

Weekly: analizza pattern d'uso e propone 1-3 nuove feature/automazioni.
"""
import json
import threading
import time

from .team_base import TeamAgent


INNOVATOR_PROMPT = """Sei l'INNOVATOR del team agentico di Vega (assistente AI personale).
Analizzi pattern d'uso recenti e proponi 1-3 nuove feature/automazioni CONCRETE.

Vincoli:
- Ogni proposta deve avere: rationale, complexity (S/M/L), impact_estimate (low/med/high),
  dependencies (cosa serve installare), compliance_risk (low/med/high con motivo).
- Privacy: rispetta GDPR (minimizzazione, base giuridica). Se proposta tocca dati personali
  di terzi → compliance_risk=high con DPO review obbligatoria.
- No proposte già implementate.

Output SOLO JSON:
{
  "proposals": [
    {
      "title": "...",
      "rationale": "...",
      "complexity": "S|M|L",
      "impact": "low|medium|high",
      "dependencies": ["..."],
      "compliance_risk": "low|medium|high",
      "compliance_notes": "..."
    },
    ...
  ]
}
"""


class InnovatorAgent(TeamAgent):
    name = "innovator"
    tier = 2
    icon = "💡"
    description = "Weekly: analizza pattern e propone feature/automazioni"
    model_pref = "haiku"
    schedule = "weekly Sunday 18:00"

    def __init__(self):
        super().__init__()
        threading.Thread(target=self._loop, daemon=True,
                          name="innovator_loop").start()

    def _loop(self):
        # First analysis 5 min after boot, then every 7 days
        time.sleep(300)
        while True:
            if self.is_enabled():
                try:
                    self.safe_run({"op": "weekly_proposals"})
                except Exception:
                    pass
            time.sleep(7 * 24 * 3600)

    def _gather_context(self) -> str:
        """Riassume usage patterns + bus events recenti."""
        ctx_parts = []
        try:
            import memory_graph as mg
            stats = mg.stats()
            ctx_parts.append(f"Memory graph stats: {stats}")
        except Exception:
            pass
        try:
            import bus
            recent = bus.history()[-100:]
            topics = {}
            for e in recent:
                t = e.get("topic", "?")
                topics[t] = topics.get(t, 0) + 1
            ctx_parts.append(f"Top topics last 100 events: {dict(sorted(topics.items(), key=lambda x: -x[1])[:10])}")
        except Exception:
            pass
        try:
            import memory_graph as mg
            patterns = mg.list_by_kind("behavioral", limit=10) if hasattr(mg, "list_by_kind") else []
            if patterns:
                ctx_parts.append("Pattern comportamentali rilevati:\n" +
                                 "\n".join(f"- {p.get('content', '')[:120]}" for p in patterns[:5]))
        except Exception:
            pass
        return "\n\n".join(ctx_parts)

    def weekly_proposals(self) -> dict:
        ctx = self._gather_context()
        prompt = (
            f"{INNOVATOR_PROMPT}\n\n"
            f"CONTESTO USO RECENTE:\n{ctx[:2000]}\n\n"
            f"JSON:"
        )
        result = self.call_haiku_json(prompt)
        proposals = (result or {}).get("proposals", [])
        # Salva ogni proposta in memory_graph + emit card
        for p in proposals[:3]:
            self.remember(
                "instruction",
                f"Proposta Innovator: {p.get('title')}. "
                f"Rationale: {p.get('rationale', '')}. "
                f"Complessità: {p.get('complexity')}. Impatto: {p.get('impact')}. "
                f"Privacy risk: {p.get('compliance_risk')}.",
                importance=0.65,
                tags=["innovation", f"impact:{p.get('impact', 'medium')}"],
            )
        if proposals:
            try:
                import bus
                bus.publish("card", {
                    "type": "innovation_proposal",
                    "data": {
                        "title": f"💡 {len(proposals)} proposte settimanali",
                        "proposals": proposals[:3],
                    },
                })
            except Exception:
                pass
        self._emit("weekly", {"count": len(proposals)})
        return {"ok": True, "proposals": proposals}

    def run(self, payload: dict) -> dict:
        op = payload.get("op", "weekly_proposals")
        if op == "weekly_proposals":
            return self.weekly_proposals()
        return {"ok": False, "error": f"op sconosciuta: {op}"}


AGENT = InnovatorAgent()
