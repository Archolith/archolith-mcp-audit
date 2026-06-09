"""Codex PostToolUse hook observer."""

import json
import sys
import time
from pathlib import Path


def main():
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        print(json.dumps({"continue": True}))
        return

    tool_name = payload.get("tool_name", "unknown")
    result = payload.get("tool_result") or payload.get("output") or ""
    chars = len(str(result))
    session_id = payload.get("session_id", "codex-default")

    sessions_dir = Path.home() / ".archolith" / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
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
        with open(sessions_dir / f"{session_id}.jsonl", "a", encoding="utf-8") as f:
            f.write(entry + "\n")
    except OSError:
        pass

    print(json.dumps({"continue": True}))


if __name__ == "__main__":
    main()
