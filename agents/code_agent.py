"""CodeAgent: dati, calcoli, analisi spreadsheet."""
from .base import BaseAgent


class CodeAgent(BaseAgent):
    NAME = "code"
    SYSTEM = """Sei un agente specialista in calcoli, dati e analisi.
Hai accesso a code_exec (Python sandbox), analyze_spreadsheet, make_chart, calculate."""
    TOOLS = ["code_exec", "calculate", "analyze_spreadsheet", "make_chart"]

    def run(self, action: str, shared_state: dict) -> str:
        import tools as tool_registry
        action_low = action.lower()

        # Math expression detection: heuristic
        if any(op in action for op in ["+", "-", "*", "/", "^", "="]) and any(c.isdigit() for c in action):
            return tool_registry.execute("calculate", {"expression": action[-200:]})

        if ".xlsx" in action_low or ".csv" in action_low:
            # Extract path heuristically
            import re
            m = re.search(r"[A-Z]:\\[^\s\"']+\.(xlsx|csv)", action, re.I)
            if m:
                return tool_registry.execute("analyze_spreadsheet", {"path": m.group(0)})

        return super().run(action, shared_state)
