"""Tests for waste_detector module."""

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
