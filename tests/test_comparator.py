"""Tests for archolith_mcp_audit.comparator — before/after comparison mode."""

from __future__ import annotations

import json

from archolith_mcp_audit.comparator import ServerDelta, compare_reports, format_delta_report


def _make_report(servers: dict) -> dict:
    """Build a minimal JSON report dict for testing."""
    return {"servers": servers}


def _make_server(token_share: int, call_count: int, findings: list[dict] | None = None) -> dict:
    """Build a minimal server dict."""
    return {
        "token_share": token_share,
        "call_count": call_count,
        "findings": findings or [],
    }


class TestCompareReports:
    """Tests for compare_reports()."""

    def test_no_change(self) -> None:
        """Identical before/after produces zero deltas."""
        server = _make_server(1000, 10)
        before = _make_report({"gradle": server})
        after = _make_report({"gradle": server})

        deltas = compare_reports(before, after)
        assert len(deltas) == 1
        d = deltas[0]
        assert d.server == "gradle"
        assert d.token_change == 0
        assert d.waste_change == 0
        assert d.status == "no_change"

    def test_improvement(self) -> None:
        """Reduced waste → status=improved."""
        before = _make_report({"gradle": _make_server(1000, 10, [
            {"waste_type": "polling", "tokens_wasted": 800}
        ])})
        after = _make_report({"gradle": _make_server(500, 10, [
            {"waste_type": "polling", "tokens_wasted": 100}
        ])})

        deltas = compare_reports(before, after)
        d = deltas[0]
        assert d.token_change == -500
        assert d.waste_change == -700
        assert d.status == "improved"

    def test_regression(self) -> None:
        """Increased waste → status=regressed."""
        before = _make_report({"gradle": _make_server(500, 10, [
            {"waste_type": "polling", "tokens_wasted": 100}
        ])})
        after = _make_report({"gradle": _make_server(1000, 10, [
            {"waste_type": "polling", "tokens_wasted": 800}
        ])})

        deltas = compare_reports(before, after)
        d = deltas[0]
        assert d.waste_change == 700
        assert d.status == "regressed"

    def test_new_server(self) -> None:
        """Server only in 'after' → status=new."""
        before = _make_report({})
        after = _make_report({"vps": _make_server(500, 5)})

        deltas = compare_reports(before, after)
        d = deltas[0]
        assert d.server == "vps"
        assert d.status == "new"
        assert d.before_tokens == 0
        assert d.after_tokens == 500

    def test_removed_server(self) -> None:
        """Server only in 'before' → status=removed."""
        before = _make_report({"delegate": _make_server(500, 5)})
        after = _make_report({})

        deltas = compare_reports(before, after)
        d = deltas[0]
        assert d.server == "delegate"
        assert d.status == "removed"
        assert d.before_tokens == 500
        assert d.after_tokens == 0

    def test_new_waste_type_detection(self) -> None:
        """New waste type in 'after' flagged in new_waste_types."""
        before = _make_report({"gradle": _make_server(1000, 10, [
            {"waste_type": "polling", "tokens_wasted": 100}
        ])})
        after = _make_report({"gradle": _make_server(1000, 10, [
            {"waste_type": "polling", "tokens_wasted": 100},
            {"waste_type": "format_waste", "tokens_wasted": 200}
        ])})

        deltas = compare_reports(before, after)
        d = deltas[0]
        assert "format_waste" in d.new_waste_types
        assert d.resolved_waste_types == []

    def test_resolved_waste_type(self) -> None:
        """Waste type only in 'before' → resolved_waste_types."""
        before = _make_report({"gradle": _make_server(1000, 10, [
            {"waste_type": "polling", "tokens_wasted": 500},
            {"waste_type": "format_waste", "tokens_wasted": 200}
        ])})
        after = _make_report({"gradle": _make_server(500, 10, [
            {"waste_type": "polling", "tokens_wasted": 50}
        ])})

        deltas = compare_reports(before, after)
        d = deltas[0]
        assert "format_waste" in d.resolved_waste_types
        assert d.new_waste_types == []

    def test_multiple_servers(self) -> None:
        """All servers from both reports appear."""
        before = _make_report({
            "gradle": _make_server(1000, 10),
            "vps": _make_server(500, 5),
        })
        after = _make_report({
            "vps": _make_server(500, 5),
            "memory": _make_server(200, 3),
        })

        deltas = compare_reports(before, after)
        names = {d.server for d in deltas}
        assert names == {"gradle", "vps", "memory"}

    def test_sorted_output(self) -> None:
        """Servers sorted alphabetically."""
        before = _make_report({"z_server": _make_server(100, 1), "a_server": _make_server(100, 1)})
        after = _make_report({"z_server": _make_server(100, 1), "a_server": _make_server(100, 1)})

        deltas = compare_reports(before, after)
        assert [d.server for d in deltas] == ["a_server", "z_server"]

    def test_token_change_pct(self) -> None:
        """Percentage change calculated correctly."""
        before = _make_report({"gradle": _make_server(1000, 10)})
        after = _make_report({"gradle": _make_server(750, 10)})

        deltas = compare_reports(before, after)
        d = deltas[0]
        assert d.token_change_pct == -25.0

    def test_empty_reports(self) -> None:
        """Empty before/after produces no deltas."""
        deltas = compare_reports({}, {})
        assert deltas == []


class TestFormatDeltaReport:
    """Tests for format_delta_report()."""

    def test_improvement_report(self) -> None:
        """Report shows improvement correctly."""
        deltas = [ServerDelta(
            server="gradle",
            before_tokens=1000, after_tokens=500,
            token_change=-500, token_change_pct=-50.0,
            before_waste=800, after_waste=100,
            waste_change=-700, waste_change_pct=-87.5,
            before_calls=10, after_calls=10,
            new_waste_types=[], resolved_waste_types=["format_waste"],
            status="improved",
        )]
        text = format_delta_report(deltas)
        assert "IMPROVED" in text
        assert "-700" in text
        assert "format_waste" in text

    def test_regression_report(self) -> None:
        """Report shows regression correctly."""
        deltas = [ServerDelta(
            server="vps",
            before_tokens=500, after_tokens=1000,
            token_change=500, token_change_pct=100.0,
            before_waste=100, after_waste=800,
            waste_change=700, waste_change_pct=700.0,
            before_calls=5, after_calls=5,
            new_waste_types=["format_waste"], resolved_waste_types=[],
            status="regressed",
        )]
        text = format_delta_report(deltas)
        assert "REGRESSED" in text
        assert "New waste types" in text

    def test_empty_deltas(self) -> None:
        """Empty delta list produces summary-only."""
        text = format_delta_report([])
        assert "No servers to compare" in text

    def test_summary_totals(self) -> None:
        """Summary counts improved/regressed/total waste."""
        deltas = [
            ServerDelta(server="a", waste_change=-100, status="improved"),
            ServerDelta(server="b", waste_change=50, status="regressed"),
            ServerDelta(server="c", waste_change=0, status="no_change"),
        ]
        text = format_delta_report(deltas)
        assert "Servers improved:  1" in text
        assert "Servers regressed: 1" in text
        assert "-50" in text  # total waste change
