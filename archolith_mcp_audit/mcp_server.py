"""In-session MCP audit server.

Exposes three tools:
  mcp_audit_summary — lightweight per-server token share table
  mcp_audit_detail  — deep dive on one server
  mcp_audit_check   — threshold pass/fail check

The server maintains a LiveAccumulator that observes tool results
as the session progresses.
"""

from __future__ import annotations

import os
from pathlib import Path

# FastMCP is optional — the CLI works without it
try:
    from fastmcp import FastMCP
    _HAS_FASTMCP = True
except ImportError:
    _HAS_FASTMCP = False

from archolith_mcp_audit.accumulator import LiveAccumulator
from archolith_mcp_audit.attributor import _load_mapping


# Module-level accumulator (singleton per process)
_accumulator: LiveAccumulator | None = None


def get_accumulator() -> LiveAccumulator:
    """Get or create the live accumulator."""
    global _accumulator
    if _accumulator is None:
        mapping = _load_mapping()
        _accumulator = LiveAccumulator(server_mapping=mapping)
    return _accumulator


if _HAS_FASTMCP:
    mcp = FastMCP(
        "mcp-audit",
        instructions="MCP token usage audit. Use mcp_audit_summary for a quick "
                     "overview, mcp_audit_detail for deep-dive on a server, "
                     "mcp_audit_check for threshold pass/fail.",
    )

    @mcp.tool()
    def mcp_audit_summary() -> str:
        """Show per-server token usage summary for the current session.

        Returns a compact table showing each MCP server's token share,
        call count, and compression savings. ~300 tokens.
        """
        acc = get_accumulator()
        summary = acc.get_server_summary()
        mcp_share = acc.get_mcp_share()

        if not summary:
            return "No tool results observed yet in this session."

        lines = ["MCP Token Usage (this session):", ""]
        for server, data in summary.items():
            savings_flag = ""
            if data["savings_pct"] > 50:
                savings_flag = f"  high savings ({data['savings_pct']:.0f}%)"
            lines.append(
                f"  {server:<25s} {data['share_pct']:>5.1f}%  "
                f"{data['call_count']:>4} calls{savings_flag}"
            )

        lines.append("")
        lines.append(f"  Total MCP share: {mcp_share:.1f}%")
        lines.append(f"  Total results: {acc.total_results}")

        return "\n".join(lines)

    @mcp.tool()
    def mcp_audit_detail(server: str) -> str:
        """Show detailed token usage for a specific MCP server.

        Args:
            server: The MCP server name (e.g., 'gradle', 'vps', 'memory')

        Returns waste findings and optimization suggestions. ~200-500 tokens.
        """
        acc = get_accumulator()
        summary = acc.get_server_summary()

        if server not in summary:
            available = [s for s in summary if s != "non-mcp"]
            if available:
                return f"Server '{server}' not found. Available: {', '.join(available)}"
            return f"Server '{server}' not found. No MCP servers observed yet."

        data = summary[server]
        lines = [
            f"{server} — {data['call_count']} calls, "
            f"{data['raw_chars']:,} chars ({data['share_pct']:.1f}%)",
            "",
            f"Tools: {', '.join(data['tools'][:8])}",
            f"Compression savings: {data['savings_pct']:.1f}%",
        ]

        # Add suggestions based on patterns
        if data["savings_pct"] > 80:
            lines.append("")
            lines.append("Suggestion: High compression indicates server output is "
                         "very verbose. Consider compact mode or field filtering.")
        elif data["savings_pct"] > 50:
            lines.append("")
            lines.append("Suggestion: Moderate compression. Envelope stripping "
                         "or help-on-demand could reduce output size.")

        return "\n".join(lines)

    @mcp.tool()
    def mcp_audit_check(
        max_server_share: float = 20.0,
        max_total_mcp_share: float = 40.0,
    ) -> str:
        """Check if token usage exceeds thresholds.

        Args:
            max_server_share: Maximum allowed share per server (default 20%)
            max_total_mcp_share: Maximum total MCP share (default 40%)

        Returns pass/fail for each threshold. ~50-100 tokens.
        """
        acc = get_accumulator()
        summary = acc.get_server_summary()
        mcp_share = acc.get_mcp_share()

        results = []
        overall = "PASS"

        # Check per-server thresholds
        for server, data in summary.items():
            if server == "non-mcp":
                continue
            if data["share_pct"] > max_server_share:
                results.append(f"FAIL  {server} exceeds {max_server_share:.0f}% "
                             f"server share ({data['share_pct']:.1f}%)")
                overall = "FAIL"
            else:
                results.append(f"OK    {server} within limit ({data['share_pct']:.1f}%)")

        # Check total MCP share
        if mcp_share > max_total_mcp_share:
            results.append(f"FAIL  Total MCP share exceeds {max_total_mcp_share:.0f}% "
                         f"({mcp_share:.1f}%)")
            overall = "FAIL"
        else:
            results.append(f"OK    Total MCP share within limit ({mcp_share:.1f}%)")

        results.append(f"\nResult: {overall}")
        return "\n".join(results)

    def run_server() -> None:
        """Start the MCP server."""
        mcp.run()

else:
    def run_server() -> None:
        """Stub when FastMCP is not installed."""
        print("Error: FastMCP is not installed. Install with: pip install fastmcp", flush=True)
        raise SystemExit(1)


if __name__ == "__main__":
    run_server()
