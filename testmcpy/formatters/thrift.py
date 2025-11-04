"""Apache Thrift IDL generator from JSON Schema."""

import re
from typing import Any

from .base import SchemaFormatter


class ThriftFormatter(SchemaFormatter):
    """Converts JSON Schema to Apache Thrift IDL."""

    def __init__(self, schema: dict[str, Any], struct_name: str = "Parameters"):
        super().__init__(schema, struct_name)
        self.structs: list[str] = []
        self.nested_struct_counter = 0

    def format(self) -> str:
        """Format schema as Thrift struct."""
        if not self.schema or "properties" not in self.schema:
            return f"""struct {self.name} {{
  // No parameters defined
}}"""

        lines = []

        # Generate nested structs first
        for name, prop in self.schema["properties"].items():
            self._convert_type(prop, name, 0)

        # Add nested structs
        if self.structs:
            lines.extend(self.structs)
            lines.append("")

        lines.append(f"struct {self.name} {{")

        field_id = 1
        for name, prop in self.schema["properties"].items():
            thrift_type = self._convert_type(prop, name, 0)
            optional = "optional " if name not in self.schema.get("required", []) else ""
            comment = f"  // {prop['description']}" if prop.get("description") else ""
            lines.append(f"  {field_id}: {optional}{thrift_type} {name}{comment}")
            field_id += 1

        lines.append("}")

        return "\n".join(lines)

    def _convert_type(self, prop: dict[str, Any], parent_name: str = "", depth: int = 0) -> str:
        """Convert JSON Schema type to Thrift type."""
        prop_type = prop.get("type")

        if prop_type == "string":
            return "string"
        elif prop_type == "number":
            return "double"
        elif prop_type == "integer":
            return "i64" if prop.get("format") == "int64" else "i32"
        elif prop_type == "boolean":
            return "bool"
        elif prop_type == "array":
            if "items" in prop:
                item_type = self._convert_type(prop["items"], parent_name, depth)
                return f"list<{item_type}>"
            return "list<string>"
        elif prop_type == "object":
            if "properties" in prop:
                self.nested_struct_counter += 1
                # Sanitize struct name
                nested_struct_name = (
                    re.sub(
                        r"[^a-zA-Z0-9_]",
                        "_",
                        f"{parent_name[0].upper()}{parent_name[1:]}",
                    )
                    if parent_name
                    else f"Nested{self.nested_struct_counter}"
                )

                nested_lines = [f"struct {nested_struct_name} {{"]
                field_id = 1
                for nested_name, nested_prop in prop["properties"].items():
                    nested_type = self._convert_type(nested_prop, nested_name, depth + 1)
                    optional = (
                        "optional " if nested_name not in prop.get("required", []) else ""
                    )
                    comment = (
                        f"  // {nested_prop['description']}"
                        if nested_prop.get("description")
                        else ""
                    )
                    nested_lines.append(
                        f"  {field_id}: {optional}{nested_type} {nested_name}{comment}"
                    )
                    field_id += 1
                nested_lines.append("}")

                self.structs.append("\n".join(nested_lines))
                return nested_struct_name
            return "map<string, string>"
        else:
            return "string"


def to_thrift(schema: dict[str, Any], struct_name: str = "Parameters") -> str:
    """
    Convert JSON Schema to Apache Thrift IDL.

    Args:
        schema: JSON Schema to convert
        struct_name: Name for the Thrift struct

    Returns:
        Thrift IDL definition as string
    """
    formatter = ThriftFormatter(schema, struct_name)
    return formatter.format()
