"""Tamper-evident audit log via hash chain.

Ogni evento è una riga JSON con:
    {ts, event, data, hash_prev, hash}
dove hash = sha256(canonical(event_record_without_hash) + hash_prev).

Manomettere una riga rompe la catena: verify_integrity() lo rileva.

Eventi sensibili da loggare:
  - auth.login_ok / auth.login_fail
  - auth.token_rotated
  - pin.set / pin.verify_fail
  - tool.executed (tool_name, args_hash) — non i full args (privacy)
  - acl.consent_granted / revoked
  - acl.blocked
  - settings.changed (key, only)
  - net_guard.blocked
  - prompt_shield.detected (high risk)
  - memory.deleted
  - server.boot / shutdown
"""
import hashlib
import json
import threading
import time
from pathlib import Path

ROOT = Path(__file__).parent
LOG_FILE = ROOT / "data" / "audit.log.jsonl"
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

GENESIS_HASH = "0" * 64
_lock = threading.Lock()
_last_hash = None


def _canonical(d: dict) -> str:
    return json.dumps(d, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _compute_hash(record_no_hash: dict, prev: str) -> str:
    payload = _canonical(record_no_hash) + prev
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _read_last_hash() -> str:
    """Read the last hash from the log file (cached after first read)."""
    global _last_hash
    if _last_hash is not None:
        return _last_hash
    if not LOG_FILE.exists():
        _last_hash = GENESIS_HASH
        return _last_hash
    last = GENESIS_HASH
    try:
        with open(LOG_FILE, "rb") as f:
            # Seek to last line: read backward from end
            f.seek(0, 2)
            size = f.tell()
            if size == 0:
                _last_hash = GENESIS_HASH
                return _last_hash
            # Read last 2KB and split
            chunk_size = min(size, 2048)
            f.seek(size - chunk_size)
            chunk = f.read()
            lines = chunk.split(b"\n")
            for line in reversed(lines):
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    last = rec.get("hash", GENESIS_HASH)
                    break
                except Exception:
                    continue
    except Exception:
        pass
    _last_hash = last
    return _last_hash


def log(event: str, data: dict = None):
    """Append an event to the audit log. Non-blocking, fast."""
    global _last_hash
    with _lock:
        prev = _read_last_hash()
        record_no_hash = {
            "ts": int(time.time() * 1000),
            "event": event,
            "data": data or {},
            "hash_prev": prev,
        }
        h = _compute_hash(record_no_hash, prev)
        record = dict(record_no_hash)
        record["hash"] = h
        try:
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(_canonical(record) + "\n")
            _last_hash = h
        except Exception:
            pass


def verify_integrity() -> dict:
    """Walk the entire log and verify every hash. Returns {ok, total, broken_at}."""
    if not LOG_FILE.exists():
        return {"ok": True, "total": 0, "empty": True}
    prev = GENESIS_HASH
    total = 0
    broken_at = None
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            for i, line in enumerate(f):
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    broken_at = i
                    break
                expected_prev = rec.get("hash_prev", "")
                if expected_prev != prev:
                    broken_at = i
                    break
                record_no_hash = {k: rec[k] for k in ("ts", "event", "data", "hash_prev") if k in rec}
                expected_hash = _compute_hash(record_no_hash, prev)
                if expected_hash != rec.get("hash"):
                    broken_at = i
                    break
                prev = rec["hash"]
                total += 1
    except Exception as e:
        return {"ok": False, "total": total, "error": str(e)}
    return {"ok": broken_at is None, "total": total, "broken_at": broken_at}


def tail(n: int = 50) -> list:
    """Return last N records."""
    if not LOG_FILE.exists():
        return []
    out = []
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()[-n:]
        for line in lines:
            try:
                out.append(json.loads(line))
            except Exception:
                pass
    except Exception:
        pass
    return out


def search(event: str = None, since_ts: int = None, limit: int = 200) -> list:
    """Filter records."""
    if not LOG_FILE.exists():
        return []
    out = []
    with open(LOG_FILE, "r", encoding="utf-8") as f:
        for line in f:
            try:
                rec = json.loads(line)
            except Exception:
                continue
            if event and rec.get("event") != event:
                continue
            if since_ts and rec.get("ts", 0) < since_ts:
                continue
            out.append(rec)
            if len(out) >= limit:
                break
    return out


# ============ Bus subscriber: auto-log relevant events ============

_AUTO_LOG_EVENTS = {
    "acl.consent_granted": "acl.consent",
    "acl.warning": "acl.warning",
    "prompt_shield.detected": "shield.injection",
    "net.blocked": "net.blocked",
    "self_healing.suggestion": "healing.suggestion",
    "system.boot": "server.boot",
    "auth.login_ok": "auth.login_ok",
    "auth.login_fail": "auth.login_fail",
}


def _on_bus_event(evt):
    try:
        topic = evt.get("topic", "")
        if topic in _AUTO_LOG_EVENTS:
            log(_AUTO_LOG_EVENTS[topic], evt.get("payload", {}))
    except Exception:
        pass


def start():
    """Subscribe to bus to auto-capture events."""
    try:
        import bus
        for topic in _AUTO_LOG_EVENTS:
            bus.subscribe(topic, _on_bus_event)
        log("audit.started", {})
    except Exception as e:
        print(f"[audit] start error: {e}")
