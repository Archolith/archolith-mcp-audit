# archolith-mcp-audit

MCP token usage audit system. Scans LLM session logs (Claude JSONL, Codex JSONL, OpenCode SQLite), attributes tool results to their MCP server, measures token cost per server, detects waste patterns, and produces per-server report cards with concrete optimization suggestions.

**Design principle**: This is a diagnostic tool, not a proxy. It measures and reports. It does NOT intercept, compress, or modify MCP traffic.

**Limitations:** Token counts use OpenAI-compatible tokenizers (`cl100k_base` and `o200k_base`)
through `tiktoken`. Treat cross-provider counts and heuristic savings
percentages as directional unless a refreshed schema catalog and provider-specific validation are
attached to the evidence.

## Names

This repository is `archolith-mcp-audit`. The Python package and CLI distribution are
`archolith-audit`, and the import module is `archolith_mcp_audit`.

## Quick Start

```bash
pip install -e ".[dev]"

# Audit a Claude session
python -m archolith_mcp_audit --claude ~/.claude/projects/<id>.jsonl

# Refresh MCP tool schema catalog
python -m archolith_mcp_audit --refresh-schemas

# CI gate check
python -m archolith_mcp_audit --claude <path> --ci --max-server-share 20 --max-total-mcp-share 40
```

## In-Session MCP Tools

When `MCP_AUDIT_ENABLED=1`, the audit server exposes four tools for real-time monitoring:

| Tool | Purpose | Output size |
|------|---------|-----------|
| `mcp_audit_summary` | Per-server token share across all active sessions | ~300 tokens |
| `mcp_audit_detail` | Deep dive on a specific server with waste findings | ~200-500 tokens |
| `mcp_audit_check` | Threshold pass/fail check (configurable limits) | ~50-150 tokens |
| `mcp_audit_bridge_status` | Telemetry bridge status and observation count | ~50 tokens |

The MCP server is disabled by default. Set `MCP_AUDIT_ENABLED=1` in the MCP server environment
before expecting the tools to return live data.

Optional telemetry environment variables:

| Variable | Purpose |
|----------|---------|
| `MCP_AUDIT_FILTER` | Preferred flag for reading archolith-filter telemetry (`1`, `true`, or `yes`) |
| `MCP_AUDIT_RTK` | Legacy alias for `MCP_AUDIT_FILTER` |
| `MCP_AUDIT_TELEMETRY_FILE` | Override path for the JSONL telemetry file read by the bridge |

## Privacy

Session metrics are stored locally under `~/.archolith/sessions/` unless a telemetry file override is
configured. The audit does not transmit session data. Session JSONL and `.name` files are local
runtime artifacts and are safe to delete when no longer needed.

## `.mcp.json` Trust Model

`--refresh-schemas` reads the nearest `.mcp.json` and passes each server's configured `env` mapping
to that server subprocess. This is intentional: `.mcp.json` is operator-curated MCP configuration,
and some servers need credentials to start. Do not place secrets in a server's `env` unless that
server should receive them. During schema refresh, archolith-audit logs a warning for secret-like
env key names so operators can review the configuration; it does not redact, filter, or block the
configured subprocess environment.

## Sample Report

```text
MCP TOKEN AUDIT REPORT
Session: claude (example), 42 tool results

OVERVIEW
  Total tool result tokens:        18,240 (cl100k estimate)
  MCP server share:                12,900 (70.7%)
  Result waste detected:            4,800 (26.3% of result tokens)

PER-SERVER REPORT CARDS
--- gradle --------------------------------------------
  Token share:        7,200 (39.5%)
  Calls:                 12
  Waste findings:
    [    HIGH]  polling
      Repeated status calls returned unchanged output.
      Suggestion: Return status deltas on poll.
```

## Documentation

| File | Purpose |
|------|---------|
| [.agent/README.md](.agent/README.md) | Agent context and maintenance rules |
| [.agent/architecture.md](.agent/architecture.md) | System design, data flow, component map |
| [.agent/data_models.md](.agent/data_models.md) | Entities, DTOs, enums, waste findings |
| [.agent/CHANGELOG.md](.agent/CHANGELOG.md) | Running log of changes |

## License

Licensed under the Apache License 2.0.

archolith&trade; is a trademark of Charles Harvey.
