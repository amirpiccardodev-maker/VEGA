"""Persistent telemetry — counters, gauges, histograms on SQLite.

Salva metriche su disco (vs solo memoria) per analisi nel tempo.
Rolling 30 giorni di rentenzione.

API:
    counter(name, value=1, tags={})         # incrementa contatore
    gauge(name, value, tags={})             # imposta valore istantaneo
    histogram(name, value, tags={})         # registra in serie temporale
    query(name, since_sec=86400) -> list   # ultimi N secondi
    aggregate(name, since_sec, by="hour") -> list
"""
import sqlite3
import threading
import time
from pathlib import Path

import json


ROOT = Path(__file__).parent
DB_PATH = ROOT / "data" / "telemetry.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

_conn = None
_lock = threading.Lock()
RETENTION_SEC = 30 * 24 * 3600


def _get():
    global _conn
    if _conn is not None:
        return _conn
    _conn = sqlite3.connect(str(DB_PATH), check_same_thread=False, timeout=30.0)
    _conn.row_factory = sqlite3.Row
    _conn.execute("PRAGMA journal_mode=WAL")
    _conn.execute("PRAGMA synchronous=NORMAL")
    _conn.execute("PRAGMA busy_timeout=30000")
    _conn.execute("""
        CREATE TABLE IF NOT EXISTS metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts INTEGER NOT NULL,
            kind TEXT NOT NULL,
            name TEXT NOT NULL,
            value REAL NOT NULL,
            tags TEXT
        )
    """)
    _conn.execute("CREATE INDEX IF NOT EXISTS idx_metrics_name_ts ON metrics(name, ts DESC)")
    _conn.execute("CREATE INDEX IF NOT EXISTS idx_metrics_kind ON metrics(kind)")
    _conn.commit()
    return _conn


def _record(kind: str, name: str, value: float, tags: dict = None):
    conn = _get()
    with _lock:
        conn.execute(
            "INSERT INTO metrics (ts, kind, name, value, tags) VALUES (?, ?, ?, ?, ?)",
            (int(time.time()), kind, name, float(value),
             json.dumps(tags) if tags else None),
        )
        conn.commit()


def counter(name: str, value: float = 1, tags: dict = None):
    _record("counter", name, value, tags)


def gauge(name: str, value: float, tags: dict = None):
    _record("gauge", name, value, tags)


def histogram(name: str, value: float, tags: dict = None):
    _record("histogram", name, value, tags)


def query(name: str, since_sec: int = 86400) -> list:
    conn = _get()
    cutoff = int(time.time()) - since_sec
    rows = conn.execute(
        "SELECT ts, kind, value, tags FROM metrics "
        "WHERE name=? AND ts>=? ORDER BY ts",
        (name, cutoff),
    ).fetchall()
    return [{"ts": r["ts"], "kind": r["kind"], "value": r["value"],
              "tags": json.loads(r["tags"]) if r["tags"] else None}
            for r in rows]


def aggregate(name: str, since_sec: int = 86400, by: str = "hour") -> list:
    """Aggregate metric by hour/day. Returns time-bucketed sum/avg."""
    bucket = 3600 if by == "hour" else 86400
    rows = query(name, since_sec)
    buckets = {}
    for r in rows:
        b = (r["ts"] // bucket) * bucket
        bk = buckets.setdefault(b, {"sum": 0, "count": 0, "max": 0, "min": float("inf")})
        bk["sum"] += r["value"]
        bk["count"] += 1
        bk["max"] = max(bk["max"], r["value"])
        bk["min"] = min(bk["min"], r["value"])
    out = []
    for ts, b in sorted(buckets.items()):
        b["ts"] = ts
        b["avg"] = b["sum"] / b["count"] if b["count"] else 0
        if b["min"] == float("inf"):
            b["min"] = 0
        out.append(b)
    return out


def names() -> list:
    """List of distinct metric names seen."""
    conn = _get()
    rows = conn.execute(
        "SELECT DISTINCT name, kind, COUNT(*) as c FROM metrics GROUP BY name ORDER BY c DESC"
    ).fetchall()
    return [{"name": r["name"], "kind": r["kind"], "count": r["c"]}
            for r in rows]


def prune_old():
    """Remove entries older than RETENTION_SEC."""
    conn = _get()
    cutoff = int(time.time()) - RETENTION_SEC
    with _lock:
        conn.execute("DELETE FROM metrics WHERE ts<?", (cutoff,))
        conn.commit()


def start_pruner():
    """Background daily pruner."""
    def _loop():
        time.sleep(3600)  # first sleep
        while True:
            try:
                prune_old()
            except Exception:
                pass
            time.sleep(24 * 3600)
    threading.Thread(target=_loop, daemon=True, name="telemetry_pruner").start()
