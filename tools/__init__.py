"""Auto-discover tools.

Each tool module defines:
    TOOLS = [ {anthropic tool schema}, ... ]
    def run(name, args) -> str  (returns result text)
"""
import importlib
import pkgutil
from pathlib import Path

_ALL_SCHEMAS = []
_RUNNERS = {}  # name -> (module, runner)


def _discover():
    pkg_dir = Path(__file__).parent
    for mod_info in pkgutil.iter_modules([str(pkg_dir)]):
        if mod_info.name.startswith("_"):
            continue
        mod = importlib.import_module(f"tools.{mod_info.name}")
        schemas = getattr(mod, "TOOLS", [])
        run = getattr(mod, "run", None)
        if not schemas or run is None:
            continue
        for schema in schemas:
            _ALL_SCHEMAS.append(schema)
            _RUNNERS[schema["name"]] = run


_discover()


def all_schemas():
    return _ALL_SCHEMAS


MAX_TOOL_RESULT_CHARS = 2000  # Aggressive truncation: Claude usually doesn't need more


def execute(name: str, args: dict, emit=None):
    """Execute a tool with caching + observability + progress feedback.

    Se il tool impiega più di 1.5s, emette periodic 'tool_progress' events
    che la UI mostra come "sto cercando..." per evitare la sensazione di blocco.
    """
    from tools import _shared
    import tool_cache
    import time as _t
    import threading as _th

    # Auto-disable check (B4.1)
    try:
        import tool_health
        if tool_health.is_disabled(name):
            return (f"[TOOL_DISABLED tool={name}] Auto-disabilitato per troppi "
                    f"fallimenti recenti. Riproverà tra qualche minuto. "
                    f"PROPONI un tool alternativo o spiega all'utente.")
    except Exception:
        pass

    # Try cache first
    cached = tool_cache.get(name, args or {})
    if cached is not None:
        if emit:
            try: emit("cache_hit", {"tool": name})
            except Exception: pass
        return cached

    runner = _RUNNERS.get(name)
    if not runner:
        return f"Tool sconosciuto: {name}"
    _shared.set_emit(emit)
    started = _t.time()
    error = False

    # Progress feedback thread: emits tool_progress every 2s if still running
    PROGRESS_DELAY = 1.5  # emit first progress after 1.5s
    PROGRESS_INTERVAL = 2.0
    progress_done = _th.Event()

    def _progress_loop():
        if not emit:
            return
        # Wait initial delay
        if progress_done.wait(PROGRESS_DELAY):
            return  # done before delay
        elapsed = _t.time() - started
        try:
            emit("tool_progress", {
                "tool": name,
                "elapsed_sec": round(elapsed, 1),
                "message": _progress_msg_for(name, elapsed),
            })
        except Exception:
            pass
        # Subsequent updates
        while not progress_done.wait(PROGRESS_INTERVAL):
            elapsed = _t.time() - started
            try:
                emit("tool_progress", {
                    "tool": name,
                    "elapsed_sec": round(elapsed, 1),
                    "message": _progress_msg_for(name, elapsed),
                })
            except Exception:
                break

    if emit:
        progress_th = _th.Thread(target=_progress_loop, daemon=True,
                                    name=f"tool_progress_{name}")
        progress_th.start()
    else:
        progress_th = None

    try:
        result = runner(name, args or {})
    except Exception as e:
        result = f"Errore esecuzione {name}: {e}"
        error = True
    finally:
        progress_done.set()
        _shared.set_emit(None)
        elapsed_ms = int((_t.time() - started) * 1000)
        if emit and elapsed_ms > int(PROGRESS_DELAY * 1000):
            # Emit final "done" if we had been showing progress
            try:
                emit("tool_progress", {
                    "tool": name,
                    "elapsed_sec": round(elapsed_ms / 1000, 1),
                    "message": "fatto",
                    "done": True,
                })
            except Exception:
                pass
        try:
            import observability as _obs
            _obs.record_tool_call(name, elapsed_ms, error)
        except Exception:
            pass
        try:
            import tool_health
            tool_health.record_call(name, not error, elapsed_ms)
        except Exception:
            pass
    if isinstance(result, str) and len(result) > MAX_TOOL_RESULT_CHARS:
        result = result[:MAX_TOOL_RESULT_CHARS] + "\n[...troncato]"
    tool_cache.put(name, args or {}, result)
    return result


def _progress_msg_for(name: str, elapsed: float) -> str:
    """Generate a user-friendly progress message per tool name."""
    # Tool-specific friendly labels
    labels = {
        "web_search": "cerco online",
        "web_images": "cerco immagini",
        "wikipedia": "consulto Wikipedia",
        "get_weather": "controllo il meteo",
        "get_news": "leggo le notizie",
        "generate_image": "genero l'immagine",
        "read_article_aloud": "leggo l'articolo",
        "list_emails": "scarico le email",
        "summarize_inbox": "riassumo la posta",
        "send_email": "invio l'email",
        "browse_url": "navigo la pagina",
        "analyze_screen": "guardo lo schermo",
        "analyze_image": "analizzo l'immagine",
        "ask_recent_news": "cerco tra le news recenti",
    }
    base = labels.get(name, f"eseguo {name}")
    if elapsed > 5:
        return f"{base}... (ci sto ancora lavorando, {int(elapsed)}s)"
    return f"{base}..."
