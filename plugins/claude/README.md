# archolith-audit — Claude Code Plugin

Live MCP token usage audit for Claude Code sessions. Tracks per-server token spend and waste patterns in real time.

## Install

### From GitHub (recommended)

```
/plugin install github:Archolith/archolith-audit-plugin-claude
```

Claude Code clones the plugin, registers the MCP server, and activates the hooks.
On first MCP startup, the plugin creates an isolated runtime under
`~/.archolith/venvs/claude-pyXY` and installs `requirements.txt` there. It does
not mutate your global Python environment.

### Manual install (no plugin system)

Clone the repo and run the installer:

```bash
git clone https://github.com/Archolith/archolith-audit-plugin-claude
cd archolith-audit-plugin-claude
python install.py
```

Restart Claude Code after running.

### Local testing (development)

Test a local copy without installing:

```bash
claude --plugin-dir /path/to/archolith-audit-plugin-claude
```

### Verify

After install, start a session and do some work. Then:

```
/archolith-audit:audit
```

Or ask Claude directly: _"show me the MCP audit summary"_

If it shows "No tool results observed yet," the hook is not firing — check that
`MCP_AUDIT_ENABLED=1` is set in the MCP server env and that Python can find
`archolith_mcp_audit` via the `PYTHONPATH` set in `plugin.json`.

To verify the runtime without starting a full Claude session:

```bash
PYTHONPATH="$(pwd)" python -m archolith_mcp_audit.bootstrap check --agent claude
```

### Uninstall

```
/plugin uninstall archolith-audit
```

## Structure

```
.claude-plugin/plugin.json    ← metadata + MCP server registration
hooks/hooks.json              ← async PostToolUse hook (.* matcher)
hook_observer.py              ← standalone hook wrapper (writes JSONL observations)
skills/audit/SKILL.md         ← /archolith-audit:audit slash command
install.py                    ← manual installer (no plugin system required)
requirements.txt              ← Python runtime dependencies
archolith_mcp_audit/          ← bundled core Python package
```

## Requirements

- Python 3.10+ on PATH with `venv` and `pip`
- Network access on first MCP startup unless the managed venv is already populated
- Claude Code
