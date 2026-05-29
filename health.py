"""Health check aggregato di Vega.

Risponde a:
  - /api/health        — overall status + sub-component check
  - /api/health/live   — liveness (process is responding)
  - /api/health/ready  — readiness (all critical components ready)

Componenti monitorati:
  - brain (Anthropic client init)
  - memory_graph (SQLite reachable)
  - mem0 (Chroma loaded)
  - ollama (local LLM available, opt-in)
  - bus (in-process)
  - task_queue (workers + DB)
  - news_graph (scout activity)
  - tools (registry loaded)
"""
import time


def _check_brain() -> dict:
    try:
        import config
        ok = bool(config.ANTHROPIC_API_KEY)
        return {"ok": ok, "detail": "configured" if ok else "missing API key"}
    except Exception as e:
        return {"ok": False, "detail": str(e)[:120]}


def _check_memory_graph() -> dict:
    try:
        import memory_graph as mg
        stats = mg.stats()
        return {"ok": True, "detail": f"{stats.get('total', 0)} records"}
    except Exception as e:
        return {"ok": False, "detail": str(e)[:120]}


def _check_mem0() -> dict:
    try:
        import episodic_memory
        s = episodic_memory.stats()
        return {"ok": s.get("available", False),
                "detail": f"{s.get('total', 0)} episodic memories"}
    except Exception as e:
        return {"ok": False, "detail": str(e)[:120]}


def _check_ollama() -> dict:
    try:
        import local_brain
        avail = local_brain.is_available()
        return {"ok": True if avail else None,  # None = optional/not configured
                "detail": "online" if avail else "offline (optional)",
                "optional": True}
    except Exception as e:
        return {"ok": None, "detail": str(e)[:120], "optional": True}


def _check_bus() -> dict:
    try:
        import bus
        hist = bus.history()
        return {"ok": True, "detail": f"{len(hist[-100:])} recent events"}
    except Exception as e:
        return {"ok": False, "detail": str(e)[:120]}


def _check_task_queue() -> dict:
    try:
        import task_queue as tq
        stats = tq.stats()
        return {"ok": True, "detail": str(stats)}
    except Exception as e:
        return {"ok": False, "detail": str(e)[:120]}


def _check_news_graph() -> dict:
    try:
        import news_graph
        return {"ok": True, "detail": "feeds configured"}
    except Exception as e:
        return {"ok": False, "detail": str(e)[:120]}


def _check_tools() -> dict:
    try:
        import tools as tr
        n = len(tr.all_schemas())
        return {"ok": n > 0, "detail": f"{n} tools registered"}
    except Exception as e:
        return {"ok": False, "detail": str(e)[:120]}


def _check_team_agents() -> dict:
    try:
        from agents import team_registry
        n = len(team_registry.all_agents())
        return {"ok": n > 0, "detail": f"{n} team agents loaded"}
    except Exception as e:
        return {"ok": False, "detail": str(e)[:120]}


_START_TIME = time.time()


def liveness() -> dict:
    """Minimal: is the process alive?"""
    return {"alive": True, "uptime_sec": int(time.time() - _START_TIME)}


def readiness() -> dict:
    """All critical components ready to serve traffic."""
    critical = ["brain", "memory_graph", "tools"]
    components = check_all()
    not_ready = [c for c in critical
                  if not components.get(c, {}).get("ok")]
    return {
        "ready": len(not_ready) == 0,
        "not_ready_components": not_ready,
        "uptime_sec": int(time.time() - _START_TIME),
    }


def check_all() -> dict:
    """Run all health checks. Returns dict of {component: {ok, detail}}."""
    return {
        "brain": _check_brain(),
        "memory_graph": _check_memory_graph(),
        "mem0": _check_mem0(),
        "ollama": _check_ollama(),
        "bus": _check_bus(),
        "task_queue": _check_task_queue(),
        "news_graph": _check_news_graph(),
        "tools": _check_tools(),
        "team_agents": _check_team_agents(),
    }


def overall() -> dict:
    """Public summary: green/yellow/red + per-component breakdown."""
    components = check_all()
    critical_ok = all(
        components[c]["ok"]
        for c in ("brain", "memory_graph", "tools")
        if c in components
    )
    optional_problems = sum(
        1 for c, info in components.items()
        if not info.get("optional") and info.get("ok") is False
        and c not in ("brain", "memory_graph", "tools")
    )
    if critical_ok and optional_problems == 0:
        status = "healthy"
    elif critical_ok:
        status = "degraded"
    else:
        status = "unhealthy"
    return {
        "status": status,
        "uptime_sec": int(time.time() - _START_TIME),
        "components": components,
        "checked_at": int(time.time()),
    }
