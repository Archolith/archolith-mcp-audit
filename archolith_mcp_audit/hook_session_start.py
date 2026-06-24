#!/usr/bin/env python3
"""
archolith-audit session start hook.

Fires once per Claude Code session via the SessionStart hook event.
Reads session_id and cwd from stdin JSON, generates a human-readable
session name, and writes:
  ~/.archolith/sessions/<session_id>.name   — human-readable label
  ~/.archolith/sessions/<session_id>.jsonl  — created empty (pre-touch)

Zero package imports. Never raises.

Usage (configured in settings.json):
  "SessionStart": [{"hooks": [{"type": "command", "command": "python hook_session_start.py"}]}]
"""

import datetime
import json
import os
import re
import sys
import tempfile
from pathlib import Path

SESSIONS_DIR = Path.home() / ".archolith" / "sessions"
_UNSAFE_SESSION_CHARS = "/\\\x00\r\n\t"


def _safe_session_id(session_id: str) -> str:
    cleaned = session_id
    for char in _UNSAFE_SESSION_CHARS:
        cleaned = cleaned.replace(char, "_")
    cleaned = cleaned.replace("..", "_").strip()
    return cleaned if cleaned.strip("._") else "unknown"


def _write_text_atomic(path: Path, text: str) -> None:
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


def slugify(text: str, max_words: int = 4) -> str:
    words = re.sub(r"[^\w\s-]", "", text.lower()).split()[:max_words]
    return "-".join(words) if words else "session"


def main() -> None:
    try:
        payload = json.loads(sys.stdin.read())
    except Exception:
        print(json.dumps({"continue": True}))
        return

    session_id = _safe_session_id(str(payload.get("session_id", "unknown")))
    cwd = payload.get("cwd", "")
    project = Path(cwd).name if cwd else "workspace"
    date = datetime.date.today().isoformat()
    name = f"{date}-{slugify(project)}"

    try:
        _write_text_atomic(SESSIONS_DIR / f"{session_id}.name", name)
        jsonl_path = SESSIONS_DIR / f"{session_id}.jsonl"
        if not jsonl_path.exists():
            jsonl_path.touch()
    except Exception:
        pass  # never block the session

    print(json.dumps({"continue": True}))


if __name__ == "__main__":
    main()
