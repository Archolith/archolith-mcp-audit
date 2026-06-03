# /audit

Runs an MCP token usage report for the current session.

## When to use
Invoke when the user types `/audit` or asks about token usage, context costs,
or which tools are consuming the most tokens.

## Steps
1. Call `mcp_audit_summary` to get the per-server table.
2. If the user asks for detail on a specific server, call `mcp_audit_detail(server=<name>)`.
3. If the user asks for a pass/fail check, call `mcp_audit_check`.
4. Present findings with the waste type and suggested fix.
