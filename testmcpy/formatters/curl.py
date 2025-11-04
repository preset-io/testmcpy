"""cURL command generator for MCP JSON-RPC requests."""

import json
from typing import Any

from .base import SchemaFormatter, generate_example


class CurlFormatter(SchemaFormatter):
    """Converts JSON Schema to cURL command for MCP JSON-RPC."""

    def __init__(
        self,
        schema: dict[str, Any],
        tool_name: str = "tool_name",
        mcp_url: str | None = None,
        auth_token: str | None = None,
    ):
        super().__init__(schema, tool_name)
        self.mcp_url = mcp_url
        self.auth_token = auth_token

    def format(self) -> str:
        """Format schema as cURL command for MCP JSON-RPC."""
        # Generate example arguments
        example_args = generate_example(self.schema)

        # Create proper MCP JSON-RPC request
        mcp_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": self.name, "arguments": example_args},
        }

        json_str = json.dumps(mcp_request, indent=2)

        # Use actual values if provided, otherwise use placeholders
        url = self.mcp_url if self.mcp_url else "${MCP_URL}"
        token = self.auth_token if self.auth_token else "${AUTH_TOKEN}"

        # Generate cURL command with MCP-specific headers
        if self.mcp_url or self.auth_token:
            # If using actual values, add a warning
            warning = """# WARNING: This command contains actual credentials!
# Only use in secure environments and never commit to version control.

"""
        else:
            warning = """# MCP JSON-RPC Tool Call
# Replace ${MCP_URL} with your MCP server URL (e.g., http://localhost:8000/mcp)
# Replace ${AUTH_TOKEN} with your bearer token if authentication is required

"""

        return f"""{warning}curl -X POST {url} \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer {token}" \\
  -d '{json_str}'

# For SSE (Server-Sent Events) transport:
# Add header: -H "Accept: text/event-stream"

# For stdio transport:
# Use tool-specific client library instead of cURL"""


def to_curl(
    schema: dict[str, Any],
    tool_name: str = "tool_name",
    mcp_url: str | None = None,
    auth_token: str | None = None,
) -> str:
    """
    Convert JSON Schema to cURL command for MCP JSON-RPC.

    Args:
        schema: JSON Schema to convert
        tool_name: Name of the MCP tool
        mcp_url: Optional MCP server URL (uses placeholder if not provided)
        auth_token: Optional auth token (uses placeholder if not provided)

    Returns:
        cURL command as string
    """
    formatter = CurlFormatter(schema, tool_name, mcp_url, auth_token)
    return formatter.format()
