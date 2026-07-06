# Changelog — archolith-audit

## 2026-07-05 — Ignore local agent runtime configuration

- Added `.claude/` session/agent state and `.mcp.json` to `.gitignore` so local runtime configuration does not
  enter the project history.

## 2026-06-21 — Audit Remediation Sessions A/B/C/D/E/G/H

- Fixed the CF-1 CLI import blocker by importing `_load_mapping` from `attributor.py`; added CLI smoke tests and synced/rebuilt plugin bundles.
- Completed the safe-fix docs/package batch: removed the deprecated license classifier, excluded generated plugin/dist trees from Ruff, added third-party license notes, documented naming/privacy/env vars, and added empty schema-catalog warnings.
- Hardened session file paths with sanitization plus atomic JSONL/text writes in hook/session paths; added regression tests for path safety and hook subprocess execution.
- Added report-output tokenizer disclosures in text, JSON, and Markdown formats.
- Documented the trusted `.mcp.json` env model and added secret-like env key warnings during schema refresh.
- Added CLI flag coverage, hook-script subprocess tests, and defensive `mcp_audit_detail` handling for partial summary payloads.
- Added a 30-second TTL cache for active session scans in `mcp_server.py`.
- Tightened polling detection so byte-identical repeats are high-confidence waste while similar-but-changing loops are low-confidence informational findings; added `confidence` metadata to findings.
- Finished the remaining heuristic/performance pass: detector savings assumptions now load from bundled config, findings carry evidence IDs for overlapping recovery deduplication, report outputs cap serialized finding lists, schema refresh queries servers concurrently, repeated token counting uses a bounded cache, and Claude/Codex JSONL extractors parse each file once.

## 2026-06-21 — Shared Token Counting Primitive

- Routed audit text token counting through `archolith-maintenance` while preserving the existing `TokenCount` report shape and explicit-encoding test path.
- Added `archolith-maintenance` as the shared helper dependency for canonical token accounting.

## 2026-06-08 — audit-remediation closeout + plugin telemetry schema fix

- Completed the remaining items of `archolith-mcp-audit-remediation-plan` after a
  WIP checkpoint had already landed Phases 1-4, 6.1, 7.1/7.2/7.6/7.8/7.9/7.10, 8:
  added `__all__` to the public modules and extractors (with
  `extract_{claude,codex,opencode}_session` re-exports), renamed the product to
  `archolith-audit` in `schema_estimator` docstrings and LLM instruction headers,
  and swept the last stale `RTK` references in current docs to `archolith-filter`
  (env table now lists `MCP_AUDIT_FILTER` preferred, `MCP_AUDIT_RTK` legacy alias).
- Won't-fix (documented): `SESSIONS_DIR` dedup (7.7) and envelope-overhead helper
  dedup (7.4). The standalone hooks are intentionally zero-package-import and
  copied into each plugin bundle; `_extract_payload_from_json` is already shared.
- Plugin telemetry fix: the Codex, Gemini, and OpenCode hook adapters wrote a
  compact `{"tool","chars","ts"}` object that `FileTelemetrySource` silently
  misparsed; all three now emit the canonical `tool_name/raw_*/filtered_*/`
  `timestamp/session_id` schema (verified end-to-end through `FileTelemetrySource`).
- Added `PLUGIN_STATUS.md` and `.agent/workflows/plugin_runtime_verification.md`
  (step-by-step live-agent verification checklist).
- Verification: `ruff check archolith_mcp_audit tests` PASS; `pytest tests/ -q`
  PASS (175/175). `pyright` NOT RUN (not installed).

## 2026-06-02 — remediation follow-up: refresh contract and verification closeout

- Added real FastMCP-path refresh tests in `tests/test_schema_estimator.py` for success, partial failure, and all-fail scenarios, replacing the prior `_refresh_all_servers`-only coverage gap.
- Updated `SchemaRefreshResult.total_servers` semantics in `schema_estimator.py` and `.agent/data_models.md` to count only refresh-eligible servers (self and non-stdio entries excluded).
- Fixed `telemetry_bridge.py` warning text so fallback diagnostics report `raw_tokens` / `filtered_tokens` instead of incorrectly saying `using 0`; added regression coverage in `tests/test_telemetry_bridge.py`.
- Fixed lingering Ruff drift in `hook_observer_codex.py`.
- Verification: `python -m ruff check archolith_mcp_audit tests` PASS; `TMP/TEMP=C:\tmp python -m pytest tests/ -q` PASS (`175/175`).

## 2026-06-02 — Quality remediation: god-file split, shared rendering, config cleanup

- **Phase 1**: Split `waste_detector.py` (736 LOC god file) into `detectors/` package with one file per detector plus `_helpers.py`. Original file remains as backward-compatible re-export shim. All 22 waste detector tests pass.
- **Phase 2**: Extracted `_build_server_summaries()` shared rendering in `report.py`. `format_report_text` and `format_report_markdown` now use a common intermediate representation. All 6 report tests pass with identical output.
- **Phase 3**: Enhanced `refresh_schema_catalog()` to return `SchemaRefreshResult` with per-server success/failure info. CLI now prints per-server status when refreshing schemas.
- **Phase 4**: Replaced hardcoded Windows user paths in `cli.py --all` with `CLAUDE_PROJECTS_DIR`, `CODEX_SESSIONS_DIR`, and `OPENCODE_DB` env vars (with `Path.home()` fallbacks). Also fixed `claude_dir` to scan all project subdirectories.
- **Phase 5**: Added diagnostic logging when RTK telemetry entries are missing required fields (`tool_name`, `raw_chars`, `filtered_chars`). Warns once per field per batch.
- **Phase 6**: Normalized comparator thresholds from raw `±100` token magic numbers to configurable percentage-based (`regression_threshold_pct`, default 20%).
- **Phase 0**: Consolidated 3 `run_server()` definitions into one, fixed tautological `__main__.py` docstring, added NOTE about tiktoken duplication in `hook_observer_standalone.py`.
- **Lint**: Ruff check passes cleanly. 172/172 tests pass at the time of this phase wrapup.

## 2026-05-29 — redundant_fields detector accuracy fix

- `waste_detector._detect_redundant_fields` no longer flags text-returning tools. It now
  requires a genuine JSON field count above threshold; `_count_json_fields` returns 0 for
  non-JSON and bare scalars. Fixes the `query_structure` false positive (was the #1
  redundant_fields source at ~92k, but it returns lean formatted text, not JSON).
- Replaced the flat 50/70% recoverable assumption with a measured byte ratio
  (`_trimmable_fraction`): metadata-like leaves (numbers, bools, short scalar strings) count
  as trimmable; long content strings do not. Results dominated by a large text field now
  score near 0% instead of 70%. Estimate capped at 50%.
- Description now reports the representative (max) field count instead of the last result's
  count (fixes the misleading "~1 fields").
- Tests: 3 added in `test_waste_detector.py` (156 total pass).

## 2026-05-28 — Multi-session bridge and SessionStart naming hook

- Added `hook_session_start.py`: standalone SessionStart hook — fires once per session, writes `~/.archolith/sessions/<session_id>.name` (human-readable label from CWD basename + date) and pre-touches the session JSONL file
- Updated `mcp_server.py`: replaced singleton `_accumulator`/`_bridge` with per-session dicts keyed by `session_id`; added `list_active_sessions()` (scans last 24h JSONL files), `get_session_name()`, `get_accumulator(session_id)`, `get_bridge(session_id)`; all four MCP tools now iterate all active sessions and display per-session named output
- Updated `scripts/install.py`: added `SESSION_START_HOOK_SRC`/`CLAUDE_SESSION_START_DEST` constants; `install_claude()` now also installs and registers the SessionStart hook; `uninstall_claude()` removes it; `--check` shows SessionStart hook status
- Installed `~/.claude/hooks/archolith-audit-session-start.py` and registered in `settings.json` `SessionStart` block
- 153 tests passing

## 2026-05-27 — Telemetry bridge and hook observers

- Added `telemetry_bridge.py`: TelemetryBridge, RtkTelemetrySource, FileTelemetrySource, InMemoryTelemetrySource
- Added `hook_observer.py`: HookObserver, ClaudeCodeHookObserver, CodexHookObserver, OpenCodeHookObserver
- Updated `mcp_server.py`: integrated TelemetryBridge, added mcp_audit_bridge_status tool, added get_bridge()
- Added `tests/test_telemetry_bridge.py` and `tests/test_hook_observer.py`
- Updated architecture.md, data_models.md, code_conventions.md

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
