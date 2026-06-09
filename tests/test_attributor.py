"""Tests for attributor module."""

from archolith_mcp_audit.attributor import attribute_results, attribute_tool


class TestAttributeTool:
    def test_known_mcp_pattern(self):
        assert attribute_tool("mcp__memory__query_structure") == "memory"

    def test_known_mcp_pattern_vps(self):
        assert attribute_tool("mcp__vps__vps_status") == "vps"

    def test_known_mcp_pattern_harness(self):
        assert attribute_tool("mcp__harness__harness_list_sessions") == "harness"

    def test_non_mcp_tool_read(self):
        assert attribute_tool("Read") == "non-mcp"

    def test_non_mcp_tool_bash(self):
        assert attribute_tool("Bash") == "non-mcp"

    def test_non_mcp_tool_edit(self):
        assert attribute_tool("Edit") == "non-mcp"

    def test_unknown_prefix(self):
        assert attribute_tool("mcp__unknown_server__some_tool") == "unknown_server"

    def test_custom_mapping(self):
        mapping = {"custom__": "custom-server"}
        assert attribute_tool("custom__tool_name", mapping) == "custom-server"

    def test_opencode_naming(self):
        assert attribute_tool("memory_query_structure") == "memory"

    def test_attribute_results_groups_correctly(self):
        results = [
            ("mcp__vps__vps_status", "output1"),
            ("mcp__memory__query_structure", "output2"),
            ("Read", "file content"),
        ]
        groups = attribute_results(results)
        assert "vps" in groups
        assert "memory" in groups
        assert "non-mcp" in groups
        assert len(groups["vps"]) == 1
        assert len(groups["non-mcp"]) == 1
