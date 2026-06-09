"""CI integration — threshold-based exit codes for preventing MCP regressions.

Checks audit reports against configurable thresholds and exits with
code 2 if any threshold is exceeded. Designed for CI pipelines.
"""

from __future__ import annotations

from archolith_mcp_audit.report import AuditReport

__all__ = [
    "check_thresholds",
    "run_ci_check",
]


def check_thresholds(
    report: AuditReport,
    max_server_share: float = 20.0,
    max_total_mcp_share: float = 40.0,
    max_waste_pct: float = 50.0,
) -> tuple[bool, list[str]]:
    """Check report against CI thresholds.

    Returns (passed, messages) where passed is True if all thresholds OK.
    """
    messages: list[str] = []
    passed = True

    # Check per-server share
    for server_name, sr in report.servers.items():
        if sr.token_share_pct > max_server_share:
            messages.append(
                f"FAIL: {server_name} exceeds {max_server_share:.0f}% server share "
                f"({sr.token_share_pct:.1f}%)"
            )
            passed = False
        else:
            messages.append(
                f"OK: {server_name} within {max_server_share:.0f}% share "
                f"({sr.token_share_pct:.1f}%)"
            )

    # Check total MCP share
    if report.mcp_share_pct > max_total_mcp_share:
        messages.append(
            f"FAIL: Total MCP share exceeds {max_total_mcp_share:.0f}% "
            f"({report.mcp_share_pct:.1f}%)"
        )
        passed = False
    else:
        messages.append(
            f"OK: Total MCP share within {max_total_mcp_share:.0f}% "
            f"({report.mcp_share_pct:.1f}%)"
        )

    # Check waste percentage per server
    for server_name, sr in report.servers.items():
        if sr.token_share > 0 and sr.estimated_recoverable_tokens > 0:
            waste_pct = sr.estimated_recoverable_tokens / sr.token_share * 100
            if waste_pct > max_waste_pct:
                messages.append(
                    f"FAIL: {server_name} waste exceeds {max_waste_pct:.0f}% "
                    f"of server tokens ({waste_pct:.1f}%)"
                )
                passed = False
            else:
                messages.append(
                    f"OK: {server_name} waste within {max_waste_pct:.0f}% "
                    f"({waste_pct:.1f}%)"
                )

    return passed, messages


def run_ci_check(
    report: AuditReport,
    max_server_share: float = 20.0,
    max_total_mcp_share: float = 40.0,
    max_waste_pct: float = 50.0,
) -> int:
    """Run CI threshold check and return exit code.

    Returns 0 if all thresholds pass, 2 if any threshold fails.
    """
    passed, messages = check_thresholds(
        report,
        max_server_share=max_server_share,
        max_total_mcp_share=max_total_mcp_share,
        max_waste_pct=max_waste_pct,
    )

    for msg in messages:
        print(msg)

    if passed:
        print("\nCI CHECK: PASS")
        return 0
    else:
        print("\nCI CHECK: FAIL")
        return 2
