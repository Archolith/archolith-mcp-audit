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
  "plugins": ["@archolith/opencode-plugin"]
}
```

Then add the MCP server:

```json
{
  "mcpServers": {
    "archolith-audit": {
      "command": "python",
      "args": ["-m", "archolith_mcp_audit.mcp_server"],
      "env": {
        "MCP_AUDIT_ENABLED": "1",
        "MCP_AUDIT_SESSION_ID": "${OPENCODE_SESSION_ID}",
        "PYTHONPATH": "${OPENCODE_PLUGIN_DIR}"
      }
    }
  }
}
```

OpenCode installs via Bun at next startup. No `pip install` needed — the Python
package is bundled inside the npm package.

### Local development

```bash
cd plugin-opencode
npm install
npm run build
```

Add to OpenCode config:

```json
{
  "plugins": ["/absolute/path/to/plugin-opencode"]
}
```

### Verify

Start an OpenCode session. After a few tool calls, call `mcp_audit_summary` via the
audit MCP tools. Should show per-server data. Check `~/.archolith/sessions/` for the
JSONL file — it should be growing as tools are called.

## Structure

```
package.json                  ← npm package manifest (opencode-plugin keyword)
tsconfig.json                 ← TypeScript compiler config
src/index.ts                  ← plugin entry point (in-process, no subprocess)
archolith_mcp_audit/          ← bundled core Python package (no pip install needed)
```

## Why This Is Cleaner Than the Other Agents

- Runs in-process: no subprocess spawn, no stdin/stdout overhead
- `context.sessionId` is the real OpenCode session ID — perfect file scoping
- TypeScript: type-safe, IDE support
- `tool.execute.after` gives `event.result` directly — no payload parsing needed

## Known Gaps

1. **OPENCODE_PLUGIN_DIR env var**: Verify whether OpenCode provides a
   `${OPENCODE_PLUGIN_DIR}` variable for `PYTHONPATH`. If not, set programmatically
   in `index.ts`.
2. **OPENCODE_SESSION_ID forwarding**: Verify whether OpenCode forwards session ID
   env vars into MCP server subprocesses. If not, use hour-based fallback.
3. **Bun package resolution**: Verify that Bun correctly installs npm packages that
   include non-JS files (the bundled Python package).

## Requirements

- Python 3.11+ on PATH (for MCP server)
- OpenCode
