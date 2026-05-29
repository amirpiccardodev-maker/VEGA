"""Base class per Monitor Agents — agenti che osservano un subsystem specifico.

Differenza rispetto a TeamAgent normale:
  - Tier 4 (monitoring, sotto le operations ma sopra worker)
  - Espongono `status()` (snapshot rapido) e `diagnose()` (analisi completa)
  - Hanno `actions[]` (lista comandi disponibili tipo "purge cache", "restart subsystem")
  - L'utente li chatta via Conversation Tab per fare domande specifiche
"""
from .team_base import TeamAgent


class MonitorAgent(TeamAgent):
    """Subsystem monitor. Override:
      - subsystem_name (str)
      - actions (list of {name, description, fn_name}) for available ops
      - _snapshot() -> dict  (status veloce)
      - _diagnose() -> dict  (analisi approfondita)
      - _do_action(name, args) -> dict  (esegue comandi)
    """
    tier = 4
    subsystem_name = "generic"
    actions = []

    def _snapshot(self) -> dict:
        return {"status": "unknown"}

    def _diagnose(self) -> dict:
        return {"snapshot": self._snapshot(), "details": {}}

    def _do_action(self, name: str, args: dict = None) -> dict:
        return {"ok": False, "error": f"action sconosciuta: {name}"}

    def run(self, payload: dict) -> dict:
        op = (payload or {}).get("op", "status")
        if op == "status":
            return {"ok": True, "subsystem": self.subsystem_name,
                    "status": self._snapshot()}
        if op == "diagnose":
            return {"ok": True, "subsystem": self.subsystem_name,
                    "report": self._diagnose()}
        if op == "actions":
            return {"ok": True, "actions": self.actions}
        if op == "do":
            return self._do_action(payload.get("action", ""),
                                    payload.get("args", {}))
        return {"ok": False, "error": f"op sconosciuta: {op}"}
