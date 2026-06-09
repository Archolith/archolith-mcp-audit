"""Waste pattern detectors for MCP token waste.

Detectors:
    polling     — repeated calls with unchanged results
    oversized   — envelope overhead, help text bloat
    redundant_fields — overbroad queries, missing field filters
    schema_cost — tool schema token overhead in system prompt
    format_waste — JSON where CSV/key-value would be shorter
    cache_breaker — content that changes but is semantically identical
"""

from __future__ import annotations

from archolith_mcp_audit.detectors._helpers import WasteFinding
from archolith_mcp_audit.detectors.cache_breaker import detect_cache_breakers
from archolith_mcp_audit.detectors.format_waste import detect_format_waste
from archolith_mcp_audit.detectors.oversized import detect_oversized
from archolith_mcp_audit.detectors.polling import detect_polling
from archolith_mcp_audit.detectors.redundant_fields import detect_redundant_fields
from archolith_mcp_audit.detectors.schema_cost import detect_schema_cost
from archolith_mcp_audit.extractors.base import SessionData

__all__ = [
    "WasteFinding",
    "detect_waste",
    "detect_polling",
    "detect_oversized",
    "detect_redundant_fields",
    "detect_schema_cost",
    "detect_format_waste",
    "detect_cache_breakers",
]


def detect_waste(
    session: SessionData,
    server_mapping: dict[str, str] | None = None,
) -> list[WasteFinding]:
    """Run all waste detectors on a session and return findings."""
    calls_by_id: dict[str, dict] = {
        tc.call_id: {"tool_name": tc.tool_name, "args": tc.args, "turn": tc.turn_number}
        for tc in session.tool_calls
    }

    findings: list[WasteFinding] = []

    findings.extend(detect_polling(session.tool_results, calls_by_id, server_mapping))
    findings.extend(detect_oversized(session.tool_results, server_mapping))
    findings.extend(detect_redundant_fields(session.tool_results, server_mapping))
    findings.extend(detect_schema_cost(
        session.tool_results, server_mapping, session.total_turns
    ))
    findings.extend(detect_format_waste(session.tool_results, server_mapping))
    findings.extend(detect_cache_breakers(session.tool_results, server_mapping))

    return findings
