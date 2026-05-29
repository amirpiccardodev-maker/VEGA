"""Episodic memory via Mem0.

Strato sopra mem0ai che:
  - configura Mem0 con Anthropic (Haiku) come LLM di estrazione fatti
  - Chroma come vector store (local, no DB esterno)
  - HuggingFace sentence-transformers per embeddings (riusa modello già scaricato)
  - Espone API minimale: add(messages), search(query), recall_context(query)

Storage: ~/.vega_mem0/  (separato da memory_graph esistente)

Filosofia: Mem0 estrae automaticamente fatti, preferenze, contesto rilevante
dalle conversazioni. Niente più "ricordati che..." manuale.
"""
import os
import threading
from pathlib import Path

import config


_lock = threading.Lock()
_memory = None  # lazy singleton
_init_error = None
_user_id = "amir"

STORAGE_DIR = Path.home() / ".vega_mem0"

# One-time migration from the pre-rebrand directory so existing memories survive.
_legacy_dir = Path.home() / ".jarvis_mem0"
if _legacy_dir.exists() and not STORAGE_DIR.exists():
    try:
        _legacy_dir.rename(STORAGE_DIR)
    except OSError:
        pass

STORAGE_DIR.mkdir(exist_ok=True)


def _build_config() -> dict:
    """Configurazione Mem0: tutto locale tranne LLM (Haiku via API key esistente)."""
    return {
        "llm": {
            "provider": "anthropic",
            "config": {
                "model": "claude-haiku-4-5",
                "api_key": config.ANTHROPIC_API_KEY,
                "temperature": 0.0,
                "max_tokens": 1500,
            },
        },
        "embedder": {
            "provider": "huggingface",
            "config": {
                "model": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
            },
        },
        "vector_store": {
            "provider": "chroma",
            "config": {
                "collection_name": "vega_episodic",
                "path": str(STORAGE_DIR / "chroma"),
            },
        },
        "version": "v1.1",
    }


def get_memory():
    """Lazy-init the Mem0 singleton. Returns None if init failed."""
    global _memory, _init_error
    if _memory is not None:
        return _memory
    if _init_error is not None:
        return None  # already failed, don't keep retrying
    with _lock:
        if _memory is not None:
            return _memory
        try:
            from mem0 import Memory
            _memory = Memory.from_config(_build_config())
            print("[episodic_memory] Mem0 initialized")
        except Exception as e:
            _init_error = str(e)
            print(f"[episodic_memory] init failed: {e}")
            return None
    return _memory


def _kw_user():
    """Returns the right kwargs for Mem0 v1.1+ API which moved user_id under filters."""
    return {"filters": {"user_id": _user_id}}


def add(messages, metadata: dict = None):
    """Add a conversation exchange. messages = [{"role":"user","content":...},
    {"role":"assistant","content":...}] or a single string.

    Mem0 estrarrà fatti/preferenze automaticamente in background."""
    m = get_memory()
    if m is None:
        return None
    try:
        if isinstance(messages, str):
            messages = [{"role": "user", "content": messages}]
        # Mem0 v1.1 supports user_id top-level for add() (it's per-entity)
        return m.add(messages, user_id=_user_id, metadata=metadata or {})
    except Exception as e:
        # Fallback to filters API
        try:
            return m.add(messages, metadata=metadata or {}, **_kw_user())
        except Exception as e2:
            print(f"[episodic_memory] add error: {e} / fallback: {e2}")
            return None


def search(query: str, limit: int = 5) -> list:
    """Cerca memorie rilevanti per la query."""
    m = get_memory()
    if m is None:
        return []
    try:
        res = m.search(query=query, limit=limit, **_kw_user())
        if isinstance(res, dict):
            res = res.get("results", [])
        return res or []
    except Exception as e:
        print(f"[episodic_memory] search error: {e}")
        return []


def recall_context(query: str, max_chars: int = 800) -> str:
    """Restituisce un blocco di testo pronto per essere iniettato nel system prompt.
    Vuoto se non c'è nulla di rilevante."""
    results = search(query, limit=5)
    if not results:
        # Aiuta Claude a NON dire "non ricordo": se memoria vuota,
        # suggerisce di MEMORIZZARE ora
        m = get_memory()
        if m is not None:
            return ("NOTA MEMORIA: non ho memoria diretta su questo argomento. "
                    "Se l'utente fornisce dettagli nella conversazione, "
                    "potresti memorizzarli con remember_fact() per il futuro.")
        return ""
    lines = []
    for r in results:
        if isinstance(r, dict):
            text = r.get("memory") or r.get("text") or r.get("content") or ""
            score = r.get("score") or r.get("similarity")
        else:
            text = str(r)
            score = None
        if not text:
            continue
        if score is not None and score < 0.30:
            continue
        lines.append(f"- {text.strip()}")
    if not lines:
        return ""
    block = "\n".join(lines)
    if len(block) > max_chars:
        block = block[:max_chars - 3] + "..."
    return "MEMORIE RILEVANTI SU AMIR (Mem0):\n" + block


def stats() -> dict:
    m = get_memory()
    if m is None:
        return {"available": False, "error": _init_error}
    try:
        all_mem = m.get_all(**_kw_user())
        if isinstance(all_mem, dict):
            all_mem = all_mem.get("results", [])
        return {
            "available": True,
            "total": len(all_mem) if all_mem else 0,
            "user_id": _user_id,
        }
    except Exception as e:
        return {"available": True, "error": str(e)}


def list_all(limit: int = 50) -> list:
    """Lista tutte le memorie (per UI panel)."""
    m = get_memory()
    if m is None:
        return []
    try:
        res = m.get_all(**_kw_user())
        if isinstance(res, dict):
            res = res.get("results", [])
        return (res or [])[:limit]
    except Exception as e:
        print(f"[episodic_memory] list_all error: {e}")
        return []


def delete(memory_id: str) -> bool:
    m = get_memory()
    if m is None:
        return False
    try:
        m.delete(memory_id=memory_id)
        return True
    except Exception as e:
        print(f"[episodic_memory] delete error: {e}")
        return False


def warm_up():
    """Pre-init in background al boot."""
    threading.Thread(target=get_memory, daemon=True).start()
