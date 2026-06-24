"""Tests for archolith_mcp_audit.cli — CLI smoke tests."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from archolith_mcp_audit.cli import main
from archolith_mcp_audit.report import AuditReport, ServerReport
from archolith_mcp_audit.schema_estimator import SchemaRefreshResult
from archolith_mcp_audit.waste_detector import WasteFinding


class TestCliComparison:
    """Test --compare mode."""

    def test_compare_no_regression(self) -> None:
        """Comparison with no regression exits 0."""
        before = {
            "servers": {
                "gradle": {
                    "token_share": 1000,
                    "call_count": 10,
                    "findings": [{"waste_type": "polling", "tokens_wasted": 800}],
                }
            }
        }
        after = {
            "servers": {
                "gradle": {
                    "token_share": 500,
                    "call_count": 10,
                    "findings": [{"waste_type": "polling", "tokens_wasted": 100}],
                }
            }
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as bf:
            json.dump(before, bf)
            bf_path = bf.name
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as af:
            json.dump(after, af)
            af_path = af.name

        try:
            exit_code = main(["--compare", bf_path, af_path])
            assert exit_code == 0
        finally:
            Path(bf_path).unlink(missing_ok=True)
            Path(af_path).unlink(missing_ok=True)

    def test_compare_with_regression(self) -> None:
        """Comparison with regression exits 2."""
        before = {
            "servers": {
                "gradle": {
                    "token_share": 500,
                    "call_count": 10,
                    "findings": [{"waste_type": "polling", "tokens_wasted": 100}],
                }
            }
        }
        after = {
            "servers": {
                "gradle": {
                    "token_share": 1000,
                    "call_count": 10,
                    "findings": [{"waste_type": "polling", "tokens_wasted": 800}],
                }
            }
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as bf:
            json.dump(before, bf)
            bf_path = bf.name
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as af:
            json.dump(after, af)
            af_path = af.name

        try:
            exit_code = main(["--compare", bf_path, af_path])
            assert exit_code == 2
        finally:
            Path(bf_path).unlink(missing_ok=True)
            Path(af_path).unlink(missing_ok=True)


class TestCliSchemaRefresh:
    """Test --refresh-schemas mode."""

    def test_refresh_exits_0(self) -> None:
        """Schema refresh with servers succeeds exits 0."""
        with patch(
            "archolith_mcp_audit.schema_estimator.refresh_schema_catalog",
            return_value=SchemaRefreshResult(
                catalog={"gradle": [{"name": "gradle_compile", "schema_tokens": 250}]},
                total_servers=1,
            ),
        ):
            exit_code = main(["--refresh-schemas"])
            assert exit_code == 0

    def test_refresh_all_fail_exits_1(self) -> None:
        """Schema refresh with all servers failing exits 1."""
        with patch(
            "archolith_mcp_audit.schema_estimator.refresh_schema_catalog",
            return_value=SchemaRefreshResult(catalog={}),
        ):
            exit_code = main(["--refresh-schemas"])
            assert exit_code == 1

    def test_refresh_with_results_shows_summary(self, capsys) -> None:
        """Refresh with results prints server summary."""
        with patch(
            "archolith_mcp_audit.schema_estimator.refresh_schema_catalog",
            return_value=SchemaRefreshResult(
                catalog={
                    "gradle": [{"name": "gradle_compile", "schema_tokens": 250}],
                    "vps": [{"name": "vps_status", "schema_tokens": 180}],
                    "memory": [{"name": "query_structure", "schema_tokens": 300}],
                },
                total_servers=3,
            ),
        ):
            exit_code = main(["--refresh-schemas"])
            captured = capsys.readouterr()
            assert exit_code == 0
            assert "3 servers OK" in captured.out

    def test_refresh_all_fail_shows_error(self, capsys) -> None:
        """Refresh with all failures prints error to stderr."""
        with patch(
            "archolith_mcp_audit.schema_estimator.refresh_schema_catalog",
            return_value=SchemaRefreshResult(catalog={}),
        ):
            exit_code = main(["--refresh-schemas"])
            captured = capsys.readouterr()
            assert exit_code == 1
            assert "Error" in captured.err
            assert "failed" in captured.err


class TestCliNoSources:
    """Test error handling when no sources provided."""

    def test_no_sources_exits_error(self) -> None:
        """No sources specified → parser error (exit 2)."""
        try:
            main([])
            assert False, "Should have raised SystemExit"
        except SystemExit as e:
            assert e.code == 2


class TestCliAuditModes:
    """Test main audit mode flags without requiring real session files."""

    def test_source_modes_call_runner(self) -> None:
        for args, expected in [
            (["--claude", "claude.jsonl"], ("claude", "claude.jsonl")),
            (["--codex", "codex.jsonl"], ("codex", "codex.jsonl")),
            (["--opencode", "opencode.db"], ("opencode", "opencode.db")),
        ]:
            with patch("archolith_mcp_audit.cli._run_audit", return_value=AuditReport(session="s")) as run:
                assert main(args) == 0
                assert run.call_args.args[:2] == expected

    def test_server_and_min_severity_filters_apply(self, capsys) -> None:
        high = WasteFinding(
            tool_name="mcp__gradle__gradle_compile",
            server="gradle",
            waste_type="polling",
            severity="high",
            tokens_wasted=100,
            bytes_wasted=200,
            call_count=1,
            total_calls=1,
            description="high finding",
            suggestion="fix gradle",
            estimated_savings_pct=80.0,
        )
        low = WasteFinding(
            tool_name="mcp__vps__vps_status",
            server="vps",
            waste_type="format",
            severity="low",
            tokens_wasted=10,
            bytes_wasted=20,
            call_count=1,
            total_calls=1,
            description="low finding",
            suggestion="fix vps",
            estimated_savings_pct=10.0,
        )
        report = AuditReport(
            session="s",
            servers={
                "gradle": ServerReport(server="gradle", findings=[high]),
                "vps": ServerReport(server="vps", findings=[low]),
            },
            top_optimizations=[high, low],
        )

        with patch("archolith_mcp_audit.cli._run_audit", return_value=report):
            assert main(["--claude", "x.jsonl", "--servers", "gradle", "--min-severity", "medium"]) == 0

        captured = capsys.readouterr()
        assert "gradle" in captured.out
        assert "vps" not in captured.out
        assert "high finding" in captured.out
        assert "low finding" not in captured.out
