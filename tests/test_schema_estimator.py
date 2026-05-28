"""Tests for archolith_mcp_audit.schema_estimator — schema token cost estimation."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from archolith_mcp_audit.schema_estimator import (
    ServerSchemaCost,
    SchemaEntry,
    compute_all_schema_costs,
    count_schema_tokens,
    estimate_server_schema_cost,
    load_catalog,
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
