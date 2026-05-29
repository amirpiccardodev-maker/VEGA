"""Chief Steward — Tier 0 orchestrator.

Routing intelligente: dopo classify, delega davvero al target e raccoglie risultato.
Supporta catene multi-step per richieste complesse.
"""
from .team_base import TeamAgent


CLASSIFY_PROMPT = """Sei il CHIEF STEWARD di un team agentico AI personale.
Classifica la richiesta utente. Output JSON con 3 campi:

{
  "category": "SHORTCUT|SIMPLE|SENSITIVE|COMPLEX|INTEL_REQUEST|MARKETING|AGENT_MGMT|COMPLIANCE|FINANCE|HR|SAFETY|REPORT",
  "primary_agent": "<nome>",
  "supporting_agents": ["..."],
  "needs_compliance_review": true|false,
  "needs_security_review": true|false,
  "rationale": "1 frase italiana"
}

Mappa categoria → agente:
- SHORTCUT/SIMPLE → nessun agente specifico (brain default)
- SENSITIVE → primary: dpo (preflight)
- INTEL_REQUEST → primary: privacy_scout o cyber_scout o market_scout
- MARKETING → primary: marketing
- AGENT_MGMT → primary: architect
- COMPLIANCE → primary: dpo, supporting: audit_watcher
- FINANCE → primary: admin
- HR → primary: hr, supporting: rspp, training_manager
- SAFETY → primary: rspp, supporting: safety_scout
- REPORT → primary: report_builder, supporting: client_onboarding
- COMPLEX → primary: agent multi-step (chain)
"""


# Categorie con routing predefinito
CATEGORY_ROUTING = {
    "SHORTCUT":      {"primary": None, "supporting": []},
    "SIMPLE":        {"primary": None, "supporting": []},
    "SENSITIVE":     {"primary": "dpo", "supporting": []},
    "INTEL_REQUEST": {"primary": "privacy_scout", "supporting": []},  # default
    "MARKETING":     {"primary": "marketing", "supporting": ["market_scout"]},
    "AGENT_MGMT":    {"primary": "architect", "supporting": []},
    "COMPLIANCE":    {"primary": "dpo", "supporting": ["audit_watcher"]},
    "FINANCE":       {"primary": "admin", "supporting": []},
    "HR":            {"primary": "hr", "supporting": ["rspp", "training_manager"]},
    "SAFETY":        {"primary": "rspp", "supporting": ["safety_scout"]},
    "REPORT":        {"primary": "report_builder", "supporting": ["client_onboarding"]},
    "COMPLEX":       {"primary": None, "supporting": []},  # uses chain
}


class StewardAgent(TeamAgent):
    name = "steward"
    tier = 0
    icon = "🧭"
    description = "Direttore generale: classifica richiesta, delega, sintetizza"
    model_pref = "haiku"
    subscribes = []

    def _declare_actions(self):
        return [
            {"name": "classify", "description": "Classifica richiesta utente",
             "args_schema": {"user_message": "str"}},
            {"name": "orchestrate", "description": "Classifica + delega + raccoglie",
             "args_schema": {"user_message": "str"}},
            {"name": "delegate_to", "description": "Delega esplicita a un agente",
             "args_schema": {"target": "str", "payload": "dict"}},
            {"name": "subordinates_status", "description": "Stato tutti i subordinati",
             "args_schema": {}},
            {"name": "team_overview", "description": "Overview live del team",
             "args_schema": {}},
        ]

    def classify(self, user_msg: str) -> dict:
        prompt = f"{CLASSIFY_PROMPT}\n\nRichiesta: \"{user_msg}\"\n\nJSON:"
        result = self.call_haiku_json(prompt)
        if not result or "category" not in result:
            return {"category": "SIMPLE", "primary_agent": None,
                     "supporting_agents": [], "needs_compliance_review": False,
                     "needs_security_review": False,
                     "rationale": "fallback (LLM unavailable)"}
        # Normalize: fill in primary_agent from CATEGORY_ROUTING if missing
        cat = result.get("category", "SIMPLE")
        routing = CATEGORY_ROUTING.get(cat, {"primary": None, "supporting": []})
        if not result.get("primary_agent"):
            result["primary_agent"] = routing["primary"]
        if not result.get("supporting_agents"):
            result["supporting_agents"] = routing["supporting"]
        return result

    def orchestrate(self, user_msg: str, execute: bool = True) -> dict:
        """Full orchestration: classify → delegate → collect → synthesize."""
        decision = self.classify(user_msg)
        self._emit("classify", {
            "category": decision.get("category"),
            "primary": decision.get("primary_agent"),
            "supporting": decision.get("supporting_agents"),
            "rationale": decision.get("rationale", "")[:200],
        })

        if not execute:
            return {"ok": True, "decision": decision, "executed": False}

        primary = decision.get("primary_agent")
        if not primary:
            return {"ok": True, "decision": decision, "executed": False,
                    "note": "no specific agent, falling back to brain default"}

        # Compliance preflight (se richiesto e diverso da DPO stesso)
        compliance_result = None
        if decision.get("needs_compliance_review") and primary != "dpo":
            self._emit("compliance_preflight", {"target": primary})
            d_res = self.delegate("dpo", {"op": "preflight",
                                            "tool": primary,
                                            "args": {"context": user_msg}})
            verdict = (d_res.get("result") or {}).get("verdict")
            if verdict == "deny":
                return {"ok": False, "decision": decision,
                        "blocked_by_dpo": True,
                        "reason": (d_res.get("result") or {}).get("rationale")}
            compliance_result = d_res.get("result")

        # Security preflight (CISO)
        security_result = None
        if decision.get("needs_security_review") and primary != "ciso":
            self._emit("security_preflight", {"target": primary})
            # CISO classify dell'evento. Non blocca by default.
            try:
                s_res = self.delegate("ciso", {"op": "classify",
                                                  "event_type": "user_request",
                                                  "data": {"action": primary,
                                                            "msg": user_msg[:200]}})
                security_result = s_res.get("result")
            except Exception:
                pass

        # Delega al primary
        self._emit("delegating", {"target": primary})
        primary_res = self.delegate(primary, {"op": "default",
                                                "user_message": user_msg,
                                                "context": user_msg})

        # Supporting agents in parallel (fire-and-collect)
        supporting_results = {}
        for sup in decision.get("supporting_agents", []):
            try:
                r = self.delegate(sup, {"op": "default",
                                          "user_message": user_msg})
                supporting_results[sup] = r.get("result")
            except Exception as e:
                supporting_results[sup] = {"error": str(e)}

        # Audit
        try:
            import audit_log
            audit_log.log("steward.orchestrate", {
                "category": decision.get("category"),
                "primary": primary,
                "supporting": list(supporting_results.keys()),
                "ok": True,
            })
        except Exception:
            pass

        return {
            "ok": True,
            "decision": decision,
            "executed": True,
            "primary_result": primary_res.get("result"),
            "supporting_results": supporting_results,
            "compliance_preflight": compliance_result,
            "security_preflight": security_result,
        }

    def subordinates_status(self) -> dict:
        """Aggregated status of all subordinates."""
        try:
            from . import team_registry
        except Exception:
            return {"ok": False, "error": "registry unavailable"}
        out = {"enabled": [], "disabled": [], "by_tier": {}}
        for name in self.subordinates():
            ag = team_registry.get(name)
            if not ag:
                continue
            s = ag.status()
            out["enabled" if s["enabled"] else "disabled"].append(name)
            tier = s.get("tier", 0)
            out["by_tier"].setdefault(tier, []).append(name)
        out["total"] = len(out["enabled"]) + len(out["disabled"])
        return out

    def team_overview(self) -> dict:
        """Live overview: status + recent activity per agente."""
        try:
            from . import team_registry
            import time as _time
        except Exception:
            return {}
        now = _time.time()
        agents_data = []
        for ag in team_registry.all_agents():
            s = ag.status()
            agents_data.append({
                "name": s["name"], "tier": s["tier"], "icon": s["icon"],
                "enabled": s["enabled"],
                "tasks": s["task_count"],
                "last_active_sec": int(now - s["last_activity_ts"])
                                   if s["last_activity_ts"] else None,
            })
        agents_data.sort(key=lambda x: (x["tier"], -x["tasks"]))
        return {"total": len(agents_data),
                "active_last_5min": sum(1 for a in agents_data
                                          if a["last_active_sec"] is not None
                                          and a["last_active_sec"] < 300),
                "agents": agents_data}

    def run(self, payload: dict) -> dict:
        payload = payload or {}
        op = payload.get("op", "orchestrate")

        if op in ("orchestrate", "default"):
            user_msg = payload.get("user_message", "")
            if not user_msg:
                return {"ok": False, "error": "user_message vuoto"}
            return self.orchestrate(user_msg,
                                     execute=payload.get("execute", True))

        if op == "classify":
            return {"ok": True, "decision": self.classify(
                payload.get("user_message", ""))}

        if op == "delegate_to":
            return self.delegate(payload.get("target", ""),
                                  payload.get("payload", {}))

        if op == "subordinates_status":
            return {"ok": True, "status": self.subordinates_status()}

        if op == "team_overview":
            return {"ok": True, "overview": self.team_overview()}

        return {"ok": False, "error": f"op sconosciuta: {op}",
                "available_ops": ["orchestrate", "classify", "delegate_to",
                                    "subordinates_status", "team_overview"]}


AGENT = StewardAgent()
