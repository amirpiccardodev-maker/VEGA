"""Task queue persistente con SQLite.

Sostituisce gradualmente i scheduler ortogonali (automations, backup, etc.).
Permette: retry/backoff, dlq, dedup, scheduled_at futuro, recovery cross-restart.

API:
    task_id = enqueue(type, payload, scheduled_at=None, dedup_key=None, ...)
    task = dequeue()  # pesca uno pending (scheduled_at <= now)
    complete(task_id, result)
    retry(task_id, reason)
    fail(task_id, reason)
    list_tasks(status=None, limit=50)

Worker pool: chiamare start_workers(dispatch_fn) all'avvio del server.
"""
import json
import os
import sqlite3
import threading
import time
import uuid
from pathlib import Path

import bus

ROOT = Path(__file__).parent
DB_PATH = ROOT / "tasks.db"

_lock = threading.RLock()  # solo per init e dispatch registry
_conn = None
_workers = []
_stop = threading.Event()
_dispatch = None  # callback(task_dict) -> result or raises


def _get_conn():
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(str(DB_PATH), check_same_thread=False, timeout=30.0)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("PRAGMA synchronous=NORMAL")
        _conn.execute("PRAGMA busy_timeout=30000")
        _conn.execute("PRAGMA journal_size_limit=104857600")
        _conn.execute("PRAGMA temp_store=MEMORY")
        _conn.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id           TEXT PRIMARY KEY,
                type         TEXT NOT NULL,
                payload      TEXT NOT NULL,
                status       TEXT NOT NULL,
                priority     INTEGER DEFAULT 5,
                attempts     INTEGER DEFAULT 0,
                max_attempts INTEGER DEFAULT 3,
                scheduled_at INTEGER,
                started_at   INTEGER,
                ended_at     INTEGER,
                result       TEXT,
                error        TEXT,
                parent_id    TEXT,
                workflow_id  TEXT,
                dedup_key    TEXT,
                origin       TEXT,
                created_at   INTEGER
            )
        """)
        _conn.execute("CREATE INDEX IF NOT EXISTS idx_status_sched ON tasks(status, scheduled_at)")
        _conn.execute("CREATE INDEX IF NOT EXISTS idx_dedup ON tasks(dedup_key)")
        _conn.execute("CREATE INDEX IF NOT EXISTS idx_workflow ON tasks(workflow_id)")
        _conn.commit()
    return _conn


def enqueue(type: str, payload: dict, scheduled_at: int = None,
            dedup_key: str = None, priority: int = 5, max_attempts: int = 3,
            parent_id: str = None, workflow_id: str = None, origin: str = "user") -> str:
    """Add task to queue. Returns task_id."""
    now = int(time.time())
    sched = scheduled_at or now

    conn = _get_conn()
    with _lock:
        # Dedup check: if a non-completed task with same key exists, skip
        if dedup_key:
            cur = conn.execute(
                "SELECT id FROM tasks WHERE dedup_key=? AND status IN ('pending','running')",
                (dedup_key,)
            )
            existing = cur.fetchone()
            if existing:
                return existing["id"]

        task_id = uuid.uuid4().hex[:16]
        conn.execute("""
            INSERT INTO tasks (id, type, payload, status, priority, attempts, max_attempts,
                              scheduled_at, dedup_key, parent_id, workflow_id, origin, created_at)
            VALUES (?, ?, ?, 'pending', ?, 0, ?, ?, ?, ?, ?, ?, ?)
        """, (task_id, type, json.dumps(payload, ensure_ascii=False),
              priority, max_attempts, sched, dedup_key, parent_id, workflow_id, origin, now))
        conn.commit()

    bus.publish(bus.Topics.TASK_ENQUEUED, {"id": task_id, "type": type})
    return task_id


def dequeue() -> dict:
    """Pesca un task pending pronto. Mark as running atomically."""
    now = int(time.time())
    conn = _get_conn()
    with _lock:
        cur = conn.execute("""
            SELECT * FROM tasks
            WHERE status='pending' AND scheduled_at <= ?
            ORDER BY priority ASC, scheduled_at ASC
            LIMIT 1
        """, (now,))
        row = cur.fetchone()
        if not row:
            return None
        task_id = row["id"]
        conn.execute("""
            UPDATE tasks SET status='running', started_at=?, attempts=attempts+1
            WHERE id=? AND status='pending'
        """, (now, task_id))
        if conn.total_changes == 0:
            return None  # someone else picked it
        conn.commit()
    return dict(row)


def complete(task_id: str, result):
    conn = _get_conn()
    with _lock:
        conn.execute("""
            UPDATE tasks SET status='ok', ended_at=?, result=?
            WHERE id=?
        """, (int(time.time()), json.dumps(result, default=str, ensure_ascii=False)[:5000], task_id))
        conn.commit()
    bus.publish(bus.Topics.TASK_OK, {"id": task_id})


def retry(task_id: str, reason: str = "", delay_sec: int = 30):
    conn = _get_conn()
    now = int(time.time())
    with _lock:
        cur = conn.execute("SELECT attempts, max_attempts FROM tasks WHERE id=?", (task_id,))
        row = cur.fetchone()
        if not row:
            return
        if row["attempts"] >= row["max_attempts"]:
            return fail(task_id, reason)
        # Exponential backoff
        backoff = delay_sec * (2 ** (row["attempts"] - 1))
        conn.execute("""
            UPDATE tasks SET status='pending', scheduled_at=?, error=?
            WHERE id=?
        """, (now + backoff, reason[:1000], task_id))
        conn.commit()
    bus.publish(bus.Topics.TASK_RETRIED, {"id": task_id, "reason": reason, "delay": backoff})


def fail(task_id: str, reason: str = ""):
    conn = _get_conn()
    with _lock:
        conn.execute("""
            UPDATE tasks SET status='dlq', ended_at=?, error=?
            WHERE id=?
        """, (int(time.time()), reason[:1000], task_id))
        conn.commit()
    bus.publish(bus.Topics.TASK_FAILED, {"id": task_id, "reason": reason})


def list_tasks(status: str = None, limit: int = 100, workflow_id: str = None) -> list:
    conn = _get_conn()
    q = "SELECT * FROM tasks"
    where = []
    params = []
    if status:
        where.append("status=?"); params.append(status)
    if workflow_id:
        where.append("workflow_id=?"); params.append(workflow_id)
    if where:
        q += " WHERE " + " AND ".join(where)
    q += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    cur = conn.execute(q, params)
    return [dict(r) for r in cur.fetchall()]


def get_task(task_id: str) -> dict:
    conn = _get_conn()
    cur = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,))
    row = cur.fetchone()
    return dict(row) if row else None


def stats() -> dict:
    conn = _get_conn()
    out = {}
    for status in ("pending", "running", "ok", "dlq"):
        cur = conn.execute("SELECT COUNT(*) AS c FROM tasks WHERE status=?", (status,))
        out[status] = cur.fetchone()["c"]
    cur = conn.execute("SELECT COUNT(*) AS c FROM tasks")
    out["total"] = cur.fetchone()["c"]
    return out


def cleanup(keep_days: int = 30):
    """Remove ok tasks older than N days."""
    cutoff = int(time.time()) - keep_days * 86400
    conn = _get_conn()
    with _lock:
        conn.execute("DELETE FROM tasks WHERE status='ok' AND ended_at < ?", (cutoff,))
        conn.commit()


def stuck_recovery():
    """At startup, any task left in 'running' is recovered to pending (retry)."""
    conn = _get_conn()
    with _lock:
        conn.execute("UPDATE tasks SET status='pending', scheduled_at=? WHERE status='running'",
                     (int(time.time()),))
        conn.commit()


# ============ Worker pool ============

class RetryableError(Exception):
    """Raise from dispatch to trigger retry (vs permanent failure)."""
    pass


def set_dispatch(fn):
    """Register the function that executes a task."""
    global _dispatch
    _dispatch = fn


def _worker_loop(worker_id: int):
    while not _stop.is_set():
        try:
            task = dequeue()
        except Exception as e:
            print(f"[worker {worker_id}] dequeue error: {e}")
            time.sleep(2); continue
        if not task:
            time.sleep(1); continue
        bus.publish(bus.Topics.TASK_STARTED, {"id": task["id"], "type": task["type"]})
        try:
            if not _dispatch:
                raise RuntimeError("no dispatch function registered")
            result = _dispatch(task)
            complete(task["id"], result)
        except RetryableError as e:
            retry(task["id"], reason=str(e))
        except Exception as e:
            # Retry if we have attempts left, else fail
            t = get_task(task["id"])
            if t and t["attempts"] < t["max_attempts"]:
                retry(task["id"], reason=str(e))
            else:
                fail(task["id"], reason=str(e))


def start_workers(dispatch_fn, n: int = 2):
    """Start N worker threads with given dispatch function."""
    set_dispatch(dispatch_fn)
    stuck_recovery()
    global _workers
    for i in range(n):
        t = threading.Thread(target=_worker_loop, args=(i,), daemon=True, name=f"taskworker-{i}")
        t.start()
        _workers.append(t)


def stop_workers():
    _stop.set()
