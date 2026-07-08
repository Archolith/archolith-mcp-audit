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


def test_cli_help_shows_skree() -> None:
    """Verifies the CLI help text mentions Archolith Skree."""
    proc = subprocess.run(
        [sys.executable, "-m", "archolith_mcp_audit", "--help"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    assert proc.returncode == 0
    assert "Archolith Skree" in proc.stdout


def test_skree_alias_registered() -> None:
    """Verifies the skree entry point is importable and runs."""
    result = subprocess.run(
        [sys.executable, "-c", "from archolith_mcp_audit.cli import main; exit(main(['--help']))"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0
    assert "Archolith Skree" in result.stdout
