"""TypeScript interface generator from JSON Schema."""

from typing import Any

from .base import SchemaFormatter


class TypeScriptFormatter(SchemaFormatter):
    """Converts JSON Schema to TypeScript interfaces."""

    def __init__(self, schema: dict[str, Any], interface_name: str = "Parameters"):
        super().__init__(schema, interface_name)
        self.interfaces: list[str] = []
        self.nested_interface_counter = 0

    def format(self) -> str:
        """Format schema as TypeScript interface."""
        if not self.schema or "properties" not in self.schema:
            return f"""interface {self.name} {{
  // No parameters defined
}}"""

        lines = [f"interface {self.name} {{"]

        for name, prop in self.schema["properties"].items():
            optional = "" if name in self.schema.get("required", []) else "?"
            prop_type = self._convert_type(prop, 0, name)
            comment = f"  // {prop['description']}" if prop.get("description") else ""
            lines.append(f"  {name}{optional}: {prop_type}{comment}")

        lines.append("}")

        # Prepend nested interfaces
        if self.interfaces:
            return "\n\n".join(self.interfaces) + "\n\n" + "\n".join(lines)

        return "\n".join(lines)

    def _convert_type(self, prop: dict[str, Any], depth: int = 0, parent_name: str = "") -> str:
        """Convert JSON Schema type to TypeScript type."""
        if "enum" in prop:
            return " | ".join(
                f"'{v}'" if isinstance(v, str) else str(v) for v in prop["enum"]
            )

        # Handle anyOf (union types)
        if "anyOf" in prop and isinstance(prop["anyOf"], list):
            types = [
                self._convert_type(t, depth, parent_name)
                for t in prop["anyOf"]
                if t.get("type") != "null"
            ]
            has_null = any(t.get("type") == "null" for t in prop["anyOf"])

            if not types:
                return "null"
            if len(types) == 1:
                return f"{types[0]} | null" if has_null else types[0]

            union_type = " | ".join(types)
            return f"({union_type}) | null" if has_null else union_type

        prop_type = prop.get("type")

        if prop_type == "string":
            return "string"
        elif prop_type in ("number", "integer"):
            return "number"
        elif prop_type == "boolean":
            return "boolean"
        elif prop_type == "array":
            if "items" in prop:
                item_type = self._convert_type(prop["items"], depth, parent_name)
                return f"{item_type}[]"
            return "any[]"
        elif prop_type == "object":
            if "properties" in prop:
                # For nested objects, create a separate interface or inline type
                if depth == 0:
                    # Inline for first level
                    nested_lines = []
                    for nested_name, nested_prop in prop["properties"].items():
                        nested_type = self._convert_type(nested_prop, depth + 1, nested_name)
                        optional = (
                            ""
                            if nested_name in prop.get("required", [])
                            else "?"
                        )
                        comment = (
                            f"  // {nested_prop['description']}"
                            if nested_prop.get("description")
                            else ""
                        )
                        nested_lines.append(
                            f"    {nested_name}{optional}: {nested_type}{comment}"
                        )
                    return "{\n" + "\n".join(nested_lines) + "\n  }"
                else:
                    # Create separate interface for deeper nesting
                    self.nested_interface_counter += 1
                    nested_interface_name = (
                        f"{parent_name[0].upper()}{parent_name[1:]}"
                        if parent_name
                        else f"Nested{self.nested_interface_counter}"
                    )

                    nested_lines = [f"interface {nested_interface_name} {{"]
                    for nested_name, nested_prop in prop["properties"].items():
                        nested_type = self._convert_type(nested_prop, depth + 1, nested_name)
                        optional = (
                            ""
                            if nested_name in prop.get("required", [])
                            else "?"
                        )
                        comment = (
                            f"  // {nested_prop['description']}"
                            if nested_prop.get("description")
                            else ""
                        )
                        nested_lines.append(
                            f"  {nested_name}{optional}: {nested_type}{comment}"
                        )
                    nested_lines.append("}")
                    self.interfaces.append("\n".join(nested_lines))

                    return nested_interface_name
            return "Record<string, any>"
        else:
            return "any"


def to_typescript(schema: dict[str, Any], interface_name: str = "Parameters") -> str:
    """
    Convert JSON Schema to TypeScript interface.

    Args:
        schema: JSON Schema to convert
        interface_name: Name for the TypeScript interface

    Returns:
        TypeScript interface definition as string
    """
    formatter = TypeScriptFormatter(schema, interface_name)
    return formatter.format()
