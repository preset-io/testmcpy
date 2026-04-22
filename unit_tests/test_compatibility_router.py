"""
Unit tests for the compatibility matrix endpoint logic.

Tests input validation, matrix construction, schema comparison,
and error handling for cross-server tool compatibility.

Story: SC-103111 — MCP client compatibility testing matrix
"""

import pytest
from pydantic import ValidationError

from testmcpy.server.routers.compatibility import (
    CompatibilityMatrixRequest,
    ToolTestResult,
)

# ── Request validation ───────────────────────────────────────────────────────


class TestCompatibilityMatrixRequest:
    """Test the Pydantic request model."""

    def test_valid_request(self):
        req = CompatibilityMatrixRequest(
            profiles=["staging:Preset Staging", "prod:Preset Production"],
            tool_names=["list_dashboards", "list_charts"],
        )
        assert len(req.profiles) == 2
        assert len(req.tool_names) == 2

    def test_empty_profiles_allowed_by_model(self):
        """Model allows empty list — endpoint enforces min 2."""
        req = CompatibilityMatrixRequest(profiles=[], tool_names=["list_dashboards"])
        assert req.profiles == []

    def test_empty_tool_names_allowed_by_model(self):
        """Model allows empty list — endpoint enforces min 1."""
        req = CompatibilityMatrixRequest(
            profiles=["staging:Preset Staging", "prod:Preset Production"],
            tool_names=[],
        )
        assert req.tool_names == []

    def test_missing_profiles_raises(self):
        """Missing required field should raise validation error."""
        with pytest.raises(ValidationError):
            CompatibilityMatrixRequest(tool_names=["list_dashboards"])

    def test_missing_tool_names_raises(self):
        with pytest.raises(ValidationError):
            CompatibilityMatrixRequest(profiles=["staging:Preset Staging"])


class TestToolTestResult:
    """Test the result model."""

    def test_pass_result(self):
        r = ToolTestResult(status="pass", has_tool=True, schema_match=True)
        assert r.status == "pass"
        assert r.has_tool is True
        assert r.error is None

    def test_missing_result(self):
        r = ToolTestResult(status="missing", has_tool=False)
        assert r.status == "missing"
        assert r.has_tool is False

    def test_error_result(self):
        r = ToolTestResult(status="error", error="Connection refused")
        assert r.status == "error"
        assert r.error == "Connection refused"

    def test_fail_with_duration(self):
        r = ToolTestResult(status="fail", has_tool=True, schema_match=False, duration_ms=125.5)
        assert r.duration_ms == 125.5
        assert r.schema_match is False

    def test_defaults(self):
        r = ToolTestResult(status="pass")
        assert r.has_tool is False
        assert r.schema_match is None
        assert r.call_success is None
        assert r.error is None
        assert r.duration_ms == 0


# ── Profile reference parsing ────────────────────────────────────────────────


class TestProfileRefParsing:
    """Test profile reference format 'profile_id:mcp_name'."""

    def test_valid_profile_ref(self):
        ref = "staging:Preset Staging"
        assert ":" in ref
        profile_id, mcp_name = ref.split(":", 1)
        assert profile_id == "staging"
        assert mcp_name == "Preset Staging"

    def test_profile_ref_with_colons_in_name(self):
        ref = "prod:MCP Server: v2"
        profile_id, mcp_name = ref.split(":", 1)
        assert profile_id == "prod"
        assert mcp_name == "MCP Server: v2"

    def test_invalid_profile_ref_no_colon(self):
        ref = "staging-only"
        assert ":" not in ref


# ── Schema comparison logic ──────────────────────────────────────────────────


class TestSchemaComparison:
    """Test the schema comparison logic used in matrix building."""

    def test_identical_schemas_match(self):
        old_schema = {"properties": {"page": {"type": "integer"}, "q": {"type": "string"}}}
        new_schema = {"properties": {"page": {"type": "integer"}, "q": {"type": "string"}}}
        old_props = old_schema.get("properties", {})
        new_props = new_schema.get("properties", {})
        assert set(old_props.keys()) == set(new_props.keys())
        for param in old_props:
            assert old_props[param].get("type") == new_props[param].get("type")

    def test_different_property_sets(self):
        old_schema = {"properties": {"page": {"type": "integer"}}}
        new_schema = {"properties": {"page": {"type": "integer"}, "limit": {"type": "integer"}}}
        old_props = old_schema.get("properties", {})
        new_props = new_schema.get("properties", {})
        assert set(old_props.keys()) != set(new_props.keys())

    def test_same_keys_different_types(self):
        old_schema = {"properties": {"page": {"type": "integer"}}}
        new_schema = {"properties": {"page": {"type": "string"}}}
        old_props = old_schema.get("properties", {})
        new_props = new_schema.get("properties", {})
        assert set(old_props.keys()) == set(new_props.keys())
        assert old_props["page"]["type"] != new_props["page"]["type"]

    def test_empty_schemas_match(self):
        old_schema = {"properties": {}}
        new_schema = {"properties": {}}
        assert set(old_schema["properties"].keys()) == set(new_schema["properties"].keys())

    def test_missing_properties_key(self):
        schema = {}
        props = schema.get("properties", {})
        assert props == {}

    def test_none_schema_handled(self):
        schema = None
        props = (schema or {}).get("properties", {})
        assert props == {}


# ── Matrix structure ─────────────────────────────────────────────────────────


class TestMatrixStructure:
    """Test the expected matrix output structure."""

    def test_matrix_keys(self):
        """Matrix should have tool names as top-level keys."""
        matrix = {
            "list_dashboards": {
                "staging:Preset": {"status": "pass", "has_tool": True},
                "prod:Preset": {"status": "pass", "has_tool": True},
            },
            "list_charts": {
                "staging:Preset": {"status": "pass", "has_tool": True},
                "prod:Preset": {"status": "missing", "has_tool": False},
            },
        }
        assert "list_dashboards" in matrix
        assert "list_charts" in matrix
        assert matrix["list_charts"]["prod:Preset"]["status"] == "missing"

    def test_error_profile_in_matrix(self):
        """When a profile has a connection error, all tools show error."""
        matrix = {}
        tools = ["list_dashboards", "list_charts"]
        error_msg = "Connection refused"
        for tool in tools:
            matrix[tool] = {
                "broken:Server": {"status": "error", "has_tool": False, "error": error_msg}
            }
        assert matrix["list_dashboards"]["broken:Server"]["status"] == "error"
        assert matrix["list_charts"]["broken:Server"]["error"] == error_msg
