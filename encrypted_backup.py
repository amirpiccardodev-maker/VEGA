"""End-to-end encrypted backup of Vega data dirs.

Crea un tar.gz cifrato con Fernet (master key da PIN) di:
  - tasks.db, memory_graph.db, memory.json, capabilities.json
  - data/voice_profiles, data/email_drafts, data/vapid.json (NO auth.json/cert)
  - workflows/, automations.json
  - audit.log.jsonl

NON include: .env (già cifrato separatamente via vault),
chroma/ (può essere ricostruito da Mem0 da capo), assets statici.

Output: data/backups/vega_backup_<ts>.enc

Restore: tool separato (backup_restore.py) — l'utente deve fornire PIN.
"""
import io
import os
import tarfile
import time
import base64
import hashlib
import socket
from pathlib import Path

ROOT = Path(__file__).parent
BACKUP_DIR = ROOT / "data" / "backups"
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

INCLUDE_PATHS = [
    "tasks.db", "memory_graph.db", "memory.json", "capabilities.json",
    "automations.json", "workflows", "data/voice_profiles",
    "data/email_drafts", "data/vapid.json", "data/audit.log.jsonl",
    "news_feeds.json",
]


def _derive_key(pin: str) -> bytes:
    salt = ("vega_backup_v1:" + socket.gethostname()).encode("utf-8")
    raw = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), salt, 200_000)
    return base64.urlsafe_b64encode(raw)


def create_backup(pin: str) -> dict:
    """Create an encrypted backup tar. Returns {ok, path, size_bytes}."""
    if not pin or len(pin) < 4:
        return {"ok": False, "error": "PIN troppo corto"}
    try:
        from cryptography.fernet import Fernet
    except Exception as e:
        return {"ok": False, "error": f"cryptography mancante: {e}"}

    # Build tar in memory
    buf = io.BytesIO()
    files_added = 0
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for rel in INCLUDE_PATHS:
            p = ROOT / rel
            if not p.exists():
                continue
            try:
                tar.add(str(p), arcname=rel)
                files_added += 1
            except Exception:
                pass

    plain = buf.getvalue()
    key = _derive_key(pin)
    f = Fernet(key)
    token = f.encrypt(plain)

    ts = int(time.time())
    out_path = BACKUP_DIR / f"vega_backup_{ts}.enc"
    out_path.write_bytes(b"JBK01" + token)
    try:
        os.chmod(out_path, 0o600)
    except Exception:
        pass

    try:
        import audit_log
        audit_log.log("backup.created", {
            "file": out_path.name, "size": out_path.stat().st_size,
            "files": files_added,
        })
    except Exception:
        pass

    return {
        "ok": True,
        "path": str(out_path),
        "filename": out_path.name,
        "size_bytes": out_path.stat().st_size,
        "files_included": files_added,
    }


def list_backups() -> list:
    out = []
    if not BACKUP_DIR.exists():
        return out
    for p in sorted(BACKUP_DIR.glob("vega_backup_*.enc"), reverse=True):
        try:
            stat = p.stat()
            out.append({
                "name": p.name,
                "size_bytes": stat.st_size,
                "created_ts": int(stat.st_mtime),
            })
        except Exception:
            pass
    return out


def delete_backup(name: str) -> bool:
    """Delete a backup by filename (safely)."""
    if "/" in name or "\\" in name or ".." in name:
        return False
    p = BACKUP_DIR / name
    if p.exists() and p.is_file() and p.suffix == ".enc":
        try:
            p.unlink()
            return True
        except Exception:
            return False
    return False


def verify_backup(name: str, pin: str) -> dict:
    """Try to decrypt a backup to verify the PIN works and the file isn't corrupt."""
    if "/" in name or "\\" in name or ".." in name:
        return {"ok": False, "error": "nome non valido"}
    p = BACKUP_DIR / name
    if not p.exists():
        return {"ok": False, "error": "non trovato"}
    try:
        from cryptography.fernet import Fernet, InvalidToken
        raw = p.read_bytes()
        if raw[:5] == b"JBK01":
            raw = raw[5:]
        try:
            plain = Fernet(_derive_key(pin)).decrypt(raw)
        except InvalidToken:
            return {"ok": False, "error": "PIN errato"}
        # Validate tarball
        with tarfile.open(fileobj=io.BytesIO(plain), mode="r:gz") as tar:
            names = tar.getnames()
        return {"ok": True, "files": len(names), "first_files": names[:8]}
    except Exception as e:
        return {"ok": False, "error": str(e)}
