"""Tests for archolith_mcp_audit.telemetry_bridge."""

from __future__ import annotations

import json
from pathlib import Path

from archolith_mcp_audit.accumulator import LiveAccumulator
from archolith_mcp_audit.telemetry_bridge import (
    FileTelemetrySource,
    InMemoryTelemetrySource,
    TelemetryBridge,
    TelemetryEntry,
    write_telemetry_entry,
)


class TestTelemetryEntry:
    def test_fields(self) -> None:
        entry = TelemetryEntry(tool_name="test", raw_chars=100, filtered_chars=50)
        assert entry.tool_name == "test"
        assert entry.raw_chars == 100
        assert entry.filtered_chars == 50
        assert entry.timestamp == 0.0

    def test_defaults(self) -> None:
        entry = TelemetryEntry(tool_name="test", raw_chars=100)
        assert entry.filtered_chars == 0
        assert entry.session_id == ""
        assert entry.metadata == {}


class TestInMemoryTelemetrySource:
    def test_available_by_default(self) -> None:
        source = InMemoryTelemetrySource()
        assert source.is_available()

    def test_add_and_pull(self) -> None:
        source = InMemoryTelemetrySource()
        source.add_observation("mcp__vps__vps_status", 1000, 500)
        source.add_observation("mcp__memory__query_structure", 500, 250)
        entries = source.pull()
        assert len(entries) == 2
        assert entries[0].tool_name == "mcp__vps__vps_status"
        assert entries[0].raw_chars == 1000
        assert entries[1].tool_name == "mcp__memory__query_structure"

    def test_pull_clears_buffer(self) -> None:
        source = InMemoryTelemetrySource()
        source.add_observation("test", 100)
        entries = source.pull()
        assert len(entries) == 1
        entries2 = source.pull()
        assert len(entries2) == 0

    def test_add_entry_directly(self) -> None:
        source = InMemoryTelemetrySource()
        entry = TelemetryEntry(tool_name="test", raw_chars=42, filtered_chars=20)
        source.add(entry)
        entries = source.pull()
        assert len(entries) == 1
        assert entries[0].raw_chars == 42


class TestFileTelemetrySource:
    def test_missing_file_unavailable(self, tmp_path: Path) -> None:
        source = FileTelemetrySource(tmp_path / "nonexistent.jsonl")
        assert not source.is_available()

    def test_pull_from_file(self, tmp_path: Path) -> None:
        path = tmp_path / "telemetry.jsonl"
        entries_data = [
            {"tool_name": "mcp__vps__vps_status", "raw_chars": 1000, "filtered_chars": 500},
            {"tool_name": "mcp__gradle__gradle_compile", "raw_chars": 2000, "filtered_chars": 800},
        ]
        with open(path, "w", encoding="utf-8") as f:
            for entry in entries_data:
                f.write(json.dumps(entry) + "\n")

        source = FileTelemetrySource(path)
        assert source.is_available()
        entries = source.pull()
        assert len(entries) == 2
        assert entries[0].tool_name == "mcp__vps__vps_status"
        assert entries[0].raw_chars == 1000
        assert entries[1].tool_name == "mcp__gradle__gradle_compile"

    def test_incremental_pull(self, tmp_path: Path) -> None:
        path = tmp_path / "telemetry.jsonl"
        with open(path, "w", encoding="utf-8") as f:
            f.write(json.dumps({"tool_name": "first", "raw_chars": 100}) + "\n")

        source = FileTelemetrySource(path)
        entries1 = source.pull()
        assert len(entries1) == 1

        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"tool_name": "second", "raw_chars": 200}) + "\n")

        entries2 = source.pull()
        assert len(entries2) == 1
        assert entries2[0].tool_name == "second"

    def test_invalid_json_skipped(self, tmp_path: Path) -> None:
        path = tmp_path / "telemetry.jsonl"
        with open(path, "w", encoding="utf-8") as f:
            f.write(json.dumps({"tool_name": "valid", "raw_chars": 100}) + "\n")
            f.write("invalid json\n")
            f.write(json.dumps({"tool_name": "also_valid", "raw_chars": 200}) + "\n")

        source = FileTelemetrySource(path)
        entries = source.pull()
        assert len(entries) == 2


class TestTelemetryBridge:
    def test_push_directly(self) -> None:
        acc = LiveAccumulator()
        bridge = TelemetryBridge(accumulator=acc)
        bridge.push("mcp__vps__vps_status", 1000, 500)
        summary = acc.get_server_summary()
        assert "vps" in summary
        assert summary["vps"]["call_count"] == 1
        assert bridge.total_synced == 1

    def test_sync_from_memory_source(self) -> None:
        acc = LiveAccumulator()
        bridge = TelemetryBridge(accumulator=acc)
        source = InMemoryTelemetrySource()
        source.add_observation("mcp__vps__vps_status", 1000, 500)
        source.add_observation("mcp__gradle__gradle_compile", 2000, 1000)
        bridge.add_source(source)

        count = bridge.sync()
        assert count == 2
        summary = acc.get_server_summary()
        assert "vps" in summary
        assert "gradle" in summary

    def test_sync_from_file_source(self, tmp_path: Path) -> None:
        path = tmp_path / "telemetry.jsonl"
        with open(path, "w", encoding="utf-8") as f:
            f.write(json.dumps({"tool_name": "mcp__vps__vps_status", "raw_chars": 800}) + "\n")

        acc = LiveAccumulator()
        bridge = TelemetryBridge(accumulator=acc)
        bridge.connect_file(path)

        count = bridge.sync()
        assert count == 1
        summary = acc.get_server_summary()
        assert "vps" in summary

    def test_sync_multiple_sources(self) -> None:
        acc = LiveAccumulator()
        bridge = TelemetryBridge(accumulator=acc)

        source1 = InMemoryTelemetrySource()
        source1.add_observation("mcp__vps__vps_status", 1000)
        bridge.add_source(source1)

        source2 = InMemoryTelemetrySource()
        source2.add_observation("mcp__memory__query_structure", 500)
        bridge.add_source(source2)

        count = bridge.sync()
        assert count == 2
        assert bridge.source_count() == 2
        assert bridge.active_source_count() == 2

    def test_sync_empty_sources(self) -> None:
        acc = LiveAccumulator()
        bridge = TelemetryBridge(accumulator=acc)
        source = InMemoryTelemetrySource()
        bridge.add_source(source)
        count = bridge.sync()
        assert count == 0

    def test_push_increments_total(self) -> None:
        acc = LiveAccumulator()
        bridge = TelemetryBridge(accumulator=acc)
        bridge.push("mcp__vps__vps_status", 1000)
        bridge.push("mcp__gradle__gradle_compile", 2000)
        assert bridge.total_synced == 2


class TestWriteTelemetryEntry:
    def test_writes_jsonl(self, tmp_path: Path) -> None:
        path = tmp_path / "out.jsonl"
        write_telemetry_entry(path, "mcp__vps__vps_status", 1000, 500)
        write_telemetry_entry(path, "mcp__gradle__gradle_compile", 2000)

        with open(path, encoding="utf-8") as f:
            lines = f.readlines()
        assert len(lines) == 2

        entry1 = json.loads(lines[0])
        assert entry1["tool_name"] == "mcp__vps__vps_status"
        assert entry1["raw_chars"] == 1000
        assert entry1["filtered_chars"] == 500
        assert "timestamp" in entry1

    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        path = tmp_path / "deep" / "nested" / "out.jsonl"
        write_telemetry_entry(path, "test", 100)
        assert path.exists()

    def test_metadata(self, tmp_path: Path) -> None:
        path = tmp_path / "out.jsonl"
        write_telemetry_entry(path, "test", 100, metadata={"key": "value"})
        with open(path, encoding="utf-8") as f:
            entry = json.loads(f.readline())
        assert entry["metadata"] == {"key": "value"}
