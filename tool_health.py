"""Tool health tracker — sliding-window failure detection + auto-disable.

Ogni tool ha un ring buffer dei N esecuzioni più recenti.
Se fail_rate > FAIL_THRESHOLD in finestra recente → auto-disable temporaneo.
Auto-recovery dopo COOLDOWN_SEC.

API:
    record_call(tool_name, success: bool, duration_ms: int)
    is_disabled(tool_name) -> bool
    disable(tool_name, reason)
    enable(tool_name)
    status() -> dict
"""
import threading
import time
from collections import deque

import bus


WINDOW_SIZE = 20
FAIL_THRESHOLD = 0.7         # >70% fail in window → auto-disable
MIN_CALLS_FOR_DECISION = 5
COOLDOWN_SEC = 30 * 60        # 30 min before auto-recover

_lock = threading.Lock()
_buffers = {}                 # tool_name -> deque[{ts, success, duration_ms}]
_disabled = {}                # tool_name -> {"since": ts, "reason": str, "until": ts}


def record_call(tool_name: str, success: bool, duration_ms: int = 0):
    now = time.time()
    with _lock:
        buf = _buffers.get(tool_name)
        if buf is None:
            buf = deque(maxlen=WINDOW_SIZE)
            _buffers[tool_name] = buf
        buf.append({"ts": now, "ok": bool(success), "ms": int(duration_ms)})
        # Check health
        if len(buf) >= MIN_CALLS_FOR_DECISION:
            fails = sum(1 for e in buf if not e["ok"])
            fail_rate = fails / len(buf)
            if fail_rate >= FAIL_THRESHOLD and tool_name not in _disabled:
                _disabled[tool_name] = {
                    "since": now,
                    "reason": f"fail_rate {fail_rate:.0%} on last {len(buf)} calls",
                    "until": now + COOLDOWN_SEC,
                }
                try:
                    bus.publish("tool.auto_disabled", {
                        "tool": tool_name,
                        "fail_rate": round(fail_rate, 2),
                        "window_size": len(buf),
                        "cooldown_sec": COOLDOWN_SEC,
                    })
                    import audit_log
                    audit_log.log("tool.auto_disabled", {
                        "tool": tool_name, "fail_rate": round(fail_rate, 2),
                    })
                except Exception:
                    pass


def is_disabled(tool_name: str) -> bool:
    now = time.time()
    with _lock:
        d = _disabled.get(tool_name)
        if not d:
            return False
        if now >= d.get("until", 0):
            # Auto-recover
            del _disabled[tool_name]
            try:
                bus.publish("tool.auto_recovered", {"tool": tool_name})
            except Exception:
                pass
            return False
        return True


def disable(tool_name: str, reason: str = "manual", duration_sec: int = COOLDOWN_SEC):
    now = time.time()
    with _lock:
        _disabled[tool_name] = {
            "since": now, "reason": reason, "until": now + duration_sec,
        }


def enable(tool_name: str) -> bool:
    with _lock:
        if tool_name in _disabled:
            del _disabled[tool_name]
            return True
    return False


def status() -> dict:
    now = time.time()
    with _lock:
        per_tool = {}
        for name, buf in _buffers.items():
            if not buf:
                continue
            fails = sum(1 for e in buf if not e["ok"])
            avg_ms = int(sum(e["ms"] for e in buf) / len(buf))
            per_tool[name] = {
                "calls": len(buf),
                "fails": fails,
                "fail_rate": round(fails / len(buf), 3),
                "avg_ms": avg_ms,
                "disabled": name in _disabled,
            }
        active_dis = [
            {"tool": k, "reason": v["reason"],
             "since": int(v["since"]),
             "remaining_sec": max(0, int(v["until"] - now))}
            for k, v in _disabled.items()
        ]
    return {
        "tracked_tools": len(per_tool),
        "disabled_count": len(active_dis),
        "per_tool": per_tool,
        "disabled": active_dis,
    }
