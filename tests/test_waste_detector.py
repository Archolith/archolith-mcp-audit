"""Tests for waste_detector module."""

import json

from archolith_mcp_audit.extractors.base import SessionData, ToolResult
from archolith_mcp_audit.waste_detector import detect_waste, _similarity, _is_help_text


class TestPollingDetection:
    def test_detects_repeated_results(self):
        """Repeated identical results should be flagged as polling waste."""
        results = [
            ToolResult(tool_name="mcp__gradle__gradle_job_status",
                       result_text="Status: running\nJob ID: abc\nDuration: 10s",
                       call_id=str(i), turn_number=i)
            for i in range(10)
        ]
        session = SessionData(source="test", session_id="test", tool_results=results)
        findings = detect_waste(session)
        polling = [f for f in findings if f.waste_type == "polling"]
        assert len(polling) >= 1
        assert polling[0].server == "gradle"

    def test_clean_output_not_flagged(self):
        """Non-repeating results should not be flagged."""
        results = [
            ToolResult(tool_name="mcp__vps__vps_status",
                       result_text=f"Server status: running (check {i})",
                       call_id=str(i), turn_number=i)
            for i in range(5)
        ]
        session = SessionData(source="test", session_id="test", tool_results=results)
        findings = detect_waste(session)
        polling = [f for f in findings if f.waste_type == "polling"]
        # These are all different, should not be flagged as polling
        assert len(polling) == 0


class TestOversizedDetection:
    def test_detects_help_text(self):
        """Large help text should be flagged."""
        help_text = "Usage:\n" + "\n".join(f"  --flag{i}  Description of flag {i}" for i in range(20))
        results = [
            ToolResult(tool_name="mcp__vps__vps_help",
                       result_text=help_text, call_id="1", turn_number=1)
        ]
        session = SessionData(source="test", session_id="test", tool_results=results)
        findings = detect_waste(session)
        oversized = [f for f in findings if f.waste_type == "oversized"]
        assert len(oversized) >= 1

    def test_detects_json_envelope(self):
        """JSON with envelope keys should be flagged."""
        envelope = '{"status": "ok", "meta": {"version": "1.0", "timestamp": "2026-01-01T00:00:00Z", '
        envelope += '"request_id": "abc-123-def-456-ghi-789"}, "data": {"key": "value"}}'
        results = [
            ToolResult(tool_name="mcp__harness__harness_get_session",
                       result_text=envelope, call_id=str(i), turn_number=i)
            for i in range(5)  # Need >=2 for envelope detection
        ]
        session = SessionData(source="test", session_id="test", tool_results=results)
        findings = detect_waste(session)
        oversized = [f for f in findings if f.waste_type == "oversized"]
        assert len(oversized) >= 1


class TestFormatWasteDetection:
    def test_detects_json_table(self):
        """JSON array of same-key objects should be flagged."""
        items = []
        for i in range(5):
            items.append(f'  {{"name": "item{i}", "value": {i}, "status": "ok", '
                         f'"description": "A longer description for item {i} to add bulk"}}')
        table_data = "[\n" + ",\n".join(items) + "\n]"
        results = [
            ToolResult(tool_name="mcp__memory__query_structure",
                       result_text=table_data, call_id="1", turn_number=1)
        ]
        session = SessionData(source="test", session_id="test", tool_results=results)
        findings = detect_waste(session)
        format_or_redundant = [f for f in findings if f.waste_type in ("format", "redundant_fields")]
        # Either format waste or redundant fields should be detected for large JSON
        assert len(format_or_redundant) >= 1


class TestHelperFunctions:
    def test_similarity_identical(self):
        assert _similarity("hello world", "hello world") == 1.0

    def test_similarity_different(self):
        assert _similarity("hello world", "foo bar baz") < 0.5

    def test_similarity_empty(self):
        assert _similarity("", "") == 1.0

    def test_is_help_text_short(self):
        assert not _is_help_text("short text")

    def test_is_help_text_with_flags(self):
        text = "Usage:\n" + "\n".join(f"  --flag{i}  Description" for i in range(10))
        assert _is_help_text(text)

    def test_is_help_text_normal_code(self):
        assert not _is_help_text("def hello():\n    pass\n")


class TestRedundantFieldsDetection:
    """Tests for redundant_fields detector (3c)."""

    def test_detects_overbroad_tool(self) -> None:
        """Known overbroad tool (query_structure) flagged."""
        # Simulate a large query_structure result
        data = {f"field_{i}": f"value_{i}" for i in range(20)}
        result_text = json.dumps(data)
        results = [
            ToolResult(tool_name="mcp__memory__query_structure",
                        result_text=result_text, call_id="1", turn_number=1)
        ]
        session = SessionData(source="test", session_id="test", tool_results=results)
        findings = detect_waste(session)
        redundant = [f for f in findings if f.waste_type == "redundant_fields"]
        assert len(redundant) >= 1
        assert redundant[0].server == "memory"
        # Verify example_before is populated
        assert redundant[0].example_before != ""

    def test_many_fields_flagged(self) -> None:
        """JSON with >10 top-level keys flagged."""
        data = {f"key_{i}": f"val_{i}" for i in range(15)}
        results = [
            ToolResult(tool_name="mcp__harness__harness_get_session",
                        result_text=json.dumps(data), call_id="1", turn_number=1)
        ]
        session = SessionData(source="test", session_id="test", tool_results=results)
        findings = detect_waste(session)
        redundant = [f for f in findings if f.waste_type == "redundant_fields"]
        assert len(redundant) >= 1

    def test_few_fields_not_flagged(self) -> None:
        """JSON with few fields not flagged as redundant."""
        results = [
            ToolResult(tool_name="mcp__vps__vps_status",
                        result_text='{"status": "running", "uptime": 42}',
                        call_id="1", turn_number=1)
        ]
        session = SessionData(source="test", session_id="test", tool_results=results)
        findings = detect_waste(session)
        redundant = [f for f in findings if f.waste_type == "redundant_fields"]
        assert len(redundant) == 0


class TestSchemaCostDetection:
    """Tests for schema cost detector (3d)."""

    def test_detects_schema_overhead(self) -> None:
        """Multiple tools across multiple turns flagged as schema waste."""
        results = [
            ToolResult(tool_name=f"mcp__workspace-artifacts__tool_{i}",
                        result_text="ok", call_id=str(i), turn_number=i)
            for i in range(8)  # 8 distinct tools
        ]
        session = SessionData(source="test", session_id="test", tool_results=results, total_turns=20)
        findings = detect_waste(session)
        schema = [f for f in findings if f.waste_type == "schema"]
        assert len(schema) >= 1
        assert schema[0].server == "workspace-artifacts"
        # Session cost should be per_turn * total_turns
        assert schema[0].tokens_wasted > 0
        # Verify example_before/after populated
        assert schema[0].example_before != ""
        assert schema[0].example_after != ""

    def test_single_tool_not_flagged(self) -> None:
        """Single tool with few turns not flagged (below threshold)."""
        results = [
            ToolResult(tool_name="mcp__memory__query_structure",
                        result_text="ok", call_id="1", turn_number=1)
        ]
        session = SessionData(source="test", session_id="test", tool_results=results, total_turns=1)
        findings = detect_waste(session)
        schema = [f for f in findings if f.waste_type == "schema"]
        # 1 tool × 300 tokens × 1 turn = 300 × 0.6 = 180 < 1000 threshold
        assert len(schema) == 0


class TestCacheBreakerDetection:
    """Tests for cache breaker detector (3f)."""

    def test_detects_timestamp_changes(self) -> None:
        """Same tool, same content except timestamps → cache breaker."""
        results = [
            ToolResult(tool_name="mcp__gradle__gradle_job_status",
                        result_text="Status: running\nDuration: 10s\nTimestamp: 2026-01-01T10:00:00",
                        call_id=str(i), turn_number=i)
            for i in range(5)
        ]
        # Make timestamps differ
        for i, r in enumerate(results):
            r.result_text = f"Status: running\nDuration: {10+i}s\nTimestamp: 2026-01-01T10:0{i}:00"

        session = SessionData(source="test", session_id="test", tool_results=results)
        findings = detect_waste(session)
        cache_breakers = [f for f in findings if f.waste_type == "cache_breaker"]
        assert len(cache_breakers) >= 1
        assert cache_breakers[0].server == "gradle"
        # Verify example_before populated
        assert cache_breakers[0].example_before != ""

    def test_stable_content_not_flagged(self) -> None:
        """Identical content across calls → polling, not cache breaker."""
        results = [
            ToolResult(tool_name="mcp__vps__vps_status",
                        result_text="Server status: running",
                        call_id=str(i), turn_number=i)
            for i in range(5)
        ]
        session = SessionData(source="test", session_id="test", tool_results=results)
        findings = detect_waste(session)
        cache_breakers = [f for f in findings if f.waste_type == "cache_breaker"]
        # Identical content = polling, not cache breaking
        assert len(cache_breakers) == 0

    def test_truly_different_content_not_flagged(self) -> None:
        """Actually different results not flagged."""
        results = [
            ToolResult(tool_name="mcp__vps__vps_service_logs",
                        result_text=f"Log line {i}: different content each time",
                        call_id=str(i), turn_number=i)
            for i in range(5)
        ]
        session = SessionData(source="test", session_id="test", tool_results=results)
        findings = detect_waste(session)
        cache_breakers = [f for f in findings if f.waste_type == "cache_breaker"]
        assert len(cache_breakers) == 0
