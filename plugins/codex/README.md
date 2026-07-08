# archolith-audit — Codex Plugin

Live MCP token usage audit for Codex sessions. Tracks per-server token spend and waste patterns in real time.

## Install

### One-command install

```bash
curl -fsSL https://raw.githubusercontent.com/Archolith/archolith-mcp-audit/main/scripts/install.sh | bash -s -- codex
```

The installer clones `https://github.com/Archolith/archolith-audit-plugin-codex` to
`~/.archolith/plugins/archolith-audit-plugin-codex`, verifies the managed Python runtime, and runs
`codex mcp add` with the correct `PYTHONPATH`.

On first MCP startup, the plugin creates an isolated runtime under
`~/.archolith/venvs/codex-pyXY` and installs `requirements.txt` there. It does
not mutate your global Python environment.

### Manual install

```bash
git clone https://github.com/Archolith/archolith-audit-plugin-codex \
  ~/.archolith/plugins/archolith-audit-plugin-codex
codex mcp add archolith-audit \
  --env MCP_AUDIT_ENABLED=1 \
  --env PYTHONPATH="$HOME/.archolith/plugins/archolith-audit-plugin-codex" \
  -- python -m archolith_mcp_audit.bootstrap mcp --agent codex
```

Restart Codex after installing.

### Verify

After a few tool calls, run `mcp_audit_summary` via the MCP tool. Should show
per-server data. If empty, check that the JSONL file exists at
`~/.archolith/sessions/`.

To verify the runtime without starting a full Codex session:

```bash
PYTHONPATH="$HOME/.archolith/plugins/archolith-audit-plugin-codex" \
  python -m archolith_mcp_audit.bootstrap check --agent codex
```

## Structure

```
plugin.json                   ← metadata + MCP server registration
hooks/hooks.json              ← PostToolUse hook (calls hook_observer_codex.py)
hook_observer_codex.py        ← standalone hook wrapper (writes JSONL observations)
requirements.txt              ← Python runtime dependencies
archolith_mcp_audit/          ← bundled core Python package
```

## Session ID

Codex does not inject session ID into MCP server env automatically.
This plugin uses a per-hour fallback session key (`codex-<hour>`).
All observations from the same hour's Codex session map to the same file.
Good enough for reporting; not perfectly session-scoped.

## Requirements

- Python 3.10+ on PATH with `venv` and `pip`
- Network access on first MCP startup unless the managed venv is already populated
- Codex CLI
