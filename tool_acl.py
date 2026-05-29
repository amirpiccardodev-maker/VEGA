"""Tool access control list — sensitive tools require user authorization.

Niente "Claude può fare email/file delete senza che l'utente confermi".

Politiche per tier:
  - HIGH (block-by-default, require PIN session):
      shutdown_pc, lock_pc, send_email, send_draft, file_delete,
      execute_code, run_powershell, format
  - MEDIUM (require explicit consent toggle in prefs, dry_run flag):
      delete_memory, web_email_send, browse_url (con action=click/fill)
  - LOW (no restriction):
      everything else (read-only, info gathering)

API:
    can_execute(tool_name, args) -> (bool, reason)
    register_consent(tool_name, ttl_sec)
    revoke_consent(tool_name)
"""
import time
import threading


HIGH_RISK = {
    "shutdown_pc", "lock_pc",
    "send_email", "send_draft",
    "file_delete", "delete_file",
    "execute_code", "run_powershell", "run_command",
    "format_drive",
}

MEDIUM_RISK = {
    "delete_memory", "clear_memory",
    "compose_draft",  # creates a draft (no send) -> medium
    "browse_url",     # ok per read, ma click/fill può fare azioni
}

_lock = threading.Lock()
# tool_name -> expiry_ts
_consents = {}
CONSENT_TTL_DEFAULT = 300  # 5 min


def _is_action_unsafe_browse(args: dict) -> bool:
    """browse_url is fine for read; risky if action=click/fill on form."""
    a = (args or {}).get("action", "extract")
    return a in ("click", "fill")


def can_execute(tool_name: str, args: dict = None) -> tuple:
    """Returns (allowed: bool, reason: str)."""
    args = args or {}
    # Always allow low risk
    if tool_name not in HIGH_RISK and tool_name not in MEDIUM_RISK:
        return True, "low_risk"

    # browse_url with read-only action is low risk
    if tool_name == "browse_url" and not _is_action_unsafe_browse(args):
        return True, "browse_read"

    # HIGH: require PIN session
    if tool_name in HIGH_RISK:
        try:
            import security
            if security.has_valid_pin_session():
                return True, "pin_session_valid"
            if not security.pin_is_set():
                # No PIN set => log warning, allow but note it
                import bus
                bus.publish("acl.warning", {
                    "tool": tool_name,
                    "reason": "high_risk tool executed without PIN set"
                })
                return True, "no_pin_set"
        except Exception:
            return True, "security_module_unavailable"

        # PIN set but no session: check explicit consent
        with _lock:
            exp = _consents.get(tool_name, 0)
            if time.time() < exp:
                return True, "explicit_consent_valid"
        return False, "high_risk_no_pin_session"

    # MEDIUM: explicit consent OR pref opt-in
    if tool_name in MEDIUM_RISK:
        try:
            import memory
            if memory.get_preferences().get(f"allow_{tool_name}", False):
                return True, "preference_allowed"
        except Exception:
            pass
        with _lock:
            exp = _consents.get(tool_name, 0)
            if time.time() < exp:
                return True, "explicit_consent_valid"
        return False, "medium_risk_consent_needed"

    return True, "unknown_default_allow"


def register_consent(tool_name: str, ttl_sec: int = None) -> bool:
    """Grant a one-shot or time-limited consent for a sensitive tool."""
    ttl = ttl_sec or CONSENT_TTL_DEFAULT
    with _lock:
        _consents[tool_name] = time.time() + ttl
    import bus
    bus.publish("acl.consent_granted", {"tool": tool_name, "ttl_sec": ttl})
    return True


def revoke_consent(tool_name: str) -> bool:
    with _lock:
        if tool_name in _consents:
            del _consents[tool_name]
            return True
    return False


def list_consents() -> dict:
    now = time.time()
    with _lock:
        return {k: int(v - now) for k, v in _consents.items() if v > now}


def status() -> dict:
    return {
        "high_risk_tools": sorted(HIGH_RISK),
        "medium_risk_tools": sorted(MEDIUM_RISK),
        "active_consents": list_consents(),
    }
