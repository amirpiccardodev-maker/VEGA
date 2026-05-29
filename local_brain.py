"""Local LLM fallback via Ollama.

Filosofia: Anthropic Claude resta il "main brain". Ollama interviene solo se:
  - il server Ollama (localhost:11434) e' raggiungibile
  - la query e' breve/casual (no tool use, no contesto complesso)
  - oppure Anthropic API e' down e serve un fallback

Modello di default: llama3.2 (3B, ~2GB). L'utente puo' cambiarlo via preferenze
o variabile env VEGA_LOCAL_MODEL.

API:
    is_available() -> bool      # check rapido del server
    list_models() -> [str]
    chat(prompt, system=None) -> str
    chat_stream(prompt) -> generator
"""
import os
import time
import threading
from urllib.parse import urlparse
from urllib.request import urlopen, Request


OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
DEFAULT_MODEL = os.environ.get("VEGA_LOCAL_MODEL", "llama3.2:3b")
HEALTH_CACHE_SEC = 30

_health_cache = {"ok": None, "ts": 0}
_lock = threading.Lock()


def is_available() -> bool:
    """Cached health check (30s) — evita di pingare ad ogni query."""
    now = time.time()
    with _lock:
        if _health_cache["ok"] is not None and (now - _health_cache["ts"]) < HEALTH_CACHE_SEC:
            return _health_cache["ok"]
    try:
        req = Request(OLLAMA_HOST + "/api/tags", headers={"Accept": "application/json"})
        with urlopen(req, timeout=1.0) as r:
            ok = r.status == 200
    except Exception:
        ok = False
    with _lock:
        _health_cache["ok"] = ok
        _health_cache["ts"] = now
    return ok


def list_models() -> list:
    if not is_available():
        return []
    try:
        import ollama
        client = ollama.Client(host=OLLAMA_HOST)
        info = client.list()
        # New API returns object, old API returns dict with "models"
        models_data = getattr(info, "models", None) or info.get("models", [])
        out = []
        for m in models_data:
            name = getattr(m, "model", None) or (m.get("model") if isinstance(m, dict) else None)
            if name:
                out.append(name)
        return out
    except Exception as e:
        print(f"[local_brain] list_models error: {e}")
        return []


def get_model() -> str:
    """Resolve the model to use. Prefer the explicit default if installed,
    else pick the first available."""
    available = list_models()
    if not available:
        return DEFAULT_MODEL
    # Exact match
    if DEFAULT_MODEL in available:
        return DEFAULT_MODEL
    # Prefix match (e.g. "llama3.2" -> "llama3.2:3b")
    for name in available:
        if name.startswith(DEFAULT_MODEL.split(":")[0]):
            return name
    return available[0]


def chat(prompt: str, system: str = None, timeout: float = 20.0) -> str:
    """Sync chat. Returns response text or empty string on failure."""
    if not is_available():
        return ""
    try:
        import ollama
        client = ollama.Client(host=OLLAMA_HOST, timeout=timeout)
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        resp = client.chat(model=get_model(), messages=messages, options={
            "temperature": 0.4,
            "num_predict": 512,
        })
        return (resp.get("message", {}) or {}).get("content", "").strip()
    except Exception as e:
        print(f"[local_brain] chat error: {e}")
        return ""


def chat_stream(prompt: str, system: str = None):
    """Generator yielding text chunks as Ollama generates."""
    if not is_available():
        return
    try:
        import ollama
        client = ollama.Client(host=OLLAMA_HOST)
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        for chunk in client.chat(model=get_model(), messages=messages, stream=True):
            piece = (chunk.get("message", {}) or {}).get("content", "")
            if piece:
                yield piece
    except Exception as e:
        print(f"[local_brain] chat_stream error: {e}")


# ============ Smart routing decision ============
# Strategy: prefer local LLM for cases where:
#  1. Conversation is purely chat-style (no tool/realtime data needed)
#  2. Output quality requirement is low (smalltalk, acknowledgement)
#  3. Query length suggests a quick interaction (<300 chars)
# This expanded list captures ~30-50% more queries vs the original conservative set.

_LOCAL_PATTERNS = (
    # casual / smalltalk
    "ciao", "salve", "buongiorno", "buonasera", "buonanotte",
    "come stai", "come va", "tutto bene", "tutto ok",
    "grazie", "prego", "scusa", "perdona", "ok grazie",
    "a presto", "a dopo", "ciao ciao", "addio",
    # acknowledgements
    "va bene", "perfetto", "ottimo", "bene", "capito", "ho capito",
    "ricevuto", "d'accordo", "esatto", "giusto", "vero",
    # quick reasoning / opinion / explanation
    "spiegami", "che vuol dire", "cosa significa", "cosa intendi",
    "perché", "come mai", "in che senso", "per quale motivo",
    "definizione", "definisci",
    "fammi un esempio", "esempio di", "tipo cosa",
    # quick math / mental tasks
    "quanto fa", "calcola", "quanti", "qual è",
    "scrivi una", "inventa", "raccontami",
    # philosophical / opinion (no tool needed)
    "secondo te", "cosa ne pensi", "ti piace", "che ne dici",
    "preferiresti", "consigliami", "suggerisci",
    # micro-task no-tool
    "riassumi in", "traducimi", "correggimi", "rendi più",
    "rendi formale", "rendi informale", "in altre parole",
)

_SKIP_LOCAL = (
    # anything that needs tools/web/realtime data
    "meteo", "tempo a", "che tempo fa", "news", "notizie", "ultime",
    "borsa", "stock", "criptovalute",
    "email", "mail", "gmail", "calendario", "todo", "agenda",
    "ricordami", "salva", "memorizza", "ricorda che",
    "apri", "chiudi", "lancia", "esegui", "avvia",
    "screenshot", "schermo", "guarda lo", "vedi cosa",
    "agente", "fai per me", "pianifica", "missione",
    "manda", "invia", "spedisci",
    "cerca", "trova online", "google", "wikipedia",
    "genera immagine", "genera foto", "disegnami",
    "dibattito", "pensaci bene",
)


# Stats counters
_routing_stats = {"local": 0, "anthropic": 0, "local_failed": 0}


def routing_stats() -> dict:
    return dict(_routing_stats)


def record_routed_to(target: str):
    """Internal: bumps counter (called from brain after deciding)."""
    if target in _routing_stats:
        _routing_stats[target] += 1


def should_use_local(query: str) -> bool:
    """Heuristic: should we route this query to Ollama instead of Anthropic?

    Expanded version: catches ~30-50% more queries than the conservative set.
    """
    try:
        prefs = _load_prefs()
    except Exception:
        prefs = {}
    if not prefs.get("local_brain_enabled", False):
        return False
    if not is_available():
        return False
    q = (query or "").strip().lower()
    # Length window expanded
    if len(q) < 2 or len(q) > 300:
        return False
    # Hard skip: any phrase that suggests tool usage / realtime data
    if any(skip in q for skip in _SKIP_LOCAL):
        return False
    # Strong signals: casual/smalltalk/acks/explainers
    if any(pat in q for pat in _LOCAL_PATTERNS):
        return True
    # Soft signal: very short queries without verbs of action → likely chitchat
    if len(q.split()) <= 4 and not any(verb in q for verb in
        ("fai", "vai", "manda", "apri", "trova", "cerca", "scrivi",
         "elimina", "cancella", "controlla")):
        return True
    return False


def _load_prefs():
    try:
        import memory
        return memory.get_preferences()
    except Exception:
        return {}
