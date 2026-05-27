# archolith-mcp-audit — Data Models

## Entities

### SessionData

Core container for an extracted session. Produced by extractors.

| Field | Type | Description |
|-------|------|-------------|
| `source` | `str` | `"claude"`, `"codex"`, or `"opencode"` |
| `session_id` | `str` | Session identifier from the log |
| `tool_calls` | `list[ToolCall]` | All tool invocations in the session |
| `tool_results` | `list[ToolResult]` | All tool results in the session |
| `system_prompt_tokens` | `int` | Estimated schema token cost |
| `total_turns` | `int` | Number of turns in the session |

### ToolCall

A single tool invocation (the request, not the response).

| Field | Type | Description |
|-------|------|-------------|
| `tool_name` | `str` | Full tool name (e.g., `mcp__vps__vps_status`) |
| `args` | `str` | JSON string of call arguments |
| `call_id` | `str` | ID for matching to result |
| `turn_number` | `int` | Sequence position in session |

### ToolResult

A single tool response.

| Field | Type | Description |
|-------|------|-------------|
| `tool_name` | `str` | Full tool name |
| `result_text` | `str` | Raw result content |
| `call_id` | `str` | ID matching to ToolCall |
| `turn_number` | `int` | Sequence position in session |

### TokenCount

Token measurement for a single result.

| Field | Type | Description |
|-------|------|-------------|
| `chars` | `int` | Character count |
| `bytes` | `int` | Byte count (UTF-8) |
| `tokens_cl100k` | `int` | Token count (cl100k_base encoding) |
| `tokens_o200k` | `int` | Token count (o200k_base encoding) |
| `chars_per_token_cl100k` | `float` | Efficiency ratio (cl100k) |
| `chars_per_token_o200k` | `float` | Efficiency ratio (o200k) |

## DTOs

### WasteFinding

A single waste detection result, attached to a server.

| Field | Type | Description |
|-------|------|-------------|
| `tool_name` | `str` | Tool that produced the waste |
| `server` | `str` | Canonical MCP server name |
| `waste_type` | `str` | One of: `polling`, `oversized`, `redundant_fields`, `schema`, `format`, `cache_breaker` |
| `severity` | `str` | One of: `low`, `medium`, `high`, `critical` |
| `tokens_wasted` | `int` | Estimated wasted tokens |
| `bytes_wasted` | `int` | Wasted bytes |
| `call_count` | `int` | Number of calls exhibiting this waste |
| `total_calls` | `int` | Total calls to this tool |
| `description` | `str` | Human-readable explanation |
| `suggestion` | `str` | Concrete server-side fix |
| `estimated_savings_pct` | `float` | Savings if fix applied (0-100) |
| `example_before` | `str` | Truncated example of wasteful output |
| `example_after` | `str` | What it could look like after fix |

### ServerReport

Per-server report card.

| Field | Type | Description |
|-------|------|-------------|
| `server` | `str` | Canonical MCP server name |
| `token_share` | `int` | Total tokens attributed to this server |
| `token_share_pct` | `float` | Share of total session tokens |
| `call_count` | `int` | Total tool calls |
| `tools` | `list[str]` | Tool names under this server |
| `findings` | `list[WasteFinding]` | Waste findings for this server |
| `estimated_recoverable_tokens` | `int` | Sum of recoverable tokens from findings |

### AuditReport

Full session audit report.

| Field | Type | Description |
|-------|------|-------------|
| `session` | `str` | Session identifier |
| `source` | `str` | Session source |
| `total_tokens` | `int` | Total tokens in session |
| `mcp_tokens` | `int` | Tokens attributed to MCP servers |
| `mcp_share_pct` | `float` | MCP share of total |
| `servers` | `dict[str, ServerReport]` | Per-server report cards |
| `top_optimizations` | `list[WasteFinding]` | Top 5 findings by impact |
| `total_recoverable_tokens` | `int` | Total estimated recoverable |
| `total_recoverable_pct` | `float` | Recoverable share of total |

### DeltaReport

Before/after comparison.

| Field | Type | Description |
|-------|------|-------------|
| `server` | `str` | Server being compared |
| `before` | `ServerReport` | Pre-optimization state |
| `after` | `ServerReport` | Post-optimization state |
| `token_change` | `int` | Absolute token change |
| `token_change_pct` | `float` | Percentage token change |
| `waste_change` | `int` | Absolute waste change |
| `waste_change_pct` | `float` | Percentage waste change |
| `regressions` | `list[WasteFinding]` | New waste introduced |

## Enums

### WasteType

| Value | Description |
|-------|-------------|
| `polling` | Repeated calls with unchanged results |
| `oversized` | Envelope overhead or oversized help text |
| `redundant_fields` | Overbroad results with unneeded fields |
| `schema` | Tool schema token overhead in system prompt |
| `format` | JSON where compact format would be shorter |
| `cache_breaker` | Semantically identical but textually different content |

### Severity

| Value | Description |
|-------|-------------|
| `low` | <10% of server tokens wasted |
| `medium` | 10-30% of server tokens wasted |
| `high` | 30-60% of server tokens wasted |
| `critical` | >60% of server tokens wasted |

### OutputFormat

| Value | Description |
|-------|-------------|
| `report` | Human-readable text report (default) |
| `json` | Structured JSON for programmatic use |
| `markdown` | Markdown for docs/PRs |

## Repository Reference

| Data | Storage | Access |
|------|---------|--------|
| Server mapping | `data/server_mapping.json` | Loaded by attributor |
| Schema catalog | `data/schema_catalog.json` | Loaded by schema_estimator |
| Session logs | External (Claude/Codex/OpenCode paths) | Read by extractors |
| Live telemetry | In-memory (RTK FilterTelemetryStore) | Read by accumulator |
