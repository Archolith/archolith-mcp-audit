"""Tests for archolith_mcp_audit.cli — CLI smoke tests."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from archolith_mcp_audit.cli import main
from archolith_mcp_audit.schema_estimator import SchemaRefreshResult


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
