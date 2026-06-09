"""Before/after comparison mode for measuring optimization effectiveness.

Takes two JSON audit reports (from --format json), compares per-server
metrics, and produces a delta report showing what changed.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ServerDelta:
    """Change in token metrics for a single server."""

    server: str
    before_tokens: int = 0
    after_tokens: int = 0
    token_change: int = 0
    token_change_pct: float = 0.0
    before_waste: int = 0
    after_waste: int = 0
    waste_change: int = 0
    waste_change_pct: float = 0.0
    before_calls: int = 0
    after_calls: int = 0
    new_waste_types: list[str] | None = None
    resolved_waste_types: list[str] | None = None
    status: str = ""  # "improved", "regressed", "no_change", "new", "removed"


def compare_reports(
    before: dict,
    after: dict,
    regression_threshold_pct: float = 20.0,
) -> list[ServerDelta]:
    """Compare two JSON audit reports and return per-server deltas.

    Args:
        before: The baseline JSON audit report.
        after: The follow-up JSON audit report.
        regression_threshold_pct: Percentage change in waste at which a
            server is considered "regressed" or "improved". Default 20%.
    """
    all_servers = set(list(before.get("servers", {}).keys()) + list(after.get("servers", {}).keys()))
    all_servers.discard("non-mcp")

    deltas: list[ServerDelta] = []

    for server in sorted(all_servers):
        b = before.get("servers", {}).get(server, {})
        a = after.get("servers", {}).get(server, {})

        b_tokens = b.get("token_share", 0)
        a_tokens = a.get("token_share", 0)
        b_waste = sum(f.get("tokens_wasted", 0) for f in b.get("findings", []))
        a_waste = sum(f.get("tokens_wasted", 0) for f in a.get("findings", []))
        b_calls = b.get("call_count", 0)
        a_calls = a.get("call_count", 0)

        token_change = a_tokens - b_tokens
        waste_change = a_waste - b_waste

        token_pct = (token_change / b_tokens * 100) if b_tokens > 0 else float("inf") if a_tokens > 0 else 0.0
        waste_pct = (waste_change / b_waste * 100) if b_waste > 0 else float("inf") if a_waste > 0 else 0.0

        b_types = {f.get("waste_type") for f in b.get("findings", [])}
        a_types = {f.get("waste_type") for f in a.get("findings", [])}
        new_waste = sorted(a_types - b_types)
        resolved_waste = sorted(b_types - a_types)

        if b_tokens == 0 and a_tokens > 0:
            status = "new"
        elif a_tokens == 0 and b_tokens > 0:
            status = "removed"
        elif b_waste > 0 and waste_pct < -regression_threshold_pct:
            status = "improved"
        elif b_waste > 0 and waste_pct > regression_threshold_pct:
            status = "regressed"
        else:
            status = "no_change"

        deltas.append(ServerDelta(
            server=server,
            before_tokens=b_tokens,
            after_tokens=a_tokens,
            token_change=token_change,
            token_change_pct=token_pct,
            before_waste=b_waste,
            after_waste=a_waste,
            waste_change=waste_change,
            waste_change_pct=waste_pct,
            before_calls=b_calls,
            after_calls=a_calls,
            new_waste_types=new_waste,
            resolved_waste_types=resolved_waste,
            status=status,
        ))

    return deltas


def format_delta_report(deltas: list[ServerDelta], after: dict | None = None) -> str:
    """Format comparison results as human-readable text.

    Args:
        deltas: Per-server comparison results.
        after: The "after" JSON report dict, used to show remaining waste.
    """
    lines = []
    lines.append("=" * 70)
    lines.append("MCP AUDIT COMPARISON")
    lines.append("=" * 70)

    if not deltas:
        lines.append("No servers to compare.")
        return "\n".join(lines)

    for d in deltas:
        lines.append("")
        lines.append(f"--- {d.server} ---")
        lines.append(f"  Before: {d.before_calls} calls, {d.before_tokens:,} tokens, {d.before_waste:,} wasted")
        lines.append(f"  After:  {d.after_calls} calls, {d.after_tokens:,} tokens, {d.after_waste:,} wasted")

        if d.before_tokens > 0:
            lines.append(f"  Change: {d.token_change:+,} tokens ({d.token_change_pct:+.1f}%), "
                         f"{d.waste_change:+,} waste")
        else:
            lines.append(f"  Change: new server ({d.after_tokens:,} tokens)")

        if d.new_waste_types:
            lines.append(f"  WARNING: New waste types: {', '.join(d.new_waste_types)}")
        if d.resolved_waste_types:
            lines.append(f"  Resolved waste types: {', '.join(d.resolved_waste_types)}")

        # Explicit warning for servers that disappeared
        if d.status == "removed":
            lines.append(f"  WARNING: Server '{d.server}' present in before but missing in after data")

        status_labels = {
            "improved": "IMPROVED",
            "regressed": "REGRESSED",
            "no_change": "No significant change",
            "new": "NEW SERVER",
            "removed": "REMOVED",
        }
        lines.append(f"  Status: {status_labels.get(d.status, d.status)}")

        # Show remaining waste details for this server
        if after and d.status != "removed" and d.after_waste > 0:
            after_server = after.get("servers", {}).get(d.server, {})
            after_findings = after_server.get("findings", [])
            if after_findings:
                lines.append("  Remaining waste:")
                for f in after_findings[:3]:
                    sev = f.get("severity", "unknown").upper()
                    wtype = f.get("waste_type", "unknown")
                    wasted = f.get("tokens_wasted", 0)
                    lines.append(f"    [{sev}]  {wtype}  {wasted:,} tokens")
                if len(after_findings) > 3:
                    lines.append(f"    ... and {len(after_findings) - 3} more")

    # Summary
    total_waste_change = sum(d.waste_change for d in deltas)
    lines.append("")
    lines.append("=" * 70)
    lines.append("SUMMARY")
    lines.append("=" * 70)
    improved = [d for d in deltas if d.status == "improved"]
    regressed = [d for d in deltas if d.status == "regressed"]
    removed = [d for d in deltas if d.status == "removed"]
    lines.append(f"  Servers improved:  {len(improved)}")
    lines.append(f"  Servers regressed: {len(regressed)}")
    if removed:
        lines.append(f"  Servers removed:   {len(removed)} (present in before, missing in after)")
    lines.append(f"  Total waste change: {total_waste_change:+,} tokens")
    if total_waste_change < 0:
        lines.append("  Overall: Optimization effective")
    elif total_waste_change > 0:
        lines.append("  Overall: REGRESSION — total waste increased")
    else:
        lines.append("  Overall: No significant change")

    return "\n".join(lines)
