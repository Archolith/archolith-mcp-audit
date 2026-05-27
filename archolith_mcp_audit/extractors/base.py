"""Shared data structures for session extraction adapters."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ToolCall:
    """A single tool invocation (the request, not the response)."""

    tool_name: str
    args: str  # JSON string of call arguments
    call_id: str  # ID for matching to result
    turn_number: int  # Sequence position in session


@dataclass
class ToolResult:
    """A single tool response."""

    tool_name: str
    result_text: str
    call_id: str  # ID matching to ToolCall
    turn_number: int  # Sequence position in session


@dataclass
class SessionData:
    """Core container for an extracted session."""

    source: str  # "claude", "codex", or "opencode"
    session_id: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_results: list[ToolResult] = field(default_factory=list)
    system_prompt_tokens: int = 0  # Estimated schema token cost
    total_turns: int = 0
