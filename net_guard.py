"""Network egress firewall: domain allowlist + outbound logging.

Monkey-patches socket.getaddrinfo (the chokepoint of all network DNS resolution
in Python stdlib + most libs) to:
  - check destination host against allowlist
  - log every outbound connection (with hash of dest, no full URL)
  - block if not allowlisted (when strict_mode=True)

Modalità:
  - "observe" (default): logga ma non blocca
  - "strict": blocca outbound non-allowlistato

L'allowlist è data/net_allowlist.json, creato con default sensati al boot.
"""
import json
import socket
import threading
import time
from pathlib import Path

import bus


ROOT = Path(__file__).parent
ALLOW_FILE = ROOT / "data" / "net_allowlist.json"
LOG_FILE = ROOT / "data" / "outbound.log.jsonl"
ALLOW_FILE.parent.mkdir(parents=True, exist_ok=True)


# Default allowlist: solo i domini effettivamente usati da Vega
DEFAULT_ALLOWLIST = [
    # Anthropic
    "api.anthropic.com",
    # ElevenLabs
    "api.elevenlabs.io",
    # Hugging Face (modelli embedding)
    "huggingface.co", "cdn-lfs.huggingface.co", "cdn-lfs.hf.co",
    "*.huggingface.co", "*.hf.co",
    # Whisper / faster-whisper / openwakeword cache
    "models.silero.ai",
    # Pollinations image gen
    "image.pollinations.ai", "pollinations.ai",
    # DuckDuckGo search
    "duckduckgo.com", "html.duckduckgo.com", "*.duckduckgo.com",
    "links.duckduckgo.com",
    # News feeds (default)
    "www.ansa.it", "www.repubblica.it", "www.ilpost.it",
    "news.ycombinator.com", "feeds.bbci.co.uk", "www.bbc.co.uk",
    # Wikipedia
    "*.wikipedia.org", "*.wikimedia.org",
    # Weather
    "api.open-meteo.com", "geocoding-api.open-meteo.com",
    # Ollama (local, ma per sicurezza listato)
    "localhost", "127.0.0.1",
    # Gmail SMTP
    "smtp.gmail.com",
    # NTP / time
    "time.windows.com", "pool.ntp.org",
    # YouTube transcript (se utilizzato)
    "*.youtube.com", "www.youtube.com", "youtube.com",
    # Web Push providers
    "*.push.services.mozilla.com", "*.googleapis.com", "*.windows.com",
    "fcm.googleapis.com",
]


_lock = threading.Lock()
_mode = "observe"  # "observe" | "strict" | "off"
_allowlist_cache = None
_orig_getaddrinfo = None
_installed = False


def _load_allowlist() -> list:
    global _allowlist_cache
    if _allowlist_cache is not None:
        return _allowlist_cache
    if not ALLOW_FILE.exists():
        with open(ALLOW_FILE, "w", encoding="utf-8") as f:
            json.dump({"hosts": DEFAULT_ALLOWLIST, "mode": "observe"},
                      f, ensure_ascii=False, indent=2)
        _allowlist_cache = list(DEFAULT_ALLOWLIST)
        return _allowlist_cache
    try:
        with open(ALLOW_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        _allowlist_cache = data.get("hosts", DEFAULT_ALLOWLIST)
        global _mode
        _mode = data.get("mode", "observe")
    except Exception:
        _allowlist_cache = list(DEFAULT_ALLOWLIST)
    return _allowlist_cache


def _save_allowlist():
    with open(ALLOW_FILE, "w", encoding="utf-8") as f:
        json.dump({"hosts": _allowlist_cache, "mode": _mode},
                  f, ensure_ascii=False, indent=2)


def _matches(host: str, pattern: str) -> bool:
    """Match host against allowlist entry. Supports leading wildcard '*.'"""
    if not host or not pattern:
        return False
    if pattern == host:
        return True
    if pattern.startswith("*."):
        suffix = pattern[1:]  # ".huggingface.co"
        if host.endswith(suffix):
            return True
    return False


def is_allowed(host: str) -> bool:
    if not host:
        return False
    # IP literals on private/local ranges always allowed
    if host.startswith(("127.", "10.", "192.168.", "::1")):
        return True
    if host.startswith("172."):
        try:
            if 16 <= int(host.split(".")[1]) <= 31:
                return True
        except Exception:
            pass
    allowlist = _load_allowlist()
    for entry in allowlist:
        if _matches(host, entry):
            return True
    return False


def _log_outbound(host: str, allowed: bool):
    """Append to outbound log + publish on bus (no full URL, host only)."""
    entry = {"ts": int(time.time()), "host": host, "allowed": allowed}
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass
    bus.publish("net.outbound", entry)


def _wrapped_getaddrinfo(host, *args, **kwargs):
    """Intercepted getaddrinfo. Enforces allowlist when mode==strict."""
    try:
        allowed = is_allowed(host) if host else True
        if _mode != "off":
            _log_outbound(str(host), allowed)
        if _mode == "strict" and not allowed:
            bus.publish("net.blocked", {"host": str(host)})
            raise socket.gaierror(socket.EAI_FAIL, f"Blocked by Vega net_guard: {host}")
    except socket.gaierror:
        raise
    except Exception:
        pass
    return _orig_getaddrinfo(host, *args, **kwargs)


def install():
    """Activate the firewall (monkey-patch socket.getaddrinfo)."""
    global _installed, _orig_getaddrinfo
    if _installed:
        return
    _orig_getaddrinfo = socket.getaddrinfo
    socket.getaddrinfo = _wrapped_getaddrinfo
    _installed = True
    _load_allowlist()
    bus.publish("net_guard.installed", {"mode": _mode, "hosts": len(_load_allowlist())})


def uninstall():
    global _installed
    if _installed and _orig_getaddrinfo:
        socket.getaddrinfo = _orig_getaddrinfo
        _installed = False


def set_mode(mode: str) -> bool:
    global _mode
    if mode not in ("observe", "strict", "off"):
        return False
    _mode = mode
    _save_allowlist()
    return True


def add_host(host: str) -> bool:
    al = _load_allowlist()
    if host in al:
        return False
    al.append(host)
    _save_allowlist()
    return True


def remove_host(host: str) -> bool:
    al = _load_allowlist()
    if host in al:
        al.remove(host)
        _save_allowlist()
        return True
    return False


def status() -> dict:
    return {
        "installed": _installed,
        "mode": _mode,
        "hosts_count": len(_load_allowlist()),
        "hosts": _load_allowlist()[:50],
    }


def recent_outbound(limit: int = 50) -> list:
    """Last N outbound log entries."""
    if not LOG_FILE.exists():
        return []
    out = []
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            for line in f.readlines()[-limit:]:
                try:
                    out.append(json.loads(line))
                except Exception:
                    pass
    except Exception:
        pass
    return out
