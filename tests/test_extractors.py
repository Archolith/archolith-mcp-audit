"""Tests for archolith_mcp_audit extractors — Claude, Codex, OpenCode."""

from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path

from archolith_mcp_audit.extractors.base import SessionData, ToolCall, ToolResult
from archolith_mcp_audit.extractors.claude import extract_session as extract_claude
from archolith_mcp_audit.extractors.codex import extract_session as extract_codex
from archolith_mcp_audit.extractors.opencode import extract_session as extract_opencode


def _write_jsonl(path: Path, entries: list[dict]) -> None:
    """Write JSONL entries to a temp file."""
    with open(path, "w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")


# ---------------------------------------------------------------------------
# Claude extractor tests
# ---------------------------------------------------------------------------

class TestClaudeExtractor:
    """Tests for Claude JSONL extraction."""

    def test_extracts_tool_calls_and_results(self) -> None:
        """Known session produces correct SessionData with calls and results."""
        entries = [
            # Assistant with tool use
            {"type": "assistant", "message": {"content": [
                {"type": "tool_use", "id": "call_1", "name": "mcp__gradle__gradle_compile",
                 "input": {"project_root": "/tmp/project"}}
            ]}},
            # User with tool result
            {"type": "user", "message": {"content": [
                {"type": "tool_result", "tool_use_id": "call_1",
                 "content": "BUILD SUCCESSFUL"}
            ]}},
        ]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            for e in entries:
                f.write(json.dumps(e) + "\n")
            path = Path(f.name)

        try:
            session = extract_claude(path)
            assert session.source == "claude"
            assert len(session.tool_calls) == 1
            assert session.tool_calls[0].tool_name == "mcp__gradle__gradle_compile"
            assert len(session.tool_results) == 1
            assert session.tool_results[0].result_text == "BUILD SUCCESSFUL"
        finally:
            path.unlink(missing_ok=True)

    def test_calls_matched_by_id(self) -> None:
        """Tool calls and results are matched by call_id."""
        entries = [
            {"type": "assistant", "message": {"content": [
                {"type": "tool_use", "id": "c1", "name": "mcp__vps__vps_status", "input": {}},
                {"type": "tool_use", "id": "c2", "name": "mcp__memory__query_structure", "input": {}},
            ]}},
            {"type": "user", "message": {"content": [
                {"type": "tool_result", "tool_use_id": "c1", "content": "Server running"},
                {"type": "tool_result", "tool_use_id": "c2", "content": "Graph data"},
            ]}},
        ]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            for e in entries:
                f.write(json.dumps(e) + "\n")
            path = Path(f.name)

        try:
            session = extract_claude(path)
            assert len(session.tool_calls) == 2
            assert len(session.tool_results) == 2
            # Results should have correct tool names via call_id mapping
            result_by_id = {r.call_id: r for r in session.tool_results}
            assert result_by_id["c1"].tool_name == "mcp__vps__vps_status"
            assert result_by_id["c2"].tool_name == "mcp__memory__query_structure"
        finally:
            path.unlink(missing_ok=True)

    def test_args_extracted(self) -> None:
        """Tool call arguments are extracted and parseable."""
        entries = [
            {"type": "assistant", "message": {"content": [
                {"type": "tool_use", "id": "call_args", "name": "mcp__vps__vps_deploy",
                 "input": {"service": "yawn-rip", "timeout_s": 600}}
            ]}},
            {"type": "user", "message": {"content": [
                {"type": "tool_result", "tool_use_id": "call_args", "content": "Deploying..."}
            ]}},
        ]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            for e in entries:
                f.write(json.dumps(e) + "\n")
            path = Path(f.name)

        try:
            session = extract_claude(path)
            args = json.loads(session.tool_calls[0].args)
            assert args["service"] == "yawn-rip"
            assert args["timeout_s"] == 600
        finally:
            path.unlink(missing_ok=True)

    def test_turn_numbers_sequential(self) -> None:
        """Turn numbers are sequential."""
        entries = [
            {"type": "assistant", "message": {"content": [
                {"type": "tool_use", "id": "t1", "name": "tool_a", "input": {}}
            ]}},
            {"type": "user", "message": {"content": [
                {"type": "tool_result", "tool_use_id": "t1", "content": "result1"}
            ]}},
            {"type": "assistant", "message": {"content": [
                {"type": "tool_use", "id": "t2", "name": "tool_b", "input": {}}
            ]}},
            {"type": "user", "message": {"content": [
                {"type": "tool_result", "tool_use_id": "t2", "content": "result2"}
            ]}},
        ]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            for e in entries:
                f.write(json.dumps(e) + "\n")
            path = Path(f.name)

        try:
            session = extract_claude(path)
            turns = [tc.turn_number for tc in session.tool_calls]
            assert turns == sorted(turns)
            assert len(set(turns)) == len(turns)  # unique
        finally:
            path.unlink(missing_ok=True)

    def test_malformed_entries_skipped(self) -> None:
        """Malformed JSONL entries are skipped gracefully."""
        entries = [
            {"type": "assistant", "message": {"content": [
                {"type": "tool_use", "id": "ok1", "name": "tool_a", "input": {}}
            ]}},
            "this is not json",
            "",
            {"type": "user", "message": {"content": [
                {"type": "tool_result", "tool_use_id": "ok1", "content": "result1"}
            ]}},
        ]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            for e in entries:
                if isinstance(e, str):
                    f.write(e + "\n")
                else:
                    f.write(json.dumps(e) + "\n")
            path = Path(f.name)

        try:
            session = extract_claude(path)
            assert len(session.tool_results) == 1
        finally:
            path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Codex extractor tests
# ---------------------------------------------------------------------------

class TestCodexExtractor:
    """Tests for Codex JSONL extraction."""

    def test_extracts_function_calls(self) -> None:
        """Codex JSONL produces correct SessionData."""
        entries = [
            {"type": "session_meta", "payload": {"session_id": "test-codex"}},
            {"type": "response_item", "payload": {
                "type": "function_call",
                "call_id": "fc1",
                "name": "mcp__gradle__gradle_test",
                "arguments": '{"project_root": "/tmp"}',
            }},
            {"type": "response_item", "payload": {
                "type": "function_call_output",
                "call_id": "fc1",
                "output": "All tests passed",
            }},
        ]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            for e in entries:
                f.write(json.dumps(e) + "\n")
            path = Path(f.name)

        try:
            session = extract_codex(path)
            assert session.source == "codex"
            assert len(session.tool_calls) == 1
            assert session.tool_calls[0].tool_name == "mcp__gradle__gradle_test"
            assert len(session.tool_results) == 1
            assert session.tool_results[0].result_text == "All tests passed"
        finally:
            path.unlink(missing_ok=True)

    def test_malformed_entries_skipped(self) -> None:
        """Malformed Codex entries are skipped."""
        entries = [
            "not json",
            {"type": "response_item", "payload": {
                "type": "function_call",
                "call_id": "fc1",
                "name": "tool_a",
                "arguments": "{}",
            }},
            {"type": "response_item", "payload": {
                "type": "function_call_output",
                "call_id": "fc1",
                "output": "ok",
            }},
        ]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            for e in entries:
                if isinstance(e, str):
                    f.write(e + "\n")
                else:
                    f.write(json.dumps(e) + "\n")
            path = Path(f.name)

        try:
            session = extract_codex(path)
            assert len(session.tool_results) == 1
        finally:
            path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# OpenCode extractor tests
# ---------------------------------------------------------------------------

class TestOpenCodeExtractor:
    """Tests for OpenCode SQLite extraction."""

    def _make_db(self, parts: list[dict]) -> Path:
        """Create a temp SQLite DB with tool entries in the part table."""
        db_path = Path(tempfile.mktemp(suffix=".db"))
        conn = sqlite3.connect(str(db_path))
        c = conn.cursor()
        c.execute("CREATE TABLE part (data TEXT)")
        for p in parts:
            c.execute("INSERT INTO part (data) VALUES (?)", (json.dumps(p),))
        conn.commit()
        conn.close()
        return db_path

    def test_extracts_tools_from_sqlite(self) -> None:
        """OpenCode SQLite produces correct SessionData."""
        # Note: the extractor uses LIKE '%"type":"tool"%' — no space after colon
        # to match the typical JSON format in the real OpenCode DB
        parts = [
            {"type":"tool", "id":"oc1", "tool":"mcp__vps__vps_status",
             "state":{"input":{}, "output":"Server running"}},
            {"type":"tool", "id":"oc2", "tool":"mcp__memory__query_structure",
             "state":{"input":{"query_type":"files"}, "output":"Graph data"}},
        ]
        db_path = self._make_db(parts)

        try:
            session = extract_opencode(db_path)
            assert session.source == "opencode"
            assert len(session.tool_calls) == 2
            assert len(session.tool_results) == 2
            assert session.tool_results[0].tool_name == "mcp__vps__vps_status"
        finally:
            db_path.unlink(missing_ok=True)

    def test_parameterized_query_prevents_injection(self) -> None:
        """Session ID with special characters doesn't break SQL."""
        parts = [
            {"type": "tool", "session_id": "test'; DROP TABLE part;--",
             "id": "oc1", "tool": "mcp__vps__vps_status",
             "state": {"input": {}, "output": "Server running"}},
        ]
        db_path = self._make_db(parts)

        try:
            # Should not raise, even with SQL-chars in session_id
            session = extract_opencode(db_path, session_id="test'; DROP TABLE part;--")
            assert isinstance(session, SessionData)
        finally:
            db_path.unlink(missing_ok=True)

    def test_malformed_json_skipped(self) -> None:
        """Malformed JSON in part table is skipped gracefully."""
        db_path = Path(tempfile.mktemp(suffix=".db"))
        conn = sqlite3.connect(str(db_path))
        c = conn.cursor()
        c.execute("CREATE TABLE part (data TEXT)")
        c.execute("INSERT INTO part (data) VALUES (?)", ("not json",))
        c.execute("INSERT INTO part (data) VALUES (?)",
                  (json.dumps({"type":"tool", "tool":"tool_a", "state":{"output":"ok"}}),))
        conn.commit()
        conn.close()

        try:
            session = extract_opencode(db_path)
            assert len(session.tool_results) == 1
        finally:
            db_path.unlink(missing_ok=True)
