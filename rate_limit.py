"""Rate limiting + PIN brute-force protection.

Algoritmi:
  - General: token-bucket per IP (default 60 req/min)
  - PIN: 5 fail entro 15 min -> lockout 15 min per quel IP
  - Localhost: bypass (è il PC dell'utente)

In-memory only. Reset al restart server (accettabile per single-user).
"""
import threading
import time
from collections import deque


_lock = threading.Lock()

# IP -> deque[timestamps]
_buckets = {}
# IP -> {"fails": int, "first_ts": float, "lockout_until": float}
_pin_state = {}

DEFAULT_RPM = 120  # 2/sec on average is plenty for a single-user assistant
PIN_MAX_FAILS = 5
PIN_LOCKOUT_SEC = 15 * 60
PIN_FAIL_WINDOW_SEC = 15 * 60


def _is_local(ip: str) -> bool:
    return (ip or "").lower() in ("127.0.0.1", "::1", "localhost")


def check_request(ip: str, limit_rpm: int = DEFAULT_RPM) -> bool:
    """Return True if request is allowed under rate limit."""
    if _is_local(ip):
        return True
    now = time.time()
    with _lock:
        bucket = _buckets.get(ip)
        if bucket is None:
            bucket = deque()
            _buckets[ip] = bucket
        # Drop entries older than 60s
        while bucket and bucket[0] < now - 60:
            bucket.popleft()
        if len(bucket) >= limit_rpm:
            return False
        bucket.append(now)
    return True


def check_pin_lockout(ip: str) -> bool:
    """Return True if this IP is allowed to attempt PIN."""
    if _is_local(ip):
        return True
    now = time.time()
    with _lock:
        st = _pin_state.get(ip)
        if not st:
            return True
        if st.get("lockout_until", 0) > now:
            return False
    return True


def register_pin_fail(ip: str):
    """Record a PIN failure. After PIN_MAX_FAILS in window, lock out."""
    if _is_local(ip):
        return
    now = time.time()
    with _lock:
        st = _pin_state.get(ip)
        if not st or now - st.get("first_ts", 0) > PIN_FAIL_WINDOW_SEC:
            _pin_state[ip] = {"fails": 1, "first_ts": now, "lockout_until": 0}
            return
        st["fails"] = st.get("fails", 0) + 1
        if st["fails"] >= PIN_MAX_FAILS:
            st["lockout_until"] = now + PIN_LOCKOUT_SEC
            import bus
            bus.publish("auth.lockout", {"ip": ip, "duration_sec": PIN_LOCKOUT_SEC})


def clear_pin_fails(ip: str):
    """Reset PIN fail counter after a successful login."""
    with _lock:
        if ip in _pin_state:
            del _pin_state[ip]


def status() -> dict:
    now = time.time()
    with _lock:
        return {
            "tracked_ips": len(_buckets),
            "active_lockouts": [
                {"ip": ip, "until_in_sec": int(st["lockout_until"] - now)}
                for ip, st in _pin_state.items()
                if st.get("lockout_until", 0) > now
            ],
        }
