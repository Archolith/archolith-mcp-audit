# archolith-audit — Codex Plugin

Live MCP token usage audit for Codex sessions. Tracks per-server token spend and waste patterns in real time.

## Install

### Via Codex CLI

```
/plugins install github:Archolith/archolith-audit-plugin-codex
```

Install the Python runtime dependencies once in the Python environment Codex uses:

```bash
python -m pip install -r ~/.codex/plugins/archolith-audit/requirements.txt
```

### Manual install

1. Clone `https://github.com/Archolith/archolith-audit-plugin-codex` to `~/.codex/plugins/archolith-audit/`.
2. Ensure Python is available on `PATH`.
3. Run `python -m pip install -r ~/.codex/plugins/archolith-audit/requirements.txt`.
4. Restart Codex.

### Verify

After a few tool calls, run `mcp_audit_summary` via the MCP tool. Should show
per-server data. If empty, check that the JSONL file exists at
`~/.archolith/sessions/`.

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

- Python 3.11+ on PATH (for MCP server + hook observer)
- `tiktoken` and `fastmcp` installed in that Python environment
- Codex CLI
