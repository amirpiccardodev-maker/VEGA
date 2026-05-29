"""Web Push minimo per notifiche mobile PWA.

Genera VAPID keypair al primo avvio (salvato in data/vapid.json), gestisce
subscription dei browser, e invia notifiche broadcast.

API:
    public_key() -> str (base64url, da passare al SW per subscribe)
    add_subscription(sub_dict)
    push(title, body, url=None) -> notifica tutti i subscriber
"""
import json
import threading
from pathlib import Path

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)
VAPID_FILE = DATA_DIR / "vapid.json"
SUBS_FILE = DATA_DIR / "push_subscriptions.json"

_lock = threading.Lock()
_vapid = None


def _ensure_vapid():
    global _vapid
    if _vapid is not None:
        return _vapid
    if VAPID_FILE.exists():
        with open(VAPID_FILE, "r", encoding="utf-8") as f:
            _vapid = json.load(f)
        return _vapid
    # Generate VAPID keypair
    try:
        from py_vapid import Vapid01
        v = Vapid01()
        v.generate_keys()
        priv_pem = v.private_pem().decode("ascii")
        # Public key in URL-safe base64 (uncompressed point, 65 bytes -> b64url)
        from cryptography.hazmat.primitives.asymmetric import ec
        pub_numbers = v.public_key.public_numbers()
        from cryptography.hazmat.primitives import serialization
        pub_bytes = v.public_key.public_bytes(
            encoding=serialization.Encoding.X962,
            format=serialization.PublicFormat.UncompressedPoint,
        )
        import base64
        pub_b64url = base64.urlsafe_b64encode(pub_bytes).decode("ascii").rstrip("=")
        _vapid = {"private_pem": priv_pem, "public_key": pub_b64url}
    except Exception as e:
        print(f"[web_push] vapid gen failed: {e}")
        _vapid = {"private_pem": "", "public_key": ""}
    with open(VAPID_FILE, "w", encoding="utf-8") as f:
        json.dump(_vapid, f)
    return _vapid


def public_key() -> str:
    return _ensure_vapid().get("public_key", "")


def _load_subs():
    if not SUBS_FILE.exists():
        return []
    try:
        with open(SUBS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save_subs(subs):
    with open(SUBS_FILE, "w", encoding="utf-8") as f:
        json.dump(subs, f, ensure_ascii=False, indent=2)


def add_subscription(sub: dict) -> bool:
    with _lock:
        subs = _load_subs()
        # Dedup by endpoint
        endpoint = sub.get("endpoint", "")
        subs = [s for s in subs if s.get("endpoint") != endpoint]
        subs.append(sub)
        _save_subs(subs)
    return True


def remove_subscription(endpoint: str) -> bool:
    with _lock:
        subs = _load_subs()
        before = len(subs)
        subs = [s for s in subs if s.get("endpoint") != endpoint]
        if len(subs) != before:
            _save_subs(subs)
            return True
    return False


def push(title: str, body: str, url: str = None, badge: str = None) -> dict:
    """Send a push notification to all subscribers. Returns dict with counts."""
    v = _ensure_vapid()
    if not v.get("private_pem"):
        return {"sent": 0, "error": "vapid not configured"}
    try:
        from pywebpush import webpush, WebPushException
    except Exception as e:
        return {"sent": 0, "error": f"pywebpush not installed: {e}"}

    payload = {"title": title, "body": body}
    if url:
        payload["url"] = url
    if badge:
        payload["badge"] = badge
    payload_json = json.dumps(payload)

    subs = _load_subs()
    sent = 0
    errors = 0
    dead = []
    for sub in subs:
        try:
            webpush(
                subscription_info=sub,
                data=payload_json,
                vapid_private_key=v["private_pem"],
                vapid_claims={"sub": "mailto:vega@local"},
            )
            sent += 1
        except WebPushException as e:
            errors += 1
            # If 410 Gone, the subscription is dead
            try:
                if e.response is not None and e.response.status_code in (404, 410):
                    dead.append(sub.get("endpoint"))
            except Exception:
                pass
        except Exception:
            errors += 1
    # Cleanup dead subs
    for endpoint in dead:
        remove_subscription(endpoint)
    return {"sent": sent, "errors": errors, "total_subs": len(subs)}


def stats() -> dict:
    return {
        "subscribers": len(_load_subs()),
        "vapid_configured": bool(_ensure_vapid().get("public_key")),
    }
