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
    parser.add_argument("--refresh-schemas", action="store_true",
                        help="Refresh MCP tool schema catalog")
    parser.add_argument("--ci", action="store_true",
                        help="CI mode: exit 2 if thresholds exceeded")
    parser.add_argument("--max-server-share", type=float, default=20.0,
                        help="CI: max per-server token share %% (default: 20)")
    parser.add_argument("--max-total-mcp-share", type=float, default=40.0,
                        help="CI: max total MCP share %% (default: 40)")
    parser.add_argument("--max-waste-pct", type=float, default=50.0,
                        help="CI: max waste %% per server (default: 50)")
    args = parser.parse_args(argv)

    # Load server mapping
    server_mapping = _load_mapping()

    # Schema refresh mode
    if args.refresh_schemas:
        from archolith_mcp_audit.schema_estimator import refresh_schema_catalog
        catalog = refresh_schema_catalog()
        servers = list(catalog.keys()) if catalog else []
        print(f"Schema catalog refreshed. {len(servers)} servers: {', '.join(servers) if servers else 'none'}")
        return 0

    # Comparison mode
    if args.compare:
        from archolith_mcp_audit.comparator import compare_reports, format_delta_report
        before_path, after_path = args.compare
        with open(before_path, encoding="utf-8") as f:
            before = json.load(f)
        with open(after_path, encoding="utf-8") as f:
            after = json.load(f)
        deltas = compare_reports(before, after)
        print(format_delta_report(deltas, after=after))
        # Exit 2 if any server regressed
        has_regression = any(d.status == "regressed" for d in deltas)
        return 2 if has_regression else 0

    sources = _resolve_sources(args)
    if not sources:
        parser.error("No session sources specified. Use --claude, --codex, --opencode, or --all")

    all_reports: list[AuditReport] = []
    had_error = False

    for source_type, source_path in sources:
        try:
            report = _run_audit(
                source_type, source_path, server_mapping,
                max_results=args.max_results,
                opencode_session=args.opencode_session,
            )
        except Exception as e:
            print(f"Error processing {source_path}: {e}", file=sys.stderr)
            had_error = True
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
        if args.ci:
            # CI mode: run threshold checks instead of report
            from archolith_mcp_audit.ci import run_ci_check
            return run_ci_check(
                report,
                max_server_share=args.max_server_share,
                max_total_mcp_share=args.max_total_mcp_share,
                max_waste_pct=args.max_waste_pct,
            )

        if args.format == "report":
            print(format_report_text(report))
        elif args.format == "json":
            print(format_report_json(report))
        elif args.format == "markdown":
            print(format_report_markdown(report))

    # Exit codes: 0=success, 1=error, 2=critical waste detected
    if had_error and not all_reports:
        return 1  # All sources failed
    has_critical = any(
        any(f.severity == "critical" for sr in report.servers.values() for f in sr.findings)
        for report in all_reports
    )
    if has_critical:
        return 2
    if had_error:
        return 1  # Some sources failed but we produced partial output
    return 0


if __name__ == "__main__":
    sys.exit(main())
