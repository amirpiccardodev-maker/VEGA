"""Automations / agents system: scheduled commands that run on their own.

Schedule formats supported:
  - "daily HH:MM"          -> ogni giorno a quell'ora
  - "weekday HH:MM"        -> lun-ven a quell'ora
  - "weekend HH:MM"        -> sab-dom a quell'ora
  - "mon HH:MM" (tue/wed/thu/fri/sat/sun) -> giorno specifico
  - "interval Xm"          -> ogni X minuti
  - "interval Xh"          -> ogni X ore
  - "once YYYY-MM-DDTHH:MM" -> singola esecuzione

Modes:
  - "voice" (default): risposta parlata + card (come una chiamata normale)
  - "card":  solo card visiva, niente voce (silenziosa visivamente)
  - "silent": solo notifica toast, no voce, no card. Risultato in storia.
"""
import json
import threading
import time as _time
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).parent
AUTOMATIONS_FILE = ROOT / "automations.json"

_lock = threading.Lock()
_executor = None  # callback(command, mode) set by server at startup
_engine_ref = None


def set_executor(callback, engine=None):
    global _executor, _engine_ref
    _executor = callback
    _engine_ref = engine


def _load():
    if not AUTOMATIONS_FILE.exists():
        return {"items": []}
    try:
        with open(AUTOMATIONS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if "items" not in data:
            data["items"] = []
        return data
    except Exception:
        return {"items": []}


def _save(data):
    tmp = str(AUTOMATIONS_FILE) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    Path(tmp).replace(AUTOMATIONS_FILE)


def list_all():
    return _load()["items"]


def find(name: str):
    name = name.strip().lower()
    for item in _load()["items"]:
        if item["name"].lower() == name:
            return item
    return None


def upsert(item: dict):
    with _lock:
        data = _load()
        existing_idx = None
        for i, it in enumerate(data["items"]):
            if it["name"].lower() == item["name"].lower():
                existing_idx = i
                break
        if existing_idx is not None:
            data["items"][existing_idx] = item
        else:
            data["items"].append(item)
        _save(data)


def delete(name: str) -> bool:
    name = name.strip().lower()
    with _lock:
        data = _load()
        n_before = len(data["items"])
        data["items"] = [it for it in data["items"] if it["name"].lower() != name]
        if len(data["items"]) != n_before:
            _save(data)
            return True
    return False


def set_enabled(name: str, enabled: bool) -> bool:
    name = name.strip().lower()
    with _lock:
        data = _load()
        for it in data["items"]:
            if it["name"].lower() == name:
                it["enabled"] = enabled
                _save(data)
                return True
    return False


# ============ Schedule parsing & evaluation ============

_DAYS = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6,
         "lun": 0, "mar": 1, "mer": 2, "gio": 3, "ven": 4, "sab": 5, "dom": 6}


def _parse_time(s: str):
    """Parse HH:MM -> (hour, minute)."""
    h, m = s.split(":")
    return int(h), int(m)


def _should_fire(item: dict, now: datetime) -> bool:
    """Determine if this routine should fire NOW."""
    if not item.get("enabled", True):
        return False
    schedule = item.get("schedule", "")
    last_run_iso = item.get("last_run")
    last_run = datetime.fromisoformat(last_run_iso) if last_run_iso else None

    try:
        if schedule.startswith("once "):
            target_str = schedule[5:].strip()
            target = datetime.fromisoformat(target_str)
            if now >= target and not last_run:
                return True
            return False

        if schedule.startswith("interval "):
            interval_str = schedule[9:].strip().lower()
            if interval_str.endswith("m"):
                mins = int(interval_str[:-1])
                delta = timedelta(minutes=mins)
            elif interval_str.endswith("h"):
                hrs = int(interval_str[:-1])
                delta = timedelta(hours=hrs)
            else:
                mins = int(interval_str)
                delta = timedelta(minutes=mins)
            if not last_run:
                return True
            return now - last_run >= delta

        parts = schedule.split(" ")
        if len(parts) != 2:
            return False
        kind, time_str = parts
        kind = kind.lower()
        h, m = _parse_time(time_str)

        target = now.replace(hour=h, minute=m, second=0, microsecond=0)
        # Only consider firing if we're at or past the target this minute
        if now < target:
            return False
        # Don't fire if more than 5 minutes have passed (avoid old triggers)
        if (now - target).total_seconds() > 5 * 60:
            # Allow catch-up if last_run is older than today's target
            if not last_run or last_run < target:
                pass  # still fire (catch-up for missed routine)
            else:
                return False

        # Filter by kind
        if kind == "daily":
            pass
        elif kind == "weekday":
            if now.weekday() >= 5:
                return False
        elif kind == "weekend":
            if now.weekday() < 5:
                return False
        elif kind in _DAYS:
            if now.weekday() != _DAYS[kind]:
                return False
        else:
            return False

        # Avoid double-fire same day
        if last_run and last_run >= target:
            return False
        return True

    except Exception:
        return False


def _mark_run(item: dict, when: datetime):
    name = item["name"]
    with _lock:
        data = _load()
        for it in data["items"]:
            if it["name"].lower() == name.lower():
                it["last_run"] = when.isoformat()
                it["run_count"] = it.get("run_count", 0) + 1
                break
        _save(data)


def _execute(item: dict):
    """Execute one automation by sending its command through the engine."""
    command = item.get("command", "")
    mode = item.get("mode", "voice")
    if not command or _executor is None:
        return
    try:
        _executor(command, mode, item.get("name"))
    except Exception:
        pass


# ============ Background scheduler thread ============

def background_loop(stop_event):
    """Check all automations every 30 seconds."""
    while not stop_event.is_set():
        try:
            now = datetime.now()
            for item in _load()["items"]:
                if _should_fire(item, now):
                    _mark_run(item, now)
                    # Execute in a separate thread so a slow one doesn't block others
                    threading.Thread(target=_execute, args=(item,), daemon=True).start()
        except Exception as e:
            print(f"[automations] {e}")
        # Sleep ~30s, but respond to stop quickly
        for _ in range(30):
            if stop_event.is_set():
                return
            _time.sleep(1)
