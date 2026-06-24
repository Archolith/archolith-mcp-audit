"""Tests for report generator."""

from archolith_mcp_audit.extractors.base import SessionData, ToolResult
from archolith_mcp_audit.report import (
    MAX_FINDINGS_PER_OUTPUT_SECTION,
    build_report,
    format_report_json,
    format_report_markdown,
    format_report_text,
)
from archolith_mcp_audit.waste_detector import WasteFinding


class TestBuildReport:
    def test_empty_session(self):
        session = SessionData(source="test", session_id="empty")
        findings = []
        report = build_report(session, findings)
        assert report.total_tokens == 0
        assert report.total_results == 0

    def test_report_with_results(self):
        results = [
            ToolResult(tool_name="mcp__vps__vps_status",
                       result_text="running", call_id="1", turn_number=1),
        ]
        session = SessionData(source="test", session_id="test", tool_results=results)
        report = build_report(session, [])
        assert report.total_tokens > 0
        assert "vps" in report.servers

    def test_report_with_findings(self):
        results = [
            ToolResult(tool_name="mcp__gradle__gradle_job_status",
                       result_text="running", call_id="1", turn_number=1),
        ]
        session = SessionData(source="test", session_id="test", tool_results=results)
        finding = WasteFinding(
            tool_name="mcp__gradle__gradle_job_status", server="gradle",
            waste_type="polling", severity="critical",
            tokens_wasted=1000, bytes_wasted=2000,
            call_count=5, total_calls=10,
            description="polling waste", suggestion="use delta",
            estimated_savings_pct=90.0,
        )
        report = build_report(session, [finding])
        assert report.total_recoverable_tokens == 1000

    def test_overlapping_findings_are_not_double_counted(self):
        results = [
            ToolResult(tool_name="mcp__gradle__gradle_job_status",
                       result_text="running", call_id="1", turn_number=1),
        ]
        session = SessionData(source="test", session_id="test", tool_results=results)
        polling = WasteFinding(
            tool_name="mcp__gradle__gradle_job_status", server="gradle",
            waste_type="polling", severity="high",
            tokens_wasted=100, bytes_wasted=200,
            call_count=1, total_calls=1,
            description="polling waste", suggestion="use delta",
            estimated_savings_pct=90.0, evidence_ids=("1",),
        )
        format_waste = WasteFinding(
            tool_name="mcp__gradle__gradle_job_status", server="gradle",
            waste_type="format", severity="medium",
            tokens_wasted=100, bytes_wasted=200,
            call_count=1, total_calls=1,
            description="format waste", suggestion="use compact",
            estimated_savings_pct=45.0, evidence_ids=("1",),
        )

        report = build_report(session, [format_waste, polling])

        assert report.total_recoverable_tokens == 100
        assert sum(f.tokens_wasted for f in report.servers["gradle"].findings) == 100


class TestFormatReport:
    def test_text_report_contains_overview(self):
        session = SessionData(source="test", session_id="test")
        report = build_report(session, [])
        text = format_report_text(report)
        assert "MCP TOKEN AUDIT REPORT" in text
        assert "OVERVIEW" in text
        assert "Token counts are estimates" in text

    def test_json_report_is_valid_json(self):
        import json
        session = SessionData(source="test", session_id="test")
        report = build_report(session, [])
        text = format_report_json(report)
        data = json.loads(text)
        assert data["session"] == "test"
        assert data["tokenizer"]["encodings"] == ["cl100k_base", "o200k_base"]
        assert "Token counts are estimates" in data["tokenizer"]["disclosure"]
        assert data["top_optimizations"] == []

    def test_json_report_caps_findings_output(self):
        import json
        results = [
            ToolResult(tool_name="mcp__gradle__gradle_job_status",
                       result_text="running", call_id="1", turn_number=1),
        ]
        session = SessionData(source="test", session_id="test", tool_results=results)
        findings = [
            WasteFinding(
                tool_name="mcp__gradle__gradle_job_status", server="gradle",
                waste_type="format", severity="low",
                tokens_wasted=1, bytes_wasted=1,
                call_count=1, total_calls=1,
                description=f"finding {i}", suggestion="use compact",
                estimated_savings_pct=1.0, evidence_ids=(str(i),),
            )
            for i in range(MAX_FINDINGS_PER_OUTPUT_SECTION + 1)
        ]

        data = json.loads(format_report_json(build_report(session, findings)))

        server = data["servers"]["gradle"]
        assert server["findings_total"] == MAX_FINDINGS_PER_OUTPUT_SECTION + 1
        assert server["findings_truncated"] is True
        assert len(server["findings"]) == MAX_FINDINGS_PER_OUTPUT_SECTION

    def test_markdown_report_has_headers(self):
        session = SessionData(source="test", session_id="test")
        report = build_report(session, [])
        text = format_report_markdown(report)
        assert "# MCP Token Audit Report" in text
        assert "## Overview" in text
        assert "Token counts are estimates" in text
