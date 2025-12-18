"""GraphQL Input Type generator from JSON Schema."""

import re
from typing import Any

from .base import SchemaFormatter


class GraphQLFormatter(SchemaFormatter):
    """Converts JSON Schema to GraphQL Input Type."""

    def __init__(self, schema: dict[str, Any], type_name: str = "ParametersInput"):
        super().__init__(schema, type_name)
        self.types: list[str] = []
        self.nested_type_counter = 0

    def format(self) -> str:
        """Format schema as GraphQL input type."""
        if not self.schema or "properties" not in self.schema:
            return f"""input {self.name} {{
  # No parameters defined
}}"""

        lines = []

        # Generate nested types first
        for name, prop in self.schema["properties"].items():
            self._convert_type(prop, name, 0)

        # Add nested types
        if self.types:
            lines.extend(self.types)
            lines.append("")

        lines.append(f"input {self.name} {{")

        for name, prop in self.schema["properties"].items():
            graphql_type = self._convert_type(prop, name, 0)
            required = "!" if name in self.schema.get("required", []) else ""
            comment = f"  # {prop['description']}" if prop.get("description") else ""
            lines.append(f"  {name}: {graphql_type}{required}{comment}")

        lines.append("}")

        return "\n".join(lines)

    def _convert_type(self, prop: dict[str, Any], parent_name: str = "", depth: int = 0) -> str:
        """Convert JSON Schema type to GraphQL type."""
        if "enum" in prop:
            # Create enum type
            self.nested_type_counter += 1
            # Sanitize enum name
            enum_name = (
                re.sub(
                    r"[^a-zA-Z0-9_]",
                    "_",
                    f"{parent_name[0].upper()}{parent_name[1:]}Enum",
                )
                if parent_name
                else f"Enum{self.nested_type_counter}"
            )

            enum_lines = [f"enum {enum_name} {{"]
            for value in prop["enum"]:
                enum_value = (
                    re.sub(r"[^A-Z0-9_]", "_", str(value).upper())
                    if isinstance(value, str)
                    else f"VALUE_{value}"
                )
                enum_lines.append(f"  {enum_value}")
            enum_lines.append("}")
            self.types.append("\n".join(enum_lines))

            return enum_name

        prop_type = prop.get("type")

        if prop_type == "string":
            return "String"
        elif prop_type == "number":
            return "Float"
        elif prop_type == "integer":
            return "Int"
        elif prop_type == "boolean":
            return "Boolean"
        elif prop_type == "array":
            if "items" in prop:
                item_type = self._convert_type(prop["items"], parent_name, depth)
                return f"[{item_type}]"
            return "[String]"
        elif prop_type == "object":
            if "properties" in prop:
                self.nested_type_counter += 1
                # Sanitize type name
                nested_type_name = (
                    re.sub(
                        r"[^a-zA-Z0-9_]",
                        "_",
                        f"{parent_name[0].upper()}{parent_name[1:]}Input",
                    )
                    if parent_name
                    else f"NestedInput{self.nested_type_counter}"
                )

                nested_lines = [f"input {nested_type_name} {{"]
                for nested_name, nested_prop in prop["properties"].items():
                    nested_type = self._convert_type(nested_prop, nested_name, depth + 1)
                    required = "!" if nested_name in prop.get("required", []) else ""
                    comment = (
                        f"  # {nested_prop['description']}"
                        if nested_prop.get("description")
                        else ""
                    )
                    nested_lines.append(f"  {nested_name}: {nested_type}{required}{comment}")
                nested_lines.append("}")

                self.types.append("\n".join(nested_lines))
                return nested_type_name
            return "JSON"  # Custom scalar for unstructured objects
        else:
            return "String"


def to_graphql(schema: dict[str, Any], type_name: str = "ParametersInput") -> str:
    """
    Convert JSON Schema to GraphQL Input Type.

    Args:
        schema: JSON Schema to convert
        type_name: Name for the GraphQL input type

    Returns:
        GraphQL input type definition as string
    """
    formatter = GraphQLFormatter(schema, type_name)
    return formatter.format()
