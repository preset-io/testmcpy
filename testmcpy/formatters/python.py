"""Python TypedDict generator from JSON Schema."""

import re
from typing import Any

from .base import SchemaFormatter


class PythonFormatter(SchemaFormatter):
    """Converts JSON Schema to Python TypedDict."""

    def __init__(self, schema: dict[str, Any], class_name: str = "Parameters"):
        super().__init__(schema, class_name)
        self.classes: list[str] = []
        self.nested_class_counter = 0

    def format(self) -> str:
        """Format schema as Python TypedDict."""
        if not self.schema or "properties" not in self.schema:
            return f"""from typing import TypedDict

class {self.name}(TypedDict):
    # No parameters defined
    pass"""

        lines = [
            "from typing import TypedDict, Optional, List, Dict, Any, Union",
            "",
        ]

        # Generate nested classes first (populate self.classes)
        for name, prop in self.schema["properties"].items():
            is_optional = name not in self.schema.get("required", [])
            self._convert_type(prop, is_optional, name, 0)

        # Add nested classes
        if self.classes:
            lines.extend(self.classes)
            lines.append("")
            lines.append("")

        lines.append(f"class {self.name}(TypedDict):")

        for name, prop in self.schema["properties"].items():
            is_optional = name not in self.schema.get("required", [])
            prop_type = self._convert_type(prop, is_optional, name, 0)
            comment = f"  # {prop['description']}" if prop.get("description") else ""

            # Python identifiers can't have special characters
            safe_name = re.sub(r"[^a-zA-Z0-9_]", "_", name)
            lines.append(f"    {safe_name}: {prop_type}{comment}")

        return "\n".join(lines)

    def _convert_type(
        self, prop: dict[str, Any], is_optional: bool = False, parent_name: str = "", depth: int = 0
    ) -> str:
        """Convert JSON Schema type to Python type."""
        base_type = None
        already_optional = False

        if "enum" in prop:
            enum_values = ", ".join(
                f"'{v}'" if isinstance(v, str) else str(v) for v in prop["enum"]
            )
            base_type = f"Union[{enum_values}]"
        elif "anyOf" in prop and isinstance(prop["anyOf"], list):
            # Handle anyOf (union types)
            types = [
                self._convert_type(t, False, parent_name, depth)
                for t in prop["anyOf"]
                if t.get("type") != "null"
            ]
            has_null = any(t.get("type") == "null" for t in prop["anyOf"])

            if not types:
                base_type = "None"
                already_optional = True
            elif len(types) == 1:
                base_type = types[0]
                if has_null:
                    base_type = f"Optional[{base_type}]"
                    already_optional = True
            else:
                base_type = f"Union[{', '.join(types)}]"
                if has_null:
                    base_type = f"Optional[{base_type}]"
                    already_optional = True
        else:
            prop_type = prop.get("type")

            if prop_type == "string":
                base_type = "str"
            elif prop_type == "number":
                base_type = "float"
            elif prop_type == "integer":
                base_type = "int"
            elif prop_type == "boolean":
                base_type = "bool"
            elif prop_type == "array":
                if "items" in prop:
                    item_type = self._convert_type(prop["items"], False, parent_name, depth)
                    base_type = f"List[{item_type}]"
                else:
                    base_type = "List[Any]"
            elif prop_type == "object":
                if "properties" in prop:
                    # Create nested TypedDict class
                    self.nested_class_counter += 1
                    # Sanitize class name
                    nested_class_name = (
                        re.sub(
                            r"[^a-zA-Z0-9_]",
                            "_",
                            f"{parent_name[0].upper()}{parent_name[1:]}",
                        )
                        if parent_name
                        else f"Nested{self.nested_class_counter}"
                    )

                    nested_lines = [f"class {nested_class_name}(TypedDict):"]
                    for nested_name, nested_prop in prop["properties"].items():
                        nested_is_optional = nested_name not in prop.get("required", [])
                        nested_type = self._convert_type(
                            nested_prop, nested_is_optional, nested_name, depth + 1
                        )
                        comment = (
                            f"  # {nested_prop['description']}"
                            if nested_prop.get("description")
                            else ""
                        )
                        safe_name = re.sub(r"[^a-zA-Z0-9_]", "_", nested_name)
                        nested_lines.append(f"    {safe_name}: {nested_type}{comment}")

                    self.classes.append("\n".join(nested_lines))
                    base_type = nested_class_name
                else:
                    base_type = "Dict[str, Any]"
            else:
                base_type = "Any"

        return f"Optional[{base_type}]" if (is_optional and not already_optional) else base_type


def to_python(schema: dict[str, Any], class_name: str = "Parameters") -> str:
    """
    Convert JSON Schema to Python TypedDict.

    Args:
        schema: JSON Schema to convert
        class_name: Name for the Python class

    Returns:
        Python TypedDict definition as string
    """
    formatter = PythonFormatter(schema, class_name)
    return formatter.format()
