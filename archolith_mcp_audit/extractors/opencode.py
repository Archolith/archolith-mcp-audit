"""OpenCode SQLite session extraction adapter."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from archolith_mcp_audit.extractors.base import SessionData, ToolCall, ToolResult


def extract_session(
    sqlite_path: str | Path,
    session_id: str | None = None,
    limit: int = 5000,
) -> SessionData:
    """Extract session data from an OpenCode SQLite database.

    Reads from the `part` table where `data` contains JSON with type="tool".
    """
    path = Path(sqlite_path)
    db = sqlite3.connect(str(path))
    c = db.cursor()

    # Find sessions
    if session_id:
        sessions = [session_id]
    else:
        sessions = [row[0] for row in c.execute(
            "SELECT DISTINCT json_extract(data, '$.session_id') FROM part "
            "WHERE json_extract(data, '$.session_id') IS NOT NULL LIMIT 100"
        )]

    # Use first session if not specified
    effective_session = sessions[0] if sessions else "unknown"

    # Extract tool parts
    query = "SELECT data FROM part WHERE data LIKE '%\"type\":\"tool\"%'"
    if effective_session and effective_session != "unknown":
        query += f" AND data LIKE '%\"session_id\":\"{effective_session}\"%'"
    query += f" LIMIT {limit}"

    tool_calls: list[ToolCall] = []
    tool_results: list[ToolResult] = []
    turn_number = 0

    for row in c.execute(query):
        try:
            data = json.loads(row[0])
        except (json.JSONDecodeError, TypeError):
            continue

        tool_name = data.get("tool", "unknown")
        state = data.get("state", {})
        if not isinstance(state, dict):
            continue

        turn_number += 1

        # Extract call arguments
        call_input = state.get("input", "")
        if isinstance(call_input, dict):
            call_input = json.dumps(call_input)

        tool_calls.append(ToolCall(
            tool_name=tool_name,
            args=call_input or "",
            call_id=data.get("id", f"opencode-{turn_number}"),
            turn_number=turn_number,
        ))

        # Extract result
        output = state.get("output", "")
        if output:
            tool_results.append(ToolResult(
                tool_name=tool_name,
                result_text=output,
                call_id=data.get("id", f"opencode-{turn_number}"),
                turn_number=turn_number,
            ))

    db.close()

    return SessionData(
        source="opencode",
        session_id=effective_session,
        tool_calls=tool_calls,
        tool_results=tool_results,
        total_turns=turn_number,
    )
