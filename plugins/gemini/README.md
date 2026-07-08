# archolith-audit — Gemini CLI Extension

Live MCP token usage audit for Gemini CLI sessions. Tracks per-server token spend and waste patterns in real time.

## Install

### Via Gemini CLI registry

```
gemini /extensions install @archolith/archolith-audit-plugin-gemini
```

Install the Python runtime dependencies once in the Python environment Gemini CLI uses:

```bash
python -m pip install -r requirements.txt
```

Python must be available on `PATH` for the MCP server to launch.

### Via GitHub

```
gemini /extensions install github:Archolith/archolith-audit-plugin-gemini
```

### Manual install

1. Clone `https://github.com/Archolith/archolith-audit-plugin-gemini` to `~/.gemini/extensions/archolith-audit/`.
2. Ensure Python is available on PATH.
3. Run `python -m pip install -r requirements.txt`.
4. Restart Gemini CLI.

### Verify

Start a Gemini CLI session. After a few tool calls, invoke `mcp_audit_summary`. Check
`~/.archolith/sessions/` for the JSONL file — it should be growing as tools are called.

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
   env var substitution in `extension.json`.

## Requirements

- Python 3.11+ on PATH (for MCP server)
- `tiktoken` and `fastmcp` installed in that Python environment
- Node.js (for hook handler)
- Gemini CLI
