# archolith-audit — OpenCode Plugin

Live MCP token usage audit for OpenCode sessions. Tracks per-server token spend and waste patterns in real time.

The cleanest integration of the four agents — runs in-process as a TypeScript plugin,
no subprocess spawn or stdin/stdout overhead. Uses the real OpenCode `sessionId` for
perfect file scoping.

## Install

### Via npm (recommended)

Add to OpenCode config (`~/.config/opencode/opencode.json`):

```json
{
  "plugin": ["@archolith/archolith-audit-plugin-opencode"]
}
```

Then add the MCP server:

```json
{
  "mcp": {
    "archolith-audit": {
      "type": "local",
      "enabled": true,
      "command": ["python", "-m", "archolith_mcp_audit.bootstrap", "mcp", "--agent", "opencode"],
      "environment": {
        "MCP_AUDIT_ENABLED": "1",
        "PYTHONPATH": "${OPENCODE_PLUGIN_DIR}"
      }
    }
  }
}
```

OpenCode installs the TypeScript plugin at next startup. On first MCP startup,
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

1. **OPENCODE_PLUGIN_DIR env var**: Verify whether OpenCode provides a
   `${OPENCODE_PLUGIN_DIR}` variable for `PYTHONPATH`. If not, use the absolute
   package path shown above.
2. **Bun package resolution**: Verify that Bun correctly installs npm packages that
   include non-JS files (the bundled Python package).

## Requirements

- Python 3.10+ on PATH with `venv` and `pip`
- Network access on first MCP startup unless the managed venv is already populated
- Node.js 18+ recommended for OpenCode; the plugin bundle avoids newer syntax for compatibility
- OpenCode
