"""Backup automatico settimanale.

Crea snapshot zippato di tutto cio' che e' importante (memoria, config, docs).
Salva in backups/ con timestamp. Mantiene gli ultimi 8 backup.
"""
import os
import zipfile
import threading
import time as _time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent
BACKUP_DIR = ROOT / "backups"
BACKUP_DIR.mkdir(exist_ok=True)

# File da includere nel backup (esistono solo se valorizzati)
INCLUDE_FILES = [
    "memory.json",
    "automations.json",
    "macros.json",
    "scenes.json",
    "workspaces.json",
    "docs_index_meta.json",
    "docs_index.npz",
    # NOTE: .env is intentionally NOT backed up — bundling secrets in a zip is what
    # caused the 2026-05 key leak. Keep credentials only in .env (gitignored).
]
INCLUDE_DIRS = ["docs", "assets/music"]

MAX_BACKUPS = 8
BACKUP_INTERVAL_SEC = 7 * 24 * 3600  # 7 days


def make_backup() -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = BACKUP_DIR / f"vega_backup_{ts}.zip"
    try:
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            # Files
            for f in INCLUDE_FILES:
                full = ROOT / f
                if full.exists() and full.is_file():
                    z.write(full, f)
            # Dirs
            for d in INCLUDE_DIRS:
                full = ROOT / d
                if full.exists() and full.is_dir():
                    for item in full.rglob("*"):
                        if item.is_file():
                            z.write(item, str(item.relative_to(ROOT)))
        # Cleanup old backups (keep MAX_BACKUPS)
        backups = sorted(BACKUP_DIR.glob("vega_backup_*.zip"))
        for old in backups[:-MAX_BACKUPS]:
            try:
                old.unlink()
            except Exception:
                pass
        return str(path)
    except Exception as e:
        print(f"[backup] {e}")
        return ""


def list_backups():
    out = []
    for b in sorted(BACKUP_DIR.glob("vega_backup_*.zip"), reverse=True):
        out.append({
            "name": b.name,
            "size_mb": round(b.stat().st_size / 1e6, 2),
            "date": datetime.fromtimestamp(b.stat().st_mtime).strftime("%d/%m/%Y %H:%M"),
        })
    return out


def _last_backup_age_days() -> float:
    backups = list(BACKUP_DIR.glob("vega_backup_*.zip"))
    if not backups:
        return 999.0
    latest = max(backups, key=lambda p: p.stat().st_mtime)
    age_sec = _time.time() - latest.stat().st_mtime
    return age_sec / 86400


def background_loop(stop_event):
    """Run a backup every BACKUP_INTERVAL_SEC if no recent backup exists."""
    while not stop_event.is_set():
        try:
            if _last_backup_age_days() >= 6.9:  # ~weekly
                path = make_backup()
                if path:
                    print(f"[backup] created {os.path.basename(path)}")
        except Exception as e:
            print(f"[backup loop] {e}")
        # Sleep 6 hours between checks
        for _ in range(6 * 3600):
            if stop_event.is_set():
                return
            _time.sleep(1)
