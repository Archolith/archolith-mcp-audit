"""Tests for archolith_mcp_audit.hook_observer."""

from __future__ import annotations

import json
from pathlib import Path

from archolith_mcp_audit.accumulator import LiveAccumulator
from archolith_mcp_audit.hook_observer import (
    ClaudeCodeHookObserver,
    CodexHookObserver,
    HookEvent,
    HookObserver,
    OpenCodeHookObserver,
    create_observer,
)
from archolith_mcp_audit.telemetry_bridge import TelemetryBridge


def _make_bridge() -> tuple[LiveAccumulator, TelemetryBridge]:
    acc = LiveAccumulator()
    bridge = TelemetryBridge(accumulator=acc)
    return acc, bridge


class TestHookEvent:
    def test_raw_chars(self) -> None:
        event = HookEvent(event_type="post_tool_use", tool_name="test", raw_result="hello world")
        assert event.raw_chars == 11

    def test_filtered_chars(self) -> None:
        event = HookEvent(
            event_type="post_tool_use", tool_name="test",
            raw_result="hello world", filtered_result="hello",
        )
        assert event.filtered_chars == 5

    def test_filtered_chars_default(self) -> None:
        event = HookEvent(event_type="post_tool_use", tool_name="test", raw_result="hello")
        assert event.filtered_chars == 0


class TestHookObserver:
    def test_on_post_tool_use(self) -> None:
        acc, bridge = _make_bridge()
        observer = HookObserver(bridge=bridge)
        event = HookEvent(
            event_type="post_tool_use",
            tool_name="mcp__vps__vps_status",
            raw_result="x" * 1000,
        )
        observer.on_post_tool_use(event)
        summary = acc.get_server_summary()
        assert "vps" in summary
        assert summary["vps"]["call_count"] == 1
        assert observer.event_count == 1

    def test_ignores_pre_tool_use(self) -> None:
        acc, bridge = _make_bridge()
        observer = HookObserver(bridge=bridge)
        event = HookEvent(event_type="pre_tool_use", tool_name="test", raw_result="data")
        observer.on_post_tool_use(event)
        assert observer.event_count == 0

    def test_skips_missing_tool_name(self) -> None:
        acc, bridge = _make_bridge()
        observer = HookObserver(bridge=bridge)
        event = HookEvent(event_type="post_tool_use", tool_name="", raw_result="data")
        observer.on_post_tool_use(event)
        assert observer.error_count == 1
        assert observer.event_count == 0

    def test_writes_telemetry_file(self, tmp_path: Path) -> None:
        acc, bridge = _make_bridge()
        telemetry_file = tmp_path / "telemetry.jsonl"
        observer = HookObserver(bridge=bridge, telemetry_file=telemetry_file)

        event = HookEvent(
            event_type="post_tool_use",
            tool_name="mcp__vps__vps_status",
            raw_result="x" * 100,
        )
        observer.on_post_tool_use(event)

        assert telemetry_file.exists()
        with open(telemetry_file, encoding="utf-8") as f:
            data = json.loads(f.readline())
        assert data["tool_name"] == "mcp__vps__vps_status"
        assert data["raw_chars"] == 100

    def test_callback(self) -> None:
        acc, bridge = _make_bridge()
        observer = HookObserver(bridge=bridge)
        received: list[HookEvent] = []
        observer.add_callback(lambda e: received.append(e))

        event = HookEvent(
            event_type="post_tool_use",
            tool_name="test",
            raw_result="data",
        )
        observer.on_post_tool_use(event)
        assert len(received) == 1
        assert received[0].tool_name == "test"


class TestClaudeCodeHookObserver:
    def test_parse_post_tool_use(self) -> None:
        acc, bridge = _make_bridge()
        observer = ClaudeCodeHookObserver(bridge=bridge)
        raw = {
            "event_type": "PostToolUse",
            "tool_name": "mcp__vps__vps_status",
            "tool_result": "result text",
        }
        event = observer.parse_event(raw)
        assert event is not None
        assert event.event_type == "post_tool_use"
        assert event.tool_name == "mcp__vps__vps_status"
        assert event.raw_result == "result text"

    def test_parse_pre_tool_use(self) -> None:
        acc, bridge = _make_bridge()
        observer = ClaudeCodeHookObserver(bridge=bridge)
        raw = {"event_type": "PreToolUse", "tool_name": "test"}
        event = observer.parse_event(raw)
        assert event is not None
        assert event.event_type == "pre_tool_use"

    def test_parse_from_json_string(self) -> None:
        acc, bridge = _make_bridge()
        observer = ClaudeCodeHookObserver(bridge=bridge)
        raw = json.dumps({
            "event_type": "PostToolUse",
            "tool_name": "test",
            "tool_result": "hello",
        })
        event = observer.parse_event(raw)
        assert event is not None
        assert event.tool_name == "test"

    def test_parse_invalid_json(self) -> None:
        acc, bridge = _make_bridge()
        observer = ClaudeCodeHookObserver(bridge=bridge)
        event = observer.parse_event("not json")
        assert event is None

    def test_parse_unknown_event_type(self) -> None:
        acc, bridge = _make_bridge()
        observer = ClaudeCodeHookObserver(bridge=bridge)
        raw = {"event_type": "Unknown", "tool_name": "test"}
        event = observer.parse_event(raw)
        assert event is None

    def test_parse_result_key_fallback(self) -> None:
        acc, bridge = _make_bridge()
        observer = ClaudeCodeHookObserver(bridge=bridge)
        raw = {"event_type": "PostToolUse", "tool_name": "test", "result": "fallback"}
        event = observer.parse_event(raw)
        assert event is not None
        assert event.raw_result == "fallback"

    def test_parse_dict_result_serialized(self) -> None:
        acc, bridge = _make_bridge()
        observer = ClaudeCodeHookObserver(bridge=bridge)
        raw = {"event_type": "PostToolUse", "tool_name": "test", "tool_result": {"key": "val"}}
        event = observer.parse_event(raw)
        assert event is not None
        parsed = json.loads(event.raw_result)
        assert parsed["key"] == "val"


class TestCodexHookObserver:
    def test_observe_tool_result(self) -> None:
        acc, bridge = _make_bridge()
        observer = CodexHookObserver(bridge=bridge)
        observer.observe_tool_result("mcp__gradle__gradle_compile", "build output")
        summary = acc.get_server_summary()
        assert "gradle" in summary
        assert observer.event_count == 1

    def test_default_telemetry_file(self) -> None:
        acc, bridge = _make_bridge()
        observer = CodexHookObserver(bridge=bridge)
        assert observer.telemetry_file is not None


class TestOpenCodeHookObserver:
    def test_observe_opencode_event(self) -> None:
        acc, bridge = _make_bridge()
        observer = OpenCodeHookObserver(bridge=bridge)
        observer.observe_opencode_event({
            "tool_name": "mcp__memory__query_structure",
            "result": "structure data",
            "session_id": "sess-123",
        })
        summary = acc.get_server_summary()
        assert "memory" in summary
        assert observer.event_count == 1

    def test_missing_tool_name(self) -> None:
        acc, bridge = _make_bridge()
        observer = OpenCodeHookObserver(bridge=bridge)
        observer.observe_opencode_event({"result": "data"})
        assert observer.event_count == 0


class TestCreateObserver:
    def test_claude(self) -> None:
        acc, bridge = _make_bridge()
        observer = create_observer("claude", bridge)
        assert isinstance(observer, ClaudeCodeHookObserver)

    def test_codex(self) -> None:
        acc, bridge = _make_bridge()
        observer = create_observer("codex", bridge)
        assert isinstance(observer, CodexHookObserver)

    def test_opencode(self) -> None:
        acc, bridge = _make_bridge()
        observer = create_observer("opencode", bridge)
        assert isinstance(observer, OpenCodeHookObserver)

    def test_unknown_falls_back(self) -> None:
        acc, bridge = _make_bridge()
        observer = create_observer("unknown_platform", bridge)
        assert isinstance(observer, HookObserver)
