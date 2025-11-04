"""
Schema formatters for converting JSON Schema to various formats.

This module provides formatters for converting MCP tool schemas to
TypeScript, Python, Protobuf, Thrift, GraphQL, cURL, JSON, and YAML.
"""

from .curl import to_curl
from .graphql import to_graphql
from .javascript_client import to_javascript_client
from .json_yaml import to_json, to_yaml
from .protobuf import to_protobuf
from .python import to_python
from .python_client import to_python_client
from .thrift import to_thrift
from .typescript import to_typescript
from .typescript_client import to_typescript_client

__all__ = [
    "to_typescript",
    "to_python",
    "to_protobuf",
    "to_thrift",
    "to_graphql",
    "to_curl",
    "to_json",
    "to_yaml",
    "to_python_client",
    "to_javascript_client",
    "to_typescript_client",
]

# Format registry for easy lookup
FORMATS = {
    "json": {"label": "JSON", "language": "json", "convert": to_json},
    "yaml": {"label": "YAML", "language": "yaml", "convert": to_yaml},
    "typescript": {"label": "TypeScript", "language": "typescript", "convert": to_typescript},
    "python": {"label": "Python", "language": "python", "convert": to_python},
    "protobuf": {"label": "Protobuf", "language": "protobuf", "convert": to_protobuf},
    "thrift": {"label": "Thrift", "language": "thrift", "convert": to_thrift},
    "graphql": {"label": "GraphQL", "language": "graphql", "convert": to_graphql},
    "curl": {"label": "cURL", "language": "bash", "convert": to_curl},
    "python_client": {"label": "Python Client", "language": "python", "convert": to_python_client},
    "javascript_client": {"label": "JavaScript Client", "language": "javascript", "convert": to_javascript_client},
    "typescript_client": {"label": "TypeScript Client", "language": "typescript", "convert": to_typescript_client},
}
