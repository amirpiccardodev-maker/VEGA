"""In-memory cache for tool results that don't change often.

Caches things like meteo (10 min), news (7 min), sports (10 min), wikipedia
(forever within session). Saves both time AND tokens (no re-fetching).
"""
import time
import hashlib
import json

_CACHE = {}

# tool_name -> ttl seconds (None = forever in session)
CACHE_TTLS = {
    "get_weather": 600,        # 10 min
    "get_news": 420,           # 7 min
    "sports_news": 600,        # 10 min
    "stock_quote": 60,         # 1 min
    "wikipedia": 86400,        # 24 hours (rarely changes)
    "youtube_search": 1800,    # 30 min
    "list_emails": 90,         # 1.5 min (emails arrive often)
    "summarize_inbox": 90,
}


# Tool schema versions: bump per invalidare cache quando lo schema cambia.
# Aggiungere qui quando si cambia args/output di un tool.
TOOL_VERSIONS = {
    "get_weather": "v2",       # bumped: nuovo formato forecast
    "get_news": "v2",          # bumped: aggiunto per_source
    "list_emails": "v1",
    "summarize_inbox": "v1",
    "ask_recent_news": "v1",
    "wikipedia": "v1",
    "web_search": "v1",
    "web_images": "v1",
}


def _version_of(tool_name: str) -> str:
    return TOOL_VERSIONS.get(tool_name, "v1")


def _key(tool_name: str, args: dict) -> str:
    blob = json.dumps(args, sort_keys=True, default=str)[:200]
    version = _version_of(tool_name)
    return f"{tool_name}@{version}::{hashlib.md5(blob.encode()).hexdigest()[:12]}"


def invalidate_tool(tool_name: str) -> int:
    """Remove all cache entries for a specific tool. Returns count cleared."""
    prefix = f"{tool_name}@"
    keys = [k for k in _CACHE.keys() if k.startswith(prefix)]
    for k in keys:
        _CACHE.pop(k, None)
    return len(keys)


def get(tool_name: str, args: dict):
    ttl = CACHE_TTLS.get(tool_name)
    if ttl is None:
        return None  # not a cached tool
    k = _key(tool_name, args)
    entry = _CACHE.get(k)
    if not entry:
        return None
    ts, val = entry
    if time.time() - ts > ttl:
        _CACHE.pop(k, None)
        return None
    return val


def put(tool_name: str, args: dict, value):
    if tool_name not in CACHE_TTLS:
        return
    k = _key(tool_name, args)
    _CACHE[k] = (time.time(), value)


def clear():
    _CACHE.clear()


def stats() -> dict:
    return {"entries": len(_CACHE), "tools": list(set(k.split("::")[0] for k in _CACHE))}
