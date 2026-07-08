#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
archolith-audit one-command installer

Usage:
  bash install.sh claude
  bash install.sh codex
  bash install.sh opencode
  bash install.sh all

One-line install:
  curl -fsSL https://raw.githubusercontent.com/Archolith/archolith-mcp-audit/main/scripts/install.sh | bash -s -- codex

Environment:
  PYTHON_BIN              Python executable to register with the MCP server. Default: python3
  ARCHOLITH_PLUGIN_ROOT   Plugin clone root. Default: ~/.archolith/plugins

Gemini CLI is intentionally omitted from this installer because that CLI is deprecated.
EOF
}

log() {
  printf '%s\n' "$*"
}

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "Required command not found: $1"
}

resolve_python() {
  local bin="${PYTHON_BIN:-python3}"
  command -v "$bin" >/dev/null 2>&1 || die "Python not found: $bin"
  command -v "$bin"
}

ensure_plugin_repo() {
  local repo="$1"
  local dest="$2"
  local url="https://github.com/Archolith/${repo}.git"

  need_cmd git
  mkdir -p "$(dirname "$dest")"

  if [ -d "$dest/.git" ]; then
    log "Updating $repo in $dest"
    git -C "$dest" pull --ff-only
    return
  fi

  if [ -e "$dest" ]; then
    die "$dest exists but is not a git checkout. Move it aside or set ARCHOLITH_PLUGIN_ROOT."
  fi

  log "Cloning $url to $dest"
  git clone --depth 1 "$url" "$dest"
}

bootstrap_check() {
  local python_cmd="$1"
  local agent="$2"
  local plugin_dir="$3"

  log "Checking managed Python runtime for $agent"
  PYTHONPATH="$plugin_dir" "$python_cmd" -m archolith_mcp_audit.bootstrap check --agent "$agent"
}

install_claude() {
  need_cmd claude
  resolve_python >/dev/null

  log "Registering Archolith plugin marketplace for Claude"
  claude plugin marketplace add Archolith/archolith-audit-plugin-claude --scope user || true

  log "Installing archolith-audit for Claude"
  claude plugin install archolith-audit@archolith --scope user

  log "Claude install complete. Restart Claude Code, then run /archolith-audit:audit."
}

install_codex() {
  need_cmd codex
  local python_cmd
  python_cmd="$(resolve_python)"
  local root="${ARCHOLITH_PLUGIN_ROOT:-$HOME/.archolith/plugins}"
  local plugin_dir="$root/archolith-audit-plugin-codex"

  ensure_plugin_repo "archolith-audit-plugin-codex" "$plugin_dir"
  bootstrap_check "$python_cmd" "codex" "$plugin_dir"

  log "Registering Codex MCP server"
  codex mcp remove archolith-audit >/dev/null 2>&1 || true
  codex mcp add archolith-audit \
    --env MCP_AUDIT_ENABLED=1 \
    --env PYTHONPATH="$plugin_dir" \
    -- "$python_cmd" -m archolith_mcp_audit.bootstrap mcp --agent codex

  log "Codex install complete. Restart Codex and ask for the MCP audit summary after a few tool calls."
}

install_opencode() {
  need_cmd opencode
  need_cmd node
  local python_cmd
  python_cmd="$(resolve_python)"
  local root="${ARCHOLITH_PLUGIN_ROOT:-$HOME/.archolith/plugins}"
  local plugin_dir="$root/archolith-audit-plugin-opencode"
  local plugin_js="$plugin_dir/dist/index.js"
  local config_path="$HOME/.config/opencode/opencode.json"

  ensure_plugin_repo "archolith-audit-plugin-opencode" "$plugin_dir"
  [ -f "$plugin_js" ] || die "OpenCode plugin bundle is missing: $plugin_js"
  node -e "const p=require(process.argv[1]); if (typeof (p.default || p) !== 'function') process.exit(1)" "$plugin_js"
  bootstrap_check "$python_cmd" "opencode" "$plugin_dir"

  log "Updating OpenCode config at $config_path"
  OPENCODE_CONFIG="$config_path" \
  OPENCODE_PLUGIN_JS="$plugin_js" \
  OPENCODE_PLUGIN_DIR="$plugin_dir" \
  OPENCODE_PYTHON="$python_cmd" \
  "$python_cmd" <<'PY'
import json
import os
from pathlib import Path

config_path = Path(os.environ["OPENCODE_CONFIG"])
plugin_js = os.environ["OPENCODE_PLUGIN_JS"]
plugin_dir = os.environ["OPENCODE_PLUGIN_DIR"]
python_cmd = os.environ["OPENCODE_PYTHON"]

if config_path.exists():
    data = json.loads(config_path.read_text(encoding="utf-8"))
else:
    data = {}

plugins = data.get("plugin", [])
if isinstance(plugins, str):
    plugins = [plugins]
if plugin_js not in plugins:
    plugins.append(plugin_js)
data["plugin"] = plugins

mcp = data.setdefault("mcp", {})
mcp["archolith-audit"] = {
    "type": "local",
    "enabled": True,
    "command": [
        python_cmd,
        "-m",
        "archolith_mcp_audit.bootstrap",
        "mcp",
        "--agent",
        "opencode",
    ],
    "environment": {
        "MCP_AUDIT_ENABLED": "1",
        "PYTHONPATH": plugin_dir,
    },
}

config_path.parent.mkdir(parents=True, exist_ok=True)
config_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
PY

  log "OpenCode install complete. Restart OpenCode and run opencode mcp list to confirm connection."
}

agent="${1:-}"
case "$agent" in
  -h|--help|"")
    usage
    ;;
  claude)
    install_claude
    ;;
  codex)
    install_codex
    ;;
  opencode)
    install_opencode
    ;;
  all)
    install_claude
    install_codex
    install_opencode
    ;;
  gemini)
    die "Gemini CLI is deprecated; this installer supports claude, codex, opencode, and all."
    ;;
  *)
    usage
    die "Unknown agent: $agent"
    ;;
esac
