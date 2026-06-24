"""Codex PostToolUse hook observer."""

import json
import os
import sys
import time
from pathlib import Path

_UNSAFE_SESSION_CHARS = "/\\\x00\r\n\t"


def _safe_session_id(session_id: str) -> str:
    cleaned = session_id
    for char in _UNSAFE_SESSION_CHARS:
        cleaned = cleaned.replace(char, "_")
    cleaned = cleaned.replace("..", "_").strip()
    return cleaned if cleaned.strip("._") else "codex-default"


def _append_jsonl(path: Path, line: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (line.rstrip("\n") + "\n").encode("utf-8")
    fd = os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
    try:
        os.write(fd, payload)
    finally:
        os.close(fd)


def main():
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        print(json.dumps({"continue": True}))
        return

    tool_name = payload.get("tool_name", "unknown")
    result = payload.get("tool_result") or payload.get("output") or ""
    chars = len(str(result))
    session_id = _safe_session_id(str(payload.get("session_id", "codex-default")))

    sessions_dir = Path.home() / ".archolith" / "sessions"
    entry = json.dumps({
        "tool_name": tool_name,
        "raw_tokens": 0,  # unavailable in Codex context
        "raw_chars": chars,
        "filtered_tokens": 0,  # unavailable in Codex context
        "filtered_chars": chars,
        "timestamp": time.time(),
        "session_id": session_id,
    })
    try:
        _append_jsonl(sessions_dir / f"{session_id}.jsonl", entry)
    except OSError:
        pass

    print(json.dumps({"continue": True}))


if __name__ == "__main__":
    main()
