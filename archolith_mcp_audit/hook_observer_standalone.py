#!/usr/bin/env python3
"""
archolith-audit hook observer — standalone shim.

Zero package imports. Reads a PostToolUse (or equivalent) payload from stdin
as JSON, measures the result size in tokens (tiktoken cl100k_base when
available, chars/4 otherwise), and appends one observation line to the shared
telemetry JSONL file at ~/.archolith/sessions/<session_id>.jsonl.

Installed by ``scripts/install.py`` to the agent-specific hooks directory.
Never raises — any error silently succeeds so the agent loop is never blocked.

Usage:
    python archolith-audit-observer.py
    python archolith-audit-observer.py <session_id>

The optional session_id argument selects which JSONL file to write.
Omit to use "current" (default for single-session testing).
Claude Code substitutes $CLAUDE_SESSION_ID in hook command strings.
"""

import datetime
import json
import os
import sys
from pathlib import Path

SESSIONS_DIR = Path.home() / ".archolith" / "sessions"
_UNSAFE_SESSION_CHARS = "/\\\x00\r\n\t"


def _safe_session_id(session_id: str) -> str:
    cleaned = session_id
    for char in _UNSAFE_SESSION_CHARS:
        cleaned = cleaned.replace(char, "_")
    cleaned = cleaned.replace("..", "_").strip()
    return cleaned if cleaned.strip("._") else "current"


def _append_jsonl(path: Path, line: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (line.rstrip("\n") + "\n").encode("utf-8")
    fd = os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
    try:
        os.write(fd, payload)
    finally:
        os.close(fd)

# ---------------------------------------------------------------------------
# Token counting — tiktoken when available, chars/4 fallback
# ---------------------------------------------------------------------------

try:
    import tiktoken
    _enc = tiktoken.get_encoding("cl100k_base")

    def _count_tokens(text: str) -> int:
        return len(_enc.encode(text, disallowed_special=()))
except Exception:
    _enc = None

    def _count_tokens(text: str) -> int:  # type: ignore[misc]
        return max(1, len(text) // 4)

# NOTE: tiktoken import code is duplicated from tokenizer.py rather than
# imported, because this file is designed to work as a standalone hook observer
# with zero package dependencies. It's installed into agent hook directories
# where the archolith_mcp_audit package may not be importable. If the package
# layout changes, keep this self-contained.


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    # Session ID: from CLI arg, env var, or "current" fallback.
    # Claude Code substitutes $CLAUDE_SESSION_ID in the hook command string.
    session_id = "current"
    if len(sys.argv) > 1 and sys.argv[1].strip():
        session_id = _safe_session_id(sys.argv[1].strip())
    elif os.environ.get("MCP_AUDIT_SESSION_ID"):
        session_id = _safe_session_id(os.environ["MCP_AUDIT_SESSION_ID"])

    # Read stdin — agent sends the full PostToolUse payload as JSON.
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        print(json.dumps({"continue": True}))
        return

    # Extract tool name — handle multiple payload shapes across agents.
    tool_name = (
        payload.get("tool_name")
        or payload.get("tool")
        or "unknown"
    )

    # Extract result text — try common field names across agent payloads.
    result = (
        payload.get("tool_response")
        or payload.get("tool_result")
        or payload.get("result")
        or payload.get("output")
        or ""
    )
    result_text = json.dumps(result) if not isinstance(result, str) else result
    chars = len(result_text)
    tokens = _count_tokens(result_text)

    # Append one JSONL observation.
    # filtered_tokens == raw_tokens means passthrough (no archolith-filter active).
    # When archolith-filter is active, RtkTelemetrySource overwrites filtered counts.
    try:
        entry = json.dumps({
            "tool_name": tool_name,
            "raw_tokens": tokens,
            "raw_chars": chars,
            "filtered_tokens": tokens,   # passthrough — 0% savings
            "filtered_chars": chars,
            "tiktoken_used": _enc is not None,
            "timestamp": datetime.datetime.now(datetime.UTC).timestamp(),
            "session_id": session_id,
        })
        _append_jsonl(SESSIONS_DIR / f"{session_id}.jsonl", entry)
    except Exception:
        pass  # never block the agent

    # Signal continue to the agent harness.
    print(json.dumps({"continue": True}))


if __name__ == "__main__":
    main()
