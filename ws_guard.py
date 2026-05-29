"""WebSocket replay protection: nonce + timestamp validation.

Client envelope format (opt-in via prefs.ws_replay_guard):
    { "event": "...", "payload": {...}, "ts": 1700000000, "nonce": "<random>" }

Server rejects:
  - missing ts/nonce
  - ts skew > 60s
  - nonce already seen in last 5 minutes (replay)

Without the envelope, behavior degrades to current (no replay protection).
This is intentional to avoid breaking old clients during rollout.
"""
import threading
import time


_seen = {}    # nonce -> ts_seen
_lock = threading.Lock()
MAX_SKEW_SEC = 60
NONCE_TTL_SEC = 300


def _cleanup_locked():
    now = time.time()
    expired = [k for k, t in _seen.items() if now - t > NONCE_TTL_SEC]
    for k in expired:
        del _seen[k]


def is_replay(data: dict) -> tuple:
    """Returns (is_replay_bool, reason).

    If envelope is absent (no ts/nonce), returns (False, 'no_envelope')
    -> permissive: legacy clients still work.
    """
    ts = data.get("ts")
    nonce = data.get("nonce")
    if ts is None and nonce is None:
        return False, "no_envelope"
    if ts is None or nonce is None:
        return True, "incomplete_envelope"
    try:
        ts = int(ts)
    except Exception:
        return True, "invalid_ts"
    now = time.time()
    if abs(now - ts) > MAX_SKEW_SEC:
        return True, "skew_too_large"
    with _lock:
        _cleanup_locked()
        if nonce in _seen:
            return True, "replayed_nonce"
        _seen[nonce] = now
    return False, "ok"


def stats() -> dict:
    with _lock:
        _cleanup_locked()
        return {
            "tracked_nonces": len(_seen),
            "max_skew_sec": MAX_SKEW_SEC,
            "nonce_ttl_sec": NONCE_TTL_SEC,
        }
