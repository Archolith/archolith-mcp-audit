"""3b. Oversized Results Detector — envelope overhead, help text bloat."""

from __future__ import annotations

from archolith_mcp_audit.attributor import attribute_tool
from archolith_mcp_audit.detectors._helpers import (
    WasteFinding,
    _envelope_overhead_bytes,
    _envelope_overhead_tokens,
    _has_json_envelope,
    _is_help_text,
    _severity_for_waste_pct,
    _truncate,
)
from archolith_mcp_audit.extractors.base import ToolResult
from archolith_mcp_audit.tokenizer import count_tokens


def detect_oversized(
    tool_results: list[ToolResult],
    server_mapping: dict[str, str] | None,
) -> list[WasteFinding]:
    """Detect oversized results — envelope overhead, help text bloat."""
    by_tool: dict[str, list[ToolResult]] = {}
    for r in tool_results:
        by_tool.setdefault(r.tool_name, []).append(r)

    findings: list[WasteFinding] = []

    for tool_name, results in by_tool.items():
        server = attribute_tool(tool_name, server_mapping)
        if server == "non-mcp":
            continue

        # Check for help text bloat
        help_results = [r for r in results if _is_help_text(r.result_text)]
        if len(help_results) >= 1 and len(results) > 0:
            help_tokens = sum(count_tokens(r.result_text).tokens_cl100k for r in help_results)
            help_bytes = sum(len(r.result_text.encode("utf-8")) for r in help_results)

            findings.append(WasteFinding(
                tool_name=tool_name,
                server=server,
                waste_type="oversized",
                severity=_severity_for_waste_pct(help_tokens / max(1, sum(
                    count_tokens(r.result_text).tokens_cl100k for r in results
                ))),
                tokens_wasted=int(help_tokens * 0.9),
                bytes_wasted=int(help_bytes * 0.9),
                call_count=len(help_results),
                total_calls=len(results),
                description=f"{len(help_results)} calls return help/usage text "
                            f"({help_tokens:,} tokens)",
                suggestion="Default to one-line summary; add --verbose flag "
                           "for full help text.",
                estimated_savings_pct=90.0,
                example_before=_truncate(help_results[0].result_text),
                example_after="[tool: help available, use --verbose for details]",
            ))

        # Check for JSON envelope overhead
        envelope_results = [r for r in results if _has_json_envelope(r.result_text)]
        if len(envelope_results) >= 2:
            envelope_tokens = sum(
                _envelope_overhead_tokens(r.result_text) for r in envelope_results
            )
            envelope_bytes = sum(
                _envelope_overhead_bytes(r.result_text) for r in envelope_results
            )

            if envelope_tokens > 100:
                findings.append(WasteFinding(
                    tool_name=tool_name,
                    server=server,
                    waste_type="oversized",
                    severity="medium",
                    tokens_wasted=envelope_tokens,
                    bytes_wasted=envelope_bytes,
                    call_count=len(envelope_results),
                    total_calls=len(results),
                    description=f"{len(envelope_results)} results have JSON envelope "
                                f"overhead ({envelope_tokens:,} tokens)",
                    suggestion="Strip envelope in compact mode. Return data "
                               "directly without wrapping status/meta.",
                    estimated_savings_pct=min(50.0, envelope_tokens / max(1, sum(
                        count_tokens(r.result_text).tokens_cl100k for r in results
                    )) * 100),
                    example_before=_truncate(envelope_results[0].result_text, 300),
                    example_after='{"key": "value", ...}',
                ))

    return findings
