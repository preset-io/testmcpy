"""
Unit tests for the testmcpy formatters module.

Tests cover:
- Schema formatting and resolution
- $ref resolution in JSON schemas
- anyOf/oneOf handling
- Property extraction
- Edge cases like nested schemas and complex references
"""

import pytest

from testmcpy.formatters.base import (
    SchemaFormatter,
    generate_example,
    generate_example_value,
    resolve_property,
    resolve_ref,
    resolve_schema,
)


class TestResolveRef:
    """Test $ref resolution functionality."""

    def test_resolve_ref_simple_defs(self):
        """Test resolving a simple $ref to $defs."""
        schema = {
            "$defs": {
                "User": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                }
            }
        }
        result = resolve_ref("#/$defs/User", schema)
        assert result == schema["$defs"]["User"]

    def test_resolve_ref_definitions(self):
        """Test resolving a $ref to definitions (legacy format)."""
        schema = {
            "definitions": {
                "User": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                }
            }
        }
        result = resolve_ref("#/definitions/User", schema)
        assert result == schema["definitions"]["User"]

    def test_resolve_ref_nested_path(self):
        """Test resolving a deeply nested $ref."""
        schema = {
            "$defs": {
                "nested": {
                    "objects": {
                        "User": {
                            "type": "object",
                            "properties": {"name": {"type": "string"}},
                        }
                    }
                }
            }
        }
        result = resolve_ref("#/$defs/nested/objects/User", schema)
        assert result == schema["$defs"]["nested"]["objects"]["User"]

    def test_resolve_ref_not_found(self):
        """Test resolving a $ref that doesn't exist."""
        schema = {"$defs": {"User": {"type": "object"}}}
        result = resolve_ref("#/$defs/NonExistent", schema)
        assert result is None

    def test_resolve_ref_invalid_ref(self):
        """Test resolving an invalid $ref."""
        schema = {"$defs": {"User": {"type": "object"}}}
        assert resolve_ref("", schema) is None
        assert resolve_ref(None, schema) is None
        assert resolve_ref("not-a-ref", schema) is None

    def test_resolve_ref_invalid_path(self):
        """Test resolving a $ref with invalid path segments."""
        schema = {"$defs": {"User": "not-a-dict"}}
        result = resolve_ref("#/$defs/User/invalid", schema)
        assert result is None


class TestResolveProperty:
    """Test property resolution functionality."""

    def test_resolve_property_simple_ref(self):
        """Test resolving a property with a simple $ref."""
        schema = {
            "$defs": {
                "Address": {
                    "type": "object",
                    "properties": {
                        "street": {"type": "string"},
                        "city": {"type": "string"},
                    },
                }
            }
        }
        prop = {"$ref": "#/$defs/Address"}
        result = resolve_property(prop, schema)

        assert result["type"] == "object"
        assert "properties" in result
        assert "street" in result["properties"]
        assert "$ref" not in result

    def test_resolve_property_ref_with_additional_properties(self):
        """Test resolving a $ref with additional properties merged."""
        schema = {
            "$defs": {
                "User": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                }
            }
        }
        prop = {"$ref": "#/$defs/User", "description": "A user object"}
        result = resolve_property(prop, schema)

        assert result["type"] == "object"
        assert result["description"] == "A user object"
        assert "$ref" not in result

    def test_resolve_property_anyof_non_null(self):
        """Test resolving anyOf with non-null types."""
        schema = {}
        prop = {
            "anyOf": [
                {"type": "string"},
                {"type": "integer"},
            ]
        }
        result = resolve_property(prop, schema)

        # Should take the first non-null type
        assert result["type"] == "string"

    def test_resolve_property_anyof_with_null(self):
        """Test resolving anyOf with null type."""
        schema = {}
        prop = {
            "anyOf": [
                {"type": "string"},
                {"type": "null"},
            ]
        }
        result = resolve_property(prop, schema)

        # Should take the first non-null type and mark as nullable
        assert result["type"] == "string"
        assert result["nullable"] is True

    def test_resolve_property_anyof_only_null(self):
        """Test resolving anyOf with only null type."""
        schema = {}
        prop = {
            "anyOf": [
                {"type": "null"},
            ]
        }
        result = resolve_property(prop, schema)

        # Should handle gracefully even with only null
        assert "anyOf" in result or result.get("type") == "null"

    def test_resolve_property_anyof_preserves_default(self):
        """Test that anyOf resolution preserves default values."""
        schema = {}
        prop = {
            "anyOf": [
                {"type": "string"},
                {"type": "null"},
            ],
            "default": "default_value",
            "description": "Test property",
        }
        result = resolve_property(prop, schema)

        assert result.get("default") == "default_value"
        assert result.get("description") == "Test property"

    def test_resolve_property_nested_properties(self):
        """Test resolving properties with nested object properties."""
        schema = {
            "$defs": {
                "Address": {
                    "type": "object",
                    "properties": {"street": {"type": "string"}},
                }
            }
        }
        prop = {
            "type": "object",
            "properties": {
                "user": {"type": "string"},
                "address": {"$ref": "#/$defs/Address"},
            },
        }
        result = resolve_property(prop, schema)

        assert result["type"] == "object"
        assert "properties" in result
        assert result["properties"]["user"]["type"] == "string"
        assert result["properties"]["address"]["type"] == "object"
        assert "$ref" not in result["properties"]["address"]

    def test_resolve_property_array_items(self):
        """Test resolving array items with $ref."""
        schema = {
            "$defs": {
                "User": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                }
            }
        }
        prop = {
            "type": "array",
            "items": {"$ref": "#/$defs/User"},
        }
        result = resolve_property(prop, schema)

        assert result["type"] == "array"
        assert result["items"]["type"] == "object"
        assert "$ref" not in result["items"]

    def test_resolve_property_empty_or_none(self):
        """Test resolving empty or None properties."""
        schema = {}
        assert resolve_property(None, schema) is None
        assert resolve_property({}, schema) == {}

    def test_resolve_property_non_dict(self):
        """Test resolving non-dictionary properties."""
        schema = {}
        assert resolve_property("string", schema) == "string"
        assert resolve_property(123, schema) == 123


class TestResolveSchema:
    """Test schema resolution functionality."""

    def test_resolve_schema_simple(self):
        """Test resolving a simple schema with $ref in properties."""
        schema = {
            "$defs": {
                "User": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                }
            },
            "properties": {
                "user": {"$ref": "#/$defs/User"},
                "count": {"type": "integer"},
            },
        }
        result = resolve_schema(schema)

        assert "properties" in result
        assert result["properties"]["user"]["type"] == "object"
        assert "$ref" not in result["properties"]["user"]
        assert result["properties"]["count"]["type"] == "integer"

    def test_resolve_schema_multiple_refs(self):
        """Test resolving a schema with multiple $refs."""
        schema = {
            "$defs": {
                "User": {"type": "object", "properties": {"name": {"type": "string"}}},
                "Address": {"type": "object", "properties": {"city": {"type": "string"}}},
            },
            "properties": {
                "user": {"$ref": "#/$defs/User"},
                "address": {"$ref": "#/$defs/Address"},
            },
        }
        result = resolve_schema(schema)

        assert result["properties"]["user"]["type"] == "object"
        assert result["properties"]["address"]["type"] == "object"
        assert "$ref" not in result["properties"]["user"]
        assert "$ref" not in result["properties"]["address"]

    def test_resolve_schema_nested_refs(self):
        """Test resolving a schema with nested $refs."""
        schema = {
            "$defs": {
                "Address": {
                    "type": "object",
                    "properties": {"city": {"type": "string"}},
                },
                "User": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "address": {"$ref": "#/$defs/Address"},
                    },
                },
            },
            "properties": {
                "user": {"$ref": "#/$defs/User"},
            },
        }
        result = resolve_schema(schema)

        assert result["properties"]["user"]["type"] == "object"
        assert result["properties"]["user"]["properties"]["address"]["type"] == "object"
        assert "$ref" not in result["properties"]["user"]["properties"]["address"]

    def test_resolve_schema_empty_or_none(self):
        """Test resolving empty or None schemas."""
        assert resolve_schema(None) is None
        assert resolve_schema({}) == {}

    def test_resolve_schema_no_properties(self):
        """Test resolving a schema without properties."""
        schema = {
            "$defs": {"User": {"type": "object"}},
            "type": "object",
        }
        result = resolve_schema(schema)
        assert result == schema

    def test_resolve_schema_preserves_defs(self):
        """Test that resolving schema preserves $defs."""
        schema = {
            "$defs": {
                "User": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                }
            },
            "properties": {
                "user": {"$ref": "#/$defs/User"},
            },
        }
        result = resolve_schema(schema)

        # $defs should still be present in the result
        assert "$defs" in result


class TestGenerateExampleValue:
    """Test example value generation for individual properties."""

    def test_generate_example_string(self):
        """Test generating example for string type."""
        assert generate_example_value({"type": "string"}) == "string"

    def test_generate_example_string_email(self):
        """Test generating example for email format."""
        result = generate_example_value({"type": "string", "format": "email"})
        assert result == "user@example.com"

    def test_generate_example_string_uri(self):
        """Test generating example for URI format."""
        result = generate_example_value({"type": "string", "format": "uri"})
        assert result == "https://example.com"

    def test_generate_example_string_with_example(self):
        """Test generating example with explicit example value."""
        result = generate_example_value({"type": "string", "example": "custom"})
        assert result == "custom"

    def test_generate_example_integer(self):
        """Test generating example for integer type."""
        assert generate_example_value({"type": "integer"}) == 0

    def test_generate_example_integer_with_minimum(self):
        """Test generating example for integer with minimum."""
        result = generate_example_value({"type": "integer", "minimum": 10})
        assert result == 10

    def test_generate_example_number(self):
        """Test generating example for number type."""
        assert generate_example_value({"type": "number"}) == 0.0

    def test_generate_example_number_with_minimum(self):
        """Test generating example for number with minimum."""
        result = generate_example_value({"type": "number", "minimum": 5.5})
        assert result == 5.5

    def test_generate_example_boolean(self):
        """Test generating example for boolean type."""
        assert generate_example_value({"type": "boolean"}) is True

    def test_generate_example_array(self):
        """Test generating example for array type."""
        result = generate_example_value({"type": "array", "items": {"type": "string"}})
        assert result == ["string"]

    def test_generate_example_array_no_items(self):
        """Test generating example for array without items."""
        result = generate_example_value({"type": "array"})
        assert result == []

    def test_generate_example_object(self):
        """Test generating example for object type."""
        prop = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "age": {"type": "integer"},
            },
            "required": ["name"],
        }
        result = generate_example_value(prop)
        assert isinstance(result, dict)
        assert "name" in result

    def test_generate_example_object_no_properties(self):
        """Test generating example for object without properties."""
        result = generate_example_value({"type": "object"})
        assert result == {}

    def test_generate_example_enum(self):
        """Test generating example for enum."""
        result = generate_example_value({"enum": ["option1", "option2", "option3"]})
        assert result == "option1"

    def test_generate_example_default(self):
        """Test that default values take precedence."""
        result = generate_example_value({"type": "string", "default": "default_val"})
        assert result == "default_val"

    def test_generate_example_unknown_type(self):
        """Test generating example for unknown type."""
        result = generate_example_value({"type": "unknown"})
        assert result is None


class TestGenerateExample:
    """Test example generation for complete schemas."""

    def test_generate_example_simple(self):
        """Test generating example for simple schema."""
        schema = {
            "properties": {
                "name": {"type": "string"},
                "age": {"type": "integer"},
            },
            "required": ["name", "age"],
        }
        result = generate_example(schema)
        assert "name" in result
        assert "age" in result
        assert result["name"] == "string"
        assert result["age"] == 0

    def test_generate_example_with_defaults(self):
        """Test generating example with default values."""
        schema = {
            "properties": {
                "name": {"type": "string", "default": "John Doe"},
                "age": {"type": "integer", "default": 30},
            },
            "required": ["name"],
        }
        result = generate_example(schema)
        assert result["name"] == "John Doe"
        assert result["age"] == 30

    def test_generate_example_optional_without_default(self):
        """Test that optional properties without defaults are excluded."""
        schema = {
            "properties": {
                "name": {"type": "string"},
                "nickname": {"type": "string"},
            },
            "required": ["name"],
        }
        result = generate_example(schema)
        assert "name" in result
        assert "nickname" not in result

    def test_generate_example_optional_with_default(self):
        """Test that optional properties with defaults are included."""
        schema = {
            "properties": {
                "name": {"type": "string"},
                "nickname": {"type": "string", "default": "Nick"},
            },
            "required": ["name"],
        }
        result = generate_example(schema)
        assert "name" in result
        assert "nickname" in result
        assert result["nickname"] == "Nick"

    def test_generate_example_enum_required(self):
        """Test generating example for required enum."""
        schema = {
            "properties": {
                "status": {"enum": ["active", "inactive", "pending"]},
            },
            "required": ["status"],
        }
        result = generate_example(schema)
        assert result["status"] == "active"

    def test_generate_example_anyof(self):
        """Test generating example for anyOf."""
        schema = {
            "properties": {
                "value": {
                    "anyOf": [
                        {"type": "string"},
                        {"type": "integer"},
                    ]
                },
            },
            "required": ["value"],
        }
        result = generate_example(schema)
        assert "value" in result
        assert result["value"] == "string"

    def test_generate_example_anyof_with_null(self):
        """Test generating example for anyOf with null."""
        schema = {
            "properties": {
                "value": {
                    "anyOf": [
                        {"type": "string"},
                        {"type": "null"},
                    ]
                },
            },
            "required": ["value"],
        }
        result = generate_example(schema)
        assert "value" in result
        assert result["value"] == "string"

    def test_generate_example_nested_object(self):
        """Test generating example for nested objects."""
        schema = {
            "properties": {
                "user": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "email": {"type": "string", "format": "email"},
                    },
                    "required": ["name", "email"],
                }
            },
            "required": ["user"],
        }
        result = generate_example(schema)
        assert "user" in result
        assert isinstance(result["user"], dict)
        assert result["user"]["name"] == "string"
        assert result["user"]["email"] == "user@example.com"

    def test_generate_example_empty_schema(self):
        """Test generating example for empty schema."""
        assert generate_example({}) == {}
        assert generate_example(None) == {}

    def test_generate_example_no_properties(self):
        """Test generating example for schema without properties."""
        schema = {"type": "object"}
        result = generate_example(schema)
        assert result == {}


class TestSchemaFormatter:
    """Test the SchemaFormatter base class."""

    def test_schema_formatter_init(self):
        """Test SchemaFormatter initialization."""
        schema = {
            "$defs": {
                "User": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                }
            },
            "properties": {
                "user": {"$ref": "#/$defs/User"},
            },
        }
        formatter = SchemaFormatter(schema, "TestSchema")

        assert formatter.name == "TestSchema"
        assert formatter.original_schema == schema
        # Schema should be resolved
        assert "$ref" not in formatter.schema.get("properties", {}).get("user", {})

    def test_schema_formatter_default_name(self):
        """Test SchemaFormatter with default name."""
        schema = {"properties": {"test": {"type": "string"}}}
        formatter = SchemaFormatter(schema)
        assert formatter.name == "Parameters"

    def test_schema_formatter_format_not_implemented(self):
        """Test that format() raises NotImplementedError."""
        schema = {"properties": {"test": {"type": "string"}}}
        formatter = SchemaFormatter(schema)

        with pytest.raises(NotImplementedError, match="Subclasses must implement format"):
            formatter.format()


class TestComplexSchemaScenarios:
    """Test complex real-world schema scenarios."""

    def test_deeply_nested_refs(self):
        """Test schema with deeply nested references."""
        schema = {
            "$defs": {
                "Country": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                },
                "City": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "country": {"$ref": "#/$defs/Country"},
                    },
                },
                "Address": {
                    "type": "object",
                    "properties": {
                        "street": {"type": "string"},
                        "city": {"$ref": "#/$defs/City"},
                    },
                },
                "User": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "address": {"$ref": "#/$defs/Address"},
                    },
                },
            },
            "properties": {
                "user": {"$ref": "#/$defs/User"},
            },
        }
        result = resolve_schema(schema)

        # Verify all refs are resolved
        user_prop = result["properties"]["user"]
        assert "$ref" not in user_prop
        assert "$ref" not in user_prop["properties"]["address"]
        assert "$ref" not in user_prop["properties"]["address"]["properties"]["city"]
        assert (
            "$ref"
            not in user_prop["properties"]["address"]["properties"]["city"]["properties"]["country"]
        )

    def test_array_of_refs(self):
        """Test schema with array of referenced objects."""
        schema = {
            "$defs": {
                "Tag": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                }
            },
            "properties": {
                "tags": {
                    "type": "array",
                    "items": {"$ref": "#/$defs/Tag"},
                }
            },
        }
        result = resolve_schema(schema)

        assert result["properties"]["tags"]["type"] == "array"
        assert result["properties"]["tags"]["items"]["type"] == "object"
        assert "$ref" not in result["properties"]["tags"]["items"]

    def test_mixed_anyof_with_refs(self):
        """Test anyOf containing $refs."""
        schema = {
            "$defs": {
                "StringValue": {
                    "type": "object",
                    "properties": {"value": {"type": "string"}},
                },
                "NumberValue": {
                    "type": "object",
                    "properties": {"value": {"type": "number"}},
                },
            },
            "properties": {
                "data": {
                    "anyOf": [
                        {"$ref": "#/$defs/StringValue"},
                        {"$ref": "#/$defs/NumberValue"},
                    ]
                }
            },
        }
        result = resolve_schema(schema)

        # anyOf should still be present but first option should be selected during property resolution
        data_prop = result["properties"]["data"]
        # The base resolve_property will take the first non-null option
        assert "type" in data_prop or "anyOf" in data_prop

    def test_complex_example_generation(self):
        """Test example generation for complex nested schema."""
        schema = {
            "properties": {
                "user": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "default": "John"},
                        "email": {"type": "string", "format": "email"},
                        "age": {"type": "integer", "minimum": 18},
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "metadata": {
                            "type": "object",
                            "properties": {
                                "created": {"type": "string"},
                            },
                            "required": ["created"],
                        },
                    },
                    "required": ["name", "email", "metadata"],
                }
            },
            "required": ["user"],
        }
        result = generate_example(schema)

        assert "user" in result
        assert result["user"]["name"] == "John"
        assert result["user"]["email"] == "user@example.com"
        assert "metadata" in result["user"]
        assert result["user"]["metadata"]["created"] == "string"

    def test_schema_with_additional_properties_preserved(self):
        """Test that additional schema properties are preserved during resolution."""
        schema = {
            "$defs": {
                "User": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                }
            },
            "properties": {
                "user": {"$ref": "#/$defs/User"},
            },
            "required": ["user"],
            "additionalProperties": False,
            "title": "Test Schema",
            "description": "A test schema",
        }
        result = resolve_schema(schema)

        assert result["required"] == ["user"]
        assert result["additionalProperties"] is False
        assert result["title"] == "Test Schema"
        assert result["description"] == "A test schema"

    def test_empty_anyof_handling(self):
        """Test handling of empty anyOf."""
        schema = {}
        prop = {"anyOf": []}
        result = resolve_property(prop, schema)

        # Should preserve the anyOf even if empty
        assert "anyOf" in result

    def test_property_with_multiple_types_in_anyof(self):
        """Test property with multiple complex types in anyOf."""
        schema = {}
        prop = {
            "anyOf": [
                {"type": "object", "properties": {"a": {"type": "string"}}},
                {"type": "array", "items": {"type": "string"}},
                {"type": "string"},
            ]
        }
        result = resolve_property(prop, schema)

        # Should select the first type (object)
        assert result["type"] == "object"

    def test_ref_to_non_existent_definition(self):
        """Test that referencing non-existent definition doesn't crash."""
        schema = {
            "$defs": {
                "User": {"type": "object"},
            },
            "properties": {
                "user": {"$ref": "#/$defs/NonExistent"},
            },
        }
        # Should not raise an error, but ref won't be resolved
        result = resolve_schema(schema)
        # The unresolved ref will remain since it can't be resolved
        assert "properties" in result
