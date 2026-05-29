"""Path traversal sanitizer for tool file operations.

Confines file ops to a whitelist of allowed root directories:
  - Vega dir (own data)
  - User's Documents, Downloads, Desktop, Pictures, Music, Videos
  - explicit tmp dirs

Blocks:
  - .. traversal that escapes allowed roots
  - Absolute paths outside allowed roots
  - Symlink resolution that points outside
  - Windows reserved names (CON, NUL, PRN, AUX, ...)
  - Null bytes in path
  - Unicode trick characters (zero-width, RLO)

API:
    safe_path(p, write=False) -> resolved Path | raises PermissionError
    is_safe(p) -> bool
    allowed_roots() -> [str]
"""
import os
import re
from pathlib import Path


VEGA_ROOT = Path(__file__).parent.resolve()

# User-specific allowed dirs (Windows + cross-platform)
def _user_allowed_dirs():
    home = Path.home()
    dirs = []
    for name in ["Desktop", "Documents", "Downloads",
                 "Pictures", "Music", "Videos"]:
        p = home / name
        if p.exists():
            dirs.append(p.resolve())
    return dirs


ALLOWED_ROOTS = [VEGA_ROOT] + _user_allowed_dirs() + [Path(os.environ.get("TEMP", "/tmp")).resolve()]

# Windows reserved filenames
WIN_RESERVED = {"CON", "PRN", "AUX", "NUL"} | {f"COM{i}" for i in range(1, 10)} | {f"LPT{i}" for i in range(1, 10)}

# Forbidden chars in any segment
FORBIDDEN_CHARS = re.compile(r"[\x00-\x1f\x7f<>\"|?*]")


def _is_under(child: Path, parent: Path) -> bool:
    """True if child is under parent (after resolution)."""
    try:
        child.resolve(strict=False).relative_to(parent.resolve(strict=False))
        return True
    except (ValueError, OSError):
        return False


def is_safe(p) -> bool:
    """Check if a path is allowed without raising."""
    try:
        safe_path(p)
        return True
    except (PermissionError, ValueError):
        return False


def safe_path(p, write: bool = False, allow_create: bool = True) -> Path:
    """Resolve and validate p. Raises PermissionError if outside allowed roots.

    Args:
        p: path to validate (str or Path)
        write: True if the operation is a write (stricter — must not be symlink)
        allow_create: if False, the path must already exist
    """
    if p is None:
        raise ValueError("Path is None")
    s = str(p)

    # Null byte injection
    if "\x00" in s:
        raise ValueError("Null byte in path")

    # Zero-width / control characters
    for ch in s:
        if ord(ch) < 32 and ch not in "\t\n\r":
            raise ValueError(f"Control character in path: {hex(ord(ch))}")
        if ord(ch) in (0x202E, 0x202D, 0x200B, 0x200C, 0x200D, 0xFEFF):
            raise ValueError("Unicode trick character in path")

    # Forbidden chars in path segments (Windows)
    for seg in Path(s).parts:
        if seg in (".", "..", "/", "\\"):
            continue
        # Strip drive letter / root marker
        cleaned = seg.rstrip(":\\/").upper()
        if cleaned in WIN_RESERVED:
            raise ValueError(f"Reserved filename: {seg}")
        # Windows reserved names are forbidden even with extension (PRN.txt == PRN)
        stem = cleaned.split(".", 1)[0]
        if stem in WIN_RESERVED:
            raise ValueError(f"Reserved filename (with extension): {seg}")
        if FORBIDDEN_CHARS.search(seg):
            raise ValueError(f"Forbidden character in segment: {seg!r}")

    # Resolve
    try:
        resolved = Path(s).expanduser().resolve(strict=False)
    except OSError as e:
        raise ValueError(f"Cannot resolve path: {e}")

    # Symlink check (write ops only): the path must not be a symlink to outside
    if write and resolved.is_symlink():
        target = resolved.readlink()
        if not any(_is_under(target, r) for r in ALLOWED_ROOTS):
            raise PermissionError(f"Symlink target outside allowed roots: {target}")

    # Must be under at least one allowed root
    if not any(_is_under(resolved, r) for r in ALLOWED_ROOTS):
        raise PermissionError(
            f"Path '{resolved}' is outside allowed roots. "
            f"Allowed: {[str(r) for r in ALLOWED_ROOTS]}"
        )

    # If allow_create=False, must exist
    if not allow_create and not resolved.exists():
        raise FileNotFoundError(f"Path does not exist: {resolved}")

    return resolved


def allowed_roots() -> list:
    return [str(r) for r in ALLOWED_ROOTS]


def safe_open(path, mode: str = "r", **kwargs):
    """Drop-in replacement for open() with path validation."""
    write = any(m in mode for m in ("w", "a", "x", "+"))
    sp = safe_path(path, write=write)
    return open(sp, mode, **kwargs)
