#!/usr/bin/env python3
"""
archolith-audit installation script.

Installs the PostToolUse hook observer and enables the MCP server for a
given agent. Idempotent — safe to re-run.

Usage:
    python scripts/install.py claude       # Claude Code (global settings)
    python scripts/install.py codex        # Codex (hooks.json)
    python scripts/install.py opencode     # OpenCode (npm plugin)
    python scripts/install.py gemini       # Gemini CLI (extension.json)
    python scripts/install.py --check      # Print current install status for all agents
    python scripts/install.py --uninstall claude  # Remove hook entry

Supported agents: claude, codex, opencode, gemini
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import sys
from pathlib import Path

# Force UTF-8 output on Windows (checkmarks / cross symbols)
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout.reconfigure(encoding="utf-8")

OK = "[OK]"
FAIL = "[--]"

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

HOME = Path.home()
IS_WINDOWS = platform.system() == "Windows"

# archolith-audit package root (this script lives in scripts/)
PKG_ROOT = Path(__file__).parent.parent.resolve()
HOOK_SRC = PKG_ROOT / "archolith_mcp_audit" / "hook_observer_standalone.py"

# archolith telemetry directory
SESSIONS_DIR = HOME / ".archolith" / "sessions"

# Agent config locations
CLAUDE_SETTINGS = HOME / ".claude" / "settings.json"
CLAUDE_HOOKS_DIR = HOME / ".claude" / "hooks"
CLAUDE_MCP_JSON = HOME / ".claude" / "claude_desktop_config.json"  # fallback
CODEX_HOOKS_JSON = HOME / ".codex" / "hooks.json"
GEMINI_EXTENSIONS_DIR = HOME / ".gemini" / "extensions" / "archolith-audit"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _confirm(prompt: str, default: bool = False) -> bool:
    """Ask yes/no question. Returns True if user confirms."""
    suffix = " [Y/n]: " if default else " [y/N]: "
    try:
        answer = input(prompt + suffix).strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    if not answer:
        return default
    return answer in ("y", "yes")


def _posix_path(p: Path) -> str:
    """Convert Windows path to POSIX for use in Claude Code command strings."""
    s = p.as_posix()
    if IS_WINDOWS and len(s) > 2 and s[1] == ":":
        drive = s[0].lower()
        return f"/c{s[2:]}" if drive == "c" else f"/{drive}{s[2:]}"
    return s


def _python_exe() -> str:
    """Return the path to the current Python interpreter, POSIX-style."""
    return _posix_path(Path(sys.executable))


def _load_json(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print(f"  WARNING: {path} contains invalid JSON — treating as empty.")
    return {}


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"  Written: {path}")


def _copy_hook_shim(dest: Path) -> None:
    """Copy the standalone hook observer to the target location."""
    if not HOOK_SRC.exists():
        # Fall back to inline copy for the Claude Code shim (already installed)
        print(f"  NOTE: {HOOK_SRC} not found — hook shim must be installed manually.")
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(HOOK_SRC, dest)
    print(f"  Installed hook shim: {dest}")


# ---------------------------------------------------------------------------
# Claude Code
# ---------------------------------------------------------------------------

CLAUDE_HOOK_DEST = CLAUDE_HOOKS_DIR / "archolith-audit-observer.py"
CLAUDE_MCP_SERVER_KEY = "archolith-audit"
CLAUDE_MCP_SERVER_ENTRY = {
    "command": _python_exe(),
    "args": ["-m", "archolith_mcp_audit.mcp_server"],
    "cwd": str(PKG_ROOT),
    "env": {
        "PYTHONPATH": str(PKG_ROOT),
        "MCP_AUDIT_ENABLED": "1",
    },
}


def install_claude() -> None:
    print("\n=== Claude Code ===")
    print(f"  This will:")
    print(f"    1. Copy hook shim to:       {CLAUDE_HOOK_DEST}")
    print(f"    2. Add PostToolUse hook to: {CLAUDE_SETTINGS}")
    print(f"    3. Register MCP server in:  <nearest .mcp.json>")
    print()

    if not _confirm("Proceed with Claude Code installation?", default=True):
        print("  Aborted.")
        return

    _ensure_sessions_dir()
    _install_claude_hook_shim()
    _add_claude_posttooluse_hook()
    _register_claude_mcp_server()

    print("\n  IMPORTANT: Restart Claude Code or open /hooks to reload settings.")
    print("  Then run: mcp_audit_summary  (or /audit if the skill is installed)")


def _ensure_sessions_dir() -> None:
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    print(f"  Sessions dir: {SESSIONS_DIR}")


def _install_claude_hook_shim() -> None:
    """Write the standalone hook observer to ~/.claude/hooks/."""
    # Use the installed shim if present, otherwise generate inline
    if HOOK_SRC.exists():
        _copy_hook_shim(CLAUDE_HOOK_DEST)
    else:
        # Generate minimal inline version (no package imports)
        _write_inline_hook_shim(CLAUDE_HOOK_DEST)


def _write_inline_hook_shim(dest: Path) -> None:
    """Write a minimal self-contained hook shim when standalone source isn't available."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    content = (PKG_ROOT / "archolith_mcp_audit" / ".." /
               "scripts" / "_hook_shim_template.py")
    # Inline fallback
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "observer",
        PKG_ROOT / "archolith_mcp_audit" / "hook_observer.py",
    )
    # Just copy the observer module itself (it works as a script too)
    shutil.copy2(
        PKG_ROOT / "archolith_mcp_audit" / "hook_observer.py",
        dest,
    )
    print(f"  Installed hook shim (from hook_observer.py): {dest}")


def _add_claude_posttooluse_hook() -> None:
    """Add PostToolUse entry to ~/.claude/settings.json. Idempotent."""
    settings = _load_json(CLAUDE_SETTINGS)
    hooks = settings.setdefault("hooks", {})
    post_hooks = hooks.setdefault("PostToolUse", [])

    hook_command = (
        f"{_python_exe()} "
        f"{_posix_path(CLAUDE_HOOK_DEST)}"
    )

    # Check if already installed
    for entry in post_hooks:
        for h in entry.get("hooks", []):
            if "archolith-audit-observer" in h.get("command", ""):
                print(f"  PostToolUse hook already present in {CLAUDE_SETTINGS}")
                return

    post_hooks.append({
        "matcher": ".*",
        "hooks": [
            {
                "type": "command",
                "command": hook_command,
                "timeout": 5000,
            }
        ],
    })
    _write_json(CLAUDE_SETTINGS, settings)
    print(f"  Added PostToolUse hook → {hook_command}")


def _register_claude_mcp_server() -> None:
    """
    Register archolith-audit MCP server.

    Checks global .mcp.json first. If not found, writes a project-local
    .mcp.json in the archolith-mcp-audit directory.
    """
    global_mcp = HOME / ".claude" / ".mcp.json"
    workspace_mcp = Path.cwd() / ".mcp.json"

    # Check if already registered in any reachable .mcp.json
    for mcp_path in [global_mcp, workspace_mcp]:
        if mcp_path.exists():
            cfg = _load_json(mcp_path)
            servers = cfg.get("mcpServers", {})
            if CLAUDE_MCP_SERVER_KEY in servers:
                print(f"  MCP server already registered in {mcp_path}")
                return

    # Write to project-local .mcp.json
    target = PKG_ROOT / ".mcp.json"
    cfg = _load_json(target)
    cfg.setdefault("mcpServers", {})[CLAUDE_MCP_SERVER_KEY] = CLAUDE_MCP_SERVER_ENTRY
    _write_json(target, cfg)
    print(f"  Registered MCP server '{CLAUDE_MCP_SERVER_KEY}' in {target}")
    print("  NOTE: Add this .mcp.json to your workspace or merge into global .mcp.json.")


def uninstall_claude() -> None:
    print("\n=== Claude Code — Uninstall ===")
    print(f"  This will remove the PostToolUse hook entry from {CLAUDE_SETTINGS}.")
    print(f"  The hook shim file will NOT be deleted.")
    print()
    if not _confirm("Proceed with uninstall?", default=False):
        print("  Aborted.")
        return

    # Remove hook entry from settings.json
    settings = _load_json(CLAUDE_SETTINGS)
    post_hooks = settings.get("hooks", {}).get("PostToolUse", [])
    before = len(post_hooks)
    settings["hooks"]["PostToolUse"] = [
        e for e in post_hooks
        if not any("archolith-audit-observer" in h.get("command", "")
                   for h in e.get("hooks", []))
    ]
    after = len(settings["hooks"]["PostToolUse"])
    if before != after:
        _write_json(CLAUDE_SETTINGS, settings)
        print("  Removed PostToolUse hook entry.")
    else:
        print("  No PostToolUse hook entry found — nothing to remove.")

    # Leave hook shim in place (not destructive)
    print("  Hook shim left in place (delete manually if desired).")
    print("  Restart Claude Code to apply.")


# ---------------------------------------------------------------------------
# Codex
# ---------------------------------------------------------------------------

CODEX_HOOK_DEST = HOME / ".codex" / "hooks" / "archolith-audit-observer.py"


def install_codex() -> None:
    print("\n=== Codex ===")
    print(f"  This will:")
    print(f"    1. Copy hook shim to: {CODEX_HOOK_DEST}")
    print(f"    2. Add PostToolUse entry to: {CODEX_HOOKS_JSON}")
    print(f"    3. Register MCP server in: {HOME / '.codex' / 'mcp.json'}")
    print()
    if not _confirm("Proceed with Codex installation?", default=True):
        print("  Aborted.")
        return
    _ensure_sessions_dir()

    # 1. Install hook shim
    _copy_hook_shim(CODEX_HOOK_DEST)

    # 2. Register in ~/.codex/hooks.json
    hooks = _load_json(CODEX_HOOKS_JSON)
    hook_command = f"{sys.executable} {CODEX_HOOK_DEST}"

    post_hooks = hooks.setdefault("PostToolUse", [])
    if not any("archolith-audit-observer" in h.get("command", "") for h in post_hooks):
        post_hooks.append({
            "command": hook_command,
            "runInBackground": True,
        })
        _write_json(CODEX_HOOKS_JSON, hooks)
        print(f"  Added PostToolUse hook → {hook_command}")
    else:
        print("  PostToolUse hook already present.")

    # 3. Register MCP server
    codex_mcp = HOME / ".codex" / "mcp.json"
    cfg = _load_json(codex_mcp)
    if CLAUDE_MCP_SERVER_KEY not in cfg.get("mcpServers", {}):
        cfg.setdefault("mcpServers", {})[CLAUDE_MCP_SERVER_KEY] = CLAUDE_MCP_SERVER_ENTRY
        _write_json(codex_mcp, cfg)
    else:
        print("  MCP server already registered.")

    print("\n  NOTE: Verify hooks.json format against current Codex version.")
    print("  See: archolith-audit-codex-plugin-plan.md for known gaps.")


# ---------------------------------------------------------------------------
# OpenCode
# ---------------------------------------------------------------------------

def install_opencode() -> None:
    print("\n=== OpenCode ===")
    print("  OpenCode uses an npm/TypeScript plugin (@archolith/opencode-plugin).")
    print("  Status: NOT YET IMPLEMENTED.")
    print("  See: archolith-audit-opencode-plugin-plan.md")
    print("")
    print("  When ready:")
    print("    bun add @archolith/opencode-plugin  # or npm install")
    print("    # Plugin auto-registers via package.json 'opencode' key")


# ---------------------------------------------------------------------------
# Gemini CLI
# ---------------------------------------------------------------------------

def install_gemini() -> None:
    print("\n=== Gemini CLI ===")
    print("  Gemini CLI extension requires extension.json + after-tool.js.")
    print("  Status: NOT YET IMPLEMENTED.")
    print("  See: archolith-audit-gemini-plugin-plan.md (4 known gaps require verification)")
    print("")
    print("  Known gaps:")
    print("    1. Exact AfterTool payload shape not verified")
    print("    2. Session ID field name in hook context not confirmed")
    print("    3. Sync execution latency impact unknown")
    print("    4. extension.json manifest format may have changed")


# ---------------------------------------------------------------------------
# Status check
# ---------------------------------------------------------------------------

def check_status() -> None:
    print("\n=== archolith-audit Installation Status ===\n")

    # Claude Code
    settings = _load_json(CLAUDE_SETTINGS)
    post_hooks = settings.get("hooks", {}).get("PostToolUse", [])
    claude_hook = any(
        "archolith-audit-observer" in h.get("command", "")
        for entry in post_hooks for h in entry.get("hooks", [])
    )
    claude_shim = CLAUDE_HOOK_DEST.exists()

    # Check .mcp.json files for archolith-audit
    mcp_registered = False
    for mcp_path in [
        HOME / ".claude" / ".mcp.json",
        Path.cwd() / ".mcp.json",
        PKG_ROOT / ".mcp.json",
        HOME / "IdeaProjects" / ".mcp.json",
    ]:
        if mcp_path.exists():
            cfg = _load_json(mcp_path)
            if CLAUDE_MCP_SERVER_KEY in cfg.get("mcpServers", {}):
                mcp_env = cfg["mcpServers"][CLAUDE_MCP_SERVER_KEY].get("env", {})
                mcp_enabled = mcp_env.get("MCP_AUDIT_ENABLED") == "1"
                mcp_registered = True
                break

    print(f"  Claude Code:")
    print(f"    Hook shim installed:   {OK if claude_shim else FAIL}  {CLAUDE_HOOK_DEST}")
    print(f"    PostToolUse hook:      {OK if claude_hook else FAIL}  {CLAUDE_SETTINGS}")
    print(f"    MCP server registered: {OK if mcp_registered else FAIL}")
    if mcp_registered:
        print(f"    MCP_AUDIT_ENABLED:     {f"{OK if mcp_enabled else FAIL + '  (set MCP_AUDIT_ENABLED=1)'}"}")

    # Codex
    codex_cfg = _load_json(CODEX_HOOKS_JSON)
    codex_hook = any(
        "archolith-audit-observer" in h.get("command", "")
        for h in codex_cfg.get("PostToolUse", [])
    )
    print(f"\n  Codex:")
    print(f"    Hook shim installed:   {OK if CODEX_HOOK_DEST.exists() else FAIL}  {CODEX_HOOK_DEST}")
    print(f"    hooks.json entry:      {OK if codex_hook else FAIL}  {CODEX_HOOKS_JSON}")

    # OpenCode / Gemini
    print(f"\n  OpenCode:              NOT IMPLEMENTED")
    print(f"  Gemini CLI:            NOT IMPLEMENTED")

    # Sessions dir
    sessions_count = len(list(SESSIONS_DIR.glob("*.jsonl"))) if SESSIONS_DIR.exists() else 0
    print(f"\n  Telemetry:")
    print(f"    Sessions dir:          {OK if SESSIONS_DIR.exists() else FAIL}  {SESSIONS_DIR}")
    print(f"    Session files:         {sessions_count}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

AGENTS = {
    "claude": (install_claude, uninstall_claude),
    "codex": (install_codex, None),
    "opencode": (install_opencode, None),
    "gemini": (install_gemini, None),
}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Install archolith-audit hooks and MCP server for LLM agents."
    )
    parser.add_argument(
        "agent",
        nargs="?",
        choices=list(AGENTS.keys()),
        help="Agent to install for",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Show current installation status for all agents",
    )
    parser.add_argument(
        "--uninstall",
        metavar="AGENT",
        choices=list(AGENTS.keys()),
        help="Remove hook entry for an agent",
    )
    args = parser.parse_args()

    if args.check:
        check_status()
    elif args.uninstall:
        _, uninstall_fn = AGENTS[args.uninstall]
        if uninstall_fn:
            uninstall_fn()
        else:
            print(f"Uninstall not yet implemented for {args.uninstall}.")
    elif args.agent:
        install_fn, _ = AGENTS[args.agent]
        install_fn()
    else:
        parser.print_help()
        print("\nCurrent status:")
        check_status()


if __name__ == "__main__":
    main()
