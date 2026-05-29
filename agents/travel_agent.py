"""TravelAgent: itinerari, meteo, foto luoghi."""
from .base import BaseAgent


class TravelAgent(BaseAgent):
    NAME = "travel"
    SYSTEM = """Sei un agente specialista in viaggi e luoghi.
Per ogni richiesta sui viaggi: cerca info, mostra foto reali, controlla meteo, sintetizza."""
    TOOLS = ["web_search", "web_images", "get_weather", "wikipedia", "read_webpage"]

    def run(self, action: str, shared_state: dict) -> str:
        import tools as tool_registry
        action_low = action.lower()

        if "meteo" in action_low or "tempo" in action_low:
            # Extract city
            city = action.split("a ", 1)[-1].split(" ", 1)[0] if " a " in action else ""
            return tool_registry.execute("get_weather", {"location": city, "days": 3})
        if "foto" in action_low or "immagini" in action_low or "vedere" in action_low:
            return tool_registry.execute("web_images", {"query": action[-100:]})
        if "cerca" in action_low or "trova" in action_low or "info" in action_low:
            return tool_registry.execute("web_search", {"query": action[-150:]})

        return super().run(action, shared_state)
