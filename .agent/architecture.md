# archolith-mcp-audit — Architecture

## Overview

MCP token usage audit system. Scans LLM session logs (Claude JSONL, Codex JSONL, OpenCode SQLite), attributes tool results to their MCP server, measures token cost per server, detects waste patterns, and produces per-server report cards with concrete optimization suggestions.

**Design principle**: This is a diagnostic tool, not a proxy. It measures and reports. It does NOT intercept, compress, or modify MCP traffic. The goal is to drive server-side fixes, not add a permanent middleware layer.

## Schema Refresh

The `--refresh-schemas` CLI command populates `data/schema_catalog.json` with
real tool definitions from MCP servers. It works via FastMCP's `Client` class
over stdio subprocess communication.

### Flow

1. `refresh_schema_catalog()` in `schema_estimator.py` is called from `cli.py`.
2. It locates `.mcp.json` (CWD-first, then ~/.claude/ fallback).
3. For each configured server (sequential, not concurrent):
   a. Check self-exclusion via `_is_self_server()` — skip archolith-audit.
   b. Skip entries without a `command` field (SSE/HTTP-only servers).
   c. Call `_query_server_via_fastmcp()` which wraps FastMCP `Client`:
      - FastMCP handles the full protocol internally: spawn subprocess,
        JSON-RPC initialize, `notifications/initialized`, `tools/list` (with
        pagination), and graceful close.
      - 15-second `asyncio.wait_for()` timeout per server.
      - On failure, the server is recorded in `failed_servers` dict.
4. Tool definitions are run through `count_schema_tokens()` and stored.
5. Catalog is written to `schema_catalog.json` via `_write_catalog()`.

### Self-exclusion

`_is_self_server(name, command, args)` returns True if:
- Server name is `"archolith-audit"`, or
- Command is a Python interpreter AND any arg contains `"archolith_mcp_audit"`

### Configuration search order

1. CWD (current working directory)
2. Parent directories up to filesystem root
3. `~/.claude/.mcp.json` (user-level fallback)

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.11+ |
| Tokenizer | tiktoken (cl100k_base + o200k_base) |
| MCP Server | FastMCP 0.4+ |
| CLI | argparse |
| Testing | pytest 8+ |
| Linting | ruff |

## Data Flow

```
Session logs (JSONL / SQLite)
        │
        ▼
┌──────────────────────┐
│  Session Extractor    │  Per-source adapter produces SessionData
│  (claude/codex/opencode)│
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  Server Attributor    │  Tool name → MCP server mapping
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  Token Counter        │  tiktoken per result (cl100k + o200k)
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  Waste Detector       │  6 pattern detectors tag each result
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  Report Generator     │  Per-server report cards (text/JSON/markdown)
└──────────────────────┘
```

### In-Session Flow (MCP Server + Telemetry Bridge)

```
RTK filter_output() runs on each tool result
        │
        ├── Normal path: filtered result → model context
        │
        └── Audit side channel: reads from FilterTelemetryStore
                │
                ▼
        ┌──────────────────────┐
        │  Telemetry Bridge    │  Connects telemetry sources to accumulator
        │  (telemetry_bridge)   │  Sources: RTK, file, in-memory, direct push
        └──────────┬───────────┘
                   │
                   ▼
        ┌──────────────────────┐
        │  Hook Observer       │  Platform-specific event listeners
        │  (hook_observer)     │  Claude Code, Codex, OpenCode hooks
        └──────────┬───────────┘
                   │
        ┌──────────────────────┐
        │  SessionStart hook   │  Fires once per session; writes
        │  (hook_session_start)│  ~/.archolith/sessions/<id>.name
        └──────────┬───────────┘
                   │
                   ▼
        ┌──────────────────────────────────┐
        │  Per-session bridges             │  dict[session_id → TelemetryBridge]
        │  list_active_sessions()          │  scans *.jsonl modified < 24h
        └──────────┬───────────────────────┘
                   │
                   ▼
           mcp_audit_summary()      — all active sessions, named
           mcp_audit_detail()       — per-session server breakdown
           mcp_audit_check()        — worst-case across sessions
           mcp_audit_bridge_status() — per-session source status
```

The accumulator is passive — it reads telemetry that already exists. No new pipeline stage, no interception, no overhead on the filter path.

The TelemetryBridge provides a uniform interface for feeding observations from multiple backends into the accumulator. Hook observers are platform-specific listeners that convert LLM-platform events into observations.

**Multi-session design:** `mcp_server.py` maintains per-session `LiveAccumulator` and `TelemetryBridge` instances keyed by `session_id`. The `SessionStart` hook (`hook_session_start.py`) fires once when a Claude Code session begins, writes a human-readable name (`YYYY-MM-DD-<project>`) to `~/.archolith/sessions/<id>.name`, and pre-touches the session JSONL file. MCP tools scan all session files modified in the last 24h and display results per session by name.

## Key Components

| Module | Purpose |
|--------|---------|
| `cli.py` | Argparse CLI entry point |
| `attributor.py` | Tool name → MCP server mapping (configurable) |
| `tokenizer.py` | tiktoken integration for token counting |
| `waste_detector.py` | 6 waste pattern detectors |
| `report.py` | Report card generation (text, JSON, markdown) |
| `schema_estimator.py` | MCP tool schema token cost in system prompt |
| `comparator.py` | Before/after comparison mode |
| `mcp_server.py` | In-session MCP audit tool (summary/detail/check/bridge_status) |
| `accumulator.py` | Live per-session token accumulator (reads RTK telemetry) |
| `telemetry_bridge.py` | Connects telemetry sources (RTK, file, in-memory) to accumulator |
| `hook_observer.py` | Platform-specific hook observers (Claude Code, Codex, OpenCode) |
| `extractors/base.py` | SessionData dataclass + shared interface |
| `extractors/claude.py` | Claude JSONL extraction |
| `extractors/codex.py` | Codex JSONL extraction |
| `extractors/opencode.py` | OpenCode SQLite extraction |

### Waste Detectors

| Detector | Waste type | What it catches |
|----------|-----------|-----------------|
| Polling | `polling_waste` | Repeated calls with same args → unchanged result (e.g., gradle_job_status) |
| Oversized | `oversized_envelope`, `oversized_help` | JSON envelopes, large help text |
| Redundant fields | `redundant_fields`, `overbroad_query` | Overbroad JSON results, missing field filters |
| Schema cost | `schema` | Tool schema token overhead in system prompt |
| Format | `format_waste_json_table`, `format_waste_key_repetition` | JSON where CSV/key-value would be shorter |
| Cache breaker | `cache_breaker` | Content that changes per-turn but is semantically identical |

## Configuration / Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `MCP_AUDIT_SERVER_MAPPING` | Path to server mapping JSON | `data/server_mapping.json` |
| `MCP_AUDIT_SCHEMA_CATALOG` | Path to schema catalog JSON | `data/schema_catalog.json` |
| `MCP_AUDIT_MAX_SHARE` | CI: max per-server token share (%) | 20 |
| `MCP_AUDIT_MAX_TOTAL_MCP` | CI: max total MCP share (%) | 40 |
| `MCP_AUDIT_MAX_WASTE_PCT` | CI: max waste per server (%) | 50 |
| `MCP_AUDIT_RTK` | Connect to RTK FilterTelemetryStore | 0 (disabled) |
| `MCP_AUDIT_TELEMETRY_FILE` | Path to JSONL telemetry file | (none) |

## External Dependencies

| Dependency | Purpose | Required |
|------------|---------|----------|
| tiktoken | Token counting (OpenAI tokenizer proxy) | Yes (pip) |
| FastMCP | MCP server for in-session audit | Yes (pip) |
| archolith-rtk telemetry | FilterTelemetryStore for live accumulator | Optional (in-session mode only) |
| Claude/Codex/OpenCode session logs | Session data to audit | Required for CLI mode |

## Relationship to Other Archolith Projects

| Project | Relationship |
|---------|-------------|
| archolith-filter (archolith-rtk) | Shares extraction patterns. archolith-filter's FilterTelemetryStore feeds the live accumulator. Audit measures what filter compresses; filter compresses what audit flags. |
| archolith-proxy (archolith-context) | Audit is the L3 measurement layer; proxy is L4 session curation. Audit findings drive server-side fixes that reduce the token volume the proxy has to manage. |
| archolith-memory | Independent. Memory handles cross-session knowledge; audit handles per-session token measurement. |
| archolith.dev | Product site. Audit ships as a standalone product (Wave 2b). |
