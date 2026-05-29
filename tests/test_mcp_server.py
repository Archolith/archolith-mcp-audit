"""Tests for archolith_mcp_audit.mcp_server — in-session MCP audit tools."""

from __future__ import annotations

from archolith_mcp_audit.accumulator import LiveAccumulator
from archolith_mcp_audit.mcp_server import get_accumulator, get_bridge
from archolith_mcp_audit.telemetry_bridge import TelemetryBridge
from archolith_mcp_audit.waste_detector import WasteFinding


class TestGetAccumulator:
    """Tests for per-session accumulator cache."""

    def test_returns_live_accumulator(self) -> None:
        """get_accumulator returns a LiveAccumulator instance."""
        acc = get_accumulator("test-session-acc")
        assert isinstance(acc, LiveAccumulator)

    def test_same_session_returns_same_instance(self) -> None:
        """Repeated calls with the same session_id return the same instance."""
        acc1 = get_accumulator("test-session-same")
        acc2 = get_accumulator("test-session-same")
        assert acc1 is acc2

    def test_different_sessions_are_isolated(self) -> None:
        """Different session IDs produce separate accumulators."""
        acc_a = get_accumulator("session-a-unique")
        acc_b = get_accumulator("session-b-unique")
        assert acc_a is not acc_b


class TestGetBridge:
    """Tests for per-session telemetry bridge cache."""

    def test_returns_telemetry_bridge(self) -> None:
        """get_bridge returns a TelemetryBridge instance."""
        bridge = get_bridge("test-session-bridge")
        assert isinstance(bridge, TelemetryBridge)

    def test_bridge_connected_to_accumulator(self) -> None:
        """Bridge's accumulator matches the session's accumulator."""
        bridge = get_bridge("test-session-linked")
        acc = get_accumulator("test-session-linked")
        assert bridge.accumulator is acc

    def test_same_session_returns_same_instance(self) -> None:
        """Repeated calls with the same session_id return the same bridge."""
        bridge1 = get_bridge("test-session-bridge-same")
        bridge2 = get_bridge("test-session-bridge-same")
        assert bridge1 is bridge2

    def test_different_sessions_are_isolated(self) -> None:
        """Different session IDs produce separate bridges."""
        bridge_a = get_bridge("bridge-session-a-unique")
        bridge_b = get_bridge("bridge-session-b-unique")
        assert bridge_a is not bridge_b


class TestMcpAuditSummaryOutput:
    """Tests for mcp_audit_summary output format (via accumulator)."""

    def test_empty_session(self) -> None:
        """Empty accumulator produces 'no results' message."""
        acc = LiveAccumulator()
        summary = acc.get_server_summary()
        assert not summary

    def test_summary_with_data(self) -> None:
        """Summary includes server data with expected keys."""
        acc = LiveAccumulator()
        acc.observe("mcp__gradle__gradle_compile", 5000, 1000)
        acc.observe("mcp__vps__vps_status", 3000, 500)

        summary = acc.get_server_summary()
        assert "gradle" in summary
        assert "vps" in summary
        assert summary["gradle"]["call_count"] == 1
        assert summary["gradle"]["share_pct"] > 0

    def test_mcp_share_calculation(self) -> None:
        """MCP share excludes non-mcp tools."""
        acc = LiveAccumulator()
        acc.observe("mcp__gradle__gradle_compile", 5000, 1000)
        acc.observe("Read", 10000, 8000)

        mcp_share = acc.get_mcp_share()
        assert mcp_share < 50.0  # gradle=5000, non-mcp=10000


class TestMcpAuditDetailWithFindings:
    """Tests for mcp_audit_detail output with waste findings attached."""

    def test_findings_available_in_summary(self) -> None:
        """Waste findings are available in server summary for detail tool."""
        acc = LiveAccumulator()
        acc.observe("mcp__gradle__gradle_compile", 5000, 1000)

        finding = WasteFinding(
            tool_name="gradle_compile", server="gradle",
            waste_type="polling", severity="critical",
            tokens_wasted=3000, bytes_wasted=12000,
            call_count=90, total_calls=100,
            description="90/100 calls are polling waste",
            suggestion="Return status-only on poll",
            estimated_savings_pct=90.0,
        )
        acc.add_waste_findings([finding])

        summary = acc.get_server_summary()
        assert "gradle" in summary
        assert len(summary["gradle"]["waste_findings"]) == 1
        assert summary["gradle"]["waste_findings"][0].waste_type == "polling"


class TestMcpAuditCheckThresholds:
    """Tests for mcp_audit_check threshold logic (via accumulator)."""

    def test_within_limits(self) -> None:
        """Multiple servers with small shares pass thresholds."""
        acc = LiveAccumulator()
        acc.observe("mcp__memory__query_structure", 500, 250)
        acc.observe("mcp__vps__vps_status", 500, 250)
        acc.observe("non-mcp-tool", 9000, 7000)  # non-mcp dominates

        summary = acc.get_server_summary()

        # Both MCP servers should have small shares since non-mcp dominates
        mcp_servers = {s: d for s, d in summary.items() if s != "non-mcp"}
        all_ok = all(data["share_pct"] <= 20.0 for data in mcp_servers.values())
        assert all_ok

    def test_no_data_passes(self) -> None:
        """No observations produces empty summary."""
        acc = LiveAccumulator()
        summary = acc.get_server_summary()
        assert not summary


class TestConditionalEnablement:
    """Tests for MCP_AUDIT_ENABLED env var check."""

    def test_disabled_by_default(self) -> None:
        """Without MCP_AUDIT_ENABLED, audit tools return disabled message."""
        import os
        was_set = "MCP_AUDIT_ENABLED" in os.environ
        try:
            os.environ.pop("MCP_AUDIT_ENABLED", None)
            # Re-import to pick up env var
            import importlib
            import archolith_mcp_audit.mcp_server as ms
            importlib.reload(ms)

            # The disabled stubs should be defined
            assert callable(ms.mcp_audit_summary)
            result = ms.mcp_audit_summary()
            assert "disabled" in result.lower() or "MCP_AUDIT_ENABLED" in result
        finally:
            if was_set:
                os.environ["MCP_AUDIT_ENABLED"] = "1"
            else:
                importlib.reload(ms)


class TestAccumulatorReset:
    """Tests for accumulator reset functionality."""

    def test_reset_clears_data(self) -> None:
        """Reset clears all accumulated data."""
        acc = LiveAccumulator()
        acc.observe("mcp__gradle__gradle_compile", 5000, 1000)
        acc.reset()
        assert acc.total_results == 0
        assert not acc.servers
