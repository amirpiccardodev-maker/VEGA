"""Auto-organize the Downloads folder: move files to typed subfolders."""
import os
import shutil
from pathlib import Path

TOOLS = [{
    "name": "organize_downloads",
    "description": "Organizza la cartella Downloads spostando i file per tipo (PDF, immagini, audio, archivi, ecc.).",
    "input_schema": {
        "type": "object",
        "properties": {
            "dry_run": {"type": "boolean", "description": "Se true, mostra cosa sposterebbe senza muovere nulla."},
        },
    },
}]


CATEGORY_MAP = {
    "PDF": {".pdf"},
    "Immagini": {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tiff", ".svg", ".heic"},
    "Audio": {".mp3", ".wav", ".m4a", ".ogg", ".flac", ".aac"},
    "Video": {".mp4", ".mkv", ".avi", ".mov", ".webm", ".wmv"},
    "Archivi": {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2"},
    "Office": {".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".odt", ".ods"},
    "Installer": {".exe", ".msi", ".bat", ".cmd"},
    "Codice": {".py", ".js", ".html", ".css", ".json", ".xml", ".csv", ".ts", ".java", ".cpp", ".c"},
    "Testo": {".txt", ".md", ".log"},
}


def _categorize(ext: str):
    ext = ext.lower()
    for cat, exts in CATEGORY_MAP.items():
        if ext in exts:
            return cat
    return None


def run(name, args):
    dry_run = bool(args.get("dry_run", False))
    downloads = Path.home() / "Downloads"
    if not downloads.exists():
        return "Cartella Downloads non trovata."

    moves = {}  # category -> count
    errors = []

    for entry in downloads.iterdir():
        if not entry.is_file():
            continue
        if entry.name.startswith("."):
            continue
        if entry.name.endswith(".tmp") or entry.name.endswith(".crdownload"):
            continue
        cat = _categorize(entry.suffix)
        if not cat:
            continue
        dest_dir = downloads / cat
        if not dry_run:
            try:
                dest_dir.mkdir(exist_ok=True)
                target = dest_dir / entry.name
                # Handle name collision
                if target.exists():
                    base = entry.stem
                    ext = entry.suffix
                    i = 2
                    while (dest_dir / f"{base}_{i}{ext}").exists():
                        i += 1
                    target = dest_dir / f"{base}_{i}{ext}"
                shutil.move(str(entry), str(target))
            except Exception as e:
                errors.append(f"{entry.name}: {e}")
                continue
        moves[cat] = moves.get(cat, 0) + 1

    if not moves:
        return "Niente da organizzare nella cartella Downloads."

    summary = []
    total = sum(moves.values())
    prefix = "Simulazione (nessun file spostato): " if dry_run else "Organizzati "
    summary.append(f"{prefix}{total} file:")
    for cat, n in sorted(moves.items(), key=lambda x: -x[1]):
        summary.append(f"  {cat}: {n} file")
    if errors:
        summary.append(f"\nErrori ({len(errors)}):")
        for e in errors[:5]:
            summary.append(f"  - {e}")
    return "\n".join(summary)
