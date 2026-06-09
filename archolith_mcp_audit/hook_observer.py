"""Hook observer — observes tool results via LLM-platform hook callbacks.

Provides hook implementations for various LLM platforms (Claude Code, Codex,
OpenCode) that observe tool results as they flow through the session and
feed them into the TelemetryBridge.

Hook observers are the "before" side of the observation pipeline:
  1. LLM platform calls a tool
  2. Tool result is produced
  3. Hook observer intercepts the result (read-only, no modification)
  4. Observer forwards raw_chars/filtered_chars to the TelemetryBridge
  5. Bridge feeds the LiveAccumulator

Design principle: Observers are passive. They measure and report.
They do NOT modify tool results or intercept tool calls.

Supported hook mechanisms:
  - Claude Code: PreToolUse / PostToolUse hook events
  - Codex: Shell hook wrapper
  - OpenCode: Event callback registration
  - Generic: File-based observation (telemetry file written by external process)
"""

from __future__ import annotations

import json
import logging
import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from archolith_mcp_audit.telemetry_bridge import (
    TelemetryBridge,
    write_telemetry_entry,
)

log = logging.getLogger(__name__)

__all__ = [
    "HookEvent",
    "HookObserver",
    "ClaudeCodeHookObserver",
    "CodexHookObserver",
    "OpenCodeHookObserver",
    "create_observer",
]


@dataclass
class HookEvent:
    """A single hook event from an LLM platform."""

    event_type: str  # "pre_tool_use", "post_tool_use", "error"
    tool_name: str = ""
    raw_result: str = ""
    filtered_result: str = ""
    timestamp: float = 0.0
    session_id: str = ""
    metadata: dict = field(default_factory=dict)

    @property
    def raw_chars(self) -> int:
        return len(self.raw_result)

    @property
    def filtered_chars(self) -> int:
        return len(self.filtered_result) if self.filtered_result else 0


HookCallback = Callable[[HookEvent], None]


class HookObserver:
    """Base hook observer that forwards tool result observations to a bridge.

    Subclasses implement platform-specific event parsing. The base class
    handles the common logic of converting hook events into accumulator
    observations.
    """

    def __init__(
        self,
        bridge: TelemetryBridge,
        telemetry_file: Path | None = None,
    ) -> None:
        self.bridge = bridge
        self.telemetry_file = telemetry_file
        self._callbacks: list[HookCallback] = []
        self._event_count: int = 0
        self._error_count: int = 0

    def on_post_tool_use(self, event: HookEvent) -> None:
        """Handle a post-tool-use event.

        This is the primary observation point — after the tool has
        produced a result, we measure it and forward to the bridge.
        """
        if event.event_type != "post_tool_use":
            return

        if not event.tool_name:
            log.warning("Hook event missing tool_name, skipping")
            self._error_count += 1
            return

        self.bridge.push(
            tool_name=event.tool_name,
            raw_chars=event.raw_chars,
            filtered_chars=event.filtered_chars,
            session_id=event.session_id,
        )
        self._event_count += 1

        if self.telemetry_file:
            try:
                write_telemetry_entry(
                    path=self.telemetry_file,
                    tool_name=event.tool_name,
                    raw_chars=event.raw_chars,
                    filtered_chars=event.filtered_chars,
                    session_id=event.session_id,
                    metadata=event.metadata,
                )
            except OSError as e:
                log.warning("Failed to write telemetry entry: %s", e)

        for cb in self._callbacks:
            try:
                cb(event)
            except Exception as e:
                log.warning("Hook callback error: %s", e)

    def add_callback(self, callback: HookCallback) -> None:
        self._callbacks.append(callback)

    @property
    def event_count(self) -> int:
        return self._event_count

    @property
    def error_count(self) -> int:
        return self._error_count


class ClaudeCodeHookObserver(HookObserver):
    """Hook observer for Claude Code's PreToolUse/PostToolUse hook protocol.

    Claude Code emits JSON hook events on stdin when configured with
    hook commands in .claude/settings.json.

    Hook event format (Claude Code):
        {
            "event_type": "PostToolUse",
            "tool_name": "mcp__vps__vps_status",
            "tool_result": "...",
            "session_id": "...",
            ...
        }
    """

    def parse_event(self, raw: str | dict) -> HookEvent | None:
        """Parse a Claude Code hook event from raw JSON or dict."""
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError:
                log.warning("Invalid JSON in Claude Code hook event")
                return None

        event_type_raw = raw.get("event_type", raw.get("type", "")).lower()
        if event_type_raw in ("posttooluse", "post_tool_use"):
            event_type = "post_tool_use"
        elif event_type_raw in ("pretooluse", "pre_tool_use"):
            event_type = "pre_tool_use"
        elif event_type_raw == "error":
            event_type = "error"
        else:
            return None

        tool_result = raw.get("tool_result", raw.get("result", ""))
        filtered_result = raw.get("filtered_result", "")

        return HookEvent(
            event_type=event_type,
            tool_name=raw.get("tool_name", raw.get("tool", "")),
            raw_result=tool_result if isinstance(tool_result, str) else json.dumps(tool_result),
            filtered_result=filtered_result if isinstance(filtered_result, str) else "",
            timestamp=raw.get("timestamp", time.time()),
            session_id=raw.get("session_id", ""),
            metadata=raw.get("metadata", {}),
        )

    def process_stdin(self) -> int:
        """Read and process hook events from stdin.

        Used when configured as a Claude Code hook command.
        Returns the number of events processed.
        """
        import sys

        count = 0
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            event = self.parse_event(line)
            if event is not None:
                self.on_post_tool_use(event)
                count += 1
        return count


class CodexHookObserver(HookObserver):
    """Hook observer for Codex's shell hook wrapper.

    Codex doesn't have native hook support, so this observer works
    by wrapping tool execution in a shell function that captures
    result sizes and forwards them to the telemetry bridge.

    The wrapper writes observations to a telemetry file which the
    FileTelemetrySource in the bridge picks up.
    """

    def __init__(
        self,
        bridge: TelemetryBridge,
        telemetry_file: Path | None = None,
    ) -> None:
        if telemetry_file is None:
            telemetry_file = Path(
                os.environ.get(
                    "MCP_AUDIT_TELEMETRY_FILE",
                    Path.home() / ".cache" / "mcp-audit" / "telemetry.jsonl",
                )
            )
        super().__init__(bridge=bridge, telemetry_file=telemetry_file)

    def observe_tool_result(
        self,
        tool_name: str,
        result: str,
        session_id: str = "",
    ) -> None:
        """Observe a tool result from Codex execution.

        This is called by the shell wrapper after each tool execution.
        """
        event = HookEvent(
            event_type="post_tool_use",
            tool_name=tool_name,
            raw_result=result,
            timestamp=time.time(),
            session_id=session_id,
        )
        self.on_post_tool_use(event)


class OpenCodeHookObserver(HookObserver):
    """Hook observer for OpenCode's event callback system.

    OpenCode provides an event callback mechanism that can be
    registered to observe tool results as they flow through the
    session.
    """

    def observe_opencode_event(self, event_data: dict) -> None:
        """Process an OpenCode tool event.

        Expected event_data keys:
            - tool_name: str
            - result: str (the tool result text)
            - session_id: str (optional)
        """
        tool_name = event_data.get("tool_name", "")
        result = event_data.get("result", "")
        session_id = event_data.get("session_id", "")

        if not tool_name:
            log.warning("OpenCode event missing tool_name")
            return

        event = HookEvent(
            event_type="post_tool_use",
            tool_name=tool_name,
            raw_result=result if isinstance(result, str) else json.dumps(result),
            timestamp=time.time(),
            session_id=session_id,
            metadata=event_data.get("metadata", {}),
        )
        self.on_post_tool_use(event)


def create_observer(
    platform: str,
    bridge: TelemetryBridge,
    telemetry_file: Path | None = None,
) -> HookObserver:
    """Factory function to create a platform-specific hook observer.

    Args:
        platform: One of "claude", "codex", "opencode", "generic"
        bridge: The TelemetryBridge to forward observations to
        telemetry_file: Optional file path for persistent telemetry

    Returns:
        A HookObserver instance for the specified platform
    """
    observers: dict[str, type[HookObserver]] = {
        "claude": ClaudeCodeHookObserver,
        "codex": CodexHookObserver,
        "opencode": OpenCodeHookObserver,
    }

    observer_cls = observers.get(platform)
    if observer_cls is None:
        log.warning("Unknown platform '%s', falling back to generic HookObserver", platform)
        return HookObserver(bridge=bridge, telemetry_file=telemetry_file)

    return observer_cls(bridge=bridge, telemetry_file=telemetry_file)
