"""Tests for accumulator module."""

from archolith_mcp_audit.accumulator import LiveAccumulator


class TestLiveAccumulator:
    def test_observe_single_result(self):
        acc = LiveAccumulator()
        acc.observe("mcp__vps__vps_status", raw_chars=1000, filtered_chars=500)
        summary = acc.get_server_summary()
        assert "vps" in summary
        assert summary["vps"]["call_count"] == 1
        assert summary["vps"]["raw_chars"] == 1000

    def test_observe_multiple_servers(self):
        acc = LiveAccumulator()
        acc.observe("mcp__vps__vps_status", raw_chars=1000)
        acc.observe("mcp__memory__query_structure", raw_chars=500)
        acc.observe("mcp__vps__vps_status", raw_chars=800)
        summary = acc.get_server_summary()
        assert "vps" in summary
        assert "memory" in summary
        assert summary["vps"]["call_count"] == 2

    def test_mcp_share(self):
        acc = LiveAccumulator()
        acc.observe("mcp__vps__vps_status", raw_chars=1000)
        acc.observe("Read", raw_chars=1000)
        share = acc.get_mcp_share()
        assert share == 50.0  # 50% MCP

    def test_reset(self):
        acc = LiveAccumulator()
        acc.observe("mcp__vps__vps_status", raw_chars=1000)
        acc.reset()
        assert acc.total_results == 0
        assert acc.get_mcp_share() == 0.0

    def test_non_mcp_grouped(self):
        acc = LiveAccumulator()
        acc.observe("Read", raw_chars=500)
        acc.observe("Bash", raw_chars=300)
        summary = acc.get_server_summary()
        assert "non-mcp" in summary
        assert summary["non-mcp"]["call_count"] == 2
