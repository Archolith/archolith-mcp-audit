"""3e. Format Waste Detector — JSON where CSV/key-value would be shorter."""

from __future__ import annotations

from archolith_mcp_audit.attributor import attribute_tool
from archolith_mcp_audit.detectors._helpers import (
    WasteFinding,
    _json_format_overhead,
    _truncate,
)
from archolith_mcp_audit.extractors.base import ToolResult
from archolith_mcp_audit.tokenizer import count_tokens


def detect_format_waste(
    tool_results: list[ToolResult],
    server_mapping: dict[str, str] | None,
) -> list[WasteFinding]:
    """Detect JSON where CSV/key-value would be more token-efficient."""
    by_tool: dict[str, list[ToolResult]] = {}
    for r in tool_results:
        by_tool.setdefault(r.tool_name, []).append(r)

    findings: list[WasteFinding] = []

    for tool_name, results in by_tool.items():
        server = attribute_tool(tool_name, server_mapping)
        if server == "non-mcp":
            continue

        format_waste = 0
        format_waste_tokens = 0
        format_waste_bytes = 0
        example = ""

        for r in results:
            overhead = _json_format_overhead(r.result_text)
            if overhead > 0.3:
                format_waste += 1
                tc = count_tokens(r.result_text)
                waste_tokens = int(tc.tokens_cl100k * overhead)
                format_waste_tokens += waste_tokens
                format_waste_bytes += int(tc.bytes * overhead)
                if not example:
                    example = _truncate(r.result_text, 300)

        if format_waste > 0 and format_waste_tokens > 100:
            total_calls = len(results)
            findings.append(WasteFinding(
                tool_name=tool_name,
                server=server,
                waste_type="format",
                severity="medium",
                tokens_wasted=format_waste_tokens,
                bytes_wasted=format_waste_bytes,
                call_count=format_waste,
                total_calls=total_calls,
                description=f"{format_waste} results with JSON format overhead "
                            f"(key repetition, structural markup)",
                suggestion="Support _compact=true parameter to return "
                           "key-value lines or CSV instead of JSON objects.",
                estimated_savings_pct=45.0,
                example_before=example,
                example_after="key1=value1\nkey2=value2\n...",
            ))

    return findings
