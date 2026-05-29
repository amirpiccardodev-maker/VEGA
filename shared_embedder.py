"""Singleton sentence-transformers model shared across all consumers.

Prima c'erano 3 caricamenti separati (memory_graph, capabilities, Mem0, semantic_shortcuts).
Ora uno solo, condiviso. Risparmia ~150MB RAM + 4-6s di import al boot.
"""
import threading


_model = None
_lock = threading.Lock()
MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"


def get():
    """Returns the shared SentenceTransformer instance, loading lazily."""
    global _model
    if _model is not None:
        return _model
    with _lock:
        if _model is not None:
            return _model
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(MODEL_NAME)
    return _model


def warm_up_async():
    """Spawn thread to load model in background without blocking."""
    threading.Thread(target=get, daemon=True, name="embedder_warmup").start()


def is_loaded() -> bool:
    return _model is not None
