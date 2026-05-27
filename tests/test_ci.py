"""Tests for archolith_mcp_audit.ci — CI threshold checks."""

from __future__ import annotations

from archolith_mcp_audit.ci import check_thresholds, run_ci_check
from archolith_mcp_audit.report import AuditReport, ServerReport
from archolith_mcp_audit.waste_detector import WasteFinding


def _make_server_report(
    token_share: int = 1000,
    token_share_pct: float = 10.0,
    call_count: int = 10,
    recoverable: int = 0,
    findings: list[WasteFinding] | None = None,
) -> ServerReport:
    """Build a ServerReport for testing."""
    return ServerReport(
        server="test_server",
        token_share=token_share,
        token_share_pct=token_share_pct,
        call_count=call_count,
        findings=findings or [],
        estimated_recoverable_tokens=recoverable,
    )


def _make_report(
    servers: dict[str, ServerReport] | None = None,
    mcp_share_pct: float = 30.0,
    total_tokens: int = 10000,
) -> AuditReport:
    """Build an AuditReport for testing."""
    return AuditReport(
        servers=servers or {},
        non_mcp_tokens=total_tokens - sum(s.token_share for s in (servers or {}).values()),
        total_tokens=total_tokens,
        mcp_share_pct=mcp_share_pct,
        top_optimizations=[],
    )


class TestCheckThresholds:
    """Tests for check_thresholds()."""

    def test_all_pass(self) -> None:
        """All thresholds within limits → passed=True."""
        report = _make_report(
            servers={"gradle": _make_server_report(token_share_pct=15.0)},
            mcp_share_pct=35.0,
        )
        passed, messages = check_thresholds(report, max_server_share=20.0, max_total_mcp_share=40.0)
        assert passed is True

    def test_server_share_exceeded(self) -> None:
        """Server over share limit → passed=False."""
        report = _make_report(
            servers={"gradle": _make_server_report(token_share_pct=25.0)},
            mcp_share_pct=30.0,
        )
        passed, messages = check_thresholds(report, max_server_share=20.0, max_total_mcp_share=40.0)
        assert passed is False
        assert any("FAIL" in m and "gradle" in m for m in messages)

    def test_total_mcp_share_exceeded(self) -> None:
        """Total MCP share over limit → passed=False."""
        report = _make_report(
            servers={"gradle": _make_server_report(token_share_pct=10.0)},
            mcp_share_pct=50.0,
        )
        passed, messages = check_thresholds(report, max_server_share=20.0, max_total_mcp_share=40.0)
        assert passed is False
        assert any("FAIL" in m and "Total MCP" in m for m in messages)

    def test_waste_pct_exceeded(self) -> None:
        """Waste over percentage limit → passed=False."""
        findings = [WasteFinding(
            tool_name="gradle_compile", server="gradle",
            waste_type="polling", severity="high",
            tokens_wasted=600, bytes_wasted=2400,
            call_count=150, total_calls=162,
            description="polling waste",
            suggestion="stop polling", estimated_savings_pct=90.0,
        )]
        report = _make_report(
            servers={"gradle": _make_server_report(
                token_share=1000, token_share_pct=10.0, recoverable=600, findings=findings
            )},
            mcp_share_pct=30.0,
        )
        passed, messages = check_thresholds(report, max_server_share=20.0, max_waste_pct=50.0)
        assert passed is False
        assert any("FAIL" in m and "waste" in m.lower() for m in messages)

    def test_multiple_servers_independent(self) -> None:
        """Each server checked independently."""
        report = _make_report(
            servers={
                "gradle": _make_server_report(token_share_pct=25.0),  # over
                "vps": _make_server_report(token_share_pct=10.0),       # under
            },
            mcp_share_pct=35.0,
        )
        passed, messages = check_thresholds(report, max_server_share=20.0)
        assert passed is False
        fail_msgs = [m for m in messages if "FAIL" in m]
        assert len(fail_msgs) == 1  # only gradle
        assert "gradle" in fail_msgs[0]

    def test_empty_report_passes(self) -> None:
        """Report with no servers passes."""
        report = _make_report(servers={}, mcp_share_pct=0.0)
        passed, messages = check_thresholds(report)
        assert passed is True


class TestRunCiCheck:
    """Tests for run_ci_check() exit codes."""

    def test_pass_returns_0(self) -> None:
        """All thresholds pass → exit 0."""
        report = _make_report(
            servers={"gradle": _make_server_report(token_share_pct=10.0)},
            mcp_share_pct=20.0,
        )
        exit_code = run_ci_check(report, max_server_share=20.0, max_total_mcp_share=40.0)
        assert exit_code == 0

    def test_fail_returns_2(self) -> None:
        """Threshold exceeded → exit 2."""
        report = _make_report(
            servers={"gradle": _make_server_report(token_share_pct=30.0)},
            mcp_share_pct=50.0,
        )
        exit_code = run_ci_check(report, max_server_share=20.0, max_total_mcp_share=40.0)
        assert exit_code == 2

    def test_custom_thresholds(self) -> None:
        """Custom thresholds override defaults."""
        report = _make_report(
            servers={"gradle": _make_server_report(token_share_pct=15.0)},
            mcp_share_pct=25.0,
        )
        # 15% is fine at default 20% limit
        assert run_ci_check(report, max_server_share=20.0) == 0
        # 15% fails at 10% limit
        assert run_ci_check(report, max_server_share=10.0) == 2
