# Changelog — archolith-audit

## 2026-05-27 — Naming and doc pass

- Renamed public product from `archolith-mcp-audit` to `archolith-audit` across all surfaces
- `pyproject.toml`: distribution name and CLI entry point updated (`archolith-audit` command)
- `mcp_server.py`: FastMCP display name updated to `"archolith-audit"`
- `data/server_mapping.json`: self-attribution keys updated from `mcp__mcp-audit` to `mcp__archolith-audit`
- `mcp-registry.json`: server keys renamed in both WSL and Windows sections; `.mcp.json` regenerated
- `README.md`: expanded from 9-line stub to full public README with usage examples, MCP tool output samples, CI gate docs, and configuration table
- `.agent/architecture.md`: relationship table updated to reflect full product family (archolith-filter, archolith-proxy, archolith-memory) and wave placement (Wave 2b)
- Added to archolith product suite as L3 measurement layer (slate gray #6b7280) in product-map.md
- Resolved product home question in archolith-questions.md

## 2026-05-21 — Full implementation (11-step plan complete)

- `attributor.py`: tool name → MCP server mapping, configurable via JSON, fallback to `non-mcp`
- `tokenizer.py`: tiktoken integration (cl100k_base + o200k_base), batch tokenization, chars/token ratio
- `waste_detector.py`: six waste pattern detectors (polling, oversized, redundant fields, schema cost, format waste, cache breaker); WasteFinding dataclass with severity, tokens_wasted, suggestion, estimated_savings_pct
- `report.py`: per-server report cards in text, JSON, and markdown formats; AuditReport and ServerReport dataclasses
- `comparator.py`: before/after comparison mode; DeltaReport with regression detection
- `ci.py`: threshold pass/fail check; exit code 2 on threshold breach
- `schema_estimator.py`: MCP tool schema token cost estimation from system prompt
- `accumulator.py`: LiveAccumulator — passive in-session per-server token aggregation; reads from FilterTelemetryStore when available
- `mcp_server.py`: FastMCP in-session server with three tools (mcp_audit_summary, mcp_audit_detail, mcp_audit_check); disabled by default (MCP_AUDIT_ENABLED=1 required)
- `extractors/claude.py`: Claude JSONL session extractor
- `extractors/codex.py`: Codex JSONL session extractor
- `extractors/opencode.py`: OpenCode SQLite session extractor
- `cli.py`: full argparse CLI — --claude, --codex, --opencode, --all, --format, --servers, --min-severity, --max-results, --compare, --ci, --refresh-schemas
- `data/server_mapping.json`: seeded with all known workspace servers
- Tests for all modules: attributor, tokenizer, waste_detector, report, comparator, ci, accumulator, mcp_server, extractors, schema_estimator

## 2026-05-XX — Initial project setup

- Created project skeleton with `.agent/` documentation
- Added LLM instruction files (CLAUDE.md, AGENTS.md, QWEN.md, gemini.md)
- Established pyproject.toml with hatchling build, tiktoken + fastmcp dependencies
- Added pytest and ruff dev dependencies
