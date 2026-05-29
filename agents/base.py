"""Base class per sub-agents. Ogni agente e' un mini-brain con tool subset."""
import json

import fast_brain


class BaseAgent:
    """Sub-agent base. Override TOOLS, SYSTEM, and optionally run()."""
    NAME = "base"
    SYSTEM = "Sei un assistente specializzato. Rispondi in italiano."
    TOOLS = []  # subset di tool names; vuoto = usa tutto cio' che serve

    def run(self, action: str, shared_state: dict) -> str:
        """Execute the requested action. Returns text output."""
        ctx = ""
        if shared_state:
            relevant = {k: v for k, v in shared_state.items() if v}
            if relevant:
                ctx = "\n\nStato condiviso dai passi precedenti:\n" + json.dumps(relevant, ensure_ascii=False)[:1000]

        # Use Haiku for cheap execution of well-defined actions
        prompt = f"{self.SYSTEM}\n\nAzione richiesta: {action}{ctx}\n\nRisposta:"
        return fast_brain.fast_call(prompt, max_tokens=400)
