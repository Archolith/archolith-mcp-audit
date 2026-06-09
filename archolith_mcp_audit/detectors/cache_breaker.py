"""3f. Cache Breaker Detector — content that changes but is semantically identical."""

from __future__ import annotations

from archolith_mcp_audit.attributor import attribute_tool
from archolith_mcp_audit.detectors._helpers import (
    WasteFinding,
    _normalize_ephemeral,
    _truncate,
)
from archolith_mcp_audit.extractors.base import ToolResult
from archolith_mcp_audit.tokenizer import count_tokens


def detect_cache_breakers(
    tool_results: list[ToolResult],
    server_mapping: dict[str, str] | None,
) -> list[WasteFinding]:
    """Detect content that changes between calls but is semantically identical."""
    by_tool: dict[str, list[ToolResult]] = {}
    for r in tool_results:
        by_tool.setdefault(r.tool_name, []).append(r)

    findings: list[WasteFinding] = []

    for tool_name, results in by_tool.items():
        server = attribute_tool(tool_name, server_mapping)
        if server == "non-mcp":
            continue

        if len(results) < 2:
            continue

        cache_breaks = 0
        cache_break_tokens = 0
        example = ""

        for i in range(1, len(results)):
            prev_norm = _normalize_ephemeral(results[i - 1].result_text)
            curr_norm = _normalize_ephemeral(results[i].result_text)

            if prev_norm == curr_norm and results[i - 1].result_text != results[i].result_text:
                cache_breaks += 1
                tc = count_tokens(results[i].result_text)
                cache_break_tokens += tc.tokens_cl100k
                if not example:
                    example = _truncate(results[i].result_text, 300)

        if cache_breaks > 0:
            total_calls = len(results)
            findings.append(WasteFinding(
                tool_name=tool_name,
                server=server,
                waste_type="cache_breaker",
                severity="medium" if cache_breaks > 3 else "low",
                tokens_wasted=int(cache_break_tokens * 0.4),
                bytes_wasted=0,
                call_count=cache_breaks,
                total_calls=total_calls,
                description=f"{cache_breaks} calls change only in timestamps/UUIDs, "
                            f"preventing prompt caching",
                suggestion="Normalize ephemeral values (timestamps, UUIDs, "
                           "durations) to stable placeholders for cache hits.",
                estimated_savings_pct=40.0,
                example_before=example,
                example_after="[same content with [TIMESTAMP]/[UUID] placeholders]",
            ))

    return findings
