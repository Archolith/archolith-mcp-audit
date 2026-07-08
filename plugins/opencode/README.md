# archolith-audit — OpenCode Plugin

Live MCP token usage audit for OpenCode sessions. Tracks per-server token spend and waste patterns in real time.

The cleanest integration of the four agents — runs in-process as a TypeScript plugin,
no subprocess spawn or stdin/stdout overhead. Uses the real OpenCode `sessionId` for
perfect file scoping.

## Install

### One-command install

```bash
curl -fsSL https://raw.githubusercontent.com/Archolith/archolith-mcp-audit/main/scripts/install.sh | bash -s -- opencode
```

The installer clones `https://github.com/Archolith/archolith-audit-plugin-opencode` to
`~/.archolith/plugins/archolith-audit-plugin-opencode`, verifies `dist/index.js`, verifies the
managed Python runtime, and writes the OpenCode plugin plus MCP config.

### Manual install

Clone the repo:

```bash
git clone https://github.com/Archolith/archolith-audit-plugin-opencode \
  ~/.archolith/plugins/archolith-audit-plugin-opencode
```

Add to OpenCode config (`~/.config/opencode/opencode.json`):

```json
{
  "plugin": [
    "/home/you/.archolith/plugins/archolith-audit-plugin-opencode/dist/index.js"
  ],
  "mcp": {
    "archolith-audit": {
      "type": "local",
      "enabled": true,
      "command": ["python", "-m", "archolith_mcp_audit.bootstrap", "mcp", "--agent", "opencode"],
      "environment": {
        "MCP_AUDIT_ENABLED": "1",
        "PYTHONPATH": "/home/you/.archolith/plugins/archolith-audit-plugin-opencode"
      }
    }
  }
}
```

On first MCP startup,
the plugin creates an isolated runtime under `~/.archolith/venvs/opencode-pyXY`
and installs `requirements.txt` there. It does not mutate your global Python
environment.

### Local development

```bash
cd archolith-audit-plugin-opencode
npm install
npm run build
```

Add to OpenCode config:

```json
{
  "plugin": ["/absolute/path/to/archolith-audit-plugin-opencode/dist/index.js"],
  "mcp": {
    "archolith-audit": {
      "type": "local",
      "enabled": true,
      "command": ["python", "-m", "archolith_mcp_audit.bootstrap", "mcp", "--agent", "opencode"],
      "environment": {
        "MCP_AUDIT_ENABLED": "1",
        "PYTHONPATH": "/absolute/path/to/archolith-audit-plugin-opencode"
      }
    }
  }
}
```

### Verify

Start an OpenCode session. After a few tool calls, call `mcp_audit_summary` via the
audit MCP tools. Should show per-server data. Check `~/.archolith/sessions/` for the
JSONL file — it should be growing as tools are called.

To verify the Python runtime without starting a full OpenCode session:

```bash
PYTHONPATH="/absolute/path/to/archolith-audit-plugin-opencode" \
  python -m archolith_mcp_audit.bootstrap check --agent opencode
```

## Structure

```
package.json                  ← npm package manifest (opencode-plugin keyword)
tsconfig.json                 ← TypeScript compiler config
src/index.ts                  ← plugin entry point (in-process, no subprocess)
requirements.txt              ← Python runtime dependencies
archolith_mcp_audit/          ← bundled core Python package
```

## Why This Is Cleaner Than the Other Agents

- Runs in-process: no subprocess spawn, no stdin/stdout overhead
- `context.sessionId` is the real OpenCode session ID — perfect file scoping
- TypeScript: type-safe, IDE support
- `tool.execute.after` gives `event.result` directly — no payload parsing needed

## Known Gaps

1. npm package publication is pending. Use the GitHub clone path until the npm package is published.

## Requirements

- Python 3.10+ on PATH with `venv` and `pip`
- Network access on first MCP startup unless the managed venv is already populated
- Node.js 18+ recommended for OpenCode; the plugin bundle avoids newer syntax for compatibility
- OpenCode
