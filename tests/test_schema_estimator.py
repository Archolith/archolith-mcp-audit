"""Tests for archolith_mcp_audit.schema_estimator — schema token cost estimation."""

from __future__ import annotations

import json
import logging
import sys
import tempfile
import types
from pathlib import Path
from unittest.mock import AsyncMock, patch

from archolith_mcp_audit.schema_estimator import (
    SchemaEntry,
    ServerSchemaCost,
    _is_self_server,
    _warn_secret_like_env,
    compute_all_schema_costs,
    count_schema_tokens,
    estimate_server_schema_cost,
    load_catalog,
    refresh_schema_catalog,
)


class TestLoadCatalog:
    """Tests for load_catalog()."""

    def test_valid_catalog_loads(self) -> None:
        """Valid JSON catalog produces correct entries."""
        catalog_data = {
            "gradle": [
                {"name": "gradle_compile", "schema_tokens": 250},
                {"name": "gradle_test", "schema_tokens": 300},
            ],
            "vps": [
                {"name": "vps_status", "schema_tokens": 200},
            ],
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(catalog_data, f)
            path = Path(f.name)

        try:
            catalog = load_catalog(path)
            assert "gradle" in catalog
            assert len(catalog["gradle"]) == 2
            assert catalog["gradle"][0].tool_name == "gradle_compile"
            assert catalog["gradle"][0].schema_tokens == 250
            assert "vps" in catalog
            assert catalog["vps"][0].schema_tokens == 200
        finally:
            path.unlink(missing_ok=True)

    def test_missing_catalog_returns_empty(self) -> None:
        """Missing file returns empty dict with warning."""
        catalog = load_catalog(Path("/nonexistent/path/catalog.json"))
        assert catalog == {}

    def test_malformed_catalog_returns_empty(self) -> None:
        """Malformed JSON returns empty dict gracefully."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("{invalid json")
            path = Path(f.name)

        try:
            catalog = load_catalog(path)
            assert catalog == {}
        finally:
            path.unlink(missing_ok=True)

    def test_array_format_catalog(self) -> None:
        """Catalog entries in [name, tokens] array format are parsed."""
        catalog_data = {
            "memory": [
                ["query_structure", 350],
                ["recall_memories", 280],
            ],
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(catalog_data, f)
            path = Path(f.name)

        try:
            catalog = load_catalog(path)
            assert "memory" in catalog
            assert catalog["memory"][0].tool_name == "query_structure"
            assert catalog["memory"][0].schema_tokens == 350
        finally:
            path.unlink(missing_ok=True)

    def test_empty_catalog_warns_about_heuristic_schema_costs(self, caplog) -> None:
        """Empty catalog warns that schema-cost findings use AVG_SCHEMA_TOKENS defaults."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({}, f)
            path = Path(f.name)

        try:
            with caplog.at_level(logging.WARNING):
                catalog = load_catalog(path)

            assert catalog == {}
            assert "AVG_SCHEMA_TOKENS=300" in caplog.text
            assert "--refresh-schemas" in caplog.text
        finally:
            path.unlink(missing_ok=True)


class TestEstimateServerSchemaCost:
    """Tests for estimate_server_schema_cost()."""

    def test_heuristic_estimate(self) -> None:
        """Heuristic produces reasonable estimates."""
        cost = estimate_server_schema_cost("gradle", ["gradle_compile", "gradle_test"], total_turns=10)
        assert cost.per_turn_cost > 0
        assert cost.session_cost == cost.per_turn_cost * 10
        assert len(cost.tools) == 2

    def test_custom_avg_tokens(self) -> None:
        """Custom avg_schema_tokens is used in estimate."""
        cost = estimate_server_schema_cost(
            "vps", ["vps_status"], total_turns=1, avg_schema_tokens=500
        )
        assert cost.per_turn_cost == 500


class TestComputeAllSchemaCosts:
    """Tests for compute_all_schema_costs()."""

    def test_catalog_used_when_available(self) -> None:
        """Catalog data used for servers that have entries."""
        catalog_data = {
            "gradle": [{"name": "gradle_compile", "schema_tokens": 250}]
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(catalog_data, f)
            path = Path(f.name)

        try:
            costs = compute_all_schema_costs(
                {"gradle": ["gradle_compile"], "vps": ["vps_status"]},
                total_turns=5,
                catalog_path=path,
            )
            # gradle uses catalog (250 tokens/turn)
            assert costs["gradle"].per_turn_cost == 250
            assert costs["gradle"].session_cost == 250 * 5
            # vps falls back to heuristic (300 tokens/turn default)
            assert costs["vps"].per_turn_cost == 300
        finally:
            path.unlink(missing_ok=True)

    def test_all_heuristic_when_no_catalog(self) -> None:
        """All servers use heuristic when no catalog path given."""
        costs = compute_all_schema_costs(
            {"memory": ["query_structure"]},
            total_turns=1,
        )
        assert "memory" in costs
        assert costs["memory"].per_turn_cost > 0


class TestCountSchemaTokens:
    """Tests for count_schema_tokens()."""

    def test_tool_def_produces_tokens(self) -> None:
        """Tool definition produces non-zero token count."""
        tool_def = {
            "name": "gradle_compile",
            "description": "Compile Java source files using Gradle",
            "parameters": {"type": "object", "properties": {"project_root": {"type": "string"}}},
        }
        tokens = count_schema_tokens(tool_def)
        assert tokens > 0

    def test_minimal_tool_def(self) -> None:
        """Tool with only name produces tokens > 0."""
        tokens = count_schema_tokens({"name": "simple_tool"})
        assert tokens > 0


class TestServerSchemaCost:
    """Tests for ServerSchemaCost.compute()."""

    def test_per_turn_x_turns_equals_session(self) -> None:
        """Per-turn cost × turns = session cost."""
        tools = [
            SchemaEntry(tool_name="tool_a", schema_tokens=200),
            SchemaEntry(tool_name="tool_b", schema_tokens=300),
        ]
        cost = ServerSchemaCost(server="test", tools=tools)
        cost.compute(total_turns=20)
        assert cost.per_turn_cost == 500
        assert cost.session_cost == 10_000


class TestIsSelfServer:
    """Tests for _is_self_server()."""

    def test_match_by_name(self) -> None:
        """Name 'archolith-audit' matches unconditionally."""
        assert _is_self_server("archolith-audit", "node", ["server.js"])

    def test_match_by_command_pattern_python(self) -> None:
        """Python interpreter + archolith_mcp_audit arg matches."""
        assert _is_self_server(
            "gradle", "python", ["-m", "archolith_mcp_audit.mcp_server"]
        )

    def test_match_by_command_pattern_python3(self) -> None:
        """python3 interpreter also matches."""
        assert _is_self_server(
            "gradle", "python3", ["-m", "archolith_mcp_audit"]
        )

    def test_no_match_unrelated_server(self) -> None:
        """Unrelated server with no archolith_mcp_audit arg does not match."""
        assert not _is_self_server("vps", "node", ["vps-server.js"])

    def test_no_match_python_but_different_module(self) -> None:
        """Python interpreter without archolith_mcp_audit arg does not match."""
        assert not _is_self_server("gradle", "python", ["-m", "gradle_mcp"])

    def test_no_match_name_similar(self) -> None:
        """Name containing similar text does not match."""
        assert not _is_self_server("mcp-audit", "node", ["server.js"])

    def test_empty_args(self) -> None:
        """Empty args list does not cause false positive."""
        assert not _is_self_server("gradle", "node", [])

    def test_command_with_exe_suffix(self) -> None:
        """python.exe with archolith_mcp_audit arg matches."""
        assert _is_self_server(
            "gradle", "python.exe", ["-m", "archolith_mcp_audit.cli"]
        )


class TestEnvTrustWarnings:
    """Tests for .mcp.json env trust-model warnings."""

    def test_secret_like_env_key_warns(self, caplog) -> None:
        with caplog.at_level(logging.WARNING):
            _warn_secret_like_env("vps", {"API_TOKEN": "redacted", "PATH": "x"})

        assert "API_TOKEN" in caplog.text
        assert "does not filter configured env" in caplog.text

    def test_non_secret_env_key_does_not_warn(self, caplog) -> None:
        with caplog.at_level(logging.WARNING):
            _warn_secret_like_env("vps", {"PATH": "x", "HOME": "y"})

        assert caplog.text == ""


class TestRefreshSchemaCatalog:
    """Mock-based tests for refresh_schema_catalog()."""

    @staticmethod
    def _make_mcp_config(servers: dict | None = None) -> Path:
        """Create a temp .mcp.json and return its path."""
        data = {
            "mcpServers": servers or {
                "gradle": {"command": "python", "args": ["-m", "gradle_mcp"]},
                "vps": {"command": "node", "args": ["vps-server.js"]},
                "archolith-audit": {"command": "python", "args": ["-m", "archolith_mcp_audit.mcp_server"]},
                "sse-server": {"url": "http://localhost:9999/sse"},
            }
        }
        config_dir = Path(tempfile.mkdtemp())
        config_path = config_dir / ".mcp.json"
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(data, f)
        return config_path

    @staticmethod
    def _make_fake_fastmcp(client_cls: type) -> types.ModuleType:
        fake_module = types.ModuleType("fastmcp")
        fake_module.Client = client_cls
        return fake_module

    @patch("archolith_mcp_audit.schema_estimator._find_mcp_config")
    @patch("archolith_mcp_audit.schema_estimator._write_catalog")
    def test_refresh_with_mock_client(
        self,
        mock_write: AsyncMock,
        mock_find: AsyncMock,
    ) -> None:
        """Refresh uses the FastMCP client path and writes real catalog entries."""
        import asyncio
        import shutil

        class FakeTool:
            def __init__(self, name: str, description: str = "", input_schema: dict | None = None) -> None:
                self.name = name
                self.description = description
                self.inputSchema = input_schema or {}

        class FakeClient:
            def __init__(self, command: str, args: list[str], cwd: str | None = None, env: dict | None = None) -> None:
                self.command = command
                self.args = args
                self.cwd = cwd
                self.env = env

            async def __aenter__(self) -> FakeClient:
                return self

            async def __aexit__(self, exc_type, exc, tb) -> None:
                return None

            async def list_tools(self) -> list[FakeTool]:
                if self.command == "python":
                    return [FakeTool("gradle_compile", "Compile Java", {"type": "object"})]
                return [FakeTool("vps_status", "Check VPS", {"type": "object"})]

        with patch.object(asyncio, "get_running_loop", side_effect=RuntimeError):
            config_path = self._make_mcp_config()
            mock_find.return_value = config_path

            with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
                output_path = Path(f.name)

            try:
                with patch.dict(sys.modules, {"fastmcp": self._make_fake_fastmcp(FakeClient)}):
                    result = refresh_schema_catalog(output_path)

                assert sorted(result.catalog) == ["gradle", "vps"]
                assert result.failed_servers == {}
                assert result.total_servers == 2
                assert result.catalog["gradle"][0]["name"] == "gradle_compile"
                assert result.catalog["vps"][0]["name"] == "vps_status"
                mock_write.assert_called_once_with(output_path, result.catalog)
            finally:
                output_path.unlink(missing_ok=True)
                shutil.rmtree(config_path.parent, ignore_errors=True)

    @patch("archolith_mcp_audit.schema_estimator._find_mcp_config")
    @patch("archolith_mcp_audit.schema_estimator._write_catalog")
    def test_refresh_partial_failure(
        self,
        mock_write: AsyncMock,
        mock_find: AsyncMock,
    ) -> None:
        """One FastMCP client call can fail without blocking other servers."""
        import asyncio
        import shutil

        class FakeTool:
            def __init__(self, name: str, description: str = "", input_schema: dict | None = None) -> None:
                self.name = name
                self.description = description
                self.inputSchema = input_schema or {}

        class FakeClient:
            def __init__(self, command: str, args: list[str], cwd: str | None = None, env: dict | None = None) -> None:
                self.command = command
                self.args = args
                self.cwd = cwd
                self.env = env

            async def __aenter__(self) -> FakeClient:
                return self

            async def __aexit__(self, exc_type, exc, tb) -> None:
                return None

            async def list_tools(self) -> list[FakeTool]:
                if self.command == "node":
                    raise RuntimeError("vps unavailable")
                return [FakeTool("gradle_compile", "Compile Java", {"type": "object"})]

        with patch.object(asyncio, "get_running_loop", side_effect=RuntimeError):
            config_path = self._make_mcp_config()
            mock_find.return_value = config_path

            with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
                output_path = Path(f.name)

            try:
                with patch.dict(sys.modules, {"fastmcp": self._make_fake_fastmcp(FakeClient)}):
                    result = refresh_schema_catalog(output_path)

                assert sorted(result.catalog) == ["gradle"]
                assert result.total_servers == 2
                assert result.failed_servers == {"vps": "vps unavailable"}
                mock_write.assert_called_once_with(output_path, result.catalog)
            finally:
                output_path.unlink(missing_ok=True)
                shutil.rmtree(config_path.parent, ignore_errors=True)

    @patch("archolith_mcp_audit.schema_estimator._find_mcp_config")
    @patch("archolith_mcp_audit.schema_estimator._write_catalog")
    def test_refresh_all_fail_nonzero(
        self,
        mock_write: AsyncMock,
        mock_find: AsyncMock,
    ) -> None:
        """When all FastMCP queries fail, the refresh result reports zero successes."""
        import asyncio
        import shutil

        class FakeClient:
            def __init__(self, command: str, args: list[str], cwd: str | None = None, env: dict | None = None) -> None:
                self.command = command
                self.args = args
                self.cwd = cwd
                self.env = env

            async def __aenter__(self) -> FakeClient:
                return self

            async def __aexit__(self, exc_type, exc, tb) -> None:
                return None

            async def list_tools(self) -> list[object]:
                raise RuntimeError(f"{self.command} unavailable")

        with patch.object(asyncio, "get_running_loop", side_effect=RuntimeError):
            config_path = self._make_mcp_config()
            mock_find.return_value = config_path

            with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
                output_path = Path(f.name)

            try:
                with patch.dict(sys.modules, {"fastmcp": self._make_fake_fastmcp(FakeClient)}):
                    result = refresh_schema_catalog(output_path)

                assert result.catalog == {}
                assert result.total_servers == 2
                assert result.failed_servers == {
                    "gradle": "python unavailable",
                    "vps": "node unavailable",
                }
                mock_write.assert_called_once_with(output_path, {})
            finally:
                output_path.unlink(missing_ok=True)
                shutil.rmtree(config_path.parent, ignore_errors=True)

    @patch("archolith_mcp_audit.schema_estimator._find_mcp_config")
    @patch("archolith_mcp_audit.schema_estimator._write_catalog")
    def test_no_mcp_config(self, mock_write: AsyncMock, mock_find: AsyncMock) -> None:
        """No .mcp.json found → empty catalog, no crash."""
        mock_find.return_value = None

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            output_path = Path(f.name)

        try:
            result = refresh_schema_catalog(output_path)
            assert result.catalog == {}
        finally:
            output_path.unlink(missing_ok=True)

    @patch("archolith_mcp_audit.schema_estimator._find_mcp_config")
    def test_self_exclusion_by_name(self, mock_find: AsyncMock) -> None:
        """Self-exclusion by name: archolith-audit not in result."""
        import asyncio

        with patch.object(asyncio, "get_running_loop", side_effect=RuntimeError):
            config_path = self._make_mcp_config({
                "archolith-audit": {
                    "command": "python",
                    "args": ["-m", "archolith_mcp_audit.mcp_server"],
                },
            })
            mock_find.return_value = config_path

            with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
                output_path = Path(f.name)

            try:
                result = refresh_schema_catalog(output_path)
                assert result.catalog == {}
            finally:
                output_path.unlink(missing_ok=True)
                import shutil
                shutil.rmtree(config_path.parent, ignore_errors=True)

    @patch("archolith_mcp_audit.schema_estimator._find_mcp_config")
    def test_self_exclusion_by_command_pattern(self, mock_find: AsyncMock) -> None:
        """Self-exclusion by command pattern: python + archolith_mcp_audit arg skipped regardless of name."""
        import asyncio

        with patch.object(asyncio, "get_running_loop", side_effect=RuntimeError):
            config_path = self._make_mcp_config({
                "some-other-name": {
                    "command": "python",
                    "args": ["-m", "archolith_mcp_audit.mcp_server"],
                },
            })
            mock_find.return_value = config_path

            with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
                output_path = Path(f.name)

            try:
                result = refresh_schema_catalog(output_path)
                assert result.catalog == {}
                assert "some-other-name" not in result.catalog
            finally:
                output_path.unlink(missing_ok=True)
                import shutil
                shutil.rmtree(config_path.parent, ignore_errors=True)

    @patch("archolith_mcp_audit.schema_estimator._find_mcp_config")
    def test_sse_server_skipped(self, mock_find: AsyncMock) -> None:
        """SSE/HTTP server (no command field) is skipped gracefully — not in catalog or failed_servers."""
        import asyncio

        with patch.object(asyncio, "get_running_loop", side_effect=RuntimeError):
            config_path = self._make_mcp_config({
                "sse-server": {"url": "http://localhost:9999/sse"},
            })
            mock_find.return_value = config_path

            with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
                output_path = Path(f.name)

            try:
                result = refresh_schema_catalog(output_path)
                assert result.catalog == {}
                assert "sse-server" not in result.failed_servers
            finally:
                output_path.unlink(missing_ok=True)
                import shutil
                shutil.rmtree(config_path.parent, ignore_errors=True)
