"""JSON and YAML formatters for JSON Schema."""

import json
from typing import Any

import yaml

from .base import SchemaFormatter


class JSONFormatter(SchemaFormatter):
    """Converts JSON Schema to formatted JSON."""

    def format(self) -> str:
        """Format schema as pretty-printed JSON."""
        return json.dumps(self.original_schema, indent=2)


class YAMLFormatter(SchemaFormatter):
    """Converts JSON Schema to YAML."""

    def format(self) -> str:
        """Format schema as YAML."""
        try:
            return yaml.dump(
                self.original_schema,
                default_flow_style=False,
                sort_keys=False,
                width=80,
                indent=2,
            )
        except Exception as e:
            return f"# Error converting to YAML: {e}"


def to_json(schema: dict[str, Any]) -> str:
    """
    Convert JSON Schema to formatted JSON.

    Args:
        schema: JSON Schema to convert

    Returns:
        Formatted JSON string
    """
    formatter = JSONFormatter(schema)
    return formatter.format()


def to_yaml(schema: dict[str, Any]) -> str:
    """
    Convert JSON Schema to YAML.

    Args:
        schema: JSON Schema to convert

    Returns:
        YAML string
    """
    formatter = YAMLFormatter(schema)
    return formatter.format()
