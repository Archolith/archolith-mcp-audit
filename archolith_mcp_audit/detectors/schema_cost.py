"""3d. Schema Cost Detector — tool schema token overhead in system prompt."""

from __future__ import annotations

from archolith_mcp_audit.attributor import attribute_tool
from archolith_mcp_audit.detectors._helpers import WasteFinding
from archolith_mcp_audit.detectors.config import savings_pct
from archolith_mcp_audit.extractors.base import ToolResult

AVG_SCHEMA_TOKENS = 300


def detect_schema_cost(
    tool_results: list[ToolResult],
    server_mapping: dict[str, str] | None,
    total_turns: int = 1,
) -> list[WasteFinding]:
    """Estimate tool schema token cost in the system prompt.

    This is a heuristic — we don't extract schemas from session logs.
    We estimate based on distinct tool names per server and assume
    ~300 tokens per tool schema (conservative average).
    """
    by_server: dict[str, set[str]] = {}

    for r in tool_results:
        server = attribute_tool(r.tool_name, server_mapping)
        if server == "non-mcp":
            continue
        by_server.setdefault(server, set()).add(r.tool_name)

    if not by_server:
        return []

    findings: list[WasteFinding] = []

    for server, tools in by_server.items():
        tool_count = len(tools)
        per_turn_cost = tool_count * AVG_SCHEMA_TOKENS
        session_cost = per_turn_cost * total_turns

        if session_cost > 1000:
            findings.append(WasteFinding(
                tool_name=f"{server} (schemas)",
                server=server,
                waste_type="schema",
                severity="medium" if per_turn_cost > 2000 else "low",
                tokens_wasted=int(session_cost * savings_pct("schema_lazy_load") / 100),
                bytes_wasted=0,
                call_count=tool_count,
                total_calls=tool_count,
                description=f"{tool_count} tool schemas at ~{AVG_SCHEMA_TOKENS} tokens each "
                            f"= {per_turn_cost:,} tokens/turn x {total_turns} turns "
                            f"= {session_cost:,} tokens total",
                suggestion="Lazy-load schemas after first call. "
                           "Abbreviate to name+1-line-description thereafter.",
                estimated_savings_pct=savings_pct("schema_lazy_load"),
                example_before=f"[{server}: {tool_count} full tool schemas, "
                               f"{per_turn_cost} tokens/turn]",
                example_after=f"[{server}: {tool_count} abbreviated schemas, "
                              f"~{tool_count * 30} tokens/turn]",
            ))

    return findings
