"""Report generator — per-server report cards in text, JSON, and markdown."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TypedDict

from archolith_mcp_audit.attributor import attribute_tool
from archolith_mcp_audit.extractors.base import SessionData
from archolith_mcp_audit.tokenizer import count_tokens
from archolith_mcp_audit.waste_detector import WasteFinding


class _ServerSummary(TypedDict):
    """Intermediate representation for server report cards."""

    name: str
    token_share: int
    token_share_pct: float
    call_count: int
    tools: list[str]
    findings: list[WasteFinding]
    estimated_recoverable_tokens: int


def _build_server_summaries(report: AuditReport) -> list[_ServerSummary]:
    """Build a list of server summaries sorted by token share descending."""
    summaries: list[_ServerSummary] = []
    for server_name in sorted(report.servers, key=lambda s: -report.servers[s].token_share):
        sr = report.servers[server_name]
        summaries.append(_ServerSummary(
            name=server_name,
            token_share=sr.token_share,
            token_share_pct=sr.token_share_pct,
            call_count=sr.call_count,
            tools=sr.tools,
            findings=sr.findings,
            estimated_recoverable_tokens=sr.estimated_recoverable_tokens,
        ))
    return summaries


@dataclass
class ServerReport:
    """Per-server report card."""

    server: str
    token_share: int = 0
    token_share_pct: float = 0.0
    call_count: int = 0
    tools: list[str] = field(default_factory=list)
    findings: list[WasteFinding] = field(default_factory=list)
    estimated_recoverable_tokens: int = 0


@dataclass
class AuditReport:
    """Full session audit report."""

    session: str = ""
    source: str = ""
    total_tokens: int = 0
    mcp_tokens: int = 0
    mcp_share_pct: float = 0.0
    non_mcp_tokens: int = 0
    non_mcp_share_pct: float = 0.0
    servers: dict[str, ServerReport] = field(default_factory=dict)
    top_optimizations: list[WasteFinding] = field(default_factory=list)
    total_recoverable_tokens: int = 0
    total_recoverable_pct: float = 0.0
    schema_tokens_wasted: int = 0  # Schema cost is per-turn overhead, separate from result waste
    total_results: int = 0


def build_report(
    session: SessionData,
    findings: list[WasteFinding],
    server_mapping: dict[str, str] | None = None,
) -> AuditReport:
    """Build an AuditReport from session data and waste findings."""
    # Count tokens per server
    server_tokens: dict[str, int] = {}
    server_calls: dict[str, int] = {}
    server_tools: dict[str, set[str]] = {}

    total_tokens = 0

    for r in session.tool_results:
        server = attribute_tool(r.tool_name, server_mapping)
        tc = count_tokens(r.result_text)
        tokens = tc.tokens_cl100k
        total_tokens += tokens

        server_tokens[server] = server_tokens.get(server, 0) + tokens
        server_calls[server] = server_calls.get(server, 0) + 1
        server_tools.setdefault(server, set()).add(r.tool_name)

    # Separate MCP vs non-MCP
    mcp_tokens = sum(v for k, v in server_tokens.items() if k != "non-mcp")
    non_mcp_tokens = server_tokens.get("non-mcp", 0)
    mcp_share_pct = (mcp_tokens / total_tokens * 100) if total_tokens > 0 else 0
    non_mcp_share_pct = (non_mcp_tokens / total_tokens * 100) if total_tokens > 0 else 0

    # Build server reports
    reports: dict[str, ServerReport] = {}
    for server in server_tokens:
        if server == "non-mcp":
            continue

        server_findings = [f for f in findings if f.server == server]
        recoverable = sum(f.tokens_wasted for f in server_findings)

        reports[server] = ServerReport(
            server=server,
            token_share=server_tokens[server],
            token_share_pct=(server_tokens[server] / total_tokens * 100) if total_tokens > 0 else 0,
            call_count=server_calls[server],
            tools=sorted(server_tools[server]),
            findings=sorted(server_findings, key=lambda f: -f.tokens_wasted),
            estimated_recoverable_tokens=recoverable,
        )

    # Top optimizations across all servers (exclude schema — it's a different cost dimension)
    result_findings = [f for f in findings if f.waste_type != "schema"]
    all_findings_sorted = sorted(result_findings, key=lambda f: -f.tokens_wasted)
    top = all_findings_sorted[:5]

    # Schema waste is per-turn overhead, tracked separately
    schema_tokens_wasted = sum(f.tokens_wasted for f in findings if f.waste_type == "schema")

    # Result waste only (not schema) for the recoverable percentage
    total_recoverable = sum(f.tokens_wasted for f in result_findings)
    total_recoverable_pct = (total_recoverable / total_tokens * 100) if total_tokens > 0 else 0

    return AuditReport(
        session=session.session_id,
        source=session.source,
        total_tokens=total_tokens,
        mcp_tokens=mcp_tokens,
        mcp_share_pct=mcp_share_pct,
        non_mcp_tokens=non_mcp_tokens,
        non_mcp_share_pct=non_mcp_share_pct,
        servers=reports,
        top_optimizations=top,
        total_recoverable_tokens=total_recoverable,
        total_recoverable_pct=total_recoverable_pct,
        schema_tokens_wasted=schema_tokens_wasted,
        total_results=len(session.tool_results),
    )


def format_report_text(report: AuditReport) -> str:
    """Format audit report as human-readable text."""
    lines = []
    lines.append("=" * 80)
    lines.append("MCP TOKEN AUDIT REPORT")
    lines.append(f"Session: {report.source} ({report.session}), "
                 f"{report.total_results:,} tool results")
    lines.append("=" * 80)
    lines.append("")

    # Overview
    lines.append("OVERVIEW")
    lines.append("-" * 60)
    lines.append(f"  Total tool result tokens:    {report.total_tokens:>10,} (cl100k estimate)")
    lines.append(f"  MCP server share:            {report.mcp_tokens:>10,} ({report.mcp_share_pct:.1f}%)")
    lines.append(f"  Non-MCP share:               {report.non_mcp_tokens:>10,} ({report.non_mcp_share_pct:.1f}%)")
    lines.append(f"  Result waste detected:       {report.total_recoverable_tokens:>10,} "
                 f"({report.total_recoverable_pct:.1f}% of result tokens)")
    if report.schema_tokens_wasted > 0:
        lines.append(f"  Schema overhead (est.):     {report.schema_tokens_wasted:>10,} "
                     f"(per-turn cost x turns)")
    lines.append("")

    # Per-server report cards
    lines.append("PER-SERVER REPORT CARDS")
    lines.append("-" * 60)
    lines.append("")

    for summary in _build_server_summaries(report):
        lines.append(f"--- {summary['name']} " + "-" * (50 - len(summary['name'])))
        lines.append(f"  Token share:   {summary['token_share']:>10,} ({summary['token_share_pct']:.1f}%)")
        lines.append(f"  Calls:        {summary['call_count']:>10,}")
        lines.append(f"  Tools:        {', '.join(summary['tools'][:5])}"
                     + (" ..." if len(summary['tools']) > 5 else ""))
        lines.append("")

        if summary['findings']:
            lines.append("  Waste findings:")
            for f in summary['findings']:
                sev = f.severity.upper()
                lines.append(f"    [{sev:>8}]  {f.waste_type}")
                lines.append(f"      {f.description}")
                lines.append(f"      Wasted: {f.tokens_wasted:,} tokens")
                lines.append(f"      Suggestion: {f.suggestion}")
                lines.append(f"      Est. savings: {f.estimated_savings_pct:.0f}%")
                lines.append("")
        else:
            lines.append("  No waste detected.")
            lines.append("")

        if summary['estimated_recoverable_tokens'] > 0:
            lines.append(f"  Estimated recoverable: {summary['estimated_recoverable_tokens']:,} tokens "
                         f"({summary['estimated_recoverable_tokens'] / max(1, summary['token_share']) * 100:.0f}% "
                         f"of server share)")
            lines.append("")

    # Summary
    lines.append("=" * 80)
    lines.append("SUMMARY")
    lines.append("=" * 80)
    lines.append("")

    if report.top_optimizations:
        lines.append("Top optimizations by impact:")
        lines.append("")
        for i, f in enumerate(report.top_optimizations, 1):
            pct = (f.tokens_wasted / max(1, report.total_tokens)) * 100
            lines.append(f"  {i}. {f.server}: {f.waste_type} "
                         f"est. {f.tokens_wasted:,} tokens saved ({pct:.1f}%)")
        lines.append("")

    lines.append(f"Total estimated recoverable: {report.total_recoverable_tokens:,} tokens "
                 f"({report.total_recoverable_pct:.1f}% of total)")

    return "\n".join(lines)


def format_report_json(report: AuditReport) -> str:
    """Format audit report as JSON."""
    data = {
        "session": report.session,
        "source": report.source,
        "total_tokens": report.total_tokens,
        "mcp_tokens": report.mcp_tokens,
        "mcp_share_pct": round(report.mcp_share_pct, 1),
        "non_mcp_tokens": report.non_mcp_tokens,
        "total_results": report.total_results,
        "servers": {},
        "top_optimizations": [],
        "total_recoverable_tokens": report.total_recoverable_tokens,
        "total_recoverable_pct": round(report.total_recoverable_pct, 1),
        "schema_tokens_wasted": report.schema_tokens_wasted,
    }

    for server_name, sr in report.servers.items():
        data["servers"][server_name] = {
            "token_share": sr.token_share,
            "token_share_pct": round(sr.token_share_pct, 1),
            "call_count": sr.call_count,
            "tools": sr.tools,
            "findings": [
                {
                    "waste_type": f.waste_type,
                    "severity": f.severity,
                    "tokens_wasted": f.tokens_wasted,
                    "call_count": f.call_count,
                    "total_calls": f.total_calls,
                    "description": f.description,
                    "suggestion": f.suggestion,
                    "estimated_savings_pct": f.estimated_savings_pct,
                }
                for f in sr.findings
            ],
            "estimated_recoverable_tokens": sr.estimated_recoverable_tokens,
        }

    for f in report.top_optimizations:
        data["top_optimizations"].append({
            "server": f.server,
            "waste_type": f.waste_type,
            "severity": f.severity,
            "tokens_wasted": f.tokens_wasted,
            "suggestion": f.suggestion,
            "estimated_savings_pct": f.estimated_savings_pct,
        })

    return json.dumps(data, indent=2)


def format_report_markdown(report: AuditReport) -> str:
    """Format audit report as Markdown."""
    lines = []
    lines.append(f"# MCP Token Audit Report — {report.source} ({report.session})")
    lines.append("")

    # Overview table
    lines.append("## Overview")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Total tool result tokens | {report.total_tokens:,} |")
    lines.append(f"| MCP server share | {report.mcp_tokens:,} ({report.mcp_share_pct:.1f}%) |")
    lines.append(f"| Non-MCP share | {report.non_mcp_tokens:,} ({report.non_mcp_share_pct:.1f}%) |")
    lines.append(
        f"| Result waste detected | {report.total_recoverable_tokens:,}"
        f" ({report.total_recoverable_pct:.1f}%) |"
    )
    if report.schema_tokens_wasted > 0:
        lines.append(f"| Schema overhead (est.) | {report.schema_tokens_wasted:,} (per-turn x turns) |")
    lines.append("")

    # Per-server tables
    lines.append("## Per-Server Report Cards")
    lines.append("")

    for summary in _build_server_summaries(report):
        lines.append(f"### {summary['name']}")
        lines.append("")
        lines.append(f"- **Token share**: {summary['token_share']:,} ({summary['token_share_pct']:.1f}%)")
        lines.append(f"- **Calls**: {summary['call_count']:,}")
        lines.append(f"- **Tools**: {', '.join(summary['tools'][:8])}")
        lines.append(f"- **Estimated recoverable**: {summary['estimated_recoverable_tokens']:,} tokens")
        lines.append("")

        if summary['findings']:
            lines.append("| Severity | Type | Description | Tokens wasted | Savings % |")
            lines.append("|----------|------|-------------|--------------|-----------|")
            for f in summary['findings']:
                lines.append(f"| {f.severity} | {f.waste_type} | {f.description} | "
                             f"{f.tokens_wasted:,} | {f.estimated_savings_pct:.0f}% |")
            lines.append("")

    # Summary
    lines.append("## Summary")
    lines.append("")
    if report.top_optimizations:
        lines.append("Top optimizations by impact:")
        lines.append("")
        for i, f in enumerate(report.top_optimizations, 1):
            pct = (f.tokens_wasted / max(1, report.total_tokens)) * 100
            lines.append(f"{i}. **{f.server}**: {f.waste_type} — "
                         f"est. {f.tokens_wasted:,} tokens saved ({pct:.1f}%)")
        lines.append("")

    lines.append(f"**Total recoverable**: {report.total_recoverable_tokens:,} tokens "
                 f"({report.total_recoverable_pct:.1f}% of total)")

    return "\n".join(lines)
