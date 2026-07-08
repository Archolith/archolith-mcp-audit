#!/usr/bin/env python3
"""
archolith-audit plugin release script.

The core archolith_mcp_audit/ package is developed at the monorepo root.
Plugin directories under plugins/ contain only adapter files (manifests,
hooks, READMEs). Bundled copies of the core are NOT tracked in git — they
are build artifacts created on demand.

Usage:
  python scripts/release.py sync          # Create bundled copies for local testing
  python scripts/release.py sync claude   # Sync one plugin only
  python scripts/release.py build         # Assemble dist/ directories for release
  python scripts/release.py build claude  # Build one plugin only
  python scripts/release.py check         # Verify synced bundles match core (if present)
  python scripts/release.py version 0.2.0 # Update version in all manifests

Workflow:
  Development: edit archolith_mcp_audit/ at monorepo root. No copies needed.
  Local test:  release.py sync -> installs bundled copy into plugins/<name>/
  Release:     release.py build -> assembles adapter + core into dist/<name>/

Plugins: claude, codex, gemini, opencode
"""

from __future__ import annotations

import argparse
import filecmp
import json
import shutil
import sys
from pathlib import Path

# Package root (scripts/ is one level below)
PKG_ROOT = Path(__file__).parent.parent.resolve()
CORE_PKG = PKG_ROOT / "archolith_mcp_audit"
PLUGINS_DIR = PKG_ROOT / "plugins"
DIST_DIR = PKG_ROOT / "dist"
INSTALLER = PKG_ROOT / "scripts" / "install.sh"

PLUGIN_NAMES = ["claude", "codex", "gemini", "opencode"]

# Files/dirs to exclude when copying the core package
EXCLUDE = {"__pycache__", ".pyc"}

# Per-plugin adapter files (relative to plugins/<name>/)
# These are the files unique to each plugin — everything else is the bundled core.
ADAPTER_FILES: dict[str, list[str]] = {
    "claude": [
        ".claude-plugin/plugin.json",
        ".claude-plugin/marketplace.json",
        ".gitattributes",
        ".gitignore",
        "requirements.txt",
        "hooks/hooks.json",
        "hook_observer.py",
        "install.py",
        "skills/audit/SKILL.md",
        "README.md",
    ],
    "codex": [
        "plugin.json",
        "requirements.txt",
        "hooks/hooks.json",
        "hook_observer_codex.py",
        "README.md",
    ],
    "gemini": [
        "package.json",
        "extension.json",
        "requirements.txt",
        "hooks/after-tool.js",
        ".gitignore",
        "README.md",
    ],
    "opencode": [
        "package.json",
        "tsconfig.json",
        "requirements.txt",
        "src/index.ts",
        ".gitignore",
        "README.md",
    ],
}

# Distribution repo names (for git tag / npm package)
DIST_NAMES = {
    "claude": "archolith-audit-plugin-claude",
    "codex": "archolith-audit-plugin-codex",
    "gemini": "archolith-audit-plugin-gemini",
    "opencode": "archolith-audit-plugin-opencode",
}


def _should_exclude(path: Path) -> bool:
    """Return True if the path should be excluded from copies."""
    return any(part in EXCLUDE for part in path.parts) or path.suffix == ".pyc"


def _copy_core(dest: Path) -> int:
    """Copy archolith_mcp_audit/ to dest, excluding __pycache__ and .pyc. Returns file count."""
    if dest.exists():
        shutil.rmtree(dest)
    count = 0
    for src_path in CORE_PKG.rglob("*"):
        if _should_exclude(src_path):
            continue
        rel = src_path.relative_to(CORE_PKG)
        dst_path = dest / rel
        if src_path.is_dir():
            dst_path.mkdir(parents=True, exist_ok=True)
        else:
            dst_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_path, dst_path)
            count += 1
    return count


def _resolve_plugins(name: str | None) -> list[str]:
    """Resolve plugin name arg to a list of plugin names."""
    if name:
        if name not in PLUGIN_NAMES:
            print(f"ERROR: Unknown plugin '{name}'. Valid: {', '.join(PLUGIN_NAMES)}")
            sys.exit(1)
        return [name]
    return list(PLUGIN_NAMES)


# ---------------------------------------------------------------------------
# sync — copy core package into plugin bundles
# ---------------------------------------------------------------------------

def cmd_sync(args: argparse.Namespace) -> None:
    """Sync core archolith_mcp_audit/ into plugin bundled copies."""
    plugins = _resolve_plugins(args.plugin)
    for name in plugins:
        dest = PLUGINS_DIR / name / "archolith_mcp_audit"
        count = _copy_core(dest)
        print(f"  {name}: synced {count} files from core -> plugins/{name}/archolith_mcp_audit/")
    print("\nDone. Run 'python scripts/release.py check' to verify.")


# ---------------------------------------------------------------------------
# check — verify all bundles match core
# ---------------------------------------------------------------------------

def cmd_check(args: argparse.Namespace) -> None:
    """Verify synced plugin bundles are identical to core (if present)."""
    plugins = _resolve_plugins(args.plugin)
    all_ok = True
    any_present = False
    for name in plugins:
        bundle = PLUGINS_DIR / name / "archolith_mcp_audit"
        if not bundle.exists():
            print(f"  {name}: not synced (run 'release.py sync' to create)")
            continue
        any_present = True

        # Compare source files
        diffs = []
        core_files = {
            f.relative_to(CORE_PKG)
            for f in CORE_PKG.rglob("*")
            if f.is_file() and not _should_exclude(f)
        }
        bundle_files = {
            f.relative_to(bundle)
            for f in bundle.rglob("*")
            if f.is_file() and not _should_exclude(f)
        }

        # Files only in core
        for f in sorted(core_files - bundle_files):
            diffs.append(f"  missing in bundle: {f}")

        # Files only in bundle
        for f in sorted(bundle_files - core_files):
            diffs.append(f"  extra in bundle: {f}")

        # Files in both but different content
        for f in sorted(core_files & bundle_files):
            if not filecmp.cmp(CORE_PKG / f, bundle / f, shallow=False):
                diffs.append(f"  content differs: {f}")

        if diffs:
            print(f"  {name}: STALE — {len(diffs)} difference(s)")
            for d in diffs:
                print(f"    {d}")
            all_ok = False
        else:
            print(f"  {name}: OK")

    if not any_present:
        print("\nNo bundles present. This is normal — bundles are build artifacts.")
        print("Run 'python scripts/release.py sync' to create them for local testing.")
    elif all_ok:
        print("\nAll synced bundles match core.")
    else:
        print("\nSome bundles are stale. Run 'python scripts/release.py sync' to fix.")
        sys.exit(1)


# ---------------------------------------------------------------------------
# build — assemble clean distribution directories
# ---------------------------------------------------------------------------

def cmd_build(args: argparse.Namespace) -> None:
    """Assemble clean distribution directories in dist/."""
    plugins = _resolve_plugins(args.plugin)
    for name in plugins:
        dist_name = DIST_NAMES[name]
        dist_path = DIST_DIR / dist_name
        if dist_path.exists():
            # Clear contents but tolerate a locked directory handle (common on Windows
            # when a .git dir was previously created there).
            def _force_remove(func, path, _exc):
                import os
                try:
                    os.chmod(path, 0o666)
                    func(path)
                except OSError:
                    pass  # locked dir shell — contents already cleared
            shutil.rmtree(dist_path, onerror=_force_remove)
        dist_path.mkdir(parents=True, exist_ok=True)

        # 1. Copy adapter files
        plugin_src = PLUGINS_DIR / name
        adapter_count = 0
        for rel_path in ADAPTER_FILES[name]:
            src = plugin_src / rel_path
            dst = dist_path / rel_path
            if src.exists():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                adapter_count += 1
            else:
                print(f"  WARNING: adapter file missing: plugins/{name}/{rel_path}")

        # 2. Copy core package
        core_count = _copy_core(dist_path / "archolith_mcp_audit")

        # 3. Copy license notes into every publishable plugin bundle.
        shutil.copy2(PKG_ROOT / "LICENSE", dist_path / "LICENSE")
        shutil.copy2(PKG_ROOT / "THIRD-PARTY-LICENSES.md", dist_path / "THIRD-PARTY-LICENSES.md")

        # 4. Copy the one-command installer into currently supported public plugin repos.
        if name in {"claude", "codex", "opencode"} and INSTALLER.exists():
            shutil.copy2(INSTALLER, dist_path / "install.sh")

        # 5. For OpenCode: copy dist/ (compiled JS) if it exists
        if name == "opencode":
            ts_dist = plugin_src / "dist"
            if ts_dist.exists():
                shutil.copytree(ts_dist, dist_path / "dist", dirs_exist_ok=True)
                print(f"  {name}: included compiled dist/")
            else:
                print(f"  {name}: WARNING — no compiled dist/ found. Run 'npm run build' in plugins/opencode/ first.")

        print(f"  {name}: built {dist_name}/ ({adapter_count} adapter + {core_count} core files)")

    print(f"\nDistribution directories assembled in: {DIST_DIR}/")
    print("Next steps:")
    print("  - Copy each dist/archolith-audit-plugin-* directory to its matching standalone repo")
    print("  - Commit, tag, and push each standalone plugin repo")
    print("  - For npm-capable plugins (gemini, opencode): publish from the matching dist directory")


# ---------------------------------------------------------------------------
# version — update version across all manifests
# ---------------------------------------------------------------------------

VERSION_FILES: dict[str, list[str]] = {
    "claude": [".claude-plugin/plugin.json"],
    "codex": ["plugin.json"],
    "gemini": ["package.json", "extension.json"],
    "opencode": ["package.json"],
}


def cmd_version(args: argparse.Namespace) -> None:
    """Update version string in all plugin manifests."""
    new_version = args.version
    if not new_version:
        print("ERROR: version argument required. Example: python scripts/release.py version 0.2.0")
        sys.exit(1)

    updated = 0
    for name in PLUGIN_NAMES:
        for rel_path in VERSION_FILES[name]:
            full_path = PLUGINS_DIR / name / rel_path
            if not full_path.exists():
                print(f"  WARNING: {full_path} not found")
                continue
            data = json.loads(full_path.read_text(encoding="utf-8"))
            old_version = data.get("version", "unknown")
            if old_version == new_version:
                print(f"  {name}/{rel_path}: already {new_version}")
                continue
            data["version"] = new_version
            full_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
            print(f"  {name}/{rel_path}: {old_version} -> {new_version}")
            updated += 1

    # Also update pyproject.toml if it has a version field
    pyproject = PKG_ROOT / "pyproject.toml"
    if pyproject.exists():
        content = pyproject.read_text(encoding="utf-8")
        import re
        new_content = re.sub(
            r'^version\s*=\s*"[^"]*"',
            f'version = "{new_version}"',
            content,
            count=1,
            flags=re.MULTILINE,
        )
        if new_content != content:
            pyproject.write_text(new_content, encoding="utf-8")
            print(f"  pyproject.toml: updated to {new_version}")
            updated += 1

    print(f"\nUpdated {updated} file(s) to version {new_version}.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sync, build, and release archolith-audit agent plugins.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # sync
    p_sync = subparsers.add_parser("sync", help="Sync core package -> plugin bundles")
    p_sync.add_argument("plugin", nargs="?", help="Plugin name (default: all)")
    p_sync.set_defaults(func=cmd_sync)

    # check
    p_check = subparsers.add_parser("check", help="Verify bundles match core")
    p_check.add_argument("plugin", nargs="?", help="Plugin name (default: all)")
    p_check.set_defaults(func=cmd_check)

    # build
    p_build = subparsers.add_parser("build", help="Assemble distribution directories")
    p_build.add_argument("plugin", nargs="?", help="Plugin name (default: all)")
    p_build.set_defaults(func=cmd_build)

    # version
    p_version = subparsers.add_parser("version", help="Update version in all manifests")
    p_version.add_argument("version", help="New version string (e.g. 0.2.0)")
    p_version.set_defaults(func=cmd_version)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
