"""Codex standalone hook observer.

Called by the PostToolUse hook in hooks/hooks.json:
    python ${CODEX_PLUGIN_DIR}/hook_observer_codex.py

Reads the hook event JSON from stdin, extracts tool_name and result size,
and appends an observation line to ~/.archolith/sessions/<sessionId>.jsonl.

Codex does not inject a session ID into hook env, so we fall back to a
per-hour key (codex-<hour>) for reasonable session grouping.
"""

import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        # If stdin is empty or invalid JSON, exit silently — don't block
        print(json.dumps({"continue": True}))
        return

    tool_name = payload.get("tool_name", payload.get("tool", "unknown"))
    result = payload.get("tool_result", payload.get("output", "") or "")
    chars = len(str(result))
    session_id = payload.get("session_id", f"codex-{datetime.now(UTC).strftime('%Y%m%d-%H')}")

    sessions_dir = Path.home() / ".archolith" / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)

    # Match the schema FileTelemetrySource.pull() expects. Token counts are
    # unavailable in the standalone Codex hook context (no tiktoken guarantee),
    # so raw/filtered tokens are 0 and char counts carry the signal.
    entry = json.dumps({
        "tool_name": tool_name,
        "raw_tokens": 0,
        "raw_chars": chars,
        "filtered_tokens": 0,
        "filtered_chars": chars,
        "timestamp": time.time(),
        "session_id": session_id,
    })

    try:
        with open(sessions_dir / f"{session_id}.jsonl", "a", encoding="utf-8") as f:
            f.write(entry + "\n")
    except OSError:
        pass  # never block the agent

    print(json.dumps({"continue": True}))


if __name__ == "__main__":
    main()
