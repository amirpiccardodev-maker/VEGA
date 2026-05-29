"""DesktopAgent: controllo app, finestre, file, sistema."""
from .base import BaseAgent


class DesktopAgent(BaseAgent):
    NAME = "desktop"
    SYSTEM = """Sei un agente per il controllo del desktop Windows.
Hai accesso a: open_application, list_windows, focus_window, close_window, minimize_all,
set_volume, set_brightness, lock_pc, find_files, take_screenshot, analyze_screen."""
    TOOLS = ["open_application", "list_windows", "focus_window", "close_window",
             "minimize_all", "set_volume", "set_brightness", "lock_pc",
             "find_files", "take_screenshot", "analyze_screen", "system_info"]

    def run(self, action: str, shared_state: dict) -> str:
        import tools as tool_registry
        action_low = action.lower()

        if "apri" in action_low:
            # Extract app name
            target = action.split("apri", 1)[-1].strip().split(" ")[0]
            return tool_registry.execute("open_application", {"target": target})
        if "chiudi" in action_low:
            target = action.split("chiudi", 1)[-1].strip().split(" ")[0]
            return tool_registry.execute("close_window", {"title": target})
        if "minimizza" in action_low or "mostra desktop" in action_low:
            return tool_registry.execute("minimize_all", {})
        if "volume" in action_low:
            import re
            m = re.search(r"\b(\d{1,3})\b", action)
            if m:
                return tool_registry.execute("set_volume", {"percent": int(m.group(1))})
        if "screenshot" in action_low or "cattura" in action_low:
            return tool_registry.execute("take_screenshot", {})
        if "schermo" in action_low or "vedi" in action_low or "cosa c" in action_low:
            return tool_registry.execute("analyze_screen", {})

        return super().run(action, shared_state)
