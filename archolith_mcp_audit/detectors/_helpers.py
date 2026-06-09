"""Shared helper functions for waste pattern detectors."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Public data structures
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


# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------

_HELP_PATTERN = re.compile(r"(?:usage|help|options|flags|commands)\s*[:\-]", re.IGNORECASE)
_JSON_ENVELOPE_KEYS = frozenset({"status", "ok", "success", "error", "meta", "metadata", "info", "version"})
_OVERBROAD_TOOLS = frozenset({
    "query_structure", "recall_memories", "artifact_read",
    "mcp__memory__query_structure", "mcp__memory__recall_memories",
    "mcp__workspace-artifacts__artifact_read",
})
_EPHEMERAL_PATTERNS = [
    re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"),  # ISO timestamps
    re.compile(r"\d+\s*(?:ms|s|min|hr|days?)\b"),  # Durations
    re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.IGNORECASE),  # UUIDs
    re.compile(r"uptime[:\s]+\d+", re.IGNORECASE),  # Uptime counters
]
_SHORT_STRING_BYTES = 40


# ---------------------------------------------------------------------------
# Severity
# ---------------------------------------------------------------------------


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
# Similarity
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


# ---------------------------------------------------------------------------
# Help / envelope detection
# ---------------------------------------------------------------------------


def _is_help_text(text: str) -> bool:
    """Detect help/usage text."""
    if len(text) < 200:
        return False
    lines = text.split("\n")
    flag_lines = sum(1 for line in lines if line.strip().startswith("--") or line.strip().startswith("-"))
    header_lines = sum(1 for line in lines if _HELP_PATTERN.search(line))
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


def _extract_payload_from_json(text: str) -> object | None:
    """Extract the payload object from a JSON envelope.

    Looks for common payload keys (data, result, results, output, body, content)
    and returns the first one found. Returns None if not a dict or no payload found.
    """
    try:
        obj = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(obj, dict):
        return None

    payload_keys = {"data", "result", "results", "output", "body", "content"}
    for key in payload_keys:
        if key in obj:
            return obj[key]

    return None


def _envelope_overhead_tokens(text: str) -> int:
    """Estimate token overhead from JSON envelope."""
    payload = _extract_payload_from_json(text)
    if payload is None:
        return 0

    from archolith_mcp_audit.tokenizer import estimate_tokens
    full_tokens = estimate_tokens(text)
    payload_tokens = estimate_tokens(json.dumps(payload))
    return max(0, full_tokens - payload_tokens)


def _envelope_overhead_bytes(text: str) -> int:
    """Estimate byte overhead from JSON envelope."""
    payload = _extract_payload_from_json(text)
    if payload is None:
        return 0

    full_bytes = len(text.encode("utf-8"))
    payload_bytes = len(json.dumps(payload).encode("utf-8"))
    return max(0, full_bytes - payload_bytes)


# ---------------------------------------------------------------------------
# JSON field counting
# ---------------------------------------------------------------------------


def _count_json_fields(text: str) -> int:
    """Count total fields in a JSON result. Returns 0 for non-JSON (e.g. plain text)."""
    try:
        obj = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return 0

    if not isinstance(obj, (dict, list)):
        return 0

    def _count(o: object) -> int:
        if isinstance(o, dict):
            return sum(1 + _count(v) for v in o.values())
        if isinstance(o, list):
            return sum(_count(item) for item in o)
        return 0

    return _count(obj)


def _trimmable_fraction(text: str) -> float:
    """Fraction of a JSON result's bytes held in metadata-like (trimmable) leaves.

    Numbers, booleans, nulls, and short scalar strings are treated as trimmable
    metadata. Long strings (>= _SHORT_STRING_BYTES) are treated as content the model
    needs and are excluded. Returns 0.0 for non-JSON or content-dominated results.
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
                not isinstance(o, str)
                or len(o) < _SHORT_STRING_BYTES
            )
            if is_metadata:
                trimmable[0] += length

    _walk(obj)
    if total[0] == 0:
        return 0.0
    return trimmable[0] / total[0]


# ---------------------------------------------------------------------------
# Format overhead
# ---------------------------------------------------------------------------


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
        all_keys: set[str] = set()
        for item in obj:
            all_keys.update(item.keys())
        shared_keys = all_keys
        for item in obj:
            if set(item.keys()) != shared_keys:
                shared_keys = set(item.keys()) & set(item.keys())
                break

        if len(shared_keys) > 2 and len(obj) > 2:
            json_len = len(text)
            csv_len = len(",".join(shared_keys)) + 1
            for item in obj:
                vals = [str(item.get(k, "")) for k in shared_keys]
                csv_len += len(",".join(vals)) + 1
            if json_len > 0:
                return min(0.8, max(0.0, 1 - csv_len / json_len))

    # For dicts with repeated key prefixes
    if isinstance(obj, dict) and len(obj) > 5:
        json_len = len(text)
        kv_len = sum(len(str(k)) + len(str(v)) + 2 for k, v in obj.items())
        if json_len > 0:
            return min(0.6, max(0.0, 1 - kv_len / json_len))

    return 0.0


# ---------------------------------------------------------------------------
# Ephemeral normalization
# ---------------------------------------------------------------------------


def _normalize_ephemeral(text: str) -> str:
    """Replace ephemeral values (timestamps, UUIDs, durations) with placeholders."""
    result = text
    for pattern in _EPHEMERAL_PATTERNS:
        result = pattern.sub("[EPHEMERAL]", result)
    return result
