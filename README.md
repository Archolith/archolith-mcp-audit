# archolith-audit

MCP token usage audit system. Measures per-server token cost, detects waste patterns, and produces report cards with concrete optimization suggestions. Part of the [archolith&trade;](https://archolith.dev) stack.

## License

Source-available under the [PolyForm Noncommercial License 1.0.0](LICENSE).
Free for non-commercial use; commercial use requires permission from the licensor.

## What it does

Scans LLM session logs (Claude JSONL, Codex JSONL, OpenCode SQLite), attributes every tool result to its MCP server, counts tokens per server, and tags each result with one or more of six waste types:

| Waste type | What it catches | Typical savings if fixed |
|------------|-----------------|--------------------------|
| Polling waste | Repeated same-tool calls returning unchanged "still running" output | 90%+ |
| Oversized results | JSON envelopes, large help text blocks | 60–80% |
| Redundant fields | Overbroad queries, missing field filters | 40–70% |
| Schema cost | Tool schema token overhead in system prompt | 10–30% |
| Format waste | JSON where CSV or key-value would be shorter | 30–50% |
| Cache breaker | Content that changes per-turn but is semantically identical | 10× cost penalty |

## Install

```bash
pip install archolith-audit
# or from source:
pip install -e ".[dev]"
```

## CLI usage

```bash
# Audit a Claude session
archolith-audit --claude ~/.claude/projects/<id>/<session>.jsonl

# Audit all available sessions (Claude + Codex + OpenCode)
archolith-audit --all

# Audit a specific OpenCode session
archolith-audit --opencode ~/.local/share/opencode/opencode.db --opencode-session <id>

# JSON output for programmatic use
archolith-audit --claude <path> --format json > audit.json

# Markdown report
archolith-audit --claude <path> --format markdown

# Filter to specific servers
archolith-audit --claude <path> --servers gradle,vps

# CI mode — exits 2 if thresholds exceeded
archolith-audit --claude <path> --ci --max-server-share 20 --max-total-mcp-share 40

# Before/after comparison
archolith-audit --compare before.json after.json
```

## In-session MCP tools

When running as an MCP server, exposes three tools for real-time token budget visibility:

**`mcp_audit_summary`** — Per-server token share table for the current session (~300 tokens).
```
MCP Token Usage (this session):

  gradle                    24.1%   162 calls  high savings (93%)
  workspace-artifacts       10.3%    47 calls
  vps                        9.8%    31 calls

  Total MCP share: 51.2%
  Total results: 847
```

**`mcp_audit_detail(server)`** — Deep dive on one server: waste findings, suggestions, estimated savings (~200–500 tokens).

**`mcp_audit_check`** — Pass/fail check against token share thresholds (~50–100 tokens). Returns `PASS` or `FAIL` per server.

### Enabling the MCP server

The MCP server is **disabled by default** to avoid adding ~200–300 tokens of schema overhead per turn to the very problem it measures. Set `MCP_AUDIT_ENABLED=1` to enable:

```json
// In .mcp.json (or add to env block in mcp-registry.json):
"archolith-audit": {
  ...
  "env": {
    "MCP_AUDIT_ENABLED": "1",
    "PYTHONPATH": "..."
  }
}
```

## Integration with archolith-filter

When archolith-filter is active in the same session, the live accumulator reads from `FilterTelemetryStore` passively — no new pipeline stage, no added latency. Audit sees both raw and filtered token counts per server, enabling before/after savings reporting in real time.

## CI gate

```bash
# Fail the build if any server exceeds 20% token share or total MCP exceeds 40%
archolith-audit --claude <path> --ci
# Exit codes: 0=pass, 1=error, 2=threshold exceeded
```

## Configuration

| Environment variable | Purpose | Default |
|---------------------|---------|---------|
| `MCP_AUDIT_ENABLED` | Enable in-session MCP server | disabled |
| `MCP_AUDIT_SERVER_MAPPING` | Path to server mapping JSON | `data/server_mapping.json` |
| `MCP_AUDIT_SCHEMA_CATALOG` | Path to schema catalog JSON | `data/schema_catalog.json` |
| `MCP_AUDIT_MAX_SHARE` | CI: max per-server token share (%) | 20 |
| `MCP_AUDIT_MAX_TOTAL_MCP` | CI: max total MCP share (%) | 40 |
| `MCP_AUDIT_MAX_WASTE_PCT` | CI: max waste per server (%) | 50 |
