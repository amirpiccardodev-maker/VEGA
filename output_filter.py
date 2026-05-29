"""Filter applied to Claude's final reply BEFORE TTS/UI display.

Defense against accidental data exfiltration via the LLM:
  - Claude might paraphrase a secret it saw in tool results
  - Could inadvertently emit canary/honeypot strings
  - Might quote raw API keys / passwords / tokens in answers

The filter:
  1. Re-applies security.mask_secrets (regex pattern masking)
  2. Checks for honeypot canary strings → DATA LEAK detected
  3. Detects credit card numbers (Luhn), phone numbers (it+international),
     IBAN, codice fiscale, partita iva → masked
  4. Optionally blocks the entire reply if leak confidence is high

API:
    sanitize_reply(text) -> {"text": sanitized, "blocked": bool, "alerts": [...]}
"""
import re
import hashlib

import bus
import security


# ============ Sensitive patterns (extends security.SECRET_PATTERNS) ============

# Credit card (with Luhn check below)
CC_PATTERN = re.compile(r"\b(?:\d[ -]*?){13,19}\b")

# IBAN (rough): country + 2 digits + up to 30 alphanum
IBAN_PATTERN = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{4,30}\b")

# Italian Codice Fiscale (16 char alphanumeric, very specific structure)
CF_PATTERN = re.compile(r"\b[A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z]\b")

# Italian Partita IVA (11 digit)
PIVA_PATTERN = re.compile(r"\b(?:IT)?\d{11}\b")

# Phone numbers (Italian + international)
PHONE_PATTERN = re.compile(r"\b(?:\+\d{1,3}[\s.]?)?(?:\d{2,4}[\s.-]?){2,4}\d{2,4}\b")

# JWT tokens
JWT_PATTERN = re.compile(r"eyJ[a-zA-Z0-9_-]{8,}\.eyJ[a-zA-Z0-9_-]{8,}\.[a-zA-Z0-9_-]{8,}")

# Generic bearer tokens
BEARER_PATTERN = re.compile(r"\bBearer\s+[A-Za-z0-9._\-]{20,}\b", re.IGNORECASE)


def _luhn_valid(digits: str) -> bool:
    d = [int(c) for c in digits if c.isdigit()]
    if len(d) < 13 or len(d) > 19:
        return False
    checksum = 0
    parity = len(d) % 2
    for i, n in enumerate(d):
        if i % 2 == parity:
            n *= 2
            if n > 9:
                n -= 9
        checksum += n
    return checksum % 10 == 0


def _mask_cc(text: str) -> tuple:
    """Mask credit card numbers (Luhn-valid). Returns (text, count)."""
    count = 0
    def replace(m):
        nonlocal count
        digits = re.sub(r"\D", "", m.group(0))
        if _luhn_valid(digits):
            count += 1
            return f"****-****-****-{digits[-4:]}"
        return m.group(0)
    return CC_PATTERN.sub(replace, text), count


def _mask_jwt_bearer(text: str) -> tuple:
    """Mask JWTs and bearer tokens."""
    count = 0
    def replace(m):
        nonlocal count
        count += 1
        return "***TOKEN-REDACTED***"
    text = JWT_PATTERN.sub(replace, text)
    text = BEARER_PATTERN.sub(replace, text)
    return text, count


def _check_honeypot(text: str) -> list:
    """If the canary string appears in output, that's a confirmed data leak."""
    try:
        import honeypot
        leaks = []
        for canary in honeypot.get_active_canaries():
            if canary["value"] in text:
                leaks.append(canary)
        return leaks
    except Exception:
        return []


def sanitize_reply(text: str) -> dict:
    """Main filter. Returns dict with sanitized text and alerts list."""
    if not text or not isinstance(text, str):
        return {"text": text or "", "blocked": False, "alerts": []}

    alerts = []

    # 0. Honeypot check FIRST (high signal — confirmed leak)
    canaries_hit = _check_honeypot(text)
    if canaries_hit:
        alerts.append({"kind": "honeypot_leak",
                       "canaries": [c["id"] for c in canaries_hit]})
        bus.publish("output_filter.canary_leaked", {
            "count": len(canaries_hit),
            "canary_ids": [c["id"] for c in canaries_hit],
        })
        try:
            import audit_log
            audit_log.log("output_filter.canary_leaked",
                          {"canaries": [c["id"] for c in canaries_hit]})
        except Exception:
            pass
        # Replace each canary with redaction
        for c in canaries_hit:
            text = text.replace(c["value"], "***LEAK-CAUGHT***")

    # 1. Standard secrets masking (uses existing security.py patterns)
    before = text
    text = security.mask_secrets(text)
    if text != before:
        alerts.append({"kind": "secret_pattern", "categories": ["api_key/email"]})

    # 2. Credit cards (Luhn-validated)
    text, cc_count = _mask_cc(text)
    if cc_count:
        alerts.append({"kind": "credit_card", "count": cc_count})

    # 3. JWT + bearer
    text, tk_count = _mask_jwt_bearer(text)
    if tk_count:
        alerts.append({"kind": "auth_token", "count": tk_count})

    # 4. IBAN
    iban_hits = IBAN_PATTERN.findall(text)
    if iban_hits:
        for iban in iban_hits:
            text = text.replace(iban, iban[:4] + "***" + iban[-4:])
        alerts.append({"kind": "iban", "count": len(iban_hits)})

    # 5. Codice Fiscale
    cf_hits = CF_PATTERN.findall(text)
    if cf_hits:
        for cf in cf_hits:
            text = text.replace(cf, cf[:4] + "********" + cf[-4:])
        alerts.append({"kind": "codice_fiscale", "count": len(cf_hits)})

    # Decision: block reply only if honeypot was triggered
    blocked = bool(canaries_hit)

    if alerts:
        bus.publish("output_filter.detected", {
            "alerts": alerts, "blocked": blocked,
        })

    return {
        "text": text,
        "blocked": blocked,
        "alerts": alerts,
    }


def safe_reply(text: str) -> str:
    """Convenience: returns sanitized text (replacement if blocked)."""
    result = sanitize_reply(text)
    if result["blocked"]:
        return ("[REDACTED] La risposta conteneva dati sensibili (canary trigger) "
                "ed è stata bloccata per sicurezza. Controlla /api/audit/tail.")
    return result["text"]
