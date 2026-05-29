"""In-session MCP audit server.

Exposes three tools:
  mcp_audit_summary — lightweight per-server token share table
  mcp_audit_detail  — deep dive on one server
  mcp_audit_check   — threshold pass/fail check

The server maintains a LiveAccumulator that observes tool results
as the session progresses. Observations are fed via a TelemetryBridge
that connects to RTK telemetry, file-based telemetry, or direct push
from hook observers.

Disabled by default to avoid adding ~200-300 tokens of schema overhead
per turn. Set MCP_AUDIT_ENABLED=1 to enable.
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

import time

from archolith_mcp_audit.accumulator import LiveAccumulator
from archolith_mcp_audit.attributor import _load_mapping
from archolith_mcp_audit.telemetry_bridge import TelemetryBridge

SESSIONS_DIR = Path.home() / ".archolith" / "sessions"
MAX_SESSION_AGE_HOURS = 24

# Per-session caches (keyed by session_id)
_accumulators: dict[str, LiveAccumulator] = {}
_bridges: dict[str, TelemetryBridge] = {}


def list_active_sessions() -> list[str]:
    """Return session IDs with JSONL files modified in the last 24h, newest first."""
    if not SESSIONS_DIR.exists():
        return []
    cutoff = time.time() - MAX_SESSION_AGE_HOURS * 3600
    sessions = [
        p.stem for p in SESSIONS_DIR.glob("*.jsonl")
        if p.stat().st_mtime > cutoff
    ]
    return sorted(
        sessions,
        key=lambda s: (SESSIONS_DIR / f"{s}.jsonl").stat().st_mtime,
        reverse=True,
    )


def get_session_name(session_id: str) -> str:
    """Return the human-readable name written by hook_session_start, or short ID."""
    name_file = SESSIONS_DIR / f"{session_id}.name"
    if name_file.exists():
        return name_file.read_text(encoding="utf-8").strip()
    return session_id[:16]


def get_accumulator(session_id: str) -> LiveAccumulator:
    """Get or create the live accumulator for a session."""
    if session_id not in _accumulators:
        mapping = _load_mapping()
        _accumulators[session_id] = LiveAccumulator(server_mapping=mapping)
    return _accumulators[session_id]


def get_bridge(session_id: str) -> TelemetryBridge:
    """Get or create the telemetry bridge for a session.

    Connects to ~/.archolith/sessions/<session_id>.jsonl written by the
    hook_observer_standalone PostToolUse hook.
    Also honours:
      - MCP_AUDIT_RTK=1          — connect to RTK FilterTelemetryStore
      - MCP_AUDIT_TELEMETRY_FILE — override file path (single-session compat)
    """
    if session_id not in _bridges:
        bridge = TelemetryBridge(accumulator=get_accumulator(session_id))

        if os.environ.get("MCP_AUDIT_RTK", "").lower() in ("1", "true", "yes"):
            bridge.connect_rtk()

        # Explicit override takes precedence (backward compat)
        override = os.environ.get("MCP_AUDIT_TELEMETRY_FILE", "")
        path = Path(override) if override else SESSIONS_DIR / f"{session_id}.jsonl"
        bridge.connect_file(path)
        _bridges[session_id] = bridge

    return _bridges[session_id]


if _HAS_FASTMCP:
    # Check if audit is explicitly enabled. Default: disabled to avoid adding
    # ~200-300 tokens of schema overhead per turn to the very problem we're measuring.
    # Set MCP_AUDIT_ENABLED=1 (or any truthy value) to enable.
    _audit_enabled = os.environ.get("MCP_AUDIT_ENABLED", "").lower() in ("1", "true", "yes")

    if not _audit_enabled:
        # Provide stubs that explain how to enable
        def mcp_audit_summary() -> str:
            """Show per-server token usage summary for the current session.

            Disabled by default. Set MCP_AUDIT_ENABLED=1 to enable.
            """
            return ("MCP audit is disabled. Set MCP_AUDIT_ENABLED=1 to enable. "
                    "This avoids adding ~200-300 tokens of schema overhead per turn.")

        def mcp_audit_detail(server: str) -> str:
            """Show detailed token usage for a specific MCP server.

            Disabled by default. Set MCP_AUDIT_ENABLED=1 to enable.
            """
            return ("MCP audit is disabled. Set MCP_AUDIT_ENABLED=1 to enable.")

        def mcp_audit_check(
            max_server_share: float = 20.0,
            max_total_mcp_share: float = 40.0,
        ) -> str:
            """Check if token usage exceeds thresholds.

            Disabled by default. Set MCP_AUDIT_ENABLED=1 to enable.
            """
            return ("MCP audit is disabled. Set MCP_AUDIT_ENABLED=1 to enable.")

        def run_server() -> None:
            """Start the MCP server (disabled)."""
            print("MCP audit server is disabled. Set MCP_AUDIT_ENABLED=1 to enable.", flush=True)
            raise SystemExit(0)

    else:
        mcp = FastMCP(
            "archolith-audit",
            instructions="MCP token usage audit. Use mcp_audit_summary for a quick "
                         "overview, mcp_audit_detail for deep-dive on a server, "
                         "mcp_audit_check for threshold pass/fail, "
                         "mcp_audit_bridge_status for telemetry source status.",
        )

        @mcp.tool()
        def mcp_audit_summary() -> str:
            """Show per-server token usage summary for all active sessions.

            Reads all ~/.archolith/sessions/*.jsonl files modified in the last
            24 hours. Each session is shown with its human-readable name
            (written by the SessionStart hook). ~300 tokens.
            """
            sessions = list_active_sessions()
            if not sessions:
                return (
                    "No active sessions found in ~/.archolith/sessions/\n"
                    "Ensure the SessionStart and PostToolUse hooks are installed."
                )

            lines = [f"MCP Token Usage ({len(sessions)} active session(s)):", ""]
            for session_id in sessions:
                bridge = get_bridge(session_id)
                bridge.sync()
                acc = get_accumulator(session_id)
                name = get_session_name(session_id)
                summary = acc.get_server_summary()
                mcp_share = acc.get_mcp_share()

                lines.append(f"  [{name}]")
                if not summary:
                    lines.append("    — no observations yet")
                else:
                    for server, data in summary.items():
                        savings_flag = ""
                        if data["savings_pct"] > 0:
                            savings_flag = f"  {data['savings_pct']:.0f}% savings"
                        lines.append(
                            f"    {server:<23s} {data['share_pct']:>5.1f}%"
                            f"  {data['call_count']:>4} calls{savings_flag}"
                        )
                    lines.append(
                        f"    MCP share: {mcp_share:.1f}%"
                        f"  |  {acc.total_raw_chars:,} chars"
                        f"  |  {acc.total_results} results"
                    )
                lines.append("")

            return "\n".join(lines)

        @mcp.tool()
        def mcp_audit_detail(server: str) -> str:
            """Show detailed token usage for a specific MCP server across all sessions.

            Args:
                server: The MCP server name (e.g., 'gradle', 'vps', 'memory')

            Returns per-session breakdown with waste findings. ~200-500 tokens.
            """
            sessions = list_active_sessions()
            if not sessions:
                return "No active sessions found."

            lines = [f"{server} — detail across active sessions:", ""]
            found_any = False

            for session_id in sessions:
                bridge = get_bridge(session_id)
                bridge.sync()
                acc = get_accumulator(session_id)
                summary = acc.get_server_summary()
                name = get_session_name(session_id)

                if server not in summary:
                    continue
                found_any = True
                data = summary[server]
                lines.append(
                    f"  [{name}]  {data['call_count']} calls, "
                    f"{data['raw_chars']:,} chars ({data['share_pct']:.1f}%)"
                )
                lines.append(f"    Tools: {', '.join(data['tools'][:6])}")
                lines.append(f"    Compression savings: {data['savings_pct']:.1f}%")

                findings = data.get("waste_findings", [])
                if findings:
                    lines.append("    Waste findings:")
                    for f in findings[:3]:
                        lines.append(f"      [{f.severity.upper()}] {f.waste_type}: {f.suggestion}")
                    if len(findings) > 3:
                        lines.append(f"      ... and {len(findings) - 3} more")
                elif data["savings_pct"] > 80:
                    lines.append("    Suggestion: Very verbose output — consider compact mode.")
                elif data["savings_pct"] > 50:
                    lines.append("    Suggestion: Moderate verbosity — envelope stripping may help.")
                lines.append("")

            if not found_any:
                all_servers: set[str] = set()
                for session_id in sessions:
                    all_servers.update(get_accumulator(session_id).get_server_summary().keys())
                available = sorted(s for s in all_servers if s != "non-mcp")
                if available:
                    return f"Server '{server}' not found. Available: {', '.join(available)}"
                return f"Server '{server}' not found. No MCP servers observed yet."

            return "\n".join(lines)

        @mcp.tool()
        def mcp_audit_check(
            max_server_share: float = 20.0,
            max_total_mcp_share: float = 40.0,
        ) -> str:
            """Check if token usage exceeds thresholds across all active sessions.

            Args:
                max_server_share: Maximum allowed share per server (default 20%)
                max_total_mcp_share: Maximum total MCP share (default 40%)

            Returns pass/fail for each session. ~50-150 tokens.
            """
            sessions = list_active_sessions()
            if not sessions:
                return "No active sessions found."

            lines = []
            overall = "PASS"

            for session_id in sessions:
                bridge = get_bridge(session_id)
                bridge.sync()
                acc = get_accumulator(session_id)
                summary = acc.get_server_summary()
                mcp_share = acc.get_mcp_share()
                name = get_session_name(session_id)

                lines.append(f"[{name}]")
                for server, data in summary.items():
                    if server == "non-mcp":
                        continue
                    if data["share_pct"] > max_server_share:
                        lines.append(f"  FAIL  {server} {data['share_pct']:.1f}% > {max_server_share:.0f}%")
                        overall = "FAIL"
                    else:
                        lines.append(f"  OK    {server} {data['share_pct']:.1f}%")
                if mcp_share > max_total_mcp_share:
                    lines.append(f"  FAIL  Total MCP {mcp_share:.1f}% > {max_total_mcp_share:.0f}%")
                    overall = "FAIL"
                else:
                    lines.append(f"  OK    Total MCP {mcp_share:.1f}%")
                lines.append("")

            lines.append(f"Result: {overall}")
            return "\n".join(lines)

        @mcp.tool()
        def mcp_audit_bridge_status() -> str:
            """Show telemetry bridge status for all active sessions. ~50 tokens."""
            sessions = list_active_sessions()
            if not sessions:
                return "No active sessions found in ~/.archolith/sessions/"

            lines = []
            for session_id in sessions:
                bridge = get_bridge(session_id)
                bridge.sync()
                name = get_session_name(session_id)
                lines.append(
                    f"[{name}]  {bridge.active_source_count()}/{bridge.source_count()} sources"
                    f"  {bridge.total_synced} observations"
                )
            return "\n".join(lines)

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
