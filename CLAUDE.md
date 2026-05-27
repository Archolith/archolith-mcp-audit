# archolith-mcp-audit

MCP token usage audit system. Measures per-server token cost, detects waste patterns, and produces report cards with concrete optimization suggestions.

Read everything in [`.agent/`](.agent/) before starting work — it contains project context, reference docs, workflows, conventions, and maintenance rules.

## Quick Start

```bash
# Install
pip install -e ".[dev]"

# Run audit on a Claude session
python -m archolith_mcp_audit --claude <jsonl_path>

# Run audit on all available sessions
python -m archolith_mcp_audit --all

# JSON output for programmatic use
python -m archolith_mcp_audit --claude <path> --format json

# Compare before/after optimization
python -m archolith_mcp_audit --compare before.json after.json
```

## Architecture

This is a **diagnostic tool**, not a proxy. It measures and reports MCP token waste to drive server-side fixes. It does NOT intercept, compress, or modify MCP traffic.

See `.agent/architecture.md` for full system design.

## Key Concepts

- **Server attribution**: Tool names like `mcp__vps__vps_status` are mapped to canonical server names (e.g., `vps`)
- **Waste detection**: Six pattern detectors flag polling waste, oversized results, redundant fields, schema cost, format waste, and cache breakers
- **Report cards**: Per-server reports with concrete optimization suggestions and estimated savings
- **Live accumulator**: In-session MCP tool reads RTK telemetry for real-time token budget visibility
