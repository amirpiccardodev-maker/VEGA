"""Persistent memory: facts about the user, notes, reminders, conversation history."""
import json
import os
from datetime import datetime
from threading import Lock

MEM_FILE = os.path.join(os.path.dirname(__file__), "memory.json")
_lock = Lock()

_DEFAULT = {
    "user_facts": [],
    "notes": [],
    "todos": [],
    "reminders": [],
    "custom_instructions": [],
    "conversation_log": [],
    "last_briefing_date": None,
    "preferences": {
        "personality": "friendly",
        "language": "it",
        "voice": "it-IT-GiuseppeNeural",
        "voice_rate": "-3%",
        "voice_pitch": "+0Hz",
        "home_location": "",
        "mode": "general",
        "startup_music": True,
        "sounds_enabled": True,
        "privacy_mode": False,
    },
    "timers": {},
    "usage": {
        "total": {"input": 0, "output": 0, "cache_write": 0, "cache_read": 0, "calls": 0},
        "daily": {},
    },
    "tts_usage": {
        "elevenlabs": {"chars": 0, "monthly": {}},
        "edge": {"chars": 0},
    },
}


def _load():
    if not os.path.exists(MEM_FILE):
        return json.loads(json.dumps(_DEFAULT))
    try:
        import security
        # Read as bytes first to detect encryption
        with open(MEM_FILE, "rb") as f:
            raw = f.read()
        if security.is_encrypted_data(raw):
            text = security.decrypt(raw)
        else:
            text = raw.decode("utf-8")
        data = json.loads(text)
        for k, v in _DEFAULT.items():
            data.setdefault(k, v)
        return data
    except Exception:
        return json.loads(json.dumps(_DEFAULT))


def _save(data):
    # Atomic write: write to temp then rename so we never end up with a
    # half-written corrupt memory.json if the process dies mid-write.
    # If security.encrypt is configured, write encrypted bytes instead.
    import security
    text = json.dumps(data, ensure_ascii=False, indent=2)
    tmp = MEM_FILE + ".tmp"
    if security._cipher is not None:
        payload = security.encrypt(text)
        with open(tmp, "wb") as f:
            f.write(payload)
            f.flush()
            try: os.fsync(f.fileno())
            except Exception: pass
    else:
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            try: os.fsync(f.fileno())
            except Exception: pass
    os.replace(tmp, MEM_FILE)


def get_all() -> dict:
    with _lock:
        return _load()


def update(modifier):
    """modifier(data) -> data (mutating ok)."""
    with _lock:
        data = _load()
        modifier(data)
        _save(data)
        return data


def add_fact(fact: str):
    def m(d):
        d["user_facts"].append({"text": fact, "ts": datetime.now().isoformat()})
    update(m)


def get_facts() -> list:
    return get_all()["user_facts"]


def add_note(text: str):
    def m(d):
        d["notes"].append({"text": text, "ts": datetime.now().isoformat()})
    update(m)


def get_notes() -> list:
    return get_all()["notes"]


def add_todo(text: str):
    def m(d):
        d["todos"].append({"text": text, "done": False, "ts": datetime.now().isoformat()})
    update(m)


def get_todos(include_done: bool = False) -> list:
    todos = get_all()["todos"]
    return todos if include_done else [t for t in todos if not t.get("done")]


def complete_todo(index: int):
    def m(d):
        todos = [t for t in d["todos"] if not t.get("done")]
        if 0 <= index < len(todos):
            target = todos[index]
            for t in d["todos"]:
                if t is target or (t["text"] == target["text"] and t["ts"] == target["ts"]):
                    t["done"] = True
                    break
    update(m)


def add_reminder(text: str, when_iso: str):
    def m(d):
        d["reminders"].append({"text": text, "when": when_iso, "fired": False, "ts": datetime.now().isoformat()})
    update(m)


def get_pending_reminders() -> list:
    now = datetime.now()
    out = []
    for r in get_all()["reminders"]:
        if r.get("fired"):
            continue
        try:
            when = datetime.fromisoformat(r["when"])
            if when <= now:
                out.append(r)
        except Exception:
            pass
    return out


def fire_reminder(reminder: dict):
    def m(d):
        for r in d["reminders"]:
            if r["text"] == reminder["text"] and r["when"] == reminder["when"]:
                r["fired"] = True
                break
    update(m)


def log_exchange(user: str, assistant: str):
    # Privacy mode: skip logging conversation content
    import security
    if not security.should_log_conversation():
        return
    def m(d):
        d["conversation_log"].append({
            "ts": datetime.now().isoformat(),
            "user": user,
            "assistant": assistant,
        })
        d["conversation_log"] = d["conversation_log"][-200:]
    update(m)


def get_preferences() -> dict:
    return get_all()["preferences"]


def set_preference(key: str, value):
    def m(d):
        d["preferences"][key] = value
    update(m)


def add_instruction(text: str):
    def m(d):
        d.setdefault("custom_instructions", []).append({"text": text, "ts": datetime.now().isoformat()})
    update(m)


def get_instructions() -> list:
    return get_all().get("custom_instructions", [])


def remove_instruction(index: int):
    def m(d):
        items = d.get("custom_instructions", [])
        if 0 <= index < len(items):
            del items[index]
    update(m)


def record_usage(input_tokens: int = 0, output_tokens: int = 0,
                 cache_write: int = 0, cache_read: int = 0):
    today = datetime.now().date().isoformat()

    def m(d):
        u = d.setdefault("usage", {"total": {}, "daily": {}})
        for bucket in (u.setdefault("total", {}), u.setdefault("daily", {}).setdefault(today, {})):
            bucket["input"] = bucket.get("input", 0) + input_tokens
            bucket["output"] = bucket.get("output", 0) + output_tokens
            bucket["cache_write"] = bucket.get("cache_write", 0) + cache_write
            bucket["cache_read"] = bucket.get("cache_read", 0) + cache_read
            bucket["calls"] = bucket.get("calls", 0) + 1
        # Keep only last 60 days of daily logs
        dailies = u["daily"]
        if len(dailies) > 60:
            keep = sorted(dailies.keys())[-60:]
            u["daily"] = {k: dailies[k] for k in keep}
    update(m)


# Prices Claude Sonnet 4.5 (USD per million tokens)
_PRICE_INPUT = 3.0
_PRICE_OUTPUT = 15.0
_PRICE_CACHE_WRITE = 3.75
_PRICE_CACHE_READ = 0.30


def estimate_cost(usage: dict) -> float:
    return (
        usage.get("input", 0) * _PRICE_INPUT
        + usage.get("output", 0) * _PRICE_OUTPUT
        + usage.get("cache_write", 0) * _PRICE_CACHE_WRITE
        + usage.get("cache_read", 0) * _PRICE_CACHE_READ
    ) / 1_000_000


def _cache_hit_rate(usage: dict) -> float:
    """Returns 0..1: cache_read / (cache_read + input). 0 if no cache used yet."""
    cr = usage.get("cache_read", 0) or 0
    inp = usage.get("input", 0) or 0
    total = cr + inp
    if total == 0:
        return 0.0
    return round(cr / total, 4)


def _cache_savings_usd(usage: dict) -> float:
    """How much we saved vs paying full price for the cache_read tokens."""
    cr = usage.get("cache_read", 0) or 0
    return round(cr * (_PRICE_INPUT - _PRICE_CACHE_READ) / 1_000_000, 4)


def get_usage_summary() -> dict:
    data = get_all().get("usage", {"total": {}, "daily": {}})
    today = datetime.now().date().isoformat()
    today_usage = data.get("daily", {}).get(today, {})
    total = data.get("total", {})
    return {
        "today": today_usage,
        "today_cost_usd": estimate_cost(today_usage),
        "today_cache_hit_rate": _cache_hit_rate(today_usage),
        "today_cache_savings_usd": _cache_savings_usd(today_usage),
        "total": total,
        "total_cost_usd": estimate_cost(total),
        "total_cache_hit_rate": _cache_hit_rate(total),
        "total_cache_savings_usd": _cache_savings_usd(total),
    }


def get_cache_metrics() -> dict:
    """Dedicated cache metrics endpoint payload."""
    data = get_all().get("usage", {"total": {}, "daily": {}})
    today = datetime.now().date().isoformat()
    today_u = data.get("daily", {}).get(today, {})
    total = data.get("total", {})
    # Last 7 days breakdown
    dailies = data.get("daily", {})
    last7 = []
    from datetime import timedelta
    base = datetime.now().date()
    for i in range(7):
        d = (base - timedelta(days=i)).isoformat()
        u = dailies.get(d, {})
        last7.append({
            "date": d,
            "cache_read": u.get("cache_read", 0),
            "cache_write": u.get("cache_write", 0),
            "input": u.get("input", 0),
            "hit_rate": _cache_hit_rate(u),
            "savings_usd": _cache_savings_usd(u),
        })
    return {
        "today": {
            "cache_read": today_u.get("cache_read", 0),
            "cache_write": today_u.get("cache_write", 0),
            "input": today_u.get("input", 0),
            "hit_rate": _cache_hit_rate(today_u),
            "savings_usd": _cache_savings_usd(today_u),
        },
        "total": {
            "cache_read": total.get("cache_read", 0),
            "cache_write": total.get("cache_write", 0),
            "input": total.get("input", 0),
            "hit_rate": _cache_hit_rate(total),
            "savings_usd": _cache_savings_usd(total),
        },
        "last7": list(reversed(last7)),
    }


def record_tts_chars(provider: str, chars: int):
    month = datetime.now().strftime("%Y-%m")

    def m(d):
        t = d.setdefault("tts_usage", {})
        prov = t.setdefault(provider, {})
        prov["chars"] = prov.get("chars", 0) + chars
        if provider == "elevenlabs":
            monthly = prov.setdefault("monthly", {})
            monthly[month] = monthly.get(month, 0) + chars
    update(m)


def get_tts_usage() -> dict:
    data = get_all().get("tts_usage", {})
    month = datetime.now().strftime("%Y-%m")
    eleven = data.get("elevenlabs", {})
    return {
        "elevenlabs_total": eleven.get("chars", 0),
        "elevenlabs_this_month": eleven.get("monthly", {}).get(month, 0),
        "edge_total": data.get("edge", {}).get("chars", 0),
    }


def briefing_done_today() -> bool:
    last = get_all().get("last_briefing_date")
    return last == datetime.now().date().isoformat()


def mark_briefing_done():
    def m(d):
        d["last_briefing_date"] = datetime.now().date().isoformat()
    update(m)
