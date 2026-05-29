"""Deduplicate memory across memory_graph and Mem0 episodic.

Strategy: per ogni fatto in memory_graph (kind=fact), cerca Mem0 con la stessa
query; se similarity > 0.90 e contenuto sovrapposto, considera duplicato.

Politica: preferiamo Mem0 (più strutturato, con LLM extraction). Marchiamo
memory_graph come "deprecated" via tag invece di cancellarlo (audit safety).

Schedulato weekly, in background thread.
"""
import threading
import time

import bus


_started = False
RUN_INTERVAL_SEC = 7 * 24 * 3600  # weekly


def _norm(s: str) -> str:
    """Normalize text for fuzzy comparison."""
    return " ".join((s or "").lower().split())


def _is_duplicate(text_a: str, text_b: str) -> bool:
    """Coarse dedup: prefix overlap + token Jaccard."""
    a = _norm(text_a)
    b = _norm(text_b)
    if not a or not b:
        return False
    # Exact match
    if a == b:
        return True
    # Prefix containment (one contained in the other)
    if len(a) >= 30 and a in b:
        return True
    if len(b) >= 30 and b in a:
        return True
    # Token Jaccard
    ta = set(a.split())
    tb = set(b.split())
    if not ta or not tb:
        return False
    jaccard = len(ta & tb) / len(ta | tb)
    return jaccard >= 0.75


def find_duplicates() -> list:
    """Returns list of {graph_id, mem0_id, graph_content, mem0_content, score}."""
    dups = []
    try:
        import memory_graph as mg
        conn = mg._get_conn()
        cur = conn.execute(
            "SELECT id, content FROM memory_records WHERE kind='fact' LIMIT 500"
        )
        graph_facts = [(r["id"], r["content"]) for r in cur.fetchall()]
    except Exception:
        return []
    try:
        import episodic_memory
        # episodic_memory.search non disponibile per all-listing; usiamo search per ogni fact
        for gid, gcontent in graph_facts:
            mem_hits = episodic_memory.search(gcontent[:120], limit=3)
            for h in mem_hits:
                mcontent = h.get("memory", "") or h.get("text", "")
                if _is_duplicate(gcontent, mcontent):
                    dups.append({
                        "graph_id": gid,
                        "mem0_id": h.get("id"),
                        "graph_content": gcontent[:160],
                        "mem0_content": mcontent[:160],
                    })
                    break
    except Exception as e:
        bus.publish("error.occurred", {"source": "memory_dedup", "error": str(e)})
    return dups


def mark_deprecated(graph_id: str) -> bool:
    """Mark memory_graph record as deprecated (add tag, keep for audit)."""
    try:
        import memory_graph as mg
        import json
        conn = mg._get_conn()
        cur = conn.execute("SELECT tags FROM memory_records WHERE id=?", (graph_id,))
        row = cur.fetchone()
        if not row:
            return False
        tags = []
        try:
            tags = json.loads(row["tags"]) if row["tags"] else []
        except Exception:
            tags = []
        if "deprecated_duplicate" not in tags:
            tags.append("deprecated_duplicate")
        with mg._lock:
            conn.execute(
                "UPDATE memory_records SET tags=?, importance=importance*0.5 "
                "WHERE id=?",
                (json.dumps(tags), graph_id),
            )
            conn.commit()
        return True
    except Exception:
        return False


def dedup_pass(apply: bool = False) -> dict:
    """Run a dedup pass. If apply=True, marks duplicates as deprecated."""
    started = time.time()
    dups = find_duplicates()
    marked = 0
    if apply:
        for d in dups:
            if mark_deprecated(d["graph_id"]):
                marked += 1
    bus.publish("memory_dedup.completed", {
        "found": len(dups),
        "marked": marked,
        "duration_sec": round(time.time() - started, 2),
        "apply": apply,
    })
    return {
        "ok": True,
        "found": len(dups),
        "marked": marked,
        "samples": dups[:10],
        "duration_sec": round(time.time() - started, 2),
    }


def _loop():
    # First pass after 24h, then weekly
    time.sleep(24 * 3600)
    while True:
        try:
            dedup_pass(apply=True)
        except Exception as e:
            bus.publish("error.occurred", {"source": "memory_dedup", "error": str(e)})
        time.sleep(RUN_INTERVAL_SEC)


def start():
    global _started
    if _started:
        return
    _started = True
    threading.Thread(target=_loop, daemon=True, name="memory_dedup").start()
    bus.publish("memory_dedup.started", {})
