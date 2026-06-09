# archolith-audit — Codex Plugin

Live MCP token usage audit for Codex sessions. Tracks per-server token spend and waste patterns in real time.

## Install

### Via Codex CLI

```
/plugins install github:archolith/archolith-audit-plugin-codex
```

No `pip install` needed — the Python package is bundled inside the plugin directory.

### Manual install

1. Clone the plugin repo to `~/.codex/plugins/archolith-audit/`.
2. Ensure Python is available on `PATH`.
3. Restart Codex.

### Verify

After a few tool calls, run `mcp_audit_summary` via the MCP tool. Should show
per-server data. If empty, check that the JSONL file exists at
`~/.archolith/sessions/`.

## Structure

```
plugin.json                   ← metadata + MCP server registration
hooks/hooks.json              ← PostToolUse hook (calls hook_observer_codex.py)
hook_observer_codex.py        ← standalone hook wrapper (writes JSONL observations)
archolith_mcp_audit/          ← bundled core Python package (no pip install needed)
```

## Session ID

Codex does not inject session ID into MCP server env automatically.
This plugin uses a per-hour fallback session key (`codex-<hour>`).
All observations from the same hour's Codex session map to the same file.
Good enough for reporting; not perfectly session-scoped.

## Requirements

- Python 3.11+ on PATH (for MCP server + hook observer)
- Codex CLI
