"""Waste pattern detection — 6 detectors for MCP token waste.

Detectors:
  3a. Polling waste — repeated calls with unchanged results
  3b. Oversized results — envelope overhead, help text bloat
  3c. Redundant field output — overbroad queries, missing field filters
  3d. Schema cost — tool schema token overhead in system prompt
  3e. Format waste — JSON where CSV/key-value would be shorter
  3f. Cache breaker — content that changes but is semantically identical
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from archolith_mcp_audit.attributor import attribute_tool
from archolith_mcp_audit.extractors.base import SessionData, ToolResult
from archolith_mcp_audit.tokenizer import count_tokens, TokenCount, estimate_tokens


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class WasteFinding:
    """A single waste detection result."""

    tool_name: str
    server: str
    waste_type: str  # polling, oversized, redundant_fields, schema, format, cache_breaker
    severity: str  # low, medium, high, critical
    tokens_wasted: int
    bytes_wasted: int
    call_count: int
    total_calls: int
    description: str
    suggestion: str
    estimated_savings_pct: float
    example_before: str = ""
    example_after: str = ""


def _severity_for_waste_pct(pct: float) -> str:
    """Map waste percentage to severity level."""
    if pct > 0.6:
        return "critical"
    if pct > 0.3:
        return "high"
    if pct > 0.1:
        return "medium"
    return "low"


def _truncate(text: str, max_len: int = 200) -> str:
    """Truncate text for example display."""
    if len(text) <= max_len:
        return text
    return text[:max_len] + "..."


# ---------------------------------------------------------------------------
# 3a. Polling Waste Detector
# ---------------------------------------------------------------------------

def _detect_polling(
    tool_results: list[ToolResult],
    tool_calls_by_id: dict[str, dict],
    server_mapping: dict[str, str] | None,
) -> list[WasteFinding]:
    """Detect repeated calls with same/unchanged results (polling waste)."""
    # Group results by tool name
    by_tool: dict[str, list[ToolResult]] = {}
    for r in tool_results:
        by_tool.setdefault(r.tool_name, []).append(r)

    findings: list[WasteFinding] = []

    for tool_name, results in by_tool.items():
        if len(results) < 3:
            continue  # Need at least 3 calls to detect polling

        server = attribute_tool(tool_name, server_mapping)
        if server == "non-mcp":
            continue  # Polling waste is primarily an MCP issue

        # Count how many results are near-identical to the previous one
        redundant = 0
        redundant_tokens = 0
        redundant_bytes = 0
        example_before = ""

        prev_text = ""
        for r in results:
            # Check if this result is >80% similar to previous
            if prev_text and _similarity(prev_text, r.result_text) > 0.8:
                redundant += 1
                tc = count_tokens(r.result_text)
                redundant_tokens += tc.tokens_cl100k
                redundant_bytes += tc.bytes
                if not example_before:
                    example_before = _truncate(r.result_text)
            prev_text = r.result_text

        if redundant > 0:
            total_calls = len(results)
            waste_pct = redundant / total_calls
            total_tokens = sum(count_tokens(r.result_text).tokens_cl100k for r in results)

            findings.append(WasteFinding(
                tool_name=tool_name,
                server=server,
                waste_type="polling",
                severity=_severity_for_waste_pct(waste_pct),
                tokens_wasted=redundant_tokens,
                bytes_wasted=redundant_bytes,
                call_count=redundant,
                total_calls=total_calls,
                description=f"{redundant}/{total_calls} calls ({waste_pct:.0%}) return "
                            f"near-identical results (polling waste)",
                suggestion="Return delta on poll, not full replay. "
                           "Add status-only mode for polling queries.",
                estimated_savings_pct=min(90.0, waste_pct * 100),
                example_before=example_before,
                example_after="[status: running, duration: 42s, 2 new lines since last check]",
            ))

    return findings


# ---------------------------------------------------------------------------
# 3b. Oversized Results Detector
# ---------------------------------------------------------------------------

_HELP_PATTERN = re.compile(r"(?:usage|help|options|flags|commands)\s*[:\-]", re.IGNORECASE)
_JSON_ENVELOPE_KEYS = frozenset({"status", "ok", "success", "error", "meta", "metadata", "info", "version"})


def _detect_oversized(
    tool_results: list[ToolResult],
    server_mapping: dict[str, str] | None,
) -> list[WasteFinding]:
    """Detect oversized results — envelope overhead, help text bloat."""
    by_tool: dict[str, list[ToolResult]] = {}
    for r in tool_results:
        by_tool.setdefault(r.tool_name, []).append(r)

    findings: list[WasteFinding] = []

    for tool_name, results in by_tool.items():
        server = attribute_tool(tool_name, server_mapping)
        if server == "non-mcp":
            continue

        # Check for help text bloat
        help_results = [r for r in results if _is_help_text(r.result_text)]
        if len(help_results) >= 1 and len(results) > 0:
            help_tokens = sum(count_tokens(r.result_text).tokens_cl100k for r in help_results)
            help_bytes = sum(len(r.result_text.encode("utf-8")) for r in help_results)

            findings.append(WasteFinding(
                tool_name=tool_name,
                server=server,
                waste_type="oversized",
                severity=_severity_for_waste_pct(help_tokens / max(1, sum(
                    count_tokens(r.result_text).tokens_cl100k for r in results
                ))),
                tokens_wasted=int(help_tokens * 0.9),  # ~90% of help is waste
                bytes_wasted=int(help_bytes * 0.9),
                call_count=len(help_results),
                total_calls=len(results),
                description=f"{len(help_results)} calls return help/usage text "
                            f"({help_tokens:,} tokens)",
                suggestion="Default to one-line summary; add --verbose flag "
                           "for full help text.",
                estimated_savings_pct=90.0,
                example_before=_truncate(help_results[0].result_text),
                example_after="[tool: help available, use --verbose for details]",
            ))

        # Check for JSON envelope overhead
        envelope_results = [r for r in results if _has_json_envelope(r.result_text)]
        if len(envelope_results) >= 2:
            envelope_tokens = sum(
                _envelope_overhead_tokens(r.result_text) for r in envelope_results
            )
            envelope_bytes = sum(
                _envelope_overhead_bytes(r.result_text) for r in envelope_results
            )

            if envelope_tokens > 100:
                findings.append(WasteFinding(
                    tool_name=tool_name,
                    server=server,
                    waste_type="oversized",
                    severity="medium",
                    tokens_wasted=envelope_tokens,
                    bytes_wasted=envelope_bytes,
                    call_count=len(envelope_results),
                    total_calls=len(results),
                    description=f"{len(envelope_results)} results have JSON envelope "
                                f"overhead ({envelope_tokens:,} tokens)",
                    suggestion="Strip envelope in compact mode. Return data "
                               "directly without wrapping status/meta.",
                    estimated_savings_pct=min(50.0, envelope_tokens / max(1, sum(
                        count_tokens(r.result_text).tokens_cl100k for r in results
                    )) * 100),
                    example_before=_truncate(envelope_results[0].result_text, 300),
                    example_after='{"key": "value", ...}',
                ))

    return findings


# ---------------------------------------------------------------------------
# 3c. Redundant Field Output Detector
# ---------------------------------------------------------------------------

_OVERBROAD_TOOLS = frozenset({
    "query_structure", "recall_memories", "artifact_read",
    "mcp__memory__query_structure", "mcp__memory__recall_memories",
    "mcp__workspace-artifacts__artifact_read",
})


def _detect_redundant_fields(
    tool_results: list[ToolResult],
    server_mapping: dict[str, str] | None,
) -> list[WasteFinding]:
    """Detect overbroad results with unneeded fields."""
    by_tool: dict[str, list[ToolResult]] = {}
    for r in tool_results:
        by_tool.setdefault(r.tool_name, []).append(r)

    findings: list[WasteFinding] = []

    for tool_name, results in by_tool.items():
        server = attribute_tool(tool_name, server_mapping)
        if server == "non-mcp":
            continue

        # Known structured tools get a lower field threshold, but ONLY when their
        # result is genuinely JSON. Text-returning tools yield field_count == 0 and
        # are never flagged (fixes the query_structure false positive).
        threshold = 6 if tool_name in _OVERBROAD_TOOLS else 10

        overbroad = 0
        overbroad_tokens = 0
        overbroad_bytes = 0
        max_field_count = 0
        trimmable_sum = 0.0
        example = ""

        for r in results:
            field_count = _count_json_fields(r.result_text)
            if field_count > threshold:
                overbroad += 1
                tc = count_tokens(r.result_text)
                overbroad_tokens += tc.tokens_cl100k
                overbroad_bytes += tc.bytes
                max_field_count = max(max_field_count, field_count)
                trimmable_sum += _trimmable_fraction(r.result_text)
                if not example:
                    example = _truncate(r.result_text, 300)

        if overbroad > 0:
            total_calls = len(results)
            waste_pct = overbroad / total_calls

            # Estimate recoverable share from the measured fraction of bytes held in
            # metadata-like leaves, averaged over the overbroad results, capped at 50%.
            # This replaces the old flat 50/70% assumption, which overstated savings
            # for results dominated by a single large content field.
            avg_trimmable = trimmable_sum / overbroad
            est_waste_pct = round(min(50.0, avg_trimmable * 100), 1)

            if est_waste_pct <= 0:
                continue  # nothing measurably trimmable

            suggestion = ("Accept fields parameter to return only requested "
                           "data. Return graph nodes, not entire structure.")
            if tool_name in _OVERBROAD_TOOLS:
                suggestion = ("Add fields= parameter to return only requested "
                              "graph nodes or memory fields, not entire structure.")

            findings.append(WasteFinding(
                tool_name=tool_name,
                server=server,
                waste_type="redundant_fields",
                severity=_severity_for_waste_pct(waste_pct),
                tokens_wasted=int(overbroad_tokens * est_waste_pct / 100),
                bytes_wasted=int(overbroad_bytes * est_waste_pct / 100),
                call_count=overbroad,
                total_calls=total_calls,
                description=f"{overbroad}/{total_calls} calls return overbroad "
                            f"results ({overbroad_tokens:,} tokens, up to {max_field_count} fields)",
                suggestion=suggestion,
                estimated_savings_pct=est_waste_pct,
                example_before=example,
                example_after="[filtered fields only, as requested]",
            ))

    return findings


# ---------------------------------------------------------------------------
# 3d. Schema Cost Detector
# ---------------------------------------------------------------------------

def _detect_schema_cost(
    tool_results: list[ToolResult],
    server_mapping: dict[str, str] | None,
    total_turns: int = 1,
) -> list[WasteFinding]:
    """Estimate tool schema token cost in the system prompt.

    This is a heuristic — we don't extract schemas from session logs.
    We estimate based on distinct tool names per server and assume
    ~300 tokens per tool schema (conservative average).
    """
    by_server: dict[str, set[str]] = {}

    for r in tool_results:
        server = attribute_tool(r.tool_name, server_mapping)
        if server == "non-mcp":
            continue
        by_server.setdefault(server, set()).add(r.tool_name)

    if not by_server:
        return []

    findings: list[WasteFinding] = []
    AVG_SCHEMA_TOKENS = 300

    for server, tools in by_server.items():
        tool_count = len(tools)
        per_turn_cost = tool_count * AVG_SCHEMA_TOKENS
        session_cost = per_turn_cost * total_turns

        if session_cost > 1000:  # Only report if meaningful
            findings.append(WasteFinding(
                tool_name=f"{server} (schemas)",
                server=server,
                waste_type="schema",
                severity="medium" if per_turn_cost > 2000 else "low",
                tokens_wasted=int(session_cost * 0.6),  # ~60% is repeated overhead
                bytes_wasted=0,
                call_count=tool_count,
                total_calls=tool_count,
                description=f"{tool_count} tool schemas at ~{AVG_SCHEMA_TOKENS} tokens each "
                            f"= {per_turn_cost:,} tokens/turn x {total_turns} turns "
                            f"= {session_cost:,} tokens total",
                suggestion="Lazy-load schemas after first call. "
                           "Abbreviate to name+1-line-description thereafter.",
                estimated_savings_pct=60.0,
                example_before=f"[{server}: {tool_count} full tool schemas, "
                               f"{per_turn_cost} tokens/turn]",
                example_after=f"[{server}: {tool_count} abbreviated schemas, "
                              f"~{tool_count * 30} tokens/turn]",
            ))

    return findings


# ---------------------------------------------------------------------------
# 3e. Format Waste Detector
# ---------------------------------------------------------------------------

def _detect_format_waste(
    tool_results: list[ToolResult],
    server_mapping: dict[str, str] | None,
) -> list[WasteFinding]:
    """Detect JSON where CSV/key-value would be more token-efficient."""
    by_tool: dict[str, list[ToolResult]] = {}
    for r in tool_results:
        by_tool.setdefault(r.tool_name, []).append(r)

    findings: list[WasteFinding] = []

    for tool_name, results in by_tool.items():
        server = attribute_tool(tool_name, server_mapping)
        if server == "non-mcp":
            continue

        format_waste = 0
        format_waste_tokens = 0
        format_waste_bytes = 0
        example = ""

        for r in results:
            overhead = _json_format_overhead(r.result_text)
            if overhead > 0.3:  # >30% format overhead
                format_waste += 1
                tc = count_tokens(r.result_text)
                waste_tokens = int(tc.tokens_cl100k * overhead)
                format_waste_tokens += waste_tokens
                format_waste_bytes += int(tc.bytes * overhead)
                if not example:
                    example = _truncate(r.result_text, 300)

        if format_waste > 0 and format_waste_tokens > 100:
            total_calls = len(results)
            findings.append(WasteFinding(
                tool_name=tool_name,
                server=server,
                waste_type="format",
                severity="medium",
                tokens_wasted=format_waste_tokens,
                bytes_wasted=format_waste_bytes,
                call_count=format_waste,
                total_calls=total_calls,
                description=f"{format_waste} results with JSON format overhead "
                            f"(key repetition, structural markup)",
                suggestion="Support _compact=true parameter to return "
                           "key-value lines or CSV instead of JSON objects.",
                estimated_savings_pct=45.0,
                example_before=example,
                example_after="key1=value1\nkey2=value2\n...",
            ))

    return findings


# ---------------------------------------------------------------------------
# 3f. Cache Breaker Detector
# ---------------------------------------------------------------------------

_EPHEMERAL_PATTERNS = [
    re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"),  # ISO timestamps
    re.compile(r"\d+\s*(?:ms|s|min|hr|days?)\b"),  # Durations
    re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.IGNORECASE),  # UUIDs
    re.compile(r"uptime[:\s]+\d+", re.IGNORECASE),  # Uptime counters
]


def _detect_cache_breakers(
    tool_results: list[ToolResult],
    server_mapping: dict[str, str] | None,
) -> list[WasteFinding]:
    """Detect content that changes between calls but is semantically identical."""
    by_tool: dict[str, list[ToolResult]] = {}
    for r in tool_results:
        by_tool.setdefault(r.tool_name, []).append(r)

    findings: list[WasteFinding] = []

    for tool_name, results in by_tool.items():
        server = attribute_tool(tool_name, server_mapping)
        if server == "non-mcp":
            continue

        if len(results) < 2:
            continue

        # Check if consecutive results differ only in ephemeral values
        cache_breaks = 0
        cache_break_tokens = 0
        example = ""

        for i in range(1, len(results)):
            prev_norm = _normalize_ephemeral(results[i - 1].result_text)
            curr_norm = _normalize_ephemeral(results[i].result_text)

            if prev_norm == curr_norm and results[i - 1].result_text != results[i].result_text:
                cache_breaks += 1
                tc = count_tokens(results[i].result_text)
                cache_break_tokens += tc.tokens_cl100k
                if not example:
                    example = _truncate(results[i].result_text, 300)

        if cache_breaks > 0:
            total_calls = len(results)
            findings.append(WasteFinding(
                tool_name=tool_name,
                server=server,
                waste_type="cache_breaker",
                severity="medium" if cache_breaks > 3 else "low",
                tokens_wasted=int(cache_break_tokens * 0.4),  # ~40% cache cost
                bytes_wasted=0,
                call_count=cache_breaks,
                total_calls=total_calls,
                description=f"{cache_breaks} calls change only in timestamps/UUIDs, "
                            f"preventing prompt caching",
                suggestion="Normalize ephemeral values (timestamps, UUIDs, "
                           "durations) to stable placeholders for cache hits.",
                estimated_savings_pct=40.0,
                example_before=example,
                example_after="[same content with [TIMESTAMP]/[UUID] placeholders]",
            ))

    return findings


# ---------------------------------------------------------------------------
# Main detection function
# ---------------------------------------------------------------------------

def detect_waste(
    session: SessionData,
    server_mapping: dict[str, str] | None = None,
) -> list[WasteFinding]:
    """Run all waste detectors on a session and return findings."""
    # Build call_id -> tool call lookup for polling detection
    calls_by_id: dict[str, dict] = {
        tc.call_id: {"tool_name": tc.tool_name, "args": tc.args, "turn": tc.turn_number}
        for tc in session.tool_calls
    }

    findings: list[WasteFinding] = []

    findings.extend(_detect_polling(session.tool_results, calls_by_id, server_mapping))
    findings.extend(_detect_oversized(session.tool_results, server_mapping))
    findings.extend(_detect_redundant_fields(session.tool_results, server_mapping))
    findings.extend(_detect_schema_cost(
        session.tool_results, server_mapping, session.total_turns
    ))
    findings.extend(_detect_format_waste(session.tool_results, server_mapping))
    findings.extend(_detect_cache_breakers(session.tool_results, server_mapping))

    return findings


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _similarity(a: str, b: str) -> float:
    """Compute simple Jaccard similarity on word sets."""
    words_a = set(a.split())
    words_b = set(b.split())
    if not words_a and not words_b:
        return 1.0
    if not words_a or not words_b:
        return 0.0
    intersection = words_a & words_b
    union = words_a | words_b
    return len(intersection) / len(union)


def _is_help_text(text: str) -> bool:
    """Detect help/usage text."""
    if len(text) < 200:
        return False
    # Help text typically has many lines with --flags or Usage:/Options: sections
    lines = text.split("\n")
    flag_lines = sum(1 for l in lines if l.strip().startswith("--") or l.strip().startswith("-"))
    header_lines = sum(1 for l in lines if _HELP_PATTERN.search(l))
    return flag_lines > 3 or header_lines > 2


def _has_json_envelope(text: str) -> bool:
    """Detect JSON with an envelope (status, data, meta keys)."""
    try:
        obj = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return False
    if not isinstance(obj, dict):
        return False
    return bool(_JSON_ENVELOPE_KEYS & set(obj.keys()))


def _envelope_overhead_tokens(text: str) -> int:
    """Estimate token overhead from JSON envelope."""
    try:
        obj = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return 0
    if not isinstance(obj, dict):
        return 0

    # Find the "data" or "result" key — that's the payload
    payload_keys = {"data", "result", "results", "output", "body", "content"}
    payload = None
    for key in payload_keys:
        if key in obj:
            payload = obj[key]
            break

    if payload is None:
        return 0

    full_tokens = estimate_tokens(text)
    payload_tokens = estimate_tokens(json.dumps(payload))
    return max(0, full_tokens - payload_tokens)


def _envelope_overhead_bytes(text: str) -> int:
    """Estimate byte overhead from JSON envelope."""
    try:
        obj = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return 0
    if not isinstance(obj, dict):
        return 0

    payload_keys = {"data", "result", "results", "output", "body", "content"}
    payload = None
    for key in payload_keys:
        if key in obj:
            payload = obj[key]
            break

    if payload is None:
        return 0

    full_bytes = len(text.encode("utf-8"))
    payload_bytes = len(json.dumps(payload).encode("utf-8"))
    return max(0, full_bytes - payload_bytes)


def _count_json_fields(text: str) -> int:
    """Count total fields in a JSON result. Returns 0 for non-JSON (e.g. plain text)."""
    try:
        obj = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return 0

    # A bare scalar (number/string/bool) is not a structured result.
    if not isinstance(obj, (dict, list)):
        return 0

    def _count(o: object) -> int:
        if isinstance(o, dict):
            return sum(1 + _count(v) for v in o.values())
        if isinstance(o, list):
            return sum(_count(item) for item in o)
        return 0

    return _count(obj)


# Scalar / short-string leaves are "metadata-like" and trimmable; long strings are
# content the model usually needs and are NOT counted as recoverable.
_SHORT_STRING_BYTES = 40


def _trimmable_fraction(text: str) -> float:
    """Fraction of a JSON result's bytes held in metadata-like (trimmable) leaves.

    Numbers, booleans, nulls, and short scalar strings are treated as trimmable
    metadata. Long strings (>= _SHORT_STRING_BYTES) are treated as content the model
    needs and are excluded. Returns 0.0 for non-JSON or content-dominated results.

    This replaces a flat 50/70% assumption with a measured byte ratio, so a result
    dominated by one large text field is correctly scored as having little to trim.
    """
    try:
        obj = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return 0.0
    if not isinstance(obj, (dict, list)):
        return 0.0

    total = [0]
    trimmable = [0]

    def _walk(o: object) -> None:
        if isinstance(o, dict):
            for k, v in o.items():
                klen = len(str(k))
                total[0] += klen
                _walk(v)
        elif isinstance(o, list):
            for item in o:
                _walk(item)
        else:
            length = len(json.dumps(o, default=str))
            total[0] += length
            is_metadata = (
                not isinstance(o, str)  # numbers, bools, null
                or len(o) < _SHORT_STRING_BYTES  # short scalar strings
            )
            if is_metadata:
                trimmable[0] += length

    _walk(obj)
    if total[0] == 0:
        return 0.0
    return trimmable[0] / total[0]


def _json_format_overhead(text: str) -> float:
    """Estimate format overhead ratio for JSON content.

    Compares JSON string length to a hypothetical key-value representation.
    """
    try:
        obj = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return 0.0

    if not isinstance(obj, (dict, list)):
        return 0.0

    # For a list of same-key objects, estimate CSV savings
    if isinstance(obj, list) and len(obj) > 2 and all(isinstance(item, dict) for item in obj):
        # Check if all objects share the same keys
        all_keys: set[str] = set()
        for item in obj:
            all_keys.update(item.keys())
        shared_keys = all_keys
        for item in obj:
            if set(item.keys()) != shared_keys:
                shared_keys = set(item.keys()) & set(item.keys())
                break

        if len(shared_keys) > 2 and len(obj) > 2:
            # CSV header + rows would be much shorter
            json_len = len(text)
            # Rough CSV estimate: keys as header + values per row
            csv_len = len(",".join(shared_keys)) + 1  # header
            for item in obj:
                vals = [str(item.get(k, "")) for k in shared_keys]
                csv_len += len(",".join(vals)) + 1
            if json_len > 0:
                return min(0.8, max(0.0, 1 - csv_len / json_len))

    # For dicts with repeated key prefixes
    if isinstance(obj, dict) and len(obj) > 5:
        json_len = len(text)
        # Dotted key representation: "key1=val1\nkey2=val2\n..."
        kv_len = sum(len(str(k)) + len(str(v)) + 2 for k, v in obj.items())
        if json_len > 0:
            return min(0.6, max(0.0, 1 - kv_len / json_len))

    return 0.0


def _normalize_ephemeral(text: str) -> str:
    """Replace ephemeral values (timestamps, UUIDs, durations) with placeholders."""
    result = text
    for pattern in _EPHEMERAL_PATTERNS:
        result = pattern.sub("[EPHEMERAL]", result)
    return result
