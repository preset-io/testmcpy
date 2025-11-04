"""
Base formatter module with shared utilities for schema conversion.

This module provides the base class and utility functions for converting
JSON Schema to various formats, including $ref resolution and example generation.
"""

from typing import Any


class SchemaFormatter:
    """Base class for schema formatters."""

    def __init__(self, schema: dict[str, Any], name: str = "Parameters"):
        """Initialize formatter with schema and name."""
        self.original_schema = schema
        self.schema = resolve_schema(schema)
        self.name = name

    def format(self) -> str:
        """Format schema to target language/format. Must be implemented by subclasses."""
        raise NotImplementedError("Subclasses must implement format()")


def resolve_ref(ref: str, schema: dict[str, Any]) -> dict[str, Any] | None:
    """
    Resolve $ref references in JSON Schema.

    Handles both internal references like:
    - #/$defs/TypeName
    - #/definitions/TypeName

    Args:
        ref: The $ref string (e.g., "#/$defs/MyType")
        schema: The complete schema to resolve against

    Returns:
        The resolved schema object, or None if not found
    """
    if not ref or not isinstance(ref, str):
        return None

    # Handle internal references like #/$defs/TypeName or #/definitions/TypeName
    if ref.startswith("#/"):
        path = ref[2:].split("/")
        current = schema

        for segment in path:
            if not current or not isinstance(current, dict):
                return None
            current = current.get(segment)

        return current

    return None


def resolve_property(prop: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
    """
    Resolve all $refs in a property recursively.

    Args:
        prop: The property to resolve
        schema: The complete schema for resolving $refs

    Returns:
        The resolved property
    """
    if not prop or not isinstance(prop, dict):
        return prop

    prop = prop.copy()

    # If this property is a $ref, resolve it
    if "$ref" in prop:
        resolved = resolve_ref(prop["$ref"], schema)
        if resolved:
            # Merge any additional properties from the reference with the resolved definition
            ref = prop.pop("$ref")
            resolved = resolved.copy()
            resolved.update(prop)
            prop = resolved

    # Handle anyOf by taking the first non-null option
    if "anyOf" in prop and isinstance(prop["anyOf"], list):
        # Filter out null types and take the first valid type
        non_null_types = [t for t in prop["anyOf"] if t.get("type") != "null"]
        if non_null_types:
            # If there's a null in anyOf, make it optional
            has_null = any(t.get("type") == "null" for t in prop["anyOf"])
            first_type = resolve_property(non_null_types[0], schema)
            # Preserve other properties like default, description
            result = {**first_type, **prop}
            if has_null:
                result["nullable"] = True
            return result

    # Recursively resolve nested properties
    if "properties" in prop:
        resolved_props = {}
        for key, value in prop["properties"].items():
            resolved_props[key] = resolve_property(value, schema)
        prop["properties"] = resolved_props

    # Resolve array items
    if "items" in prop:
        prop["items"] = resolve_property(prop["items"], schema)

    return prop


def resolve_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """
    Resolve all $refs in a schema.

    Args:
        schema: The schema to resolve

    Returns:
        The resolved schema
    """
    if not schema or not isinstance(schema, dict):
        return schema

    resolved = schema.copy()

    # Resolve properties
    if "properties" in resolved:
        resolved_props = {}
        for key, value in resolved["properties"].items():
            resolved_props[key] = resolve_property(value, schema)
        resolved["properties"] = resolved_props

    return resolved


def generate_example(schema: dict[str, Any]) -> dict[str, Any]:
    """
    Generate example data from schema.

    Args:
        schema: The schema to generate examples from

    Returns:
        Dictionary with example values
    """
    if not schema or "properties" not in schema:
        return {}

    example = {}

    for name, prop in schema["properties"].items():
        # Always include required fields, include optional only if they have defaults
        is_required = name in schema.get("required", [])

        if not is_required and "default" not in prop:
            continue

        if "default" in prop:
            example[name] = prop["default"]
        elif "enum" in prop and prop["enum"]:
            example[name] = prop["enum"][0]
        elif "anyOf" in prop and isinstance(prop["anyOf"], list):
            # Handle anyOf - take the first non-null type
            non_null_types = [t for t in prop["anyOf"] if t.get("type") != "null"]
            if non_null_types:
                example[name] = generate_example_value(non_null_types[0])
            else:
                example[name] = None
        else:
            example[name] = generate_example_value(prop)

    return example


def generate_example_value(prop: dict[str, Any]) -> Any:
    """
    Generate example value for a property.

    Args:
        prop: The property schema

    Returns:
        An appropriate example value
    """
    if "default" in prop:
        return prop["default"]
    if "enum" in prop and prop["enum"]:
        return prop["enum"][0]

    prop_type = prop.get("type")

    if prop_type == "string":
        if prop.get("format") == "email":
            return "user@example.com"
        elif prop.get("format") == "uri":
            return "https://example.com"
        elif "example" in prop:
            return prop["example"]
        else:
            return "string"
    elif prop_type == "number":
        if "minimum" in prop:
            return prop["minimum"]
        elif "example" in prop:
            return prop["example"]
        else:
            return 0.0
    elif prop_type == "integer":
        if "minimum" in prop:
            return prop["minimum"]
        elif "example" in prop:
            return prop["example"]
        else:
            return 0
    elif prop_type == "boolean":
        if "example" in prop:
            return prop["example"]
        else:
            return True
    elif prop_type == "array":
        if "items" in prop:
            return [generate_example_value(prop["items"])]
        else:
            return []
    elif prop_type == "object":
        if "properties" in prop:
            return generate_example(prop)
        else:
            return {}
    else:
        return None
