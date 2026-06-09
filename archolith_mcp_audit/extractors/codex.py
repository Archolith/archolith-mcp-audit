"""Codex JSONL session extraction adapter."""

from __future__ import annotations

import json
from pathlib import Path

from archolith_mcp_audit.extractors.base import SessionData, ToolCall, ToolResult

__all__ = ["extract_session"]


def extract_session(jsonl_path: str | Path, max_results: int | None = None) -> SessionData:
    """Extract session data from a Codex JSONL file.

    Two-pass extraction:
    1. Build call_id -> (tool_name, args) mapping from function_call entries
    2. Extract function_call_output entries
    """
    path = Path(jsonl_path)
    session_id = path.stem

    # First pass: build call_id -> (name, args)
    call_id_map: dict[str, tuple[str, str]] = {}  # call_id -> (name, args_json)
    session_meta = {}

    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            entry_type = entry.get("type", "")

            if entry_type == "session_meta":
                session_meta = entry.get("payload", {})
                # Try to extract session_id from meta
                if "session_id" in session_meta:
                    session_id = session_meta["session_id"]

            elif entry_type == "response_item":
                payload = entry.get("payload", {})
                if payload.get("type") == "function_call":
                    call_id = payload.get("call_id", "")
                    name = payload.get("name", "unknown")
                    args = payload.get("arguments", "")
                    if isinstance(args, dict):
                        args = json.dumps(args)
                    if call_id:
                        call_id_map[call_id] = (name, args or "")

    # Second pass: extract results
    tool_calls: list[ToolCall] = []
    tool_results: list[ToolResult] = []
    turn_number = 0

    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            if entry.get("type") != "response_item":
                continue

            payload = entry.get("payload", {})
            ptype = payload.get("type", "")

            if ptype == "function_call":
                turn_number += 1
                call_id = payload.get("call_id", "")
                name, args = call_id_map.get(call_id, (payload.get("name", "unknown"), ""))
                tool_calls.append(ToolCall(
                    tool_name=name,
                    args=args,
                    call_id=call_id,
                    turn_number=turn_number,
                ))

            elif ptype == "function_call_output":
                call_id = payload.get("call_id", "")
                name, _ = call_id_map.get(call_id, ("unknown", ""))
                output = payload.get("output", "")

                # Output can be string or list of dicts (e.g., view_image)
                if isinstance(output, str) and output:
                    text = output
                elif isinstance(output, list):
                    texts = []
                    for item in output:
                        item_str = json.dumps(item) if isinstance(item, dict) else str(item)
                        if item_str:
                            texts.append(item_str)
                    text = "\n".join(texts)
                else:
                    continue

                if text:
                    tool_results.append(ToolResult(
                        tool_name=name,
                        result_text=text,
                        call_id=call_id,
                        turn_number=turn_number,
                    ))

    if max_results and len(tool_results) > max_results:
        tool_results = tool_results[:max_results]

    return SessionData(
        source="codex",
        session_id=session_id,
        tool_calls=tool_calls,
        tool_results=tool_results,
        total_turns=turn_number,
    )
