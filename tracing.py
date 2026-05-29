"""Simple distributed tracing for Vega.

Ogni richiesta HTTP riceve un trace_id univoco propagato:
  - thread-local per durata richiesta
  - inserito in bus events come "trace_id"
  - usato da audit_log
  - esposto in response header X-Trace-Id

API:
    new_trace_id() -> str (16-char hex)
    set(trace_id)
    current() -> str | None
    spans(trace_id) -> list (eventi correlati)
"""
import threading
import uuid
import time
import json
from pathlib import Path


ROOT = Path(__file__).parent
TRACE_FILE = ROOT / "data" / "traces.jsonl"
TRACE_FILE.parent.mkdir(parents=True, exist_ok=True)
_TRACE_MAX_LINES = 10000

_local = threading.local()


def new_trace_id() -> str:
    return uuid.uuid4().hex[:16]


def set(trace_id: str):
    _local.trace_id = trace_id


def current() -> str:
    return getattr(_local, "trace_id", None)


def clear():
    if hasattr(_local, "trace_id"):
        del _local.trace_id


def record_span(event: str, data: dict = None, level: str = "info"):
    """Append a trace span to the local log."""
    tid = current()
    if not tid:
        return
    span = {
        "ts": int(time.time() * 1000),
        "trace_id": tid,
        "event": event,
        "level": level,
        "data": data or {},
    }
    try:
        with open(TRACE_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(span, ensure_ascii=False) + "\n")
    except Exception:
        pass
    # Tail-trim periodically (every 1000th call approx)
    try:
        if int(time.time()) % 600 == 0:  # ~10min window
            _trim()
    except Exception:
        pass


def _trim():
    """Keep file under _TRACE_MAX_LINES."""
    if not TRACE_FILE.exists():
        return
    try:
        with open(TRACE_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
        if len(lines) > _TRACE_MAX_LINES:
            with open(TRACE_FILE, "w", encoding="utf-8") as f:
                f.writelines(lines[-_TRACE_MAX_LINES:])
    except Exception:
        pass


def get_spans(trace_id: str) -> list:
    """Read all spans for a given trace_id."""
    if not TRACE_FILE.exists():
        return []
    out = []
    try:
        with open(TRACE_FILE, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    s = json.loads(line)
                    if s.get("trace_id") == trace_id:
                        out.append(s)
                except Exception:
                    continue
    except Exception:
        pass
    return out


def recent_traces(limit: int = 20) -> list:
    """List of distinct recent trace_ids with summary."""
    if not TRACE_FILE.exists():
        return []
    traces = {}
    try:
        with open(TRACE_FILE, "r", encoding="utf-8") as f:
            for line in f.readlines()[-2000:]:
                try:
                    s = json.loads(line)
                    tid = s.get("trace_id")
                    if not tid:
                        continue
                    if tid not in traces:
                        traces[tid] = {
                            "trace_id": tid,
                            "first_ts": s["ts"],
                            "last_ts": s["ts"],
                            "span_count": 0,
                            "first_event": s.get("event", "?"),
                        }
                    traces[tid]["last_ts"] = s["ts"]
                    traces[tid]["span_count"] += 1
                except Exception:
                    continue
    except Exception:
        pass
    out = sorted(traces.values(), key=lambda x: -x["last_ts"])[:limit]
    for t in out:
        t["duration_ms"] = t["last_ts"] - t["first_ts"]
    return out
