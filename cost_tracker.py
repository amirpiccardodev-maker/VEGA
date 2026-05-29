"""Cost tracking per caller (agent/tool/general).

Idea: ogni chiamata LLM viene registrata con (caller, model, tokens, cost_cents).
Si vede chi sta spendendo cosa, trovando agenti/tool inefficient.

API:
    record(caller, model, input_tokens, output_tokens, cache_read=0, cache_write=0)
    get_breakdown() -> {by_caller, by_model, today, last7}
    reset()
"""
import json
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).parent
COST_FILE = ROOT / "data" / "cost_tracking.json"
COST_FILE.parent.mkdir(parents=True, exist_ok=True)

_lock = threading.Lock()

# Prezzi USD per million tokens (Sonnet 4.5 = main)
PRICES = {
    "sonnet": {"in": 3.0, "out": 15.0, "cache_w": 3.75, "cache_r": 0.30},
    "haiku":  {"in": 0.80, "out": 4.0, "cache_w": 1.00, "cache_r": 0.08},
    "ollama": {"in": 0.0, "out": 0.0, "cache_w": 0.0, "cache_r": 0.0},
}


def _model_family(model: str) -> str:
    m = (model or "").lower()
    if "haiku" in m:
        return "haiku"
    if "ollama" in m or "llama" in m:
        return "ollama"
    return "sonnet"  # default


def _calc_cost_cents(model: str, in_t: int, out_t: int,
                       cache_r: int = 0, cache_w: int = 0) -> float:
    p = PRICES.get(_model_family(model), PRICES["sonnet"])
    usd = (in_t * p["in"] + out_t * p["out"] +
           cache_r * p["cache_r"] + cache_w * p["cache_w"]) / 1_000_000
    return round(usd * 100, 4)  # cents


def _load() -> dict:
    if not COST_FILE.exists():
        return {"entries": [], "totals": {}}
    try:
        with open(COST_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"entries": [], "totals": {}}


def _save(d: dict):
    # Cap entries to last 5000
    if len(d.get("entries", [])) > 5000:
        d["entries"] = d["entries"][-5000:]
    try:
        with open(COST_FILE, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def record(caller: str, model: str = "sonnet",
            input_tokens: int = 0, output_tokens: int = 0,
            cache_read: int = 0, cache_write: int = 0):
    """Record an LLM call attributed to a caller."""
    cost_cents = _calc_cost_cents(model, input_tokens, output_tokens,
                                     cache_read, cache_write)
    entry = {
        "ts": int(time.time()),
        "caller": caller or "unknown",
        "model": _model_family(model),
        "in": input_tokens,
        "out": output_tokens,
        "cache_r": cache_read,
        "cache_w": cache_write,
        "cents": cost_cents,
    }
    with _lock:
        d = _load()
        d.setdefault("entries", []).append(entry)
        # Update aggregates
        tot = d.setdefault("totals", {})
        by_caller = tot.setdefault("by_caller", {})
        c = by_caller.setdefault(entry["caller"], {
            "calls": 0, "cents": 0.0, "in": 0, "out": 0
        })
        c["calls"] += 1
        c["cents"] = round(c["cents"] + cost_cents, 4)
        c["in"] += input_tokens
        c["out"] += output_tokens
        # by_model
        by_model = tot.setdefault("by_model", {})
        m = by_model.setdefault(entry["model"], {"calls": 0, "cents": 0.0})
        m["calls"] += 1
        m["cents"] = round(m["cents"] + cost_cents, 4)
        _save(d)
    return cost_cents


def get_breakdown() -> dict:
    """Return breakdown for UI dashboard."""
    with _lock:
        d = _load()
    entries = d.get("entries", [])
    totals = d.get("totals", {})
    # Today + last 7 days
    now = time.time()
    day = 86400
    today_cents = 0.0
    today_calls = 0
    last7 = [0.0] * 7
    last7_calls = [0] * 7
    for e in entries:
        age_days = int((now - e.get("ts", 0)) / day)
        if age_days == 0:
            today_cents += e.get("cents", 0)
            today_calls += 1
        if 0 <= age_days < 7:
            last7[age_days] += e.get("cents", 0)
            last7_calls[age_days] += 1
    # Top 10 callers by cost
    by_caller = totals.get("by_caller", {})
    top_callers = sorted(by_caller.items(), key=lambda kv: -kv[1].get("cents", 0))[:10]
    return {
        "today_cents": round(today_cents, 2),
        "today_calls": today_calls,
        "today_usd": round(today_cents / 100, 4),
        "last7_cents": [round(c, 2) for c in last7],   # last7[0] = today
        "last7_calls": last7_calls,
        "last7_total_cents": round(sum(last7), 2),
        "by_caller_top10": [
            {"caller": c, **info} for c, info in top_callers
        ],
        "by_model": totals.get("by_model", {}),
        "total_entries": len(entries),
    }


def reset():
    """Wipe cost tracking (use with care)."""
    with _lock:
        _save({"entries": [], "totals": {}})
