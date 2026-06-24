"""archolith-audit — MCP token usage audit system.

Measures per-server token cost, detects waste patterns, and produces
report cards with concrete optimization suggestions.

Public API:
- ``__version__`` for package/version display.
- CLI entrypoint: ``archolith_mcp_audit.cli:main``.
- Report dataclasses and formatting helpers from ``archolith_mcp_audit.report``.
- Extractor DTOs from ``archolith_mcp_audit.extractors.base``.

Detector internals, hook observers, and plugin bundle code are not stable public APIs.
"""

__version__ = "0.1.0"

__all__ = ["__version__"]
