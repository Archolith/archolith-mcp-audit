# Delegate — Token Usage Analysis

**Date:** 2026-05-29
**Source:** archolith-audit per-tool drill-down over Claude sessions.
**Context:** The baseline audit flagged `delegate` at 658k server-level tokens (8% of MCP,
491 calls, 11 sessions) with a large polling component. This doc explains what actually
drives that number.

## Headline: it is almost entirely `browse_like_human`

Per-tool breakdown of delegate result tokens (Claude sessions, inner tool resolved through
the gateway):

| Inner tool | Result tokens | Calls | Sessions | Top single session |
|---|--:|--:|--:|--:|
| browse_like_human | 192,687 | 106 | 3 | 183,588 |
| delegate_task | 7,908 | 34 | 6 | 7,361 |
| search_tools | 313 | 1 | 1 | 313 |
| extract_page | 70 | 1 | 1 | 70 |
| vps_job_status | 20 | 1 | 1 | 20 |
| **Total** | **200,998** | | | |

Two facts dominate:

1. **`browse_like_human` is ~96% of delegate's token usage** (192.7k of 201k).
2. **It is concentrated in one session** — 183.6k of the 192.7k (95%) came from a single
   heavy browsing/scraping session. It is an episodic workload, not steady-state cost.

`delegate_task` — the actual code-delegation feature this server exists for — is cheap:
7.9k tokens over 34 calls (~232 tokens/call). It is not a token problem.

> Note on the 658k vs 201k gap: the baseline server-level figure includes Codex sessions and
> gateway-wrapper accounting; this Claude-only inner-tool capture maps each gateway call to its
> underlying tool. The relative conclusion is identical either way — browse_like_human dominates.

## Why browse_like_human is expensive

`browse_like_human(url, ..., include_html=False, max_chars=12000, extract_selectors=None,
extract_tables=None)` returns, per call: `ok, requested_url, final_url, title,
browser_channel, user_agent, actions (structured log), text, meta`.

- The `text` field is the extracted page text, capped at **`max_chars=12000` (~3,000 tokens)
  by default**. With `include_html=True` the raw HTML is returned on top of that.
- A scraping workflow makes many calls (navigate, scroll, click, re-read), each returning up
  to ~3k tokens. Consecutive calls on the same page overlap heavily, which is why the audit's
  polling detector also flagged it (near-identical results between actions on one page).

So the cost is inherent to the tool's job (returning page content), amplified by call volume
in dedicated scraping sessions — not a defect or a leak.

## Assessment: not a systemic target

Unlike the job-status polling fixes (gradle/vps) which were steady-state across many sessions,
browse_like_human cost is episodic and confined to occasional scraping sessions. It does not
warrant a redesign. The tool already ships the right levers to control its own output:

- `max_chars` — lower it (e.g. 3000–4000) when only a summary or specific data is needed.
- `extract_selectors` / `extract_tables` — return only targeted DOM/table data instead of the
  full page `text` dump.
- `include_html=False` (default) — keep HTML off unless structure is actually required.
- `write_html_to_file` — spill full HTML to a file instead of into the model context.

## Recommendation

No code change. The mitigation is usage discipline in scraping sessions: prefer
`extract_selectors`/`extract_tables` for targeted reads and a lower `max_chars` when the full
page body is not needed. If browse-heavy sessions become routine rather than occasional,
revisit defaulting `max_chars` lower or returning a content summary with an opt-in full-text
flag — but the current data does not justify that yet.
