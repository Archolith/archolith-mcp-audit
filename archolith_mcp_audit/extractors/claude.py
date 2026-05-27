"""Claude JSONL session extraction adapter."""

from __future__ import annotations

import json
from pathlib import Path

from archolith_mcp_audit.extractors.base import SessionData, ToolCall, ToolResult


def extract_session(jsonl_path: str | Path, max_results: int | None = None) -> SessionData:
    """Extract session data from a Claude JSONL file.

    Two-pass extraction:
    1. Build tool_use_id -> (tool_name, args) mapping from assistant messages
    2. Extract tool results from user messages
    """
    path = Path(jsonl_path)
    session_id = path.stem

    # First pass: build tool_use_id -> (name, args)
    tool_use_map: dict[str, tuple[str, str]] = {}  # id -> (name, args_json)
    total_turns = 0

    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            if entry.get("type") == "assistant":
                total_turns += 1
                for block in entry.get("message", {}).get("content", []):
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        tool_id = block.get("id", "")
                        name = block.get("name", "unknown")
                        args = block.get("input", {})
                        args_str = json.dumps(args) if isinstance(args, dict) else str(args)
                        if tool_id:
                            tool_use_map[tool_id] = (name, args_str)

    # Second pass: extract tool results
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

            if entry.get("type") == "assistant":
                turn_number += 1
                for block in entry.get("message", {}).get("content", []):
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        tool_id = block.get("id", "")
                        name, args = tool_use_map.get(tool_id, (block.get("name", "unknown"), ""))
                        tool_calls.append(ToolCall(
                            tool_name=name,
                            args=args,
                            call_id=tool_id,
                            turn_number=turn_number,
                        ))

            elif entry.get("type") == "user":
                for block in entry.get("message", {}).get("content", []):
                    if isinstance(block, str):
                        continue
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        tool_use_id = block.get("tool_use_id", "")
                        name, _ = tool_use_map.get(tool_use_id, ("unknown", ""))
                        content = block.get("content", "")

                        # Content can be string or list of dicts
                        if isinstance(content, str) and content:
                            text = content
                        elif isinstance(content, list):
                            texts = []
                            for sub in content:
                                if isinstance(sub, dict) and sub.get("type") == "text":
                                    t = sub.get("text", "")
                                    if t:
                                        texts.append(t)
                            text = "\n".join(texts)
                        else:
                            continue

                        if text:
                            tool_results.append(ToolResult(
                                tool_name=name,
                                result_text=text,
                                call_id=tool_use_id,
                                turn_number=turn_number,
                            ))

    if max_results and len(tool_results) > max_results:
        tool_results = tool_results[:max_results]

    return SessionData(
        source="claude",
        session_id=session_id,
        tool_calls=tool_calls,
        tool_results=tool_results,
        total_turns=total_turns,
    )
