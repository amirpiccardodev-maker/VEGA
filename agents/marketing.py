"""Marketing Agent — Tier 2.

Weekly brief: insight, content ideas, action concrete.
Namespace: 'business' (NON Mem0 personal facts senza consenso esplicito).
"""
import threading
import time

from .team_base import TeamAgent


MARKETING_PROMPT = """Sei il MARKETING agent del team Vega. Lavori per l'utente Amir
(progetto cliente: Libreria Islamica / Hamza Roberto Piccardo).

Output settimanale (max 6 frasi):
- 1 insight (trend o segnale rilevante)
- 3 idee contenuto concrete (titolo + angolo)
- 1 azione operativa (cosa fare lunedì)

Regole privacy: NON usare dati personali raccolti via assistente (Mem0). Solo
dati business pubblici o forniti esplicitamente come tag 'business'.

Output JSON:
{
  "insight": "...",
  "content_ideas": [{"title": "...", "angle": "..."}, ...],
  "action": "..."
}
"""


class MarketingAgent(TeamAgent):
    name = "marketing"
    tier = 2
    icon = "📢"
    description = "Brand strategist: insight, content, azioni weekly"
    model_pref = "haiku"
    schedule = "weekly Monday 09:00"

    def __init__(self):
        super().__init__()
        threading.Thread(target=self._loop, daemon=True,
                          name="marketing_loop").start()

    def _loop(self):
        time.sleep(600)
        while True:
            if self.is_enabled():
                try:
                    self.safe_run({"op": "weekly_brief"})
                except Exception:
                    pass
            time.sleep(7 * 24 * 3600)

    def weekly_brief(self) -> dict:
        # Gather business-tagged context only (privacy boundary)
        ctx_parts = []
        try:
            import memory_graph as mg
            facts = mg.search("business marketing posizionamento brand", top_k=5)
            if facts:
                ctx_parts.append("Memoria business:\n" +
                                 "\n".join(f"- {f.get('content', '')[:150]}" for f in facts[:3]))
        except Exception:
            pass
        try:
            import news_graph
            news = news_graph.search_recent("marketing brand editoria business", top_k=5)
            if news:
                ctx_parts.append("News recenti:\n" +
                                 "\n".join(f"- {n.get('content', '')[:150]}" for n in news[:3]))
        except Exception:
            pass
        ctx = "\n\n".join(ctx_parts)
        prompt = f"{MARKETING_PROMPT}\n\nCONTESTO:\n{ctx[:1500]}\n\nJSON:"
        result = self.call_haiku_json(prompt)
        if not result:
            return {"ok": False, "error": "LLM unavailable"}
        # Card UI
        try:
            import bus
            bus.publish("card", {
                "type": "marketing_brief",
                "data": {
                    "title": "📢 Brief Marketing settimanale",
                    "insight": result.get("insight", ""),
                    "content_ideas": result.get("content_ideas", [])[:3],
                    "action": result.get("action", ""),
                },
            })
        except Exception:
            pass
        self.remember("note",
                       f"Brief marketing {time.strftime('%Y-%m-%d')}: " +
                       result.get("insight", "")[:200],
                       importance=0.5, tags=["marketing", "business"])
        self._emit("weekly_brief", {})
        return {"ok": True, "brief": result}

    def run(self, payload: dict) -> dict:
        op = payload.get("op", "weekly_brief")
        if op == "weekly_brief":
            return self.weekly_brief()
        return {"ok": False, "error": f"op sconosciuta: {op}"}


AGENT = MarketingAgent()
