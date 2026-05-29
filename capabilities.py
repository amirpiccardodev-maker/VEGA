"""Capability registry semantico.

Sostituisce gradualmente smart_router.CATEGORY_MAP hardcoded.
Ogni tool ha embedding del 'description + examples'. Cerca via similarity.

API:
    register(name, description, examples=[], cost="free", tags=[])
    search(query, top_k=5)     -> list of tool names
    get(name)                   -> capability dict
    all()                       -> list

Persistenza: capabilities.json (definizioni), embeddings in-memory.
"""
import json
import threading
import os
from pathlib import Path

ROOT = Path(__file__).parent
CAP_FILE = ROOT / "capabilities.json"

_lock = threading.Lock()
_capabilities = {}  # name -> dict
_embeddings = None  # numpy array
_names = []         # parallel to _embeddings
_model = None


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
    return _model


def _load():
    if not CAP_FILE.exists():
        return {}
    try:
        with open(CAP_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save():
    tmp = str(CAP_FILE) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(_capabilities, f, ensure_ascii=False, indent=2)
    os.replace(tmp, CAP_FILE)


def register(name: str, description: str, examples: list = None,
             cost: str = "free", tags: list = None, output_kind: str = "text"):
    """Register or update a capability."""
    with _lock:
        _capabilities[name] = {
            "name": name,
            "description": description,
            "examples": examples or [],
            "cost": cost,
            "tags": tags or [],
            "output_kind": output_kind,
        }
        # Invalidate cache
        global _embeddings, _names
        _embeddings = None
        _names = []
    _save()


def get(name: str) -> dict:
    return _capabilities.get(name)


def all_capabilities() -> list:
    return list(_capabilities.values())


def _build_index():
    """Compute embeddings for all capabilities."""
    global _embeddings, _names
    if _embeddings is not None:
        return
    import numpy as np
    with _lock:
        if _embeddings is not None:
            return
        names = []
        texts = []
        for cap in _capabilities.values():
            ex = " ".join(cap.get("examples", []))
            text = f"{cap['description']} {ex}".strip()
            if text:
                names.append(cap["name"])
                texts.append(text)
        if not texts:
            _embeddings = np.zeros((0, 384), dtype=np.float32)
            _names = []
            return
        model = _get_model()
        embs = model.encode(texts, batch_size=32, show_progress_bar=False,
                            normalize_embeddings=True)
        _embeddings = np.asarray(embs, dtype=np.float32)
        _names = names


def search(query: str, top_k: int = 5, min_similarity: float = 0.30) -> list:
    """Return top-K tool names ranked by semantic similarity to query."""
    if not query:
        return []
    _build_index()
    if _embeddings is None or len(_embeddings) == 0:
        return []
    import numpy as np
    model = _get_model()
    q = model.encode([query], normalize_embeddings=True)
    q = np.asarray(q, dtype=np.float32)[0]
    sims = _embeddings @ q
    idx = np.argsort(-sims)[:top_k]
    out = []
    for i in idx:
        if float(sims[i]) >= min_similarity:
            out.append({"name": _names[int(i)], "similarity": float(sims[int(i)])})
    return out


def warm_up():
    """Build the index at startup so first query is fast."""
    _build_index()


# Load existing on import
_capabilities = _load()


# ============ Auto-registration from tool schemas ============

def auto_register_from_tools():
    """Walk through tool registry and register capabilities for any missing.
    Batch-save once at the end instead of per-tool."""
    try:
        import tools as tool_registry
        existing = set(_capabilities.keys())
        changed = False
        for schema in tool_registry.all_schemas():
            name = schema.get("name")
            if not name or name in existing:
                continue
            with _lock:
                _capabilities[name] = {
                    "name": name,
                    "description": schema.get("description", ""),
                    "examples": [],
                    "cost": "free",
                    "tags": [],
                    "output_kind": "text",
                }
            changed = True
        if changed:
            with _lock:
                global _embeddings, _names
                _embeddings = None
                _names = []
            _save()  # save once
    except Exception as e:
        print(f"[capabilities] auto-register error: {e}")
