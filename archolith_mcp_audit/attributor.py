"""Server attribution — maps tool names to canonical MCP server names."""

from __future__ import annotations

import json
from pathlib import Path

# Default mapping baked into the package
_DEFAULT_MAPPING_PATH = Path(__file__).parent / "data" / "server_mapping.json"

# Well-known non-MCP tool names (native LLM tools)
_NON_MCP_TOOLS = frozenset({
    "Read", "Write", "Edit", "Bash", "PowerShell", "Grep", "Glob",
    "WebSearch", "WebFetch", "Agent", "AskUserQuestion", "Monitor",
    "ToolSearch", "view_image", "search", "execute",
    "read", "write", "edit", "bash", "grep", "glob",
    "webfetch", "websearch", "task", "skill", "todowrite",
})


def _load_mapping(path: Path | None = None) -> dict[str, str]:
    """Load server mapping from JSON config file."""
    target = path or _DEFAULT_MAPPING_PATH
    if target.exists():
        with open(target, encoding="utf-8") as f:
            return json.load(f)
    return {}


def attribute_tool(tool_name: str, mapping: dict[str, str] | None = None) -> str:
    """Return canonical MCP server name, or 'non-mcp' for native tools.

    The mapping keys are prefixes (e.g., "mcp__memory") that match
    against the start of tool_name. Longer prefixes are tried first
    to avoid partial matches.
    """
    if mapping is None:
        mapping = _load_mapping()

    # Quick check: known non-MCP tools
    base_name = tool_name.split("__")[-1] if "__" in tool_name else tool_name
    if base_name in _NON_MCP_TOOLS or tool_name in _NON_MCP_TOOLS:
        return "non-mcp"

    # Sort by prefix length descending so longer prefixes match first
    sorted_patterns = sorted(mapping.items(), key=lambda x: len(x[0]), reverse=True)

    for pattern, server in sorted_patterns:
        if tool_name.startswith(pattern):
            return server

    # If it has an mcp__ prefix but no mapping, extract server from name
    if tool_name.startswith("mcp__"):
        parts = tool_name.split("__")
        if len(parts) >= 3:
            return parts[1]  # mcp__<server>__<tool>

    return "non-mcp"


def attribute_results(
    tool_results: list[tuple[str, str]],
    mapping: dict[str, str] | None = None,
) -> dict[str, list[tuple[str, str]]]:
    """Group tool results by MCP server.

    Returns: {server_name: [(tool_name, result_text), ...]}
    """
    groups: dict[str, list[tuple[str, str]]] = {}
    for tool_name, result_text in tool_results:
        server = attribute_tool(tool_name, mapping)
        groups.setdefault(server, []).append((tool_name, result_text))
    return groups
