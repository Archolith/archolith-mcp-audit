# archolith-mcp-audit

MCP token usage audit system. Measures per-server token cost, detects waste patterns, and produces report cards with concrete optimization suggestions.

## Install

```bash
pip install -e ".[dev]"
```

## Usage

```bash
# Audit a Claude session
python -m archolith_mcp_audit --claude <jsonl_path>

# Audit all available sessions
python -m archolith_mcp_audit --all

# JSON output
python -m archolith_mcp_audit --claude <path> --format json

# Markdown output
python -m archolith_mcp_audit --claude <path> --format markdown
```

## In-Session MCP Tools

When running as an MCP server, exposes:
- `mcp_audit_summary` — per-server token share table
- `mcp_audit_detail` — deep dive on one server
- `mcp_audit_check` — threshold pass/fail check
