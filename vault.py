"""Encrypted vault for secrets (.env).

Workflow:
  1. User imposta PIN (security.set_pin)
  2. vault.encrypt_env_from_plain(): legge .env -> scrive .env.enc cifrato con
     master key derivata da PIN tramite PBKDF2-SHA256 (200k iter), elimina .env
  3. Al boot: se .env.enc esiste e .env no, vault.unlock(pin) decifra in memoria
     e popola os.environ. Niente .env in chiaro a riposo.

Cifratura: Fernet (AES-128-CBC + HMAC-SHA256, authenticated).
KDF: PBKDF2-HMAC-SHA256, 200_000 iter, salt costante derivato dall'hostname.

API:
    is_locked() -> bool
    has_encrypted() -> bool
    encrypt_env_from_plain(pin) -> bool
    unlock(pin) -> bool
    rotate_pin(old_pin, new_pin) -> bool
    status() -> dict
"""
import base64
import hashlib
import os
import socket
from pathlib import Path

ROOT = Path(__file__).parent
ENV_PLAIN = ROOT / ".env"
ENV_ENC = ROOT / ".env.enc"

_master_key = None  # Fernet bytes, in-memory only after unlock


def _derive_key(pin: str) -> bytes:
    """Derive a Fernet key (32 bytes URL-safe base64) from PIN + machine salt."""
    salt = ("vega_vault_v1:" + socket.gethostname()).encode("utf-8")
    raw = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), salt, 200_000)
    return base64.urlsafe_b64encode(raw)


def has_encrypted() -> bool:
    return ENV_ENC.exists()


def is_locked() -> bool:
    """True if encrypted vault exists but not yet unlocked."""
    return has_encrypted() and _master_key is None


def encrypt_env_from_plain(pin: str) -> dict:
    """Read .env plaintext, encrypt to .env.enc, delete plaintext."""
    if not ENV_PLAIN.exists():
        return {"ok": False, "error": ".env non trovato"}
    if not pin or len(pin) < 4:
        return {"ok": False, "error": "PIN troppo corto (min 4)"}
    try:
        from cryptography.fernet import Fernet
        key = _derive_key(pin)
        f = Fernet(key)
        plain = ENV_PLAIN.read_bytes()
        # Tag: "JV01" header so we recognize our format
        token = f.encrypt(plain)
        ENV_ENC.write_bytes(b"JV01" + token)
        try:
            os.chmod(ENV_ENC, 0o600)
        except Exception:
            pass
        # Backup before delete (optional, named .env.backup)
        backup = ROOT / ".env.backup"
        backup.write_bytes(plain)
        try:
            os.chmod(backup, 0o600)
        except Exception:
            pass
        ENV_PLAIN.unlink()
        return {"ok": True, "msg": ".env cifrato. Backup salvato in .env.backup (cancellalo manualmente quando sicuro)."}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def unlock(pin: str) -> dict:
    """Decrypt .env.enc with PIN, load into os.environ. Returns status."""
    global _master_key
    if not ENV_ENC.exists():
        return {"ok": False, "error": ".env.enc non trovato"}
    try:
        from cryptography.fernet import Fernet, InvalidToken
        key = _derive_key(pin)
        f = Fernet(key)
        raw = ENV_ENC.read_bytes()
        if raw[:4] == b"JV01":
            raw = raw[4:]
        try:
            plain = f.decrypt(raw)
        except InvalidToken:
            return {"ok": False, "error": "PIN errato (decrypt fallito)"}
        # Parse env lines and set environ
        loaded = 0
        for line in plain.decode("utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ[k.strip()] = v.strip().strip('"').strip("'")
            loaded += 1
        _master_key = key
        return {"ok": True, "loaded": loaded}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def rotate_pin(old_pin: str, new_pin: str) -> dict:
    """Re-encrypt .env.enc with new PIN."""
    if not ENV_ENC.exists():
        return {"ok": False, "error": ".env.enc non trovato"}
    if not new_pin or len(new_pin) < 4:
        return {"ok": False, "error": "Nuovo PIN troppo corto"}
    try:
        from cryptography.fernet import Fernet, InvalidToken
        old_key = _derive_key(old_pin)
        raw = ENV_ENC.read_bytes()
        if raw[:4] == b"JV01":
            raw = raw[4:]
        try:
            plain = Fernet(old_key).decrypt(raw)
        except InvalidToken:
            return {"ok": False, "error": "PIN attuale errato"}
        new_key = _derive_key(new_pin)
        token = Fernet(new_key).encrypt(plain)
        ENV_ENC.write_bytes(b"JV01" + token)
        global _master_key
        _master_key = new_key
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def status() -> dict:
    return {
        "encrypted_exists": has_encrypted(),
        "plaintext_exists": ENV_PLAIN.exists(),
        "unlocked": _master_key is not None,
    }


def auto_unlock_if_only_encrypted():
    """At server boot, if .env.enc exists and .env doesn't, the server can't
    proceed without PIN. This is enforced at config.py import.
    Helper: if env VEGA_VAULT_PIN is set, try that PIN automatically (use cases:
    headless systemd, docker secrets)."""
    if not has_encrypted() or ENV_PLAIN.exists():
        return None
    env_pin = os.environ.get("VEGA_VAULT_PIN")
    if env_pin:
        return unlock(env_pin)
    return None
