# archolith-audit — Gemini CLI Extension

Live MCP token usage audit for Gemini CLI sessions. Tracks per-server token spend and waste patterns in real time.

## Install

### Via Gemini CLI registry

```
gemini /extensions install @archolith/archolith-audit-plugin-gemini
```

Python must be available on `PATH` for the MCP server to launch. On first MCP
startup, the extension creates an isolated runtime under
`~/.archolith/venvs/gemini-pyXY` and installs `requirements.txt` there. It does
not mutate your global Python environment.

### Via GitHub

```
gemini /extensions install github:Archolith/archolith-audit-plugin-gemini
```

### Manual install

1. Clone `https://github.com/Archolith/archolith-audit-plugin-gemini` to `~/.gemini/extensions/archolith-audit/`.
2. Ensure Python is available on PATH.
3. Restart Gemini CLI.

### Verify

Start a Gemini CLI session. After a few tool calls, invoke `mcp_audit_summary`. Check
`~/.archolith/sessions/` for the JSONL file — it should be growing as tools are called.

To verify the runtime without starting a full Gemini session:

```bash
PYTHONPATH="$HOME/.gemini/extensions/archolith-audit" \
  python -m archolith_mcp_audit.bootstrap check --agent gemini
```

## Structure

```
package.json                  ← npm package manifest (geminicli-plugin keyword)
extension.json                ← Gemini CLI extension manifest + MCP server
hooks/after-tool.js           ← AfterTool hook handler (writes JSONL observations)
requirements.txt              ← Python runtime dependencies
archolith_mcp_audit/          ← bundled core Python package
```

## Known Gaps

1. **AfterTool payload shape**: The exact JSON structure Gemini CLI sends to AfterTool
   hooks needs verification against Gemini CLI docs.
2. **Session ID**: Falls back to hour-based key if no session ID in payload.
3. **Synchronous execution**: Gemini CLI hooks run synchronously. File append is
   fast but profile before shipping.
4. **PYTHONPATH injection**: Verify whether Gemini CLI supports `${GEMINI_PLUGIN_DIR}`
   env var substitution in `extension.json`; manual installs can set PYTHONPATH to
   the extension directory.

## Requirements

- Python 3.10+ on PATH with `venv` and `pip`
- Network access on first MCP startup unless the managed venv is already populated
- Node.js (for hook handler)
- Gemini CLI
