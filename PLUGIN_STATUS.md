# archolith-audit — Plugin Status

Per-plugin maturity, known gaps, and install instructions for the four agent
plugins. Single source of truth for users evaluating which plugins to use.

**Maturity legend:** `MVP` = code-complete, not yet runtime-verified against a
live agent · `Beta` = runtime-verified, minor gaps · `Stable` = verified +
published.

| Plugin | Dir | Maturity | Hook schema | Runtime-verified |
|--------|-----|----------|-------------|------------------|
| Claude Code | `plugins/claude/` | MVP | OK (package `hook_observer_standalone.py`) | No |
| Codex | `plugins/codex/` | MVP | OK (fixed 2026-06-08) | No |
| Gemini CLI | `plugins/gemini/` | MVP | OK (fixed 2026-06-08) | No |
| OpenCode | `plugins/opencode/` | MVP | OK (fixed 2026-06-08) | No |

## Telemetry JSONL schema (all plugins)

Every hook adapter appends one JSON object per tool result to
`~/.archolith/sessions/<session_id>.jsonl`. The MCP server's
`FileTelemetrySource.pull()` requires these keys:

```json
{"tool_name": "...", "raw_tokens": 0, "raw_chars": 0,
 "filtered_tokens": 0, "filtered_chars": 0,
 "timestamp": 0.0, "session_id": "..."}
```

`timestamp` is epoch **seconds** (matches Python `time.time()`). Standalone
hooks cannot run tiktoken, so `raw_tokens`/`filtered_tokens` are `0` and the
char counts carry the signal. Earlier builds wrote a compact
`{"tool","chars","ts"}` shape that `FileTelemetrySource` silently misparsed
(`tool_name="unknown"`, `raw_chars=0`); the Codex, Gemini, and OpenCode
adapters were corrected on 2026-06-08.

## Per-plugin notes

### Claude Code — `plugins/claude/`
- **Install:** `python plugins/claude/install.py --path plugins/claude`
  (global) or `--project <path>` (project-scoped).
- **Hook:** PostToolUse → `hook_observer_standalone.py` (already canonical schema).
- **Skill:** `/audit` at `plugins/claude/skills/audit/SKILL.md`.
- **MCP env:** `MCP_AUDIT_ENABLED=1`, `PYTHONPATH=${CLAUDE_PLUGIN_DIR}`.
- **Gaps:** `/audit` skill discovery and `install.py` both modes untested in a
  live session (Plan B Phase 5).

### Codex — `plugins/codex/`
- **Install:** local path via Codex plugin config; MCP server runs
  `python -m archolith_mcp_audit.mcp_server` with `PYTHONPATH=${CODEX_PLUGIN_DIR}`.
- **Hook:** `hooks/hooks.json` → `python ${CODEX_PLUGIN_DIR}/hook_observer_codex.py`
  (standalone, no package import — `PYTHONPATH` only needed by the MCP server,
  not the hook).
- **Session ID:** Codex does not inject a session ID into hook env; falls back
  to an hour-based key `codex-YYYYMMDD-HH`.
- **Gaps:** not runtime-verified (Plan B Phase 1).

### Gemini CLI — `plugins/gemini/`
- **Install:** local path via Gemini CLI extension config.
- **Hook:** `hooks/after-tool.js` (Node).
- **Gaps (external verification required):**
  - AfterTool payload field names (`tool_name`/`tool_result`) assumed — confirm
    against `geminicli.com/docs/hooks/reference/`.
  - `extension.json` manifest filename/schema not validated against official docs.
  - Hook latency not measured.
  - Session-ID field availability unconfirmed; hour-based fallback in place.

### OpenCode — `plugins/opencode/`
- **Install:** local path via `opencode.json` `plugins`, or publish
  `@archolith/opencode-plugin` to npm.
- **Build:** `npm run build` (tsc) → `dist/index.js`. Rebuilt 2026-06-08.
- **Hook:** in-process `tool.execute.after` event; `sessionId` from plugin context.
- **Gaps:** not runtime-verified; Bun asset preservation untested; npm publish
  pending (Plan B Phases 1, 4).

## Known design decisions

- **MCP server scans all recent sessions** (`~/.archolith/sessions/*.jsonl`
  modified in the last 24h) rather than binding to a single forwarded session
  ID. `MCP_AUDIT_SESSION_ID` is intentionally not read. A single-session
  handoff would be a UX change, not a bug fix — deferred unless scoping output
  to the invoking session becomes a requirement (Plan B Phase 2.6).

See `.agent/workflows/plugin_runtime_verification.md` for the step-by-step
runtime-verification procedure that moves each plugin from MVP to Beta.
