"""Unit tests for schema diff algorithm."""

from testmcpy.src.schema_diff import (
    SchemaDiffResult,
    diff_tool_schemas,
)


class TestDiffToolSchemas:
    """Tests for diff_tool_schemas."""

    def test_identical_schemas(self):
        """No changes when schemas are identical."""
        tools = [
            {
                "name": "list_charts",
                "description": "List charts",
                "inputSchema": {
                    "type": "object",
                    "properties": {"page": {"type": "integer"}},
                    "required": ["page"],
                },
            }
        ]
        result = diff_tool_schemas(tools, tools)
        assert not result.has_changes
        assert len(result.added) == 0
        assert len(result.removed) == 0
        assert len(result.changed) == 0

    def test_added_tool(self):
        """Detect newly added tools."""
        old = [{"name": "tool_a", "description": "A"}]
        new = [
            {"name": "tool_a", "description": "A"},
            {"name": "tool_b", "description": "B"},
        ]
        result = diff_tool_schemas(old, new)
        assert result.has_changes
        assert len(result.added) == 1
        assert result.added[0].tool_name == "tool_b"

    def test_removed_tool(self):
        """Detect removed tools."""
        old = [
            {"name": "tool_a", "description": "A"},
            {"name": "tool_b", "description": "B"},
        ]
        new = [{"name": "tool_a", "description": "A"}]
        result = diff_tool_schemas(old, new)
        assert result.has_changes
        assert len(result.removed) == 1
        assert result.removed[0].tool_name == "tool_b"

    def test_description_changed(self):
        """Detect description changes."""
        old = [{"name": "tool_a", "description": "Old desc"}]
        new = [{"name": "tool_a", "description": "New desc"}]
        result = diff_tool_schemas(old, new)
        assert result.has_changes
        assert len(result.changed) == 1
        assert result.changed[0].description_changed is True
        assert result.changed[0].old_description == "Old desc"
        assert result.changed[0].new_description == "New desc"

    def test_param_added(self):
        """Detect added parameters."""
        old = [
            {
                "name": "tool_a",
                "description": "A",
                "inputSchema": {
                    "type": "object",
                    "properties": {"page": {"type": "integer"}},
                },
            }
        ]
        new = [
            {
                "name": "tool_a",
                "description": "A",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "page": {"type": "integer"},
                        "limit": {"type": "integer"},
                    },
                },
            }
        ]
        result = diff_tool_schemas(old, new)
        assert result.has_changes
        assert len(result.changed) == 1
        param_changes = result.changed[0].param_changes
        assert len(param_changes) == 1
        assert param_changes[0].param_name == "limit"
        assert param_changes[0].change_type == "added"

    def test_param_removed(self):
        """Detect removed parameters."""
        old = [
            {
                "name": "tool_a",
                "description": "A",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "page": {"type": "integer"},
                        "limit": {"type": "integer"},
                    },
                },
            }
        ]
        new = [
            {
                "name": "tool_a",
                "description": "A",
                "inputSchema": {
                    "type": "object",
                    "properties": {"page": {"type": "integer"}},
                },
            }
        ]
        result = diff_tool_schemas(old, new)
        assert result.has_changes
        param_changes = result.changed[0].param_changes
        assert any(p.param_name == "limit" and p.change_type == "removed" for p in param_changes)

    def test_param_type_changed(self):
        """Detect parameter type changes."""
        old = [
            {
                "name": "tool_a",
                "description": "A",
                "inputSchema": {
                    "type": "object",
                    "properties": {"page": {"type": "integer"}},
                },
            }
        ]
        new = [
            {
                "name": "tool_a",
                "description": "A",
                "inputSchema": {
                    "type": "object",
                    "properties": {"page": {"type": "string"}},
                },
            }
        ]
        result = diff_tool_schemas(old, new)
        assert result.has_changes
        param_changes = result.changed[0].param_changes
        assert param_changes[0].change_type == "type_changed"
        assert param_changes[0].old_value == "integer"
        assert param_changes[0].new_value == "string"

    def test_required_changed(self):
        """Detect required status changes."""
        old = [
            {
                "name": "tool_a",
                "description": "A",
                "inputSchema": {
                    "type": "object",
                    "properties": {"page": {"type": "integer"}},
                    "required": [],
                },
            }
        ]
        new = [
            {
                "name": "tool_a",
                "description": "A",
                "inputSchema": {
                    "type": "object",
                    "properties": {"page": {"type": "integer"}},
                    "required": ["page"],
                },
            }
        ]
        result = diff_tool_schemas(old, new)
        assert result.has_changes
        param_changes = result.changed[0].param_changes
        assert any(p.change_type == "required_changed" for p in param_changes)

    def test_breaking_changes(self):
        """Breaking changes include removed tools and removed params."""
        old = [
            {"name": "tool_a", "description": "A"},
            {
                "name": "tool_b",
                "description": "B",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "x": {"type": "integer"},
                        "y": {"type": "string"},
                    },
                },
            },
        ]
        new = [
            {
                "name": "tool_b",
                "description": "B",
                "inputSchema": {
                    "type": "object",
                    "properties": {"x": {"type": "integer"}},
                },
            },
        ]
        result = diff_tool_schemas(old, new)
        breaking = result.breaking_changes
        # tool_a removed is a breaking change
        assert any(bc.tool_name == "tool_a" for bc in breaking)

    def test_to_dict(self):
        """to_dict returns a serializable dict."""
        old = [{"name": "a", "description": "A"}]
        new = [{"name": "b", "description": "B"}]
        result = diff_tool_schemas(old, new)
        d = result.to_dict()
        assert "added" in d
        assert "removed" in d
        assert "changed" in d
        assert "summary" in d
        assert d["summary"]["added_count"] == 1
        assert d["summary"]["removed_count"] == 1

    def test_empty_schemas(self):
        """Empty tool lists produce no changes."""
        result = diff_tool_schemas([], [])
        assert not result.has_changes

    def test_input_schema_alias(self):
        """Supports both inputSchema and input_schema keys."""
        old = [
            {
                "name": "tool_a",
                "description": "A",
                "input_schema": {
                    "type": "object",
                    "properties": {"x": {"type": "integer"}},
                },
            }
        ]
        new = [
            {
                "name": "tool_a",
                "description": "A",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "x": {"type": "integer"},
                        "y": {"type": "string"},
                    },
                },
            }
        ]
        result = diff_tool_schemas(old, new)
        assert result.has_changes
        assert len(result.changed) == 1
