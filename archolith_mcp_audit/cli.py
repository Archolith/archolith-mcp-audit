"""CLI entry point for archolith-mcp-audit."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from archolith_mcp_audit.attributor import _load_mapping
from archolith_mcp_audit.report import (
    AuditReport,
    build_report,
    format_report_json,
    format_report_markdown,
    format_report_text,
)
from archolith_mcp_audit.waste_detector import detect_waste


def _resolve_sources(args: argparse.Namespace) -> list[tuple[str, str]]:
    """Resolve session sources from CLI args. Returns [(source_type, path), ...]."""
    sources = []

    if args.claude:
        for p in args.claude:
            sources.append(("claude", p))

    if args.codex:
        for p in args.codex:
            sources.append(("codex", p))

    if args.opencode:
        sources.append(("opencode", args.opencode))

    if args.all:
        claude_dir = Path(r"C:\Users\thron\.claude\projects\C--Users-thron-IdeaProjects")
        codex_dir = Path(r"C:\Users\thron\.codex\sessions")
        opencode_db = Path(r"C:\Users\thron\.local\share\opencode\opencode.db")

        if claude_dir.exists():
            for p in sorted(claude_dir.glob("*.jsonl")):
                sources.append(("claude", str(p)))

        if codex_dir.exists():
            for p in sorted(codex_dir.rglob("*.jsonl")):
                sources.append(("codex", str(p)))

        if opencode_db.exists():
            sources.append(("opencode", str(opencode_db)))

    return sources


def _run_audit(
    source_type: str,
    source_path: str,
    server_mapping: dict[str, str] | None,
    max_results: int | None = None,
    opencode_session: str | None = None,
) -> AuditReport:
    """Run full audit pipeline on a single session."""
    # Import extractors lazily (tiktoken may not be installed in all envs)
    if source_type == "claude":
        from archolith_mcp_audit.extractors.claude import extract_session
        session = extract_session(source_path, max_results=max_results)
    elif source_type == "codex":
        from archolith_mcp_audit.extractors.codex import extract_session
        session = extract_session(source_path, max_results=max_results)
    elif source_type == "opencode":
        from archolith_mcp_audit.extractors.opencode import extract_session
        session = extract_session(
            source_path, session_id=opencode_session, limit=max_results or 5000
        )
    else:
        raise ValueError(f"Unknown source type: {source_type}")

    findings = detect_waste(session, server_mapping)
    return build_report(session, findings, server_mapping)


def main(argv: list[str] | None = None) -> int:
    """Main CLI entry point. Returns exit code."""
    parser = argparse.ArgumentParser(
        description="MCP Token Usage Audit — measure and report per-server token waste"
    )
    parser.add_argument("--claude", nargs="*", help="Claude JSONL session files")
    parser.add_argument("--codex", nargs="*", help="Codex JSONL session files")
    parser.add_argument("--opencode", help="OpenCode SQLite database path")
    parser.add_argument("--opencode-session", help="Specific OpenCode session ID")
    parser.add_argument("--all", action="store_true", help="Audit all available sessions")
    parser.add_argument("--format", choices=["report", "json", "markdown"], default="report",
                        help="Output format (default: report)")
    parser.add_argument("--servers", help="Comma-separated server filter (e.g., gradle,vps)")
    parser.add_argument("--min-severity", choices=["low", "medium", "high", "critical"],
                        help="Minimum severity threshold")
    parser.add_argument("--max-results", type=int, help="Max tool results per session")
    parser.add_argument("--compare", nargs=2, metavar=("BEFORE", "AFTER"),
                        help="Compare two JSON audit reports")
    args = parser.parse_args(argv)

    # Load server mapping
    server_mapping = _load_mapping()

    # Comparison mode
    if args.compare:
        before_path, after_path = args.compare
        with open(before_path, encoding="utf-8") as f:
            before = json.load(f)
        with open(after_path, encoding="utf-8") as f:
            after = json.load(f)
        _print_comparison(before, after)
        return 0

    sources = _resolve_sources(args)
    if not sources:
        parser.error("No session sources specified. Use --claude, --codex, --opencode, or --all")

    all_reports: list[AuditReport] = []

    for source_type, source_path in sources:
        try:
            report = _run_audit(
                source_type, source_path, server_mapping,
                max_results=args.max_results,
                opencode_session=args.opencode_session,
            )
        except Exception as e:
            print(f"Error processing {source_path}: {e}", file=sys.stderr)
            continue

        # Filter by server
        if args.servers:
            allowed = set(args.servers.split(","))
            report.servers = {k: v for k, v in report.servers.items() if k in allowed}

        # Filter by severity
        if args.min_severity:
            sev_order = {"low": 0, "medium": 1, "high": 2, "critical": 3}
            min_sev = sev_order[args.min_severity]
            for sr in report.servers.values():
                sr.findings = [f for f in sr.findings if sev_order.get(f.severity, 0) >= min_sev]
            report.top_optimizations = [f for f in report.top_optimizations
                                        if sev_order.get(f.severity, 0) >= min_sev]

        all_reports.append(report)

    # Output
    for report in all_reports:
        if args.format == "report":
            print(format_report_text(report))
        elif args.format == "json":
            print(format_report_json(report))
        elif args.format == "markdown":
            print(format_report_markdown(report))

    # Exit code: 2 if critical waste detected
    has_critical = any(
        any(f.severity == "critical" for sr in report.servers.values() for f in sr.findings)
        for report in all_reports
    )
    return 2 if has_critical else 0


def _print_comparison(before: dict, after: dict) -> None:
    """Print a delta report comparing two JSON audit reports."""
    print("MCP AUDIT COMPARISON")
    print("=" * 60)

    for server in set(list(before.get("servers", {}).keys()) + list(after.get("servers", {}).keys())):
        b = before.get("servers", {}).get(server, {})
        a = after.get("servers", {}).get(server, {})

        b_tokens = b.get("token_share", 0)
        a_tokens = a.get("token_share", 0)
        b_waste = sum(f.get("tokens_wasted", 0) for f in b.get("findings", []))
        a_waste = sum(f.get("tokens_wasted", 0) for f in a.get("findings", []))

        token_change = a_tokens - b_tokens
        waste_change = a_waste - b_waste

        print(f"\n--- {server} ---")
        print(f"Before: {b.get('call_count', 0)} calls, {b_tokens:,} tokens, {b_waste:,} wasted")
        print(f"After:  {a.get('call_count', 0)} calls, {a_tokens:,} tokens, {a_waste:,} wasted")

        if b_tokens > 0:
            print(f"Change: {token_change:+,} tokens ({token_change / b_tokens * 100:+.1f}%), "
                  f"{waste_change:+,} waste")
        else:
            print(f"Change: {token_change:+,} tokens, {waste_change:+,} waste")

        # Regression detection
        a_types = {f.get("waste_type") for f in a.get("findings", [])}
        b_types = {f.get("waste_type") for f in b.get("findings", [])}
        new_waste = a_types - b_types
        if new_waste:
            print(f"  WARNING: New waste types introduced: {', '.join(new_waste)}")

        if waste_change < 0:
            print("  Status: Optimization effective")
        elif waste_change > 0:
            print("  Status: REGRESSION — waste increased")
        else:
            print("  Status: No change")


if __name__ == "__main__":
    sys.exit(main())
