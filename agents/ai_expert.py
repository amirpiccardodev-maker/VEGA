"""AI Expert Agent — Tier 2.

Meta-agente: consiglia su routing modello, budget thinking, scelta tool.
On-demand (no schedule).
"""
import json

from .team_base import TeamAgent


AI_EXPERT_PROMPT = """Sei l'AI EXPERT del team. Per una query ricevi:
- complessità stimata (lunghezza, contesto, multi-step)
- categoria (info / azione / planning / creative)

Consigli:
- modello: haiku (veloce/economico) | sonnet (default) | sonnet+thinking (ragionamento profondo)
- pattern: direct | tool_use | agent_fabric | agent_long_horizon | debate
- cost_estimate (cents)

Output SOLO JSON:
{
  "model": "haiku|sonnet|sonnet_thinking",
  "pattern": "direct|tool_use|agent_fabric|agent_long_horizon|debate",
  "rationale": "1 frase",
  "cost_estimate_cents": 0.0..50.0
}
"""


class AIExpertAgent(TeamAgent):
    name = "ai_expert"
    tier = 2
    icon = "🧠"
    description = "Consiglia model/pattern per query (cost vs quality)"
    model_pref = "haiku"

    def advise(self, query: str, hint: str = "") -> dict:
        prompt = (
            f"{AI_EXPERT_PROMPT}\n\n"
            f"Query: \"{query[:300]}\"\n"
            f"Hint: {hint}\n\n"
            f"JSON:"
        )
        result = self.call_haiku_json(prompt)
        if not result or "model" not in result:
            return {"model": "sonnet", "pattern": "direct",
                    "rationale": "fallback default", "cost_estimate_cents": 0.5}
        return result

    def run(self, payload: dict) -> dict:
        op = payload.get("op", "advise")
        if op == "advise":
            return {"ok": True, "advice": self.advise(
                payload.get("query", ""), payload.get("hint", ""))}
        return {"ok": False, "error": f"op sconosciuta: {op}"}


AGENT = AIExpertAgent()
