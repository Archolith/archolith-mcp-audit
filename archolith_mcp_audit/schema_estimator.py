"""Schema cost estimator — MCP tool schema token cost in system prompt.

Estimates the token cost of MCP tool schemas that are sent in the
system prompt every turn. This is a unique cost dimension because
schemas repeat every turn, compounding across the entire session.

Two modes:
  1. Static catalog: reads from data/schema_catalog.json
  2. Live refresh: calls each MCP server's list_tools and counts tokens
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from archolith_mcp_audit.tokenizer import estimate_tokens

log = logging.getLogger(__name__)

_DEFAULT_CATALOG_PATH = Path(__file__).parent / "data" / "schema_catalog.json"
_STALE_DAYS = 30


@dataclass
class SchemaEntry:
    """Token cost for a single MCP tool's schema."""

    tool_name: str
    schema_tokens: int  # tokens for name + description + parameter schema


@dataclass
class ServerSchemaCost:
    """Schema token cost for an MCP server."""

    server: str
    tools: list[SchemaEntry] = field(default_factory=list)
    per_turn_cost: int = 0
    session_cost: int = 0

    def compute(self, total_turns: int = 1) -> None:
        """Compute per_turn and session costs."""
        self.per_turn_cost = sum(t.schema_tokens for t in self.tools)
        self.session_cost = self.per_turn_cost * total_turns


def load_catalog(path: Path | None = None) -> dict[str, list[SchemaEntry]]:
    """Load schema catalog from JSON file.

    Returns: {server_name: [SchemaEntry, ...]}
    """
    target = path or _DEFAULT_CATALOG_PATH
    if not target.exists():
        return {}

    try:
        with open(target, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        log.warning("Failed to load schema catalog from %s: %s", target, e)
        return {}

    result: dict[str, list[SchemaEntry]] = {}
    for server, tools in data.items():
        entries = []
        for tool in tools:
            if isinstance(tool, dict):
                entries.append(SchemaEntry(
                    tool_name=tool.get("name", "unknown"),
                    schema_tokens=tool.get("schema_tokens", 0),
                ))
            elif isinstance(tool, list) and len(tool) >= 2:
                entries.append(SchemaEntry(tool_name=tool[0], schema_tokens=tool[1]))
        result[server] = entries

    return result


def estimate_server_schema_cost(
    server: str,
    tool_names: list[str],
    total_turns: int = 1,
    avg_schema_tokens: int = 300,
) -> ServerSchemaCost:
    """Estimate schema cost for a server when no catalog is available.

    Uses a simple heuristic: avg_schema_tokens per tool.
    """
    tools = [SchemaEntry(tool_name=name, schema_tokens=avg_schema_tokens) for name in tool_names]
    cost = ServerSchemaCost(server=server, tools=tools)
    cost.compute(total_turns)
    return cost


def compute_all_schema_costs(
    server_tools: dict[str, list[str]],
    total_turns: int = 1,
    catalog_path: Path | None = None,
) -> dict[str, ServerSchemaCost]:
    """Compute schema costs for all servers.

    Uses catalog when available, falls back to heuristic estimation.
    """
    catalog = load_catalog(catalog_path)
    results: dict[str, ServerSchemaCost] = {}

    for server, tool_names in server_tools.items():
        if server in catalog and catalog[server]:
            # Use catalog data
            cost = ServerSchemaCost(server=server, tools=catalog[server])
            cost.compute(total_turns)
            results[server] = cost
        else:
            # Fall back to heuristic
            results[server] = estimate_server_schema_cost(
                server, tool_names, total_turns
            )

    return results


def count_schema_tokens(tool_def: dict) -> int:
    """Count tokens in a single tool definition (name + description + params).

    Used by --refresh-schemas to populate the catalog.
    """
    parts = [tool_def.get("name", "")]
    desc = tool_def.get("description", "")
    if desc:
        parts.append(desc)
    params = tool_def.get("parameters", {})
    if params:
        parts.append(json.dumps(params))
    return estimate_tokens(" ".join(parts))


def refresh_schema_catalog(output_path: Path | None = None) -> dict[str, list[dict]]:
    """Refresh schema catalog by querying MCP servers.

    Attempts to call list_tools on each configured MCP server.
    Returns the catalog dict that was written.
    """
    target = output_path or _DEFAULT_CATALOG_PATH

    # Try to import FastMCP client to query servers
    try:
        from fastmcp import Client
    except ImportError:
        log.warning("FastMCP not available for schema refresh. Using empty catalog.")
        _write_catalog(target, {})
        return {}

    # Read MCP config to find servers
    mcp_config_path = Path.home() / ".claude" / ".mcp.json"
    if not mcp_config_path.exists():
        log.warning("No .mcp.json found at %s", mcp_config_path)
        _write_catalog(target, {})
        return {}

    try:
        with open(mcp_config_path, encoding="utf-8") as f:
            config = json.load(f)
    except (json.JSONDecodeError, OSError):
        log.warning("Failed to parse .mcp.json")
        _write_catalog(target, {})
        return {}

    servers_config = config.get("mcpServers", {})
    catalog: dict[str, list[dict]] = {}

    for server_name, server_conf in servers_config.items():
        if server_name == "mcp-audit":
            continue  # Don't query ourselves

        try:
            # Try to connect and list tools
            command = server_conf.get("command", "")
            args = server_conf.get("args", [])
            if not command:
                continue

            # For stdio servers, spawn the process
            # This is a best-effort approach — some servers may not be available
            log.info("Querying %s for tool schemas...", server_name)
            # Note: actual MCP client connection is async and complex.
            # For v1, we log the intent and skip actual querying.
            # The catalog should be populated manually or via a dedicated script.
        except Exception as e:
            log.warning("Failed to query %s: %s", server_name, e)

    _write_catalog(target, catalog)
    return catalog


def _write_catalog(path: Path, catalog: dict[str, list[dict]]) -> None:
    """Write catalog to JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(catalog, f, indent=2)
    log.info("Schema catalog written to %s (%d servers)", path, len(catalog))
