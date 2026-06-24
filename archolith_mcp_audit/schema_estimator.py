"""Schema cost estimator — MCP tool schema token cost in system prompt.

Estimates the token cost of MCP tool schemas that are sent in the
system prompt every turn. This is a unique cost dimension because
schemas repeat every turn, compounding across the entire session.

Two modes:
  1. Static catalog: reads from data/schema_catalog.json
  2. Live refresh: calls each MCP server's list_tools and counts tokens
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

from archolith_mcp_audit.detectors.schema_cost import AVG_SCHEMA_TOKENS
from archolith_mcp_audit.tokenizer import estimate_tokens

log = logging.getLogger(__name__)

__all__ = [
    "SchemaEntry",
    "ServerSchemaCost",
    "SchemaRefreshResult",
    "refresh_schema_catalog",
    "load_catalog",
    "estimate_server_schema_cost",
    "compute_all_schema_costs",
    "count_schema_tokens",
]

_DEFAULT_CATALOG_PATH = Path(__file__).parent / "data" / "schema_catalog.json"
_STALE_DAYS = 30
_PER_SERVER_TIMEOUT = 15.0  # seconds per server for list_tools query

# Commands that indicate a Python process (for self-exclusion check)
_PYTHON_COMMANDS = frozenset({"python", "python3", "python.exe"})
_SECRET_ENV_MARKERS = ("TOKEN", "SECRET", "KEY", "PASSWORD", "PASS", "CREDENTIAL")


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


def _is_self_server(name: str, command: str, args: list[str]) -> bool:
    """Check whether an MCP server entry refers to archolith-audit itself.

    Two checks:
      1. Server name matches ``archolith-audit``.
      2. Command is a Python interpreter AND any argument contains
         ``archolith_mcp_audit``.

    Returns True if either check fires.
    """
    if name == "archolith-audit":
        log.debug("Skipping self by server name: %s", name)
        return True

    cmd_lower = command.strip().lower()
    if cmd_lower in _PYTHON_COMMANDS or (cmd_lower.endswith(".exe") and "python" in cmd_lower):
        for arg in args:
            if "archolith_mcp_audit" in arg:
                log.debug("Skipping self by command pattern: %s %s", command, args)
                return True

    return False


def _find_mcp_config() -> Path | None:
    """Locate the nearest ``.mcp.json`` config file.

    Search order:
      1. Current working directory
      2. Parent directories up to filesystem root
      3. ``~/.claude/.mcp.json`` (fallback)

    Returns the first path found, or None.
    """
    cwd = Path.cwd()
    for parent in [cwd, *cwd.parents]:
        candidate = parent / ".mcp.json"
        if candidate.is_file():
            log.debug("Found .mcp.json at %s", candidate)
            return candidate

    fallback = Path.home() / ".claude" / ".mcp.json"
    if fallback.is_file():
        log.debug("Found .mcp.json at %s (user fallback)", fallback)
        return fallback

    return None


def _is_queryable_server(name: str, server_conf: dict) -> bool:
    """Return True when a config entry is eligible for schema refresh."""
    command = server_conf.get("command", "")
    args = server_conf.get("args", [])
    if _is_self_server(name, command, args):
        return False
    return bool(command)


def _warn_secret_like_env(server_name: str, env: dict | None) -> None:
    """Warn when trusted .mcp.json env keys look credential-like."""
    if not env:
        return

    flagged = sorted(
        key for key in env
        if any(marker in str(key).upper() for marker in _SECRET_ENV_MARKERS)
    )
    if flagged:
        log.warning(
            "%s .mcp.json env contains secret-like keys passed to the MCP subprocess: %s. "
            "Review the trusted config; archolith-audit does not filter configured env.",
            server_name,
            ", ".join(flagged),
        )


async def _query_server_via_fastmcp(
    server_name: str,
    command: str,
    args: list[str],
    cwd: str | None,
    env: dict | None,
) -> list[dict]:
    """Query one MCP server for tool definitions via FastMCP Client.

    Returns a list of tool definition dicts with keys ``name``, ``description``,
    ``parameters`` (inputSchema).

    Raises
    ------
    asyncio.TimeoutError
        If the server does not respond within ``_PER_SERVER_TIMEOUT``.
    FileNotFoundError
        If the server command is not on PATH.
    Exception
        Any FastMCP-level error.
    """
    from fastmcp import Client  # noqa: PLC0415  -- late import; dependency is optional

    client = Client(
        command=command,
        args=args,
        cwd=cwd,
        env=env,
    )
    async with client:
        tools = await asyncio.wait_for(
            client.list_tools(),
            timeout=_PER_SERVER_TIMEOUT,
        )
        return [
            {
                "name": t.name,
                "description": t.description or "",
                "parameters": t.inputSchema or {},
            }
            for t in tools
        ]


async def _refresh_all_servers(
    servers_config: dict,
    failed_servers: dict[str, str],
) -> dict[str, list[dict]]:
    """Query all configured servers concurrently, returning the catalog dict.

    Each server that fails is recorded in ``failed_servers`` with an error
    message. The catalog will contain only successfully queried servers.
    """
    catalog: dict[str, list[dict]] = {}
    eligible: list[tuple[str, dict]] = []

    for server_name, server_conf in servers_config.items():
        command = server_conf.get("command", "")
        args = server_conf.get("args", [])

        # Skip self
        if _is_self_server(server_name, command, args):
            log.info("Skipping archolith-audit itself (%s)", server_name)
            continue

        # Only stdio transport is supported (command field present)
        if not command:
            log.warning("Skipping %s — no command field (SSE/HTTP transport?)", server_name)
            continue

        eligible.append((server_name, server_conf))

    async def _refresh_one(server_name: str, server_conf: dict) -> tuple[str, list[dict] | None]:
        command = server_conf.get("command", "")
        args = server_conf.get("args", [])
        cwd = server_conf.get("cwd")
        env = server_conf.get("env")

        log.info("Querying %s for tool schemas...", server_name)
        _warn_secret_like_env(server_name, env)
        try:
            tool_defs = await _query_server_via_fastmcp(
                server_name=server_name,
                command=command,
                args=args,
                cwd=cwd,
                env=env,
            )
        except TimeoutError:
            failed_servers[server_name] = f"timed out after {_PER_SERVER_TIMEOUT}s"
            log.warning("Timed out querying %s", server_name)
            return server_name, None
        except FileNotFoundError:
            failed_servers[server_name] = f"command not found: {command}"
            log.warning("Command not found for %s: %s", server_name, command)
            return server_name, None
        except Exception as exc:
            failed_servers[server_name] = str(exc)
            log.warning("Failed to query %s: %s", server_name, exc)
            return server_name, None

        # Build catalog entry for this server
        entries: list[dict] = []
        for td in tool_defs:
            token_count = count_schema_tokens(td)
            entries.append({
                "name": td["name"],
                "schema_tokens": token_count,
            })

        if entries:
            log.info("  -> %s: %d tools, %d total schema tokens",
                      server_name, len(entries), sum(e["schema_tokens"] for e in entries))
        else:
            log.info("  -> %s: 0 tools (empty list)", server_name)
        return server_name, entries

    for server_name, entries in await asyncio.gather(
        *(_refresh_one(server_name, server_conf) for server_name, server_conf in eligible)
    ):
        if entries is not None:
            catalog[server_name] = entries

    return catalog


@dataclass
class SchemaRefreshResult:
    """Result of a schema catalog refresh operation.

    Attributes:
        catalog: Mapping of server_name -> list of tool schema entries.
            An empty dict means no servers were successfully queried.
        failed_servers: Mapping of server_name -> error message for
            servers that failed to respond or were unreachable.
        total_servers: Total number of MCP servers eligible for schema
            refresh (excluding self and non-stdio entries).
    """

    catalog: dict[str, list[dict]] = field(default_factory=dict)
    failed_servers: dict[str, str] = field(default_factory=dict)
    total_servers: int = 0

    @property
    def succeeded_servers(self) -> list[str]:
        return sorted(self.catalog.keys())

    @property
    def succeeded_count(self) -> int:
        return len(self.catalog)

    @property
    def failed_count(self) -> int:
        return len(self.failed_servers)


def refresh_schema_catalog(
    output_path: Path | None = None,
) -> SchemaRefreshResult:
    """Refresh schema catalog by querying MCP servers.

    Attempts to call list_tools on each configured MCP server.
    Returns a SchemaRefreshResult with the catalog, per-server failure
    info, and total server count. The caller can inspect the result to
    determine which servers succeeded and which failed.
    """
    target = output_path or _DEFAULT_CATALOG_PATH

    # Try to import FastMCP client to query servers
    try:
        from fastmcp import Client as _FastMCPClient  # noqa: F401  -- existence check
    except ImportError:
        log.warning("FastMCP not available for schema refresh. Using empty catalog.")
        _write_catalog(target, {})
        return SchemaRefreshResult(catalog={}, failed_servers={"FastMCP": "not installed"}, total_servers=0)

    # Locate .mcp.json (workspace-first, then user home fallback)
    mcp_config_path = _find_mcp_config()
    if mcp_config_path is None:
        log.warning("No .mcp.json found (searched cwd, parents, and ~/.claude/)")
        _write_catalog(target, {})
        return SchemaRefreshResult(catalog={}, failed_servers={"config": ".mcp.json not found"}, total_servers=0)

    try:
        with open(mcp_config_path, encoding="utf-8") as f:
            config = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        log.warning("Failed to parse %s: %s", mcp_config_path, e)
        _write_catalog(target, {})
        return SchemaRefreshResult(catalog={}, failed_servers={"config": str(e)}, total_servers=0)

    servers_config = config.get("mcpServers", {})
    if not servers_config:
        log.warning("No mcpServers found in %s", mcp_config_path)
        _write_catalog(target, {})
        return SchemaRefreshResult(catalog={}, failed_servers={"config": "no mcpServers found"}, total_servers=0)

    failed_servers: dict[str, str] = {}

    try:
        asyncio.get_running_loop()
        # Already in an async context — run_until_complete on the current loop
        # would block the running loop. Fall back to a sync no-op with warning.
        log.warning("Cannot run --refresh-schemas from within an async context. "
                     "This command must be called from a synchronous entry point.")
        _write_catalog(target, {})
        return SchemaRefreshResult(
            catalog={},
            failed_servers={"async": "cannot run from async context"},
            total_servers=0,
        )
    except RuntimeError:
        # No running event loop — safe to call asyncio.run()
        catalog = asyncio.run(_refresh_all_servers(servers_config, failed_servers))

    _write_catalog(target, catalog)

    # Log summary
    total = sum(1 for name, conf in servers_config.items() if _is_queryable_server(name, conf))
    succeeded = len(catalog)
    if failed_servers:
        log.info("Failed servers (%d):", len(failed_servers))
        for s, err in failed_servers.items():
            log.info("  %s — %s", s, err)

    if succeeded == 0:
        log.warning("Refresh failed for all %d servers.", total)
    else:
        log.info("Refresh succeeded for %d/%d servers.", succeeded, total)

    return SchemaRefreshResult(catalog=catalog, failed_servers=dict(failed_servers), total_servers=total)


def load_catalog(path: Path | None = None) -> dict[str, list[SchemaEntry]]:
    """Load schema catalog from JSON file.

    Returns: {server_name: [SchemaEntry, ...]}
    """
    target = path or _DEFAULT_CATALOG_PATH
    if not target.exists():
        log.warning("Schema catalog not found at %s", target)
        return {}

    # Staleness check
    try:
        age_days = (time.time() - target.stat().st_mtime) / 86400
        if age_days > _STALE_DAYS:
            log.warning("Schema catalog is %d days old (stale threshold: %d days). "
                        "Run --refresh-schemas to update.", int(age_days), _STALE_DAYS)
    except OSError:
        pass  # Can't check mtime, proceed anyway

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

    if not result:
        log.warning(
            "Schema catalog is empty; schema_cost detector will use AVG_SCHEMA_TOKENS=%d defaults. "
            "Run --refresh-schemas for accurate schema costs.",
            AVG_SCHEMA_TOKENS,
        )

    return result


def estimate_server_schema_cost(
    server: str,
    tool_names: list[str],
    total_turns: int = 1,
    avg_schema_tokens: int = AVG_SCHEMA_TOKENS,
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


def _write_catalog(path: Path, catalog: dict[str, list[dict]]) -> None:
    """Write catalog to JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(catalog, f, indent=2)
    log.info("Schema catalog written to %s (%d servers)", path, len(catalog))
