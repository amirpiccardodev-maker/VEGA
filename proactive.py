"""Proactive layer: trasforma pattern osservati e routine in suggerimenti/azioni.

Due funzioni:
  1. Subscribe a desktop.pattern_detected -> propone automazione all'utente
     (notifica Windows + card UI + salva suggestion in memory_graph).
  2. Daily briefing: assicura l'esistenza di un'automation "briefing_mattutino"
     che ogni mattina alle 08:00 esegue un comando combinato news+meteo+todo.

Da chiamare via proactive.start() nella fase di init asincrono del server.
"""
import time
import threading

import bus


_started = False
_seen_suggestions = set()  # dedup in-process


def _on_pattern(event):
    """When a desktop pattern is detected, propose an automation to the user.

    Event payload: {"weekday": str, "hour": int, "app": str, "count": int}
    """
    try:
        p = event["payload"]
        key = (p.get("weekday"), p.get("hour"), p.get("app"))
        if key in _seen_suggestions:
            return
        _seen_suggestions.add(key)

        app = p.get("app", "?")
        wd = p.get("weekday", "?")
        hour = p.get("hour", 0)
        count = p.get("count", 0)
        suggestion_text = (f"Ho notato che ogni {wd} verso le {hour}:00 apri {app} "
                           f"(visto {count} volte). Vuoi che lo apra io automaticamente?")

        # 1) Save as instruction-style suggestion in memory_graph
        try:
            import memory_graph as mg
            mg.add("instruction",
                   f"Suggerimento automazione: apri {app} ogni {wd} alle {hour}:00. "
                   f"Frequenza osservata: {count}.",
                   importance=0.7, source="proactive")
        except Exception:
            pass

        # 2) Emit a UI card with accept/dismiss actions
        try:
            bus.publish("card", {
                "type": "suggestion",
                "data": {
                    "title": "Suggerimento automazione",
                    "text": suggestion_text,
                    "action": {
                        "label": f"Crea automazione: ogni {wd} {hour}:00 apri {app}",
                        "automation": {
                            "name": f"auto_{app.lower()}_{wd}_{hour}".replace(" ", "_"),
                            "schedule": f"{_weekday_to_en(wd)} {hour:02d}:00",
                            "command": f"apri {app}",
                            "mode": "silent",
                        },
                    },
                },
            })
        except Exception:
            pass

        # 3) Windows notification (best-effort)
        try:
            import tools as tool_registry
            tool_registry.execute("windows_notify", {
                "title": "Vega - Suggerimento",
                "message": suggestion_text[:120],
            })
        except Exception:
            pass

        bus.publish("proactive.suggestion_emitted", {"app": app, "wd": wd, "hour": hour})
    except Exception as e:
        bus.publish("error.occurred", {"source": "proactive", "error": str(e)})


_WD_IT_TO_EN = {
    "lunedi": "monday", "martedi": "tuesday", "mercoledi": "wednesday",
    "giovedi": "thursday", "venerdi": "friday", "sabato": "saturday",
    "domenica": "sunday",
}


def _weekday_to_en(it: str) -> str:
    return _WD_IT_TO_EN.get((it or "").lower(), "daily")


def _ensure_morning_briefing():
    """Make sure there's a daily 08:00 briefing automation. Idempotent."""
    try:
        import automations
        if automations.find("briefing_mattutino"):
            return
        automations.upsert({
            "name": "briefing_mattutino",
            "schedule": "daily 08:00",
            "command": "Buongiorno. Dimmi meteo, top 3 notizie, e i miei todo di oggi.",
            "mode": "voice",
            "enabled": True,
            "created_at": int(time.time()),
            "source": "proactive",
        })
        bus.publish("proactive.briefing_installed", {"schedule": "daily 08:00"})
    except Exception as e:
        bus.publish("error.occurred", {"source": "proactive.briefing", "error": str(e)})


def start():
    """Idempotent startup hook."""
    global _started
    if _started:
        return
    _started = True
    bus.subscribe("desktop.pattern_detected", _on_pattern)
    # Defer briefing install a bit so automations.json is settled
    threading.Timer(2.0, _ensure_morning_briefing).start()
    bus.publish("proactive.started", {})
