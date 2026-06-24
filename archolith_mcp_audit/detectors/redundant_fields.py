"""3c. Redundant Field Output Detector — overbroad queries, missing field filters."""

from __future__ import annotations

from archolith_mcp_audit.attributor import attribute_tool
from archolith_mcp_audit.detectors._helpers import (
    WasteFinding,
    _count_json_fields,
    _evidence_id,
    _severity_for_waste_pct,
    _trimmable_fraction,
    _truncate,
)
from archolith_mcp_audit.detectors.config import field_threshold, overbroad_tools
from archolith_mcp_audit.extractors.base import ToolResult
from archolith_mcp_audit.tokenizer import count_tokens


def detect_redundant_fields(
    tool_results: list[ToolResult],
    server_mapping: dict[str, str] | None,
) -> list[WasteFinding]:
    """Detect overbroad results with unneeded fields."""
    by_tool: dict[str, list[ToolResult]] = {}
    for r in tool_results:
        by_tool.setdefault(r.tool_name, []).append(r)

    findings: list[WasteFinding] = []

    for tool_name, results in by_tool.items():
        server = attribute_tool(tool_name, server_mapping)
        if server == "non-mcp":
            continue

        threshold = field_threshold(tool_name)

        overbroad = 0
        overbroad_tokens = 0
        overbroad_bytes = 0
        evidence_ids: list[str] = []
        max_field_count = 0
        trimmable_sum = 0.0
        example = ""

        for index, r in enumerate(results):
            field_count = _count_json_fields(r.result_text)
            if field_count > threshold:
                overbroad += 1
                evidence_ids.append(_evidence_id(r, index))
                tc = count_tokens(r.result_text)
                overbroad_tokens += tc.tokens_cl100k
                overbroad_bytes += tc.bytes
                max_field_count = max(max_field_count, field_count)
                trimmable_sum += _trimmable_fraction(r.result_text)
                if not example:
                    example = _truncate(r.result_text, 300)

        if overbroad > 0:
            total_calls = len(results)
            waste_pct = overbroad / total_calls

            avg_trimmable = trimmable_sum / overbroad
            est_waste_pct = round(min(50.0, avg_trimmable * 100), 1)

            if est_waste_pct <= 0:
                continue

            suggestion = ("Accept fields parameter to return only requested "
                           "data. Return graph nodes, not entire structure.")
            if tool_name in overbroad_tools():
                suggestion = ("Add fields= parameter to return only requested "
                              "graph nodes or memory fields, not entire structure.")

            findings.append(WasteFinding(
                tool_name=tool_name,
                server=server,
                waste_type="redundant_fields",
                severity=_severity_for_waste_pct(waste_pct),
                tokens_wasted=int(overbroad_tokens * est_waste_pct / 100),
                bytes_wasted=int(overbroad_bytes * est_waste_pct / 100),
                call_count=overbroad,
                total_calls=total_calls,
                description=f"{overbroad}/{total_calls} calls return overbroad "
                            f"results ({overbroad_tokens:,} tokens, up to {max_field_count} fields)",
                suggestion=suggestion,
                estimated_savings_pct=est_waste_pct,
                example_before=example,
                example_after="[filtered fields only, as requested]",
                evidence_ids=tuple(evidence_ids),
            ))

    return findings
