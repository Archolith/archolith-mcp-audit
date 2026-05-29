# Baseline Token Audit — All Sessions

**Date:** 2026-05-28
**Tool:** `archolith_mcp_audit.cli --all --format json`
**Tokenizer:** tiktoken `cl100k_base` (OpenAI tokenizer used as Anthropic proxy; no public
Anthropic tokenizer exists — see Limitations)
**Scope:** 224 sessions (Claude + Codex), 60,388 tool results
**Raw data:** `.tmp/audit-all.json` (224 concatenated per-session JSON reports)
**Clears TODO:** `2b291a40` — run tiktoken/Anthropic tokenizer analysis over actual tool
result content from Claude/Codex/OpenCode logs.

## Method

`--all` produces one report per session (224 reports). Those were aggregated per server
across all sessions:

- `token_share` summed = actual measured result tokens that entered model context
- `call_count` summed = total calls to that server
- `findings[].tokens_wasted` summed by `waste_type`, **excluding `schema`** (the `schema`
  finding is a per-turn extrapolation, e.g. `300 tokens/turn x 5000 turns`, which inflates
  to billions and is not a measured per-result cost — tracked separately, not counted here)

## Headline

| Metric | Value |
|---|--:|
| Total tool-result tokens | 62,134,538 |
| MCP server share | 7,917,392 (12%) |
| Non-MCP share (Read/Bash/Edit/etc.) | 54,217,146 (88%) |
| Recoverable MCP result-waste (excl. schema) | ~1,902,087 (24% of MCP) |

MCP traffic is only 12% of total result tokens. Of that, roughly a quarter is recoverable
through field filtering and polling/delta modes.

## Per-server ranking (by actual result-token share of MCP)

| Server | Tokens | %MCP | Calls | Sessions | Top recoverable result-waste |
|---|--:|--:|--:|--:|---|
| harness | 4,293,189 | 54% | 1,417 | 17 | polling 162,257; redundant_fields 139,039 |
| vps | 1,145,890 | 14% | 5,445 | 29 | polling 144,742; redundant_fields 16,765; oversized 7,919 |
| workspace-artifacts | 938,585 | 11% | 867 | 61 | redundant_fields 608,102; polling 27,398; oversized 8,794 |
| delegate | 658,798 | 8% | 491 | 11 | polling 308,658; redundant_fields 81,999 |
| memory | 455,656 | 5% | 762 | 77 | redundant_fields 153,299; polling 31,168 |
| gradle | 254,542 | 3% | 953 | 10 | polling 154,393; oversized 11,044 |
| yawn_memory | 70,988 | 0% | 169 | 11 | polling 3,982; cache_breaker 1,024 |
| sage-wiki | 49,759 | 0% | 66 | 3 | redundant_fields 20,170; oversized 5,302 |
| yawn-memory | 22,786 | 0% | 84 | 4 | polling 869; cache_breaker 444 |
| plannerific | 13,276 | 0% | 29 | 7 | polling 6,349 |
| sage_wiki | 4,944 | 0% | 2 | 2 | - |
| workspace_artifacts | 4,268 | 0% | 10 | 2 | redundant_fields 377; oversized 156 |
| facebook_parent_group_discovery | 3,327 | 0% | 10 | 3 | redundant_fields 1,459; polling 204 |
| archolith-audit | 1,161 | 0% | 19 | 2 | - |
| cloudflare | 223 | 0% | 1 | 1 | - |

## Recoverable result-waste by type (excl. schema)

| Waste type | Tokens | Share |
|---|--:|--:|
| redundant_fields | 1,021,210 | 54% |
| polling | 841,182 | 44% |
| oversized | 35,127 | 2% |
| cache_breaker | 3,492 | <1% |
| format | 1,076 | <1% |
| **Total** | **1,902,087** | |

**Two patterns are 98% of all recoverable waste:** `redundant_fields` (full objects returned
when few fields are used) and `polling` (repeated calls returning near-identical results).

## Findings / action items

1. **harness is 54% of all MCP token spend** (4.29M tokens). It is the single highest-impact
   optimization target. Confirms existing TODO `d7249232` (harness_get_session /
   harness_watch_session dump too much). Apply field filtering + delta/status-only polling.
2. **workspace-artifacts redundant_fields = 608k** is the largest single waste line, and it
   is our own server. The compact-mode + line-range reading work shipped 2026-05-28
   (commit `b20dca8`) targets exactly this — re-audit after it appears in real sessions to
   measure the delta.
3. **vps, delegate, gradle are polling-heavy** (145k / 309k / 154k). They need delta or
   status-only modes for repeated status/list calls.
4. **Server-name dedup bug in `data/server_mapping.json`**: `yawn_memory`/`yawn-memory`,
   `sage-wiki`/`sage_wiki`, `workspace-artifacts`/`workspace_artifacts` are each split into
   two attribution entries by underscore/hyphen inconsistency. Fragments attribution; should
   be normalized.

## Recommended optimization order (feeds TODO `95a6c8d1`)

1. harness — field filtering on get_session/watch_session + polling delta mode (~300k recoverable)
2. vps — status-only/delta polling mode (~145k)
3. delegate — polling delta mode (~309k)
4. gradle — polling delta mode (~154k)
5. memory — field filtering on query_structure results (~153k)
6. workspace-artifacts — verify the 2026-05-28 compact/line-range changes reduce the 608k

## Limitations

- **No true Anthropic tokenizer.** Anthropic does not publish one. `cl100k_base` (and
  `o200k_base`) are OpenAI tokenizers used as proxies; absolute counts are estimates within
  ~10-15% of Anthropic's real tokenization. Relative rankings between servers are reliable.
- **Ground-truth provider usage not yet pulled** (separate TODO `f7dd2b09`): comparing these
  estimates against Anthropic/OpenAI billing usage logs (prompt/completion/cached tokens)
  would calibrate the proxy. Not done here.
- **`schema` overhead excluded** from waste totals — its per-turn `x N turns` extrapolation is
  not a measured per-result cost and dominates the numbers if included. Re-evaluate that
  metric's formula separately.
