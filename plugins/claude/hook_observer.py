"""Claude Code standalone hook observer.

Called by the PostToolUse hook in hooks/hooks.json:
    python ${CLAUDE_PLUGIN_DIR}/hook_observer.py ${CLAUDE_SESSION_ID}

Reads the hook event JSON from stdin, extracts tool_name and result size,
and appends an observation line to ~/.archolith/sessions/<sessionId>.jsonl.
"""

import json
import sys
from datetime import UTC, datetime
from pathlib import Path


def main() -> None:
    session_id = sys.argv[1] if len(sys.argv) > 1 else "claude-default"

    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        # If stdin is empty or invalid JSON, exit silently — don't block
        print(json.dumps({"continue": True}))
        return

    tool_name = payload.get("tool_name", payload.get("tool", "unknown"))
    result = payload.get("tool_result", payload.get("result", "") or "")
    chars = len(str(result))

    sessions_dir = Path.home() / ".archolith" / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)

    entry = json.dumps({
        "tool": tool_name,
        "chars": chars,
        "ts": datetime.now(UTC).isoformat(),
    })

    try:
        with open(sessions_dir / f"{session_id}.jsonl", "a", encoding="utf-8") as f:
            f.write(entry + "\n")
    except OSError:
        pass  # never block the agent

    print(json.dumps({"continue": True}))


if __name__ == "__main__":
    main()
