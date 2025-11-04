"""Protocol Buffers (proto3) generator from JSON Schema."""

import re
from typing import Any

from .base import SchemaFormatter


class ProtobufFormatter(SchemaFormatter):
    """Converts JSON Schema to Protocol Buffers (proto3)."""

    def __init__(self, schema: dict[str, Any], message_name: str = "Parameters"):
        super().__init__(schema, message_name)
        self.messages: list[str] = []
        self.nested_message_counter = 0

    def format(self) -> str:
        """Format schema as Protocol Buffers message."""
        if not self.schema or "properties" not in self.schema:
            return f"""syntax = "proto3";

message {self.name} {{
  // No parameters defined
}}"""

        lines = ['syntax = "proto3";', ""]

        # Generate nested messages first
        field_number = 1
        for name, prop in self.schema["properties"].items():
            self._convert_type(prop, field_number, name, 0)
            field_number += 1

        # Add nested messages
        if self.messages:
            lines.extend(self.messages)
            lines.append("")

        lines.append(f"message {self.name} {{")

        field_number = 1
        for name, prop in self.schema["properties"].items():
            result = self._convert_type(prop, field_number, name, 0)
            proto_type = result["type"]
            repeated = result["repeated"]
            comment = f"  // {prop['description']}" if prop.get("description") else ""
            repeated_keyword = "repeated " if repeated else ""
            lines.append(f"  {repeated_keyword}{proto_type} {name} = {field_number};{comment}")
            field_number += 1

        lines.append("}")

        return "\n".join(lines)

    def _convert_type(
        self, prop: dict[str, Any], field_number: int, parent_name: str = "", depth: int = 0
    ) -> dict[str, Any]:
        """Convert JSON Schema type to Protobuf type."""
        proto_type = None
        is_repeated = False

        prop_type = prop.get("type")

        if prop_type == "string":
            proto_type = "string"
        elif prop_type == "number":
            proto_type = "double"
        elif prop_type == "integer":
            proto_type = "int64" if prop.get("format") == "int64" else "int32"
        elif prop_type == "boolean":
            proto_type = "bool"
        elif prop_type == "array":
            is_repeated = True
            if "items" in prop:
                proto_type = self._convert_type(prop["items"], field_number, parent_name, depth)[
                    "type"
                ]
            else:
                proto_type = "string"
        elif prop_type == "object":
            if "properties" in prop:
                self.nested_message_counter += 1
                # Sanitize message name
                nested_message_name = (
                    re.sub(
                        r"[^a-zA-Z0-9_]",
                        "_",
                        f"{parent_name[0].upper()}{parent_name[1:]}",
                    )
                    if parent_name
                    else f"Nested{self.nested_message_counter}"
                )

                nested_lines = [f"message {nested_message_name} {{"]
                nested_field_num = 1
                for nested_name, nested_prop in prop["properties"].items():
                    result = self._convert_type(
                        nested_prop, nested_field_num, nested_name, depth + 1
                    )
                    nested_type = result["type"]
                    repeated = result["repeated"]
                    comment = (
                        f"  // {nested_prop['description']}"
                        if nested_prop.get("description")
                        else ""
                    )
                    repeated_keyword = "repeated " if repeated else ""
                    nested_lines.append(
                        f"  {repeated_keyword}{nested_type} {nested_name} = {nested_field_num};{comment}"
                    )
                    nested_field_num += 1
                nested_lines.append("}")

                self.messages.append("\n".join(nested_lines))
                proto_type = nested_message_name
            else:
                proto_type = "map<string, string>"  # Generic map for unstructured objects
        else:
            proto_type = "string"

        return {"type": proto_type, "repeated": is_repeated}


def to_protobuf(schema: dict[str, Any], message_name: str = "Parameters") -> str:
    """
    Convert JSON Schema to Protocol Buffers (proto3).

    Args:
        schema: JSON Schema to convert
        message_name: Name for the Protocol Buffers message

    Returns:
        Protocol Buffers definition as string
    """
    formatter = ProtobufFormatter(schema, message_name)
    return formatter.format()
