"""
Schema diff — compare two MCP tool schema snapshots and detect breaking changes.

Given two lists of tool definitions (each with name, description, inputSchema),
produce a structured diff that shows:
  - Added tools
  - Removed tools
  - Changed tools (parameters added/removed/type-changed, description changes)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ParamChange:
    """A change to a single parameter within a tool's input schema."""

    param_name: str
    change_type: (
        str  # "added", "removed", "type_changed", "description_changed", "required_changed"
    )
    old_value: Any = None
    new_value: Any = None


@dataclass
class ToolChange:
    """Summary of changes for a single tool between two snapshots."""

    tool_name: str
    change_type: str  # "added", "removed", "changed"
    description_changed: bool = False
    old_description: str | None = None
    new_description: str | None = None
    param_changes: list[ParamChange] = field(default_factory=list)


@dataclass
class SchemaDiffResult:
    """Result of comparing two tool schema snapshots."""

    added: list[ToolChange] = field(default_factory=list)
    removed: list[ToolChange] = field(default_factory=list)
    changed: list[ToolChange] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        return bool(self.added or self.removed or self.changed)

    @property
    def breaking_changes(self) -> list[ToolChange]:
        """Return only breaking changes (removed tools, removed params, type changes)."""
        breaking: list[ToolChange] = list(self.removed)
        for tc in self.changed:
            breaking_params = [
                p
                for p in tc.param_changes
                if p.change_type in ("removed", "type_changed")
                or (p.change_type == "required_changed" and p.new_value is True)
            ]
            if breaking_params:
                breaking.append(
                    ToolChange(
                        tool_name=tc.tool_name,
                        change_type="changed",
                        param_changes=breaking_params,
                    )
                )
        return breaking

    def to_dict(self) -> dict[str, Any]:
        def _param_to_dict(p: ParamChange) -> dict[str, Any]:
            d: dict[str, Any] = {
                "param_name": p.param_name,
                "change_type": p.change_type,
            }
            if p.old_value is not None:
                d["old_value"] = p.old_value
            if p.new_value is not None:
                d["new_value"] = p.new_value
            return d

        def _tool_to_dict(tc: ToolChange) -> dict[str, Any]:
            d: dict[str, Any] = {
                "tool_name": tc.tool_name,
                "change_type": tc.change_type,
            }
            if tc.description_changed:
                d["description_changed"] = True
                d["old_description"] = tc.old_description
                d["new_description"] = tc.new_description
            if tc.param_changes:
                d["param_changes"] = [_param_to_dict(p) for p in tc.param_changes]
            return d

        return {
            "added": [_tool_to_dict(tc) for tc in self.added],
            "removed": [_tool_to_dict(tc) for tc in self.removed],
            "changed": [_tool_to_dict(tc) for tc in self.changed],
            "has_changes": self.has_changes,
            "summary": {
                "added_count": len(self.added),
                "removed_count": len(self.removed),
                "changed_count": len(self.changed),
                "breaking_count": len(self.breaking_changes),
            },
        }


def _extract_params(schema: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Extract parameter definitions from a JSON Schema object."""
    properties = schema.get("properties", {})
    required = set(schema.get("required", []))
    params: dict[str, dict[str, Any]] = {}
    for name, prop in properties.items():
        params[name] = {
            "type": prop.get("type"),
            "description": prop.get("description", ""),
            "required": name in required,
        }
    return params


def _diff_params(
    old_params: dict[str, dict[str, Any]],
    new_params: dict[str, dict[str, Any]],
) -> list[ParamChange]:
    """Compare parameter definitions between two schemas."""
    changes: list[ParamChange] = []
    old_names = set(old_params.keys())
    new_names = set(new_params.keys())

    # Added params
    for name in sorted(new_names - old_names):
        changes.append(
            ParamChange(param_name=name, change_type="added", new_value=new_params[name])
        )

    # Removed params
    for name in sorted(old_names - new_names):
        changes.append(
            ParamChange(param_name=name, change_type="removed", old_value=old_params[name])
        )

    # Changed params
    for name in sorted(old_names & new_names):
        old_p = old_params[name]
        new_p = new_params[name]

        if old_p.get("type") != new_p.get("type"):
            changes.append(
                ParamChange(
                    param_name=name,
                    change_type="type_changed",
                    old_value=old_p.get("type"),
                    new_value=new_p.get("type"),
                )
            )

        if old_p.get("required") != new_p.get("required"):
            changes.append(
                ParamChange(
                    param_name=name,
                    change_type="required_changed",
                    old_value=old_p.get("required"),
                    new_value=new_p.get("required"),
                )
            )

        if old_p.get("description", "") != new_p.get("description", ""):
            changes.append(
                ParamChange(
                    param_name=name,
                    change_type="description_changed",
                    old_value=old_p.get("description", ""),
                    new_value=new_p.get("description", ""),
                )
            )

    return changes


def diff_tool_schemas(
    old_tools: list[dict[str, Any]],
    new_tools: list[dict[str, Any]],
) -> SchemaDiffResult:
    """Compare two lists of tool definitions and return a structured diff.

    Each tool dict is expected to have at minimum:
      - "name": str
      - "description": str (optional)
      - "inputSchema" or "input_schema": dict (optional)

    Args:
        old_tools: The baseline (old/reference) tool list.
        new_tools: The new tool list to compare against.

    Returns:
        SchemaDiffResult with added, removed, and changed tools.
    """
    old_map: dict[str, dict[str, Any]] = {}
    for t in old_tools:
        old_map[t["name"]] = t

    new_map: dict[str, dict[str, Any]] = {}
    for t in new_tools:
        new_map[t["name"]] = t

    old_names = set(old_map.keys())
    new_names = set(new_map.keys())

    result = SchemaDiffResult()

    # Added tools
    for name in sorted(new_names - old_names):
        result.added.append(ToolChange(tool_name=name, change_type="added"))

    # Removed tools
    for name in sorted(old_names - new_names):
        result.removed.append(ToolChange(tool_name=name, change_type="removed"))

    # Changed tools
    for name in sorted(old_names & new_names):
        old_t = old_map[name]
        new_t = new_map[name]

        old_desc = old_t.get("description", "")
        new_desc = new_t.get("description", "")
        desc_changed = old_desc != new_desc

        old_schema = old_t.get("inputSchema") or old_t.get("input_schema") or {}
        new_schema = new_t.get("inputSchema") or new_t.get("input_schema") or {}

        old_params = _extract_params(old_schema)
        new_params = _extract_params(new_schema)
        param_changes = _diff_params(old_params, new_params)

        if desc_changed or param_changes:
            result.changed.append(
                ToolChange(
                    tool_name=name,
                    change_type="changed",
                    description_changed=desc_changed,
                    old_description=old_desc if desc_changed else None,
                    new_description=new_desc if desc_changed else None,
                    param_changes=param_changes,
                )
            )

    return result
