# Polling Waste Reduction — Investigation & Design

**Date:** 2026-05-28
**Follow-up to:** `2026-05-28-baseline-token-audit.md`, TODO `89237b0e`
**Source data:** `archolith-audit` polling detector run per-tool across all Claude sessions.

## What "polling waste" is

The detector (`waste_detector._detect_polling`) flags a tool called >=3 times where
consecutive results are >80% similar. The wasted tokens are the near-identical repeats.

## Culprits (polling waste by tool, Claude sessions)

| Tool | Wasted | Redundant/Total | Sessions | Category |
|---|--:|--:|--:|---|
| gradle_job_status | 154,123 | 651/855 | 8 | A — design (full replay) |
| delegate browse_like_human | 138,586 | 77/101 | 1 | D — single-session anomaly |
| vps call_tool | 86,650 | 1697/4046 | 14 | B — gateway dispatch |
| harness_delete_session | 26,314 | 31/36 | 1 | D — single-session anomaly |
| artifact_read | 26,285 | 6/71 | 6 | C — static re-reads |
| harness_get_session_snapshot | 23,554 | 40/269 | 6 | A — discoverability |
| vps_gateway | 22,896 | 293/544 | 3 | B — gateway dispatch |
| memory query_structure | 15,460 | 7/35 | 2 | C — static re-reads |
| (others) | <11k each | | | mixed |

## Two root causes

1. **Design — full state replayed on every poll.** `gradle_job_status` returned the entire
   accumulated build log (`'\n'.join(output_lines)`) on every call. Polling a 800-line build
   10x sends ~8,000 lines, ~90% redundant. Same shape in `vps_service_logs` and status calls
   routed through `vps call_tool` / `vps_gateway`.
2. **Discoverability — the right tool exists but is not used.** Harness already has
   `harness_watch_session(sessionId, cursorPosition)` (cursor-based incremental output), but
   agents reach for `harness_get_session_snapshot` / `_screen`, which return the full last-N
   lines every time.

## The reusable pattern: cursor / since-line polling

Three workspace tools already solve this correctly: `artifact_read(offset_line)`,
`telemetry_bridge.read_observations(since_line)`, `harness_watch_session(cursorPosition)`.
The job/status tools just never adopted it. Three mechanisms, by leverage:

| Mechanism | Behavior | Win | Risk |
|---|---|--:|---|
| Cursor delta | `since_line` param -> return only new output + `next_line` cursor | ~90% | low (additive) |
| `status_only` mode | return status/exit/cursor only, no output (~15 tokens) | high on "is it done" loops | low |
| Long-poll | `wait_seconds` blocks until status/output changes -> 1 call replaces N | collapses the loop | medium (blocking semantics) |

## Reference implementation (shipped): gradle_job_status

`projects/ctharvey/cth.agentsmith/mcp_servers/gradle_server.py` — `get_job_status` now accepts
`since_line: int = 0` and `status_only: bool = False`:

- `since_line` returns only `output_lines[since_line:]`; response carries `next_line` (cursor),
  `total_lines`, `new_lines_count`. Default `since_line=0` returns the full log (backward
  compatible first poll); subsequent polls pass the returned `next_line` and get only deltas.
- `status_only=True` omits output entirely.
- Tool schema + the "Job started" messages now instruct agents to pass `since_line=<next_line>`
  or `status_only=true` on each poll.
- Tests: `test_gradle_server.py` (8 tests). Cursor delta alone recovers ~90% of the 154k.

Long-poll (`wait_seconds`) was deferred — cursor delta + status_only capture the bulk at low
risk; blocking semantics can be added later if needed.

## Reference implementation (shipped): vps_job_status

Per-tool drill-down showed the real vps polling culprit is **`vps_job_status`** (203k tokens
over 2,199 calls) — same async-poll pattern as gradle: running streaming jobs replayed the
last-50-line tail every poll, completed jobs replayed the full output.

`projects/yawn/yawn.vps/vps/jobs.py` — `job_status` now accepts `since_line` and `status_only`:

- Added a monotonic `lines_emitted` counter so the cursor stays valid even as the live buffer
  (capped at 500 lines, oldest dropped) rolls. Running jobs return only `live_lines` after the
  cursor; if the cursor predates the retained buffer, all retained lines are returned with a note.
- Done/non-streaming jobs slice the final `output` by line; `next_line` is the total line count.
- `status_only=True` omits output entirely. Default `since_line=0` preserves the first-poll
  full view (backward compatible).
- `vps_server.py` `vps_job_status` tool threads both params through with updated docstring.
- `vps_service_logs` already has a timestamp-based `since` param for incremental tailing — no
  change needed; the log-tail polling is a usage/discoverability matter.
- Tests: 7 added in `tests/test_vps_server.py` (38 total pass).

## Remaining per-server work (TODO 89237b0e)

- **harness snapshot/screen (~28k)** — DISCOVERABILITY. Steer polling to existing
  `harness_watch_session`; update `harness_get_session_snapshot` / `_screen` docstrings to point
  at the cursor tool.
- **memory query_structure / artifact_read re-reads (~42k, Category C)** — not a server-output
  problem. These are re-reads of static content; mitigated by client-side discipline / a
  "you already read this" hint, not a delta mode.
- **delegate browse_like_human (138k), harness_delete_session (26k)** — Category D, single
  session each. Not systemic; skip.
