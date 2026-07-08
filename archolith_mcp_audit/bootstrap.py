"""Runtime bootstrap for bundled archolith-audit plugins.

Agent plugin systems can load a bundled Python package from a plugin directory,
but they do not reliably install Python dependencies. This module is stdlib-only
so it can create an isolated runtime before starting the real MCP server.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
import sys
import venv
from pathlib import Path

DEFAULT_AGENT = "agent"
MARKER_FILE = ".archolith-requirements.sha256"


def _plugin_root() -> Path:
    """Return the root of the bundled plugin directory."""
    return Path(__file__).resolve().parents[1]


def _runtime_dir(agent: str) -> Path:
    python_tag = f"py{sys.version_info.major}{sys.version_info.minor}"
    safe_agent = "".join(c if c.isalnum() or c in ("-", "_") else "-" for c in agent)
    return Path.home() / ".archolith" / "venvs" / f"{safe_agent}-{python_tag}"


def _venv_python(runtime_dir: Path) -> Path:
    if os.name == "nt":
        return runtime_dir / "Scripts" / "python.exe"
    return runtime_dir / "bin" / "python"


def _requirements_hash(requirements: Path) -> str:
    return hashlib.sha256(requirements.read_bytes()).hexdigest()


def _run_pip(python: Path, requirements: Path) -> None:
    cmd = [
        str(python),
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "-r",
        str(requirements),
    ]
    subprocess.run(cmd, check=True, stdout=sys.stderr, stderr=sys.stderr)


def ensure_runtime(agent: str = DEFAULT_AGENT, plugin_root: Path | None = None) -> Path:
    """Create/update the per-agent venv and return its Python executable."""
    root = plugin_root or _plugin_root()
    requirements = root / "requirements.txt"
    if not requirements.exists():
        print(f"archolith-audit: missing requirements.txt at {requirements}", file=sys.stderr)
        raise SystemExit(1)

    runtime = _runtime_dir(agent)
    python = _venv_python(runtime)
    if not python.exists():
        runtime.parent.mkdir(parents=True, exist_ok=True)
        print(f"archolith-audit: creating runtime {runtime}", file=sys.stderr)
        venv.EnvBuilder(with_pip=True).create(runtime)

    expected = _requirements_hash(requirements)
    marker = runtime / MARKER_FILE
    current = marker.read_text(encoding="utf-8").strip() if marker.exists() else ""
    if current != expected:
        print(f"archolith-audit: installing runtime dependencies from {requirements}", file=sys.stderr)
        try:
            _run_pip(python, requirements)
        except subprocess.CalledProcessError as exc:
            print(
                "archolith-audit: dependency install failed. "
                f"Retry manually with: {python} -m pip install -r {requirements}",
                file=sys.stderr,
            )
            raise SystemExit(exc.returncode) from exc
        marker.write_text(expected + "\n", encoding="utf-8")

    return python


def _exec_mcp(agent: str) -> None:
    root = _plugin_root()
    python = ensure_runtime(agent=agent, plugin_root=root)
    env = os.environ.copy()
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(root) if not existing else str(root) + os.pathsep + existing
    os.execve(str(python), [str(python), "-m", "archolith_mcp_audit.mcp_server"], env)


def _check(agent: str) -> None:
    root = _plugin_root()
    python = ensure_runtime(agent=agent, plugin_root=root)
    env = os.environ.copy()
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(root) if not existing else str(root) + os.pathsep + existing
    subprocess.run(
        [
            str(python),
            "-c",
            "import fastmcp, archolith_mcp_audit; print('archolith-audit runtime ok')",
        ],
        check=True,
        env=env,
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="archolith-audit plugin runtime bootstrap")
    parser.add_argument("command", choices=["mcp", "check"], help="Action to run")
    parser.add_argument("--agent", default=DEFAULT_AGENT, help="Agent/runtime name")
    args = parser.parse_args(argv)

    if args.command == "mcp":
        _exec_mcp(args.agent)
    else:
        _check(args.agent)


if __name__ == "__main__":
    main()
