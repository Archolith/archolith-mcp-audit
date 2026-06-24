"""Configuration for heuristic detector thresholds."""

from __future__ import annotations

import json
from functools import lru_cache
from importlib.resources import files
from typing import Any

_DEFAULTS: dict[str, Any] = {
    "estimated_savings_pct": {
        "help_text": 90.0,
        "format_json": 45.0,
        "cache_breaker": 40.0,
        "schema_lazy_load": 60.0,
    },
    "field_thresholds": {
        "default": 10,
        "overbroad_tool": 6,
    },
    "overbroad_tools": [
        "query_structure",
        "recall_memories",
        "artifact_read",
        "mcp__memory__query_structure",
        "mcp__memory__recall_memories",
        "mcp__workspace-artifacts__artifact_read",
    ],
}


@lru_cache(maxsize=1)
def load_heuristic_config() -> dict[str, Any]:
    """Load bundled heuristic thresholds, falling back to defaults."""
    try:
        path = files("archolith_mcp_audit.data").joinpath("heuristic_thresholds.json")
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, ModuleNotFoundError):
        return _DEFAULTS

    merged = dict(_DEFAULTS)
    for key in ("estimated_savings_pct", "field_thresholds"):
        merged[key] = {**_DEFAULTS[key], **data.get(key, {})}
    merged["overbroad_tools"] = data.get("overbroad_tools", _DEFAULTS["overbroad_tools"])
    return merged


def savings_pct(name: str) -> float:
    """Return the configured savings percentage for a detector assumption."""
    return float(load_heuristic_config()["estimated_savings_pct"][name])


def overbroad_tools() -> frozenset[str]:
    """Return configured tool names that are known to over-return fields."""
    return frozenset(str(tool) for tool in load_heuristic_config()["overbroad_tools"])


def field_threshold(tool_name: str) -> int:
    """Return the configured redundant-field threshold for a tool."""
    thresholds = load_heuristic_config()["field_thresholds"]
    key = "overbroad_tool" if tool_name in overbroad_tools() else "default"
    return int(thresholds[key])
