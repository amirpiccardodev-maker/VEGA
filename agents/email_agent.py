"""EmailAgent: specialista email Gmail."""
from .base import BaseAgent


class EmailAgent(BaseAgent):
    NAME = "email"
    SYSTEM = """Sei un agente specialista per la gestione delle email Gmail di Amir.
Hai accesso ai tool: list_emails, search_emails, read_email, summarize_inbox, send_email.

Quando esegui un'azione:
1. Identifica il tool giusto
2. Eseguilo via il tool registry
3. Restituisci il risultato sintetico in italiano"""
    TOOLS = ["list_emails", "search_emails", "read_email", "summarize_inbox", "send_email"]

    def run(self, action: str, shared_state: dict) -> str:
        # Try to directly execute relevant tool based on action keywords
        action_low = action.lower()
        import tools as tool_registry

        if "elenc" in action_low or "lista" in action_low or "controll" in action_low:
            return tool_registry.execute("list_emails", {"limit": 10})
        if "riassum" in action_low or "summary" in action_low:
            return tool_registry.execute("summarize_inbox", {"limit": 15})
        if "cerc" in action_low or "trov" in action_low:
            # Extract query heuristically
            query = action.split("cerca", 1)[-1].split("trova", 1)[-1].strip()[:80]
            return tool_registry.execute("search_emails", {"query": query})

        # Fallback to base (LLM)
        return super().run(action, shared_state)
