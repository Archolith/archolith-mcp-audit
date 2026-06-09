"""Waste pattern detection — re-exports from detectors/ package.

Kept for backward compatibility. New code should import from
archolith_mcp_audit.detectors directly.
"""

from archolith_mcp_audit.detectors import WasteFinding, detect_waste  # noqa: F401
from archolith_mcp_audit.detectors._helpers import (  # noqa: F401
    _count_json_fields,
    _envelope_overhead_bytes,
    _envelope_overhead_tokens,
    _has_json_envelope,
    _is_help_text,
    _json_format_overhead,
    _normalize_ephemeral,
    _similarity,
    _trimmable_fraction,
)

__all__ = ["WasteFinding", "detect_waste"]
