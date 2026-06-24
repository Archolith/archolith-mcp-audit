"""3a. Polling Waste Detector — repeated calls with unchanged results."""

from __future__ import annotations

from archolith_mcp_audit.attributor import attribute_tool
from archolith_mcp_audit.detectors._helpers import (
    WasteFinding,
    _evidence_id,
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
    """Detect repeated calls with unchanged results (polling waste).

    Byte-identical adjacent results are high-confidence waste. Similar but changing
    results are emitted as low-confidence informational findings with no recoverable
    token claim, because they may be legitimate build/CI status polling.
    """
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

        exact_repeats = 0
        similar_but_distinct = 0
        exact_evidence_ids: list[str] = []
        similar_evidence_ids: list[str] = []
        redundant_tokens = 0
        redundant_bytes = 0
        example_before = ""

        prev_text = ""
        for index, r in enumerate(results):
            if prev_text:
                if r.result_text == prev_text:
                    exact_repeats += 1
                    exact_evidence_ids.append(_evidence_id(r, index))
                    tc = count_tokens(r.result_text)
                    redundant_tokens += tc.tokens_cl100k
                    redundant_bytes += tc.bytes
                    if not example_before:
                        example_before = _truncate(r.result_text)
                elif _similarity(prev_text, r.result_text) > 0.8:
                    similar_but_distinct += 1
                    similar_evidence_ids.append(_evidence_id(r, index))
            prev_text = r.result_text

        if exact_repeats > 0:
            total_calls = len(results)
            waste_pct = exact_repeats / total_calls

            findings.append(WasteFinding(
                tool_name=tool_name,
                server=server,
                waste_type="polling",
                severity=_severity_for_waste_pct(waste_pct),
                tokens_wasted=redundant_tokens,
                bytes_wasted=redundant_bytes,
                call_count=exact_repeats,
                total_calls=total_calls,
                description=f"{exact_repeats}/{total_calls} calls ({waste_pct:.0%}) return "
                            f"byte-identical results (polling waste)",
                suggestion="Return delta on poll, not full replay. "
                           "Add status-only mode for polling queries.",
                estimated_savings_pct=min(90.0, waste_pct * 100),
                example_before=example_before,
                example_after="[status: running, duration: 42s, 2 new lines since last check]",
                confidence="high",
                evidence_ids=tuple(exact_evidence_ids),
            ))

        if similar_but_distinct >= 2:
            total_calls = len(results)
            info_pct = similar_but_distinct / total_calls
            findings.append(WasteFinding(
                tool_name=tool_name,
                server=server,
                waste_type="polling",
                severity="info",
                tokens_wasted=0,
                bytes_wasted=0,
                call_count=similar_but_distinct,
                total_calls=total_calls,
                description=f"{similar_but_distinct}/{total_calls} calls ({info_pct:.0%}) had similar "
                            f"but non-identical results; possible legitimate status polling",
                suggestion="Review manually before treating this as waste; similar status updates may be legitimate.",
                estimated_savings_pct=0.0,
                confidence="low",
                evidence_ids=tuple(similar_evidence_ids),
            ))

    return findings
