"""3a. Polling Waste Detector — repeated calls with unchanged results."""

from __future__ import annotations

from archolith_mcp_audit.attributor import attribute_tool
from archolith_mcp_audit.detectors._helpers import (
    WasteFinding,
    _severity_for_waste_pct,
    _similarity,
    _truncate,
)
from archolith_mcp_audit.extractors.base import ToolResult
from archolith_mcp_audit.tokenizer import count_tokens


def detect_polling(
    tool_results: list[ToolResult],
    tool_calls_by_id: dict[str, dict],
    server_mapping: dict[str, str] | None,
) -> list[WasteFinding]:
    """Detect repeated calls with same/unchanged results (polling waste)."""
    by_tool: dict[str, list[ToolResult]] = {}
    for r in tool_results:
        by_tool.setdefault(r.tool_name, []).append(r)

    findings: list[WasteFinding] = []

    for tool_name, results in by_tool.items():
        if len(results) < 3:
            continue

        server = attribute_tool(tool_name, server_mapping)
        if server == "non-mcp":
            continue

        redundant = 0
        redundant_tokens = 0
        redundant_bytes = 0
        example_before = ""

        prev_text = ""
        for r in results:
            if prev_text and _similarity(prev_text, r.result_text) > 0.8:
                redundant += 1
                tc = count_tokens(r.result_text)
                redundant_tokens += tc.tokens_cl100k
                redundant_bytes += tc.bytes
                if not example_before:
                    example_before = _truncate(r.result_text)
            prev_text = r.result_text

        if redundant > 0:
            total_calls = len(results)
            waste_pct = redundant / total_calls

            findings.append(WasteFinding(
                tool_name=tool_name,
                server=server,
                waste_type="polling",
                severity=_severity_for_waste_pct(waste_pct),
                tokens_wasted=redundant_tokens,
                bytes_wasted=redundant_bytes,
                call_count=redundant,
                total_calls=total_calls,
                description=f"{redundant}/{total_calls} calls ({waste_pct:.0%}) return "
                            f"near-identical results (polling waste)",
                suggestion="Return delta on poll, not full replay. "
                           "Add status-only mode for polling queries.",
                estimated_savings_pct=min(90.0, waste_pct * 100),
                example_before=example_before,
                example_after="[status: running, duration: 42s, 2 new lines since last check]",
            ))

    return findings
