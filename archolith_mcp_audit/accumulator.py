"""Live per-session token accumulator.

Reads from RTK's FilterTelemetryStore (when available) or from
direct tool result observation. Provides aggregated per-server
token usage data for the in-session MCP audit tools.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from archolith_mcp_audit.attributor import attribute_tool
from archolith_mcp_audit.waste_detector import WasteFinding


@dataclass
class ServerAccumulator:
    """Accumulated data for a single MCP server."""

    call_count: int = 0
    raw_chars: int = 0
    filtered_chars: int = 0
    tool_names: set[str] = field(default_factory=set)
    waste_findings: list[WasteFinding] = field(default_factory=list)


class LiveAccumulator:
    """In-memory per-session token accumulator.

    Observes tool results as they flow through the session and
    aggregates per-server statistics. Passive — does not modify
    any data, only reads and accumulates.
    """

    def __init__(self, server_mapping: dict[str, str] | None = None) -> None:
        self.server_mapping = server_mapping
        self.servers: dict[str, ServerAccumulator] = defaultdict(ServerAccumulator)
        self.total_raw_chars = 0
        self.total_filtered_chars = 0
        self.total_results = 0

    def observe(self, tool_name: str, raw_chars: int, filtered_chars: int = 0) -> None:
        """Record a tool result observation."""
        server = attribute_tool(tool_name, self.server_mapping)
        acc = self.servers[server]
        acc.call_count += 1
        acc.raw_chars += raw_chars
        acc.filtered_chars += filtered_chars
        acc.tool_names.add(tool_name)
        self.total_raw_chars += raw_chars
        self.total_filtered_chars += filtered_chars
        self.total_results += 1

    def observe_telemetry_entry(self, entry: object) -> None:
        """Observe from an RTK FilterTelemetryStore entry.

        Expected entry attributes: tool_name, raw_chars, filtered_chars.
        Falls back gracefully if attributes don't exist.
        """
        tool_name = getattr(entry, "tool_name", getattr(entry, "tool", "unknown"))
        raw_chars = getattr(entry, "raw_chars", 0)
        filtered_chars = getattr(entry, "filtered_chars", 0)
        self.observe(tool_name, raw_chars, filtered_chars)

    def add_waste_findings(self, findings: list[WasteFinding]) -> None:
        """Add waste findings from a detection pass.

        These are attached per-server so mcp_audit_detail can report them.
        """
        for f in findings:
            acc = self.servers[f.server]
            acc.waste_findings.append(f)

    def get_server_summary(self) -> dict[str, dict]:
        """Return per-server summary data."""
        result = {}
        for server, acc in sorted(self.servers.items(), key=lambda x: -x[1].raw_chars):
            share = (acc.raw_chars / self.total_raw_chars * 100) if self.total_raw_chars > 0 else 0
            savings = ((acc.raw_chars - acc.filtered_chars) / acc.raw_chars * 100) if acc.raw_chars > 0 else 0
            result[server] = {
                "call_count": acc.call_count,
                "raw_chars": acc.raw_chars,
                "share_pct": round(share, 1),
                "savings_pct": round(savings, 1),
                "tools": sorted(acc.tool_names),
                "waste_findings": acc.waste_findings,
            }
        return result

    def get_mcp_share(self) -> float:
        """Return MCP share as percentage of total."""
        if self.total_raw_chars == 0:
            return 0.0
        mcp_chars = sum(
            acc.raw_chars for server, acc in self.servers.items()
            if server != "non-mcp"
        )
        return round(mcp_chars / self.total_raw_chars * 100, 1)

    def reset(self) -> None:
        """Reset all accumulated data."""
        self.servers.clear()
        self.total_raw_chars = 0
        self.total_filtered_chars = 0
        self.total_results = 0
