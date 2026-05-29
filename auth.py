"""Lightweight auth layer per Vega HTTP API + WebSocket.

Modello:
  - localhost (127.0.0.1, ::1): NESSUN auth richiesto (è il PC dell'utente)
  - LAN/remote: Bearer token obbligatorio
  - Token generato al primo avvio, persistente in data/auth.json (chmod ristretto)
  - Costante-time compare per evitare timing attacks

API:
    get_token() -> str
    rotate_token() -> str
    verify(req) -> bool       # True se autorizzato (localhost OR token valido)
    is_local(req) -> bool
"""
import hmac
import json
import os
import secrets
from pathlib import Path

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)
AUTH_FILE = DATA_DIR / "auth.json"

# Whitelist degli endpoint pubblici (anche da remoto, no token richiesto)
PUBLIC_PATHS = {
    "/",                  # landing/login page (serve UI)
    "/index.html",
    "/style.css",
    "/theme.css",
    "/vega.js",
    "/manifest.json",
    "/sw.js",
    "/loading.html",
    "/-/cert",            # download del cert TLS
    "/api/auth/login",    # endpoint per scambiare PIN -> token
    "/api/auth/info",     # info pubbliche minime (pin_required ecc.)
}

_token = None


def _load_or_create() -> str:
    global _token
    if _token is not None:
        return _token
    if AUTH_FILE.exists():
        try:
            with open(AUTH_FILE, "r", encoding="utf-8") as f:
                _token = json.load(f).get("token", "")
                if _token:
                    return _token
        except Exception:
            pass
    # Generate fresh
    _token = secrets.token_urlsafe(32)
    _save()
    return _token


def _save():
    AUTH_FILE.write_text(json.dumps({"token": _token}), encoding="utf-8")
    try:
        # Restrict file permissions (best-effort on Windows)
        os.chmod(AUTH_FILE, 0o600)
    except Exception:
        pass


def get_token() -> str:
    return _load_or_create()


def rotate_token() -> str:
    global _token
    _token = secrets.token_urlsafe(32)
    _save()
    return _token


def is_local(req) -> bool:
    """True if the request comes from localhost (loopback)."""
    remote = (req.remote_addr or "").lower()
    return remote in ("127.0.0.1", "::1", "localhost")


def extract_token(req) -> str:
    """Extract bearer token from header OR query param OR cookie."""
    # Authorization: Bearer <token>
    auth = req.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    # X-Auth-Token header
    if "X-Auth-Token" in req.headers:
        return req.headers["X-Auth-Token"].strip()
    # ?token=... fallback (for WS upgrade where headers harder to set)
    if "token" in req.args:
        return req.args["token"].strip()
    # Cookie
    return (req.cookies.get("vega_token") or "").strip()


def verify(req) -> bool:
    """Returns True if the request is authorized."""
    # Localhost: bypass
    if is_local(req):
        return True
    # Public path: bypass
    path = req.path or ""
    if path in PUBLIC_PATHS:
        return True
    # Static assets (icons etc.)
    if path.startswith("/assets/"):
        return True
    # Token check (constant-time)
    presented = extract_token(req)
    expected = _load_or_create()
    if not presented or not expected:
        return False
    return hmac.compare_digest(presented, expected)


def verify_pin_and_issue_token(pin: str) -> str:
    """Verify PIN; on success, return current token. UI store it."""
    import security
    if security.verify_pin(pin):
        return get_token()
    return ""


# Init at import time
_load_or_create()
