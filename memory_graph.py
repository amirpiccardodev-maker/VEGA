"""Memory graph: SQLite con embeddings per recall semantico unificato.

Sostituisce gradualmente i blob in memory.json mantenendo wrapper compat.

Kinds:
  - fact          (cose su Amir)
  - note          (info salvate manualmente)
  - todo          (task da fare)
  - instruction   (regole comportamentali)
  - conversation  (turni passati)
  - procedure     (workflow imparati / pattern desktop)
  - episodic      (eventi temporali rilevanti)

API:
    add(kind, content, importance=0.5, tags=None, source=None) -> id
    search(query, kinds=None, top_k=5) -> list[dict]
    get(id) -> dict
    update(id, **fields)
    delete(id)
    prune(kind, older_than_days, keep_top)
    consolidate()  # nightly job

NB: NON sostituisce memory.json di colpo. Dual-write opzionale (vedi memory.py).
"""
import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).parent
DB_PATH = ROOT / "memory_graph.db"

_lock = threading.RLock()
_conn = None
_model = None


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
    return _model


def _embed(text: str) -> bytes:
    """Compute embedding and return as bytes for SQLite storage."""
    import numpy as np
    model = _get_model()
    vec = model.encode([text], normalize_embeddings=True)[0]
    return np.asarray(vec, dtype=np.float32).tobytes()


def _decode_emb(b: bytes):
    import numpy as np
    return np.frombuffer(b, dtype=np.float32)


def _get_conn():
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(str(DB_PATH), check_same_thread=False, timeout=30.0)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("PRAGMA synchronous=NORMAL")
        _conn.execute("PRAGMA busy_timeout=30000")
        _conn.execute("PRAGMA journal_size_limit=104857600")  # 100MB cap
        _conn.execute("PRAGMA temp_store=MEMORY")
        _conn.execute("PRAGMA cache_size=-20000")  # 20MB cache
        _conn.execute("""
            CREATE TABLE IF NOT EXISTS memory_records (
                id           TEXT PRIMARY KEY,
                kind         TEXT NOT NULL,
                content      TEXT NOT NULL,
                embedding    BLOB,
                created_at   INTEGER,
                updated_at   INTEGER,
                importance   REAL DEFAULT 0.5,
                ttl_at       INTEGER,
                tags         TEXT,
                source       TEXT,
                meta         TEXT
            )
        """)
        _conn.execute("CREATE INDEX IF NOT EXISTS idx_kind ON memory_records(kind)")
        _conn.execute("CREATE INDEX IF NOT EXISTS idx_importance ON memory_records(importance DESC)")
        # Migration: add tenant_id column if missing (multi-tenant support)
        try:
            cols = [c[1] for c in _conn.execute("PRAGMA table_info(memory_records)").fetchall()]
            if "tenant_id" not in cols:
                _conn.execute("ALTER TABLE memory_records ADD COLUMN tenant_id TEXT")
                _conn.execute("CREATE INDEX IF NOT EXISTS idx_tenant ON memory_records(tenant_id)")
        except Exception:
            pass
        _conn.execute("""
            CREATE TABLE IF NOT EXISTS memory_links (
                from_id TEXT,
                to_id   TEXT,
                type    TEXT,
                weight  REAL DEFAULT 1.0,
                PRIMARY KEY (from_id, to_id, type)
            )
        """)
        _conn.commit()
    return _conn


def add(kind: str, content: str, importance: float = 0.5,
        tags: list = None, source: str = None, ttl_sec: int = None,
        meta: dict = None) -> str:
    """Insert a record. Returns id."""
    if not content or not content.strip():
        return None
    now = int(time.time())
    rid = uuid.uuid4().hex[:16]
    ttl_at = (now + ttl_sec) if ttl_sec else None
    try:
        emb = _embed(content[:1000])
    except Exception:
        emb = None
    conn = _get_conn()
    tenant_id = (meta or {}).get("tenant_id") if isinstance(meta, dict) else None
    with _lock:
        try:
            conn.execute("""
                INSERT INTO memory_records (id, kind, content, embedding, created_at, updated_at,
                                           importance, ttl_at, tags, source, meta, tenant_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (rid, kind, content[:5000], emb, now, now, importance, ttl_at,
                  json.dumps(tags) if tags else None, source,
                  json.dumps(meta) if meta else None, tenant_id))
        except Exception:
            # Fallback for older schema without tenant_id
            conn.execute("""
                INSERT INTO memory_records (id, kind, content, embedding, created_at, updated_at,
                                           importance, ttl_at, tags, source, meta)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (rid, kind, content[:5000], emb, now, now, importance, ttl_at,
                  json.dumps(tags) if tags else None, source,
                  json.dumps(meta) if meta else None))
        conn.commit()
    return rid


import math as _math


def _freshness_boost(created_at: int) -> float:
    """Multiplier 1.0..1.2 based on age. Items <7d get 1.2, <30d 1.1, else 1.0."""
    try:
        age_days = (int(time.time()) - int(created_at or 0)) / 86400.0
    except Exception:
        return 1.0
    if age_days < 0:
        return 1.0
    if age_days < 7:
        return 1.20
    if age_days < 30:
        return 1.10
    if age_days < 90:
        return 1.05
    return 1.0


def _importance_decay(importance: float, created_at: int) -> float:
    """Exponential decay: importance halves after ~365 days, asymptote at 0.1.

    Returns adjusted importance for ranking. Original value in DB unchanged.
    """
    try:
        age_days = (int(time.time()) - int(created_at or 0)) / 86400.0
    except Exception:
        return importance or 0.5
    base = float(importance or 0.5)
    if age_days <= 0:
        return base
    # Decay rate: half-life 365 days
    decay = _math.exp(-_math.log(2) * age_days / 365.0)
    # Floor at 0.1 * original (very old facts still count a little)
    return max(0.1 * base, base * decay)


def search(query: str, kinds: list = None, top_k: int = 5,
           min_similarity: float = 0.40, tenant_id: str = None) -> list:
    """Semantic search across memory.

    Scoring: similarity * (0.6 + 0.4 * decayed_importance) * freshness_boost
    """
    if not query:
        return []
    import numpy as np
    conn = _get_conn()
    q_emb = _decode_emb(_embed(query))

    where = "embedding IS NOT NULL"
    params = []
    if kinds:
        ph = ",".join("?" * len(kinds))
        where += f" AND kind IN ({ph})"
        params = list(kinds)
    # Multi-tenant filter (opt-in)
    if tenant_id:
        where += " AND (tenant_id = ? OR tenant_id IS NULL)"
        params.append(tenant_id)
    cur = conn.execute(
        f"SELECT id, kind, content, embedding, importance, created_at, "
        f"COALESCE(tenant_id, '') AS tenant_id, source "
        f"FROM memory_records WHERE {where}", params
    )
    rows = cur.fetchall()
    if not rows:
        return []

    scored = []
    for r in rows:
        emb = _decode_emb(r["embedding"])
        sim = float(np.dot(emb, q_emb))
        if sim < min_similarity:
            continue
        decayed_imp = _importance_decay(r["importance"], r["created_at"])
        fresh = _freshness_boost(r["created_at"])
        score = sim * (0.6 + 0.4 * decayed_imp) * fresh
        scored.append({
            "id": r["id"], "kind": r["kind"], "content": r["content"],
            "similarity": round(sim, 4),
            "score": round(score, 4),
            "importance": r["importance"],
            "decayed_importance": round(decayed_imp, 4),
            "freshness_boost": round(fresh, 3),
            "created_at": r["created_at"],
            "tenant_id": r["tenant_id"] or None,
            "source": r["source"],
        })
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_k]


def cluster_by_entity(entity_name: str, max_results: int = 30) -> dict:
    """Aggregate all memory records mentioning an entity into a single dossier.

    Useful for queries like "ricordi su Marco" → returns all facts/notes/todos/
    conversations/news that mention Marco, grouped by kind.

    Returns: {
      entity: str,
      total: int,
      by_kind: { fact: [...], note: [...], todo: [...], ... },
      most_recent: [...top 5 most recent...],
      most_important: [...top 5 by decayed_importance...]
    }
    """
    if not entity_name or not entity_name.strip():
        return {"entity": entity_name, "total": 0, "by_kind": {}}
    # Semantic search + text match
    semantic_hits = search(entity_name, top_k=max_results, min_similarity=0.30)
    # Also LIKE search for exact name matches (catches things below similarity threshold)
    conn = _get_conn()
    cur = conn.execute(
        "SELECT id, kind, content, importance, created_at, source "
        "FROM memory_records WHERE content LIKE ? ORDER BY created_at DESC LIMIT ?",
        (f"%{entity_name}%", max_results),
    )
    like_hits = []
    seen_ids = {h["id"] for h in semantic_hits}
    for r in cur.fetchall():
        if r["id"] not in seen_ids:
            like_hits.append({
                "id": r["id"], "kind": r["kind"], "content": r["content"],
                "importance": r["importance"], "created_at": r["created_at"],
                "source": r["source"],
                "similarity": 0.0,
                "score": 0.5,  # match purely textuale, score basso
                "decayed_importance": _importance_decay(r["importance"], r["created_at"]),
                "freshness_boost": _freshness_boost(r["created_at"]),
            })
    all_hits = semantic_hits + like_hits

    # Group by kind
    by_kind = {}
    for h in all_hits:
        by_kind.setdefault(h["kind"], []).append(h)

    # Most recent
    most_recent = sorted(all_hits,
                          key=lambda x: x.get("created_at", 0),
                          reverse=True)[:5]
    # Most "alive" (decayed_importance × freshness)
    most_important = sorted(all_hits,
                              key=lambda x: x.get("decayed_importance", 0)
                                            * x.get("freshness_boost", 1),
                              reverse=True)[:5]

    return {
        "entity": entity_name,
        "total": len(all_hits),
        "by_kind": by_kind,
        "most_recent": most_recent,
        "most_important": most_important,
    }


def get(rid: str) -> dict:
    conn = _get_conn()
    cur = conn.execute("SELECT * FROM memory_records WHERE id=?", (rid,))
    row = cur.fetchone()
    if not row:
        return None
    return {k: row[k] for k in row.keys() if k != "embedding"}


def update_importance(rid: str, importance: float):
    conn = _get_conn()
    with _lock:
        conn.execute("UPDATE memory_records SET importance=?, updated_at=? WHERE id=?",
                     (importance, int(time.time()), rid))
        conn.commit()


def delete(rid: str):
    conn = _get_conn()
    with _lock:
        conn.execute("DELETE FROM memory_records WHERE id=?", (rid,))
        conn.execute("DELETE FROM memory_links WHERE from_id=? OR to_id=?", (rid, rid))
        conn.commit()


def link(from_id: str, to_id: str, link_type: str = "relates_to", weight: float = 1.0):
    conn = _get_conn()
    with _lock:
        conn.execute("INSERT OR REPLACE INTO memory_links VALUES (?, ?, ?, ?)",
                     (from_id, to_id, link_type, weight))
        conn.commit()


def list_by_kind(kind: str, limit: int = 50) -> list:
    conn = _get_conn()
    cur = conn.execute("""
        SELECT id, kind, content, importance, created_at, source
        FROM memory_records WHERE kind=? ORDER BY created_at DESC LIMIT ?
    """, (kind, limit))
    return [dict(r) for r in cur.fetchall()]


def prune(kind: str = None, older_than_days: int = 60, keep_top: int = 50):
    """Remove old records of low importance, keeping top-N by importance."""
    cutoff = int(time.time()) - older_than_days * 86400
    conn = _get_conn()
    with _lock:
        if kind:
            # Keep top-N most important, delete older low-importance
            conn.execute("""
                DELETE FROM memory_records
                WHERE kind=? AND created_at < ? AND importance < 0.5
                AND id NOT IN (
                    SELECT id FROM memory_records WHERE kind=?
                    ORDER BY importance DESC LIMIT ?
                )
            """, (kind, cutoff, kind, keep_top))
        else:
            conn.execute("""
                DELETE FROM memory_records
                WHERE created_at < ? AND importance < 0.4
            """, (cutoff,))
        conn.commit()


def stats() -> dict:
    conn = _get_conn()
    out = {}
    cur = conn.execute("SELECT kind, COUNT(*) AS c FROM memory_records GROUP BY kind")
    for r in cur.fetchall():
        out[r["kind"]] = r["c"]
    cur = conn.execute("SELECT COUNT(*) AS c FROM memory_records")
    out["total"] = cur.fetchone()["c"]
    return out


# ============ Migration: copy from memory.json on first run ============

def migrate_from_json_if_needed():
    """One-time copy of facts/notes/etc from legacy memory.json."""
    import memory
    conn = _get_conn()
    cur = conn.execute("SELECT COUNT(*) AS c FROM memory_records")
    if cur.fetchone()["c"] > 0:
        return  # already migrated
    data = memory.get_all()
    count = 0
    for f in data.get("user_facts", []):
        if f.get("text"):
            add("fact", f["text"], importance=0.8, source="migration")
            count += 1
    for n in data.get("notes", []):
        if n.get("text"):
            add("note", n["text"], importance=0.5, source="migration")
            count += 1
    for t in data.get("todos", []):
        if t.get("text") and not t.get("done"):
            add("todo", t["text"], importance=0.7, source="migration")
            count += 1
    for i in data.get("custom_instructions", []):
        if i.get("text"):
            add("instruction", i["text"], importance=0.9, source="migration")
            count += 1
    if count:
        print(f"[memory_graph] migrated {count} records from memory.json")
