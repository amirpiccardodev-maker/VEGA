"""File Organizer — struttura cartelle clienti + archive + dedup."""
import json
import time
import hashlib
from pathlib import Path
from datetime import date, datetime

from .team_base import TeamAgent


ROOT = Path(__file__).parent.parent
CLIENTS_ROOT = ROOT / "data" / "client_files"
ARCHIVE_ROOT = ROOT / "data" / "client_files_archive"
CLIENTS_ROOT.mkdir(parents=True, exist_ok=True)
ARCHIVE_ROOT.mkdir(parents=True, exist_ok=True)


FOLDER_STRUCTURE = ["01_contratti", "02_documenti", "03_fatture",
                     "04_corrispondenza", "05_deliverable", "99_archivio"]


def _client_path(client: str) -> Path:
    safe = client.replace("/", "_").replace("\\", "_").strip()
    return CLIENTS_ROOT / safe


def create_client_folder(client: str) -> dict:
    p = _client_path(client)
    p.mkdir(parents=True, exist_ok=True)
    created = []
    for sub in FOLDER_STRUCTURE:
        sp = p / sub
        if not sp.exists():
            sp.mkdir()
            created.append(sub)
    # README seed
    readme = p / "README.md"
    if not readme.exists():
        readme.write_text(
            f"# Cliente: {client}\n\nCreato: {date.today().isoformat()}\n\n"
            f"## Struttura\n" + "\n".join(f"- `{s}/`" for s in FOLDER_STRUCTURE),
            encoding="utf-8")
    return {"client": client, "path": str(p),
            "created_subfolders": created}


def list_client_files(client: str) -> dict:
    p = _client_path(client)
    if not p.exists():
        return {"error": "cliente non trovato"}
    out = {}
    total = 0
    for sub in FOLDER_STRUCTURE:
        sp = p / sub
        files = [f.name for f in sp.glob("*") if f.is_file()] if sp.exists() else []
        out[sub] = {"count": len(files), "files": files[:20]}
        total += len(files)
    return {"client": client, "total_files": total, "by_folder": out}


def archive_inactive(months_inactive: int = 12) -> list:
    """Sposta in archive clienti senza modifiche da N mesi."""
    cutoff = time.time() - (months_inactive * 30 * 86400)
    moved = []
    for p in CLIENTS_ROOT.iterdir():
        if not p.is_dir():
            continue
        try:
            latest = max((f.stat().st_mtime for f in p.rglob("*") if f.is_file()),
                          default=0)
            if latest and latest < cutoff:
                target = ARCHIVE_ROOT / p.name
                # move-rename if exists
                if target.exists():
                    target = ARCHIVE_ROOT / (p.name + "_" + str(int(time.time())))
                p.rename(target)
                moved.append({"client": p.name, "to": str(target)})
        except Exception:
            continue
    return moved


def find_duplicates(client: str = None) -> list:
    """Trova file con stesso hash MD5."""
    seen = {}
    dups = []
    roots = [_client_path(client)] if client else list(CLIENTS_ROOT.iterdir())
    for root in roots:
        if not root.exists() or not root.is_dir():
            continue
        for f in root.rglob("*"):
            if not f.is_file() or f.stat().st_size > 50 * 1024 * 1024:
                continue
            try:
                h = hashlib.md5(f.read_bytes()).hexdigest()
            except Exception:
                continue
            if h in seen:
                dups.append({"hash": h, "files": [seen[h], str(f)]})
            else:
                seen[h] = str(f)
    return dups


class FileOrganizerAgent(TeamAgent):
    name = "file_organizer"
    tier = 2
    icon = "📁"
    description = "Crea struttura cartelle clienti, archivia inattivi, dedup"
    model_pref = "haiku"
    schedule = "weekly Saturday 06:00"
    subscribes = []

    def run(self, payload):
        payload = payload or {}
        op = payload.get("op", "weekly_maintenance")

        if op == "weekly_maintenance":
            archived = archive_inactive(months_inactive=12)
            dups = find_duplicates()
            if archived:
                self.remember("note",
                    f"📁 Archiviati {len(archived)} clienti inattivi >12 mesi",
                    importance=0.4, tags=["file_organizer"])
            self._emit("weekly_done", {
                "archived": len(archived), "duplicates": len(dups)
            })
            return {"ok": True, "archived": archived,
                    "duplicates_found": len(dups),
                    "duplicates_sample": dups[:5]}

        if op == "create_client_folder":
            return {"ok": True,
                    "result": create_client_folder(payload.get("client", ""))}

        if op == "list_files":
            return {"ok": True,
                    "files": list_client_files(payload.get("client", ""))}

        if op == "find_duplicates":
            return {"ok": True,
                    "duplicates": find_duplicates(payload.get("client"))}

        if op == "archive_project":
            # Workflow hook
            client = payload.get("client", "")
            if not client:
                return {"ok": False, "error": "client richiesto"}
            p = _client_path(client) / "05_deliverable"
            archive = _client_path(client) / "99_archivio"
            archive.mkdir(exist_ok=True)
            moved = 0
            if p.exists():
                ts = date.today().isoformat()
                project_archive = archive / f"project_{ts}"
                project_archive.mkdir(exist_ok=True)
                for f in p.glob("*"):
                    if f.is_file():
                        f.rename(project_archive / f.name)
                        moved += 1
            return {"ok": True, "client": client, "files_archived": moved}

        return {"ok": False, "error": f"op sconosciuta: {op}",
                "available_ops": ["weekly_maintenance", "create_client_folder",
                                    "list_files", "find_duplicates",
                                    "archive_project"]}


AGENT = FileOrganizerAgent()
