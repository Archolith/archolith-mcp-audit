from __future__ import annotations

import subprocess
import sys


def test_cli_imports() -> None:
    from archolith_mcp_audit import cli

    assert hasattr(cli, "main")


def test_cli_help_runs() -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "archolith_mcp_audit", "--help"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    assert proc.returncode == 0
    assert "usage:" in proc.stdout.lower() or "usage:" in proc.stderr.lower()
