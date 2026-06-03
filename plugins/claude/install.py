#!/usr/bin/env python3
"""
archolith-audit installer for Claude Code.

Wires the MCP server and PostToolUse hook into your Claude Code config so the
audit plugin starts observing tool calls automatically.

Usage:
    python install.py              # global install (~/.claude/)
    python install.py --project /path/to/project  # project-level install
    python install.py --uninstall  # remove from global config
    python install.py --uninstall --project /path/to/project

No pip install needed — archolith_mcp_audit/ is bundled in this directory.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PLUGIN_NAME = "archolith-audit"
HOOK_MARKER = "hook_observer.py"  # used to detect existing hook entries


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def _read_json(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            print(f"  WARNING: could not read {path} ({exc}) — will overwrite")
    return {}


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Install
# ---------------------------------------------------------------------------

def install_mcp(mcp_path: Path, plugin_dir: Path) -> None:
    """Merge archolith-audit MCP server entry into .mcp.json."""
    config = _read_json(mcp_path)
    config.setdefault("mcpServers", {})

    config["mcpServers"][PLUGIN_NAME] = {
        "command": "python",
        "args": ["-m", "archolith_mcp_audit.mcp_server"],
        "env": {
            "MCP_AUDIT_ENABLED": "1",
            "PYTHONPATH": str(plugin_dir),
        },
    }

    _write_json(mcp_path, config)
    print(f"  [MCP]   {mcp_path}")


def install_hook(settings_path: Path, plugin_dir: Path) -> None:
    """Merge PostToolUse hook entry into settings.json."""
    config = _read_json(settings_path)
    config.setdefault("hooks", {})
    config["hooks"].setdefault("PostToolUse", [])

    hook_script = plugin_dir / "hook_observer.py"
    hook_command = f'python "{hook_script}" ${{CLAUDE_SESSION_ID}}'

    # Skip if already present (check by hook_observer.py path)
    for entry in config["hooks"]["PostToolUse"]:
        for h in entry.get("hooks", []):
            if str(hook_script) in h.get("command", ""):
                print(f"  [HOOK]  already present in {settings_path}")
                return

    config["hooks"]["PostToolUse"].append(
        {
            "matcher": ".*",
            "hooks": [
                {
                    "type": "command",
                    "command": hook_command,
                    "async": True,
                }
            ],
        }
    )

    _write_json(settings_path, config)
    print(f"  [HOOK]  {settings_path}")


# ---------------------------------------------------------------------------
# Uninstall
# ---------------------------------------------------------------------------

def uninstall_mcp(mcp_path: Path) -> None:
    """Remove archolith-audit MCP entry from .mcp.json."""
    if not mcp_path.exists():
        print(f"  [MCP]   not found: {mcp_path}")
        return
    config = _read_json(mcp_path)
    servers = config.get("mcpServers", {})
    if PLUGIN_NAME in servers:
        del servers[PLUGIN_NAME]
        _write_json(mcp_path, config)
        print(f"  [MCP]   removed from {mcp_path}")
    else:
        print(f"  [MCP]   {PLUGIN_NAME} not found in {mcp_path}")


def uninstall_hook(settings_path: Path) -> None:
    """Remove archolith-audit hook entry from settings.json."""
    if not settings_path.exists():
        print(f"  [HOOK]  not found: {settings_path}")
        return
    config = _read_json(settings_path)
    entries = config.get("hooks", {}).get("PostToolUse", [])
    filtered = [
        e for e in entries
        if not any(HOOK_MARKER in h.get("command", "") for h in e.get("hooks", []))
    ]
    if len(filtered) < len(entries):
        config["hooks"]["PostToolUse"] = filtered
        _write_json(settings_path, config)
        print(f"  [HOOK]  removed from {settings_path}")
    else:
        print(f"  [HOOK]  no archolith-audit hook found in {settings_path}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description=f"Install or uninstall the {PLUGIN_NAME} Claude Code plugin.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python install.py                       # global install
  python install.py --project /my/repo    # project-level install
  python install.py --uninstall           # remove global install
        """,
    )
    parser.add_argument(
        "--project",
        metavar="DIR",
        help="Project root for project-level install. Default: global (~/.claude/)",
    )
    parser.add_argument(
        "--uninstall",
        action="store_true",
        help="Remove the plugin from the target location.",
    )
    args = parser.parse_args()

    plugin_dir = Path(__file__).parent.resolve()

    # Resolve config file paths
    if args.project:
        project_root = Path(args.project).resolve()
        if not project_root.is_dir():
            print(f"ERROR: --project directory does not exist: {project_root}")
            sys.exit(1)
        mcp_path = project_root / ".mcp.json"
        # Claude Code project settings live in <project>/.claude/settings.json
        settings_path = project_root / ".claude" / "settings.json"
        scope = f"project ({project_root})"
    else:
        claude_dir = Path.home() / ".claude"
        mcp_path = claude_dir / ".mcp.json"
        settings_path = claude_dir / "settings.json"
        scope = "global (~/.claude/)"

    if args.uninstall:
        print(f"Uninstalling {PLUGIN_NAME} [{scope}]")
        uninstall_mcp(mcp_path)
        uninstall_hook(settings_path)
        print("\nDone. Restart Claude Code.")
        return

    # Install — verify bundle is present first
    pkg = plugin_dir / "archolith_mcp_audit"
    if not pkg.exists():
        print(f"ERROR: archolith_mcp_audit/ package not found at {plugin_dir}")
        print("")
        print("This installer expects the bundled package to be in the same directory.")
        print("If you cloned the source repo, run:")
        print("  python scripts/release.py sync claude")
        print("Or download the distribution archive from GitHub Releases.")
        sys.exit(1)

    print(f"Installing {PLUGIN_NAME} [{scope}]")
    install_mcp(mcp_path, plugin_dir)
    install_hook(settings_path, plugin_dir)
    print("")
    print("Installed. Restart Claude Code to activate.")
    print("")
    print("After restarting, start a session and do some work, then ask:")
    print('  "show me the MCP audit summary"')
    print("")
    print("Or call directly:")
    print("  mcp_audit_summary")


if __name__ == "__main__":
    main()
