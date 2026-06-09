# archolith-mcp-audit

MCP token usage audit system. Scans LLM session logs (Claude JSONL, Codex JSONL, OpenCode SQLite), attributes tool results to their MCP server, measures token cost per server, detects waste patterns, and produces per-server report cards with concrete optimization suggestions.

**Design principle**: This is a diagnostic tool, not a proxy. It measures and reports. It does NOT intercept, compress, or modify MCP traffic.

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

## Documentation

| File | Purpose |
|------|---------|
| [.agent/README.md](.agent/README.md) | Agent context and maintenance rules |
| [.agent/architecture.md](.agent/architecture.md) | System design, data flow, component map |
| [.agent/data_models.md](.agent/data_models.md) | Entities, DTOs, enums, waste findings |
| [.agent/CHANGELOG.md](.agent/CHANGELOG.md) | Running log of changes |

## License

Source-available under the PolyForm Noncommercial License 1.0.0.

archolith&trade; is a trademark of Charles Harvey.
