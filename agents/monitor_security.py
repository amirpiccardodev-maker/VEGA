"""Security Monitor — auth, ACL, prompt shield, output filter, vault, audit, canaries."""
from .monitor_base import MonitorAgent


class SecurityMonitorAgent(MonitorAgent):
    name = "security_monitor"
    subsystem_name = "security"
    icon = "🛡"
    description = "Monitor sicurezza: auth, ACL, shield, vault, audit chain integrity."
    model_pref = "haiku"
    actions = [
        {"name": "rotate_token", "description": "Ruota token API Bearer"},
        {"name": "verify_audit", "description": "Verifica integrità hash chain audit"},
        {"name": "lockout_status", "description": "Lista IP in lockout PIN"},
        {"name": "list_active_consents", "description": "Tool consent attivi"},
    ]

    def _snapshot(self):
        out = {}
        try:
            import security as _sec
            out["security"] = _sec.get_security_status()
        except Exception:
            pass
        try:
            import auth
            out["auth"] = {"token_set": bool(auth.get_token())}
        except Exception:
            pass
        try:
            import tool_acl
            out["acl"] = tool_acl.status()
        except Exception:
            pass
        try:
            import rate_limit
            out["rate_limit"] = rate_limit.status()
        except Exception:
            pass
        try:
            import vault
            out["vault"] = vault.status()
        except Exception:
            pass
        try:
            import audit_log
            out["audit"] = audit_log.verify_integrity()
        except Exception:
            pass
        return out

    def _diagnose(self):
        snap = self._snapshot()
        snap["alerts"] = []
        if not snap.get("security", {}).get("pin_set"):
            snap["alerts"].append("⚠ PIN non impostato: accesso da LAN non autenticato")
        if snap.get("vault", {}).get("plaintext_exists"):
            snap["alerts"].append("⚠ .env in chiaro: considera cifratura via vault")
        audit = snap.get("audit", {})
        if not audit.get("ok"):
            snap["alerts"].append(f"🚨 AUDIT CHAIN BROKEN at {audit.get('broken_at')}")
        # Recent events count
        try:
            import audit_log
            recent = audit_log.tail(n=500)
            shield_hits = sum(1 for r in recent if r.get("event") == "shield.injection")
            veto = sum(1 for r in recent if r.get("event") == "dpo.veto")
            snap["recent_500"] = {
                "shield_injections": shield_hits,
                "dpo_vetoes": veto,
            }
        except Exception:
            pass
        return snap

    def _do_action(self, name, args=None):
        if name == "rotate_token":
            try:
                import auth
                t = auth.rotate_token()
                return {"ok": True, "new_token_preview": t[:12] + "..."}
            except Exception as e:
                return {"ok": False, "error": str(e)}
        if name == "verify_audit":
            try:
                import audit_log
                return {"ok": True, "report": audit_log.verify_integrity()}
            except Exception as e:
                return {"ok": False, "error": str(e)}
        if name == "lockout_status":
            try:
                import rate_limit
                return {"ok": True, "status": rate_limit.status()}
            except Exception as e:
                return {"ok": False, "error": str(e)}
        if name == "list_active_consents":
            try:
                import tool_acl
                return {"ok": True, "consents": tool_acl.list_consents()}
            except Exception as e:
                return {"ok": False, "error": str(e)}
        return super()._do_action(name, args)


AGENT = SecurityMonitorAgent()
