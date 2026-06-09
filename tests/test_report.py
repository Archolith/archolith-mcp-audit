"""Tests for report generator."""

from archolith_mcp_audit.extractors.base import SessionData, ToolResult
from archolith_mcp_audit.report import build_report, format_report_json, format_report_markdown, format_report_text
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


class TestFormatReport:
    def test_text_report_contains_overview(self):
        session = SessionData(source="test", session_id="test")
        report = build_report(session, [])
        text = format_report_text(report)
        assert "MCP TOKEN AUDIT REPORT" in text
        assert "OVERVIEW" in text

    def test_json_report_is_valid_json(self):
        import json
        session = SessionData(source="test", session_id="test")
        report = build_report(session, [])
        text = format_report_json(report)
        data = json.loads(text)
        assert data["session"] == "test"

    def test_markdown_report_has_headers(self):
        session = SessionData(source="test", session_id="test")
        report = build_report(session, [])
        text = format_report_markdown(report)
        assert "# MCP Token Audit Report" in text
        assert "## Overview" in text
