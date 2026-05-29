"""Lightweight metrics & observability.

Tracks per-tool: calls, errors, latency.
Tracks per-route: cache hit rate, shortcut bypass rate.
Tracks per-day: tokens, costs, success rate.

Saved to memory.json under 'metrics' key.
"""
import time
import threading
from datetime import datetime

import memory


_lock = threading.Lock()


def _today():
    return datetime.now().date().isoformat()


def record_tool_call(tool_name: str, latency_ms: int, error: bool = False):
    def m(d):
        metrics = d.setdefault("metrics", {})
        tools = metrics.setdefault("tools", {})
        t = tools.setdefault(tool_name, {"calls": 0, "errors": 0, "total_ms": 0, "max_ms": 0})
        t["calls"] += 1
        if error:
            t["errors"] += 1
        t["total_ms"] += latency_ms
        t["max_ms"] = max(t["max_ms"], latency_ms)
    memory.update(m)


def record_shortcut_hit(kind: str = "regex"):
    """kind: 'regex' or 'semantic'"""
    def m(d):
        metrics = d.setdefault("metrics", {})
        sc = metrics.setdefault("shortcuts", {"regex": 0, "semantic": 0})
        sc[kind] = sc.get(kind, 0) + 1
    memory.update(m)


def record_routing(categories: list, tool_count: int):
    def m(d):
        metrics = d.setdefault("metrics", {})
        r = metrics.setdefault("routing", {"calls": 0, "total_tools": 0, "categories": {}})
        r["calls"] += 1
        r["total_tools"] += tool_count
        for c in categories:
            r["categories"][c] = r["categories"].get(c, 0) + 1
    memory.update(m)


def get_metrics_summary() -> dict:
    data = memory.get_all().get("metrics", {})
    tools = data.get("tools", {})
    # Sorted by calls
    sorted_tools = sorted(tools.items(), key=lambda x: x[1].get("calls", 0), reverse=True)
    top_tools = []
    for name, t in sorted_tools[:15]:
        calls = t.get("calls", 0)
        avg_ms = int(t.get("total_ms", 0) / max(1, calls))
        err_rate = round(t.get("errors", 0) / max(1, calls) * 100, 1)
        top_tools.append({
            "name": name, "calls": calls, "avg_ms": avg_ms,
            "max_ms": t.get("max_ms", 0), "error_rate_pct": err_rate,
        })

    shortcuts = data.get("shortcuts", {})
    routing = data.get("routing", {})
    routing_avg = round(routing.get("total_tools", 0) / max(1, routing.get("calls", 1)), 1)

    return {
        "top_tools": top_tools,
        "shortcuts": shortcuts,
        "routing": {
            "calls": routing.get("calls", 0),
            "avg_tools_sent": routing_avg,
            "top_categories": sorted(routing.get("categories", {}).items(),
                                     key=lambda x: x[1], reverse=True)[:10],
        },
    }
