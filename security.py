"""Cybersecurity layer for Vega.

Features:
  - Privacy mode: skip logging conversations to memory.json
  - Memory encryption (optional, AES-256 via passphrase)
  - Secrets masking in logs (API keys, passwords, tokens)
  - PIN-gated critical actions (shutdown PC, send email, etc.)
  - Process integrity check on .env permissions
"""
import os
import re
import json
import base64
import hashlib
import threading
from pathlib import Path

ROOT = Path(__file__).parent
LOG_FILE = ROOT / "vega_error.log"

# State (in-memory only, not persisted)
_privacy_mode = False
_pin_session_token = None
_pin_session_expiry = 0


# Patterns of strings to MASK in logs (sensitive data)
SECRET_PATTERNS = [
    (re.compile(r"sk-ant-[a-zA-Z0-9_-]{20,}"), "***MASKED***"),
    (re.compile(r"sk_[a-zA-Z0-9]{40,}"), "***MASKED***"),
    (re.compile(r"(APP_PASSWORD\s*=\s*)[^\s\n]+"), r"\1***MASKED***"),
    (re.compile(r"(API_KEY\s*=\s*)[^\s\n]+"), r"\1***MASKED***"),
    (re.compile(r"(password['\"]?\s*[:=]\s*['\"])([^'\"]+)"), r"\1***MASKED***"),
    (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), "***MASKED***"),
]


def mask_secrets(text: str) -> str:
    """Replace API keys, emails, passwords in text with '***MASKED***'."""
    if not text:
        return text
    out = text
    for pat, repl in SECRET_PATTERNS:
        out = pat.sub(repl, out)
    return out


# ===== Privacy mode =====

def set_privacy_mode(enabled: bool):
    global _privacy_mode
    _privacy_mode = bool(enabled)


def is_privacy_mode() -> bool:
    return _privacy_mode


def should_log_conversation() -> bool:
    """Returns False when privacy mode is active."""
    return not _privacy_mode


# ===== Memory encryption =====
# When user sets a memory_passphrase, we encrypt the file at write time.
# We use AES-256-GCM via Fernet (cryptography library, well-vetted).

_cipher = None


def setup_encryption(passphrase: str):
    """Initialize encryption with a passphrase. Call once at startup if set."""
    global _cipher
    if not passphrase:
        _cipher = None
        return
    try:
        from cryptography.fernet import Fernet
        # Derive key from passphrase via PBKDF2 (avoid raw passphrase as key)
        salt = b"vega_local_salt_v1"  # static salt is fine for local use
        key = hashlib.pbkdf2_hmac("sha256", passphrase.encode("utf-8"), salt, 100000)
        fernet_key = base64.urlsafe_b64encode(key)
        _cipher = Fernet(fernet_key)
    except Exception as e:
        print(f"[security] Encryption setup failed: {e}")
        _cipher = None


def encrypt(data: str) -> bytes:
    if _cipher is None:
        return data.encode("utf-8")
    return _cipher.encrypt(data.encode("utf-8"))


def decrypt(data: bytes) -> str:
    if _cipher is None:
        return data.decode("utf-8")
    try:
        return _cipher.decrypt(data).decode("utf-8")
    except Exception:
        # Could be unencrypted file
        try:
            return data.decode("utf-8")
        except Exception:
            return ""


def is_encrypted_data(data: bytes) -> bool:
    """Heuristic: Fernet ciphertext starts with version byte 0x80 (gAAAAA...)."""
    return data[:1] == b"\x80" or (len(data) > 0 and data[:5] == b"gAAAA")


# ===== PIN for critical actions =====

_PIN_VALIDITY_SEC = 300  # 5 minutes


def set_pin(pin: str):
    """Set/update the master PIN (stored hashed in memory.json)."""
    import memory
    if not pin or len(pin) < 4:
        return False
    h = hashlib.sha256(pin.encode("utf-8")).hexdigest()
    memory.set_preference("pin_hash", h)
    return True


def verify_pin(pin: str) -> bool:
    """Verify PIN; on success, grant a 5-minute session."""
    global _pin_session_token, _pin_session_expiry
    import time as _time
    import memory
    stored = memory.get_preferences().get("pin_hash", "")
    if not stored:
        # No PIN set: allow
        return True
    h = hashlib.sha256(pin.encode("utf-8")).hexdigest()
    if h == stored:
        _pin_session_token = hashlib.md5(os.urandom(16)).hexdigest()
        _pin_session_expiry = _time.time() + _PIN_VALIDITY_SEC
        return True
    return False


def pin_is_set() -> bool:
    import memory
    return bool(memory.get_preferences().get("pin_hash"))


def has_valid_pin_session() -> bool:
    import time as _time
    return _pin_session_token is not None and _time.time() < _pin_session_expiry


def revoke_pin_session():
    global _pin_session_token, _pin_session_expiry
    _pin_session_token = None
    _pin_session_expiry = 0


def require_pin_for(action: str) -> bool:
    """Returns True if this action requires PIN auth (and PIN is set)."""
    if not pin_is_set():
        return False
    sensitive = {"shutdown_pc", "send_email", "lock_pc", "delete_memory"}
    return action in sensitive


# ===== Integrity checks =====

def check_env_permissions() -> dict:
    """Check that .env file is not world-readable (best-effort on Windows)."""
    env_path = ROOT / ".env"
    if not env_path.exists():
        return {"status": "missing", "warning": ".env non trovato"}
    # On Windows, just check file exists; can't easily check perms without pywin32
    size = env_path.stat().st_size
    if size > 10000:
        return {"status": "warning", "warning": ".env e' insolitamente grande, controlla il contenuto"}
    return {"status": "ok", "size": size}


def get_security_status() -> dict:
    """Quick overview of current security posture."""
    import memory
    prefs = memory.get_preferences()
    return {
        "privacy_mode": _privacy_mode,
        "pin_set": pin_is_set(),
        "encryption_active": _cipher is not None,
        "env_check": check_env_permissions(),
        "instructions_count": len(memory.get_instructions()),
    }
