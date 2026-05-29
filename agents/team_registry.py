"""Registry centrale per gli agenti del Team.

Carica tutti gli agenti del Team (Tier 0-3), espone API:
    get(name) -> TeamAgent
    all() -> list
    status_all() -> list of dict
    enable(name) / disable(name)
    run(name, payload) -> dict
"""
import threading


_lock = threading.Lock()
_agents = {}     # name -> TeamAgent instance
_loaded = False


def _load_all():
    """Import & instantiate every TeamAgent concrete subclass."""
    global _loaded
    if _loaded:
        return
    with _lock:
        if _loaded:
            return
        # Lazy imports to avoid circular & startup cost
        try:
            from . import steward, dpo, ciso, audit_watcher, architect
            from . import bug_hunter, innovator, marketing, ai_expert
            from . import privacy_scout, cyber_scout, market_scout
        except Exception as e:
            print(f"[team_registry] import error: {e}")
        # Static modules (core team)
        static_mods = ("steward", "architect", "dpo", "ciso", "audit_watcher",
                        "bug_hunter", "innovator", "marketing", "ai_expert",
                        "privacy_scout", "cyber_scout", "market_scout")
        for mod_name in static_mods:
            try:
                mod = __import__(f"agents.{mod_name}", fromlist=["AGENT"])
                inst = getattr(mod, "AGENT", None)
                if inst is not None:
                    _agents[inst.name] = inst
            except Exception as e:
                print(f"[team_registry] failed to load {mod_name}: {e}")

        # Dynamic discovery: agents/*.py that have AGENT and aren't already loaded.
        # This picks up agents deployed by the Architect at runtime.
        import os
        from pathlib import Path as _P
        agents_dir = _P(__file__).parent
        loaded_names = set(static_mods) | {"team_base", "team_registry", "base",
                                              "chat_personas", "__init__"}
        for f in agents_dir.glob("*.py"):
            stem = f.stem
            if stem.startswith("_") or stem in loaded_names:
                continue
            # Skip if already in _agents by matching file name
            try:
                mod = __import__(f"agents.{stem}", fromlist=["AGENT"])
                inst = getattr(mod, "AGENT", None)
                if inst is not None and inst.name not in _agents:
                    _agents[inst.name] = inst
                    print(f"[team_registry] dynamically loaded: {inst.name}")
            except Exception as e:
                print(f"[team_registry] skipped {stem}: {e}")
        _loaded = True


def get(name: str):
    _load_all()
    return _agents.get(name)


def all_agents() -> list:
    _load_all()
    return list(_agents.values())


def status_all() -> list:
    return [a.status() for a in all_agents()]


def enable(name: str) -> bool:
    a = get(name)
    if a:
        a.enable()
        return True
    return False


def disable(name: str) -> bool:
    a = get(name)
    if a:
        a.disable()
        return True
    return False


def run(name: str, payload: dict = None) -> dict:
    a = get(name)
    if not a:
        return {"ok": False, "error": f"agent {name} non trovato"}
    return a.safe_run(payload)


def shutdown_all():
    for a in all_agents():
        try:
            a.disable()
        except Exception:
            pass
