# Plugin Runtime Verification Checklist

The code side of all four plugins is complete (see `PLUGIN_STATUS.md`). What
remains can only be done by installing each plugin into a **live agent session**
and exercising it. This checklist gives exact commands. Run it to move each
plugin from `MVP` to `Beta`.

Covers the non-code tasks from `archolith-audit-plugins-remaining-work-plan.md`
(Phase 1 runtime verification, Phase 2 env-var substitution, Phase 3 Gemini
external checks, Phase 4 OpenCode build/publish, Phase 5 Claude skill/install).

---

## 0. Shared preconditions

```bash
# From repo root
cd projects/archolith/archolith-mcp-audit
pip install -e ".[dev]"            # package importable for MCP server
rm -rf ~/.archolith/sessions/*.jsonl   # start clean so counts are unambiguous
```

Standalone plugin repos include a bundled `archolith_mcp_audit/` package plus
`requirements.txt`. For split-repo runtime tests, install those requirements into
the Python environment used by the agent before launching the MCP server.

A successful run leaves per-session JSONL files here:

```bash
ls -la ~/.archolith/sessions/
# each line must be: {"tool_name":...,"raw_chars":N,...,"session_id":...}
# NOT the legacy {"tool":...,"chars":...,"ts":...} shape
```

Quick parser sanity-check on any session file:

```bash
python -c "
from pathlib import Path; import sys
from archolith_mcp_audit.telemetry_bridge import FileTelemetrySource
f = Path.home()/'.archolith'/'sessions'/sys.argv[1]
for e in FileTelemetrySource(f).pull():
    print(e.tool_name, e.raw_chars, e.session_id)
" <session_file>.jsonl
```

---

## 1. Phase 1 — Runtime verification (all four plugins)

For each plugin: install via local path, run **5+ tool calls** in a real
session, then call `mcp_audit_summary`. PASS = per-server token data returned,
not "no data".

### 1.1 Claude Code
```bash
python plugins/claude/install.py --project "$(pwd)"
# Restart Claude Code in this project so it loads the plugin + MCP server.
# In the session: run 5+ tool calls (Read/Bash/an MCP tool), then:
#   call mcp_audit_summary
```
- [ ] `mcp_audit_summary` returns per-server rows
- [ ] `~/.archolith/sessions/<id>.jsonl` present and non-empty
- [ ] `<id>.name` file written by SessionStart hook

### 1.2 Codex
```bash
# Configure Codex to load plugins/codex (local path).
# CODEX_PLUGIN_DIR must resolve to plugins/codex so the MCP server gets PYTHONPATH.
# Run 5+ tool calls, then call mcp_audit_summary.
```
- [ ] Summary returns real data
- [ ] Session file keyed `codex-YYYYMMDD-HH` (no session ID injected — expected)

### 1.3 Gemini CLI
```bash
# Install plugins/gemini as a Gemini CLI extension (local path).
# Run 5+ tool calls, then call mcp_audit_summary.
```
- [ ] Summary returns real data
- [ ] `hooks/after-tool.js` fired (session file growing)

### 1.4 OpenCode
```bash
cd plugins/opencode && npm run build && cd -
# Add plugins/opencode to opencode.json "plugins" (local path).
# Run 5+ tool calls, then call mcp_audit_summary.
```
- [ ] Summary returns real data
- [ ] In-process `tool.execute.after` fires without perceptible latency

---

## 2. Phase 2 — Env-var substitution

Confirm each agent resolves its plugin-dir variable so the MCP server finds the
Python package. FAIL symptom: `mcp_audit_summary` errors / "can't find package".

- [ ] Claude: `${CLAUDE_PLUGIN_DIR}` / `${CLAUDE_PLUGIN_ROOT}` resolved in `plugin.json`
- [ ] Codex: `${CODEX_PLUGIN_DIR}` resolved in `plugin.json` MCP `env.PYTHONPATH`
- [ ] Gemini: `${GEMINI_PLUGIN_DIR}` resolved in `extension.json`
- [ ] OpenCode: plugin-dir/env resolved in `opencode.json` MCP config
- [ ] **Codex hook** writes observations (standalone script; needs no PYTHONPATH —
      verify the file appears after a tool call)

---

## 3. Phase 3 — Gemini external checks

Require current Gemini CLI docs or a live install.

- [ ] AfterTool payload field names confirmed against
      `geminicli.com/docs/hooks/reference/` (currently assumes
      `tool_name`/`tool_result`/`session_id`)
- [ ] `extension.json` is the correct manifest filename + schema
- [ ] Latency: 100 tool calls with vs without hook; target < 5 ms/call
      ```bash
      # rough timing harness
      time (for i in $(seq 100); do echo '{"tool_name":"x","tool_result":"y"}' \
        | node plugins/gemini/hooks/after-tool.js >/dev/null; done)
      ```
- [ ] Session-ID field availability documented (else hour-based fallback noted)

---

## 4. Phase 4 — OpenCode build/publish

- [ ] `cd plugins/opencode && npm run build` exits 0; `dist/index.js` regenerated
- [ ] Local-path install via `opencode.json` `plugins` works
- [ ] Bun preserves bundled non-JS assets during `bun install` (if Bun path used)
- [ ] (Optional) publish `@archolith/archolith-audit-plugin-opencode` to npm

---

## 5. Phase 5 — Claude skill + installer

- [ ] `/audit` skill discovered and invokable in a Claude Code session
      (`plugins/claude/skills/audit/SKILL.md`)
- [ ] `python plugins/claude/install.py --path <dir>` (global) works
- [ ] `python plugins/claude/install.py --project <dir>` works

---

## 6. Phase 6 — Close-out

- [ ] Update each plugin README with verified behavior (env var, session ID, gaps)
- [ ] Update `PLUGIN_STATUS.md` maturity column: MVP -> Beta per verified plugin
- [ ] Confirm `dist/` regenerated from the same core commit as plugin source
      before any publish (`python scripts/release.py check`)

---

## Release hygiene reminder

The repo carries broad source/test changes between release points. Before
publishing any plugin, cut a clean release commit and regenerate `dist/`
directories from it — do not publish from a dirty tree.
