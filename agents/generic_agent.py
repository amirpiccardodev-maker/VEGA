"""GenericAgent: fallback per azioni generiche."""
from .base import BaseAgent


class GenericAgent(BaseAgent):
    NAME = "generic"
    SYSTEM = """Sei un assistente generale. Aiuti con ricerche, scrittura, ragionamento.
Hai accesso a tutti i tool quando serve. Rispondi in italiano, sii conciso."""
    TOOLS = []  # tutti

    def run(self, action: str, shared_state: dict) -> str:
        # Use Brain (Sonnet) only for actions that LLM truly needs to handle
        # For simpler actions, fall to Haiku via base
        if any(k in action.lower() for k in ["scrivi", "componi", "elabora", "analizza approfondit"]):
            from brain import Brain
            b = Brain()
            ctx_intro = ""
            if shared_state:
                ctx_intro = "Contesto: " + str(shared_state)[:500] + "\n\n"
            return b.ask(ctx_intro + action)
        return super().run(action, shared_state)
