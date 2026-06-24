"""Path-safety helpers for audit session files."""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

_UNSAFE_SESSION_ID_RE = re.compile(r"[\\/]|(\.\.)|[\x00-\x1f\x7f]")


def sanitize_session_id(session_id: str | None, fallback: str = "default") -> str:
    """Return a session id safe to use as a filename stem."""
    if not session_id:
        return fallback

    cleaned = _UNSAFE_SESSION_ID_RE.sub("_", str(session_id)).strip()
    if not cleaned.strip("._") or cleaned in {".", ".."}:
        return fallback
    return cleaned


def safe_session_path(sessions_dir: Path, session_id: str | None, suffix: str = ".jsonl") -> Path:
    """Return a session path guaranteed to stay under ``sessions_dir``."""
    root = sessions_dir.resolve()
    path = (root / f"{sanitize_session_id(session_id)}{suffix}").resolve()
    if not path.is_relative_to(root):
        raise ValueError(f"session_id {session_id!r} escapes sessions_dir")
    return path


def atomic_append_jsonl(path: Path, line: str) -> None:
    """Append one JSONL line using an OS-level append write."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (line.rstrip("\n") + "\n").encode("utf-8")
    fd = os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
    try:
        os.write(fd, payload)
    finally:
        os.close(fd)


def atomic_write_text(path: Path, text: str) -> None:
    """Atomically replace a small text file in the target directory."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        tmp_path.replace(path)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise
