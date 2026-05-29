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
import re
import sys
from pathlib import Path

SESSIONS_DIR = Path.home() / ".archolith" / "sessions"


def slugify(text: str, max_words: int = 4) -> str:
    words = re.sub(r"[^\w\s-]", "", text.lower()).split()[:max_words]
    return "-".join(words) if words else "session"


def main() -> None:
    try:
        payload = json.loads(sys.stdin.read())
    except Exception:
        print(json.dumps({"continue": True}))
        return

    session_id = payload.get("session_id", "unknown")
    cwd = payload.get("cwd", "")
    project = Path(cwd).name if cwd else "workspace"
    date = datetime.date.today().isoformat()
    name = f"{date}-{slugify(project)}"

    try:
        SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
        (SESSIONS_DIR / f"{session_id}.name").write_text(name, encoding="utf-8")
        jsonl_path = SESSIONS_DIR / f"{session_id}.jsonl"
        if not jsonl_path.exists():
            jsonl_path.touch()
    except Exception:
        pass  # never block the session

    print(json.dumps({"continue": True}))


if __name__ == "__main__":
    main()
