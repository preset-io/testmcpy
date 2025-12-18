"""JavaScript client code generator for MCP tool calls."""

import json
from typing import Any

from .base import SchemaFormatter, generate_example


class JavaScriptClientFormatter(SchemaFormatter):
    """Generates JavaScript client code for calling MCP tools."""

    def __init__(self, schema: dict[str, Any], tool_name: str = "tool_name", mcp_url: str | None = None, auth_token: str | None = None):
        super().__init__(schema, tool_name)
        self.mcp_url = mcp_url or "http://localhost:8000/mcp"
        self.auth_token = auth_token or "your_auth_token"

    def format(self) -> str:
        """Generate JavaScript client code for calling the MCP tool."""
        # Generate example arguments
        example_args = generate_example(self.schema)

        # Format the arguments as JSON for JavaScript
        args_json = json.dumps(example_args, indent=2)

        # Prepare auth comment based on whether auth token is provided
        auth_comment = "" if self.auth_token and self.auth_token != "your_auth_token" else "  // Replace with your auth token if needed"

        return f'''/**
 * Generated client code for MCP tool: {self.name}
 * MCP Service: {self.mcp_url}
 *
 * This is a standalone, runnable script for calling the '{self.name}' tool.
 * Run with: node script.js
 */

/**
 * Call the {self.name} MCP tool using HTTP transport
 */
async function call{self._pascal_case(self.name)}() {{
  // MCP server configuration
  const url = "{self.mcp_url}";
  const authToken = "{self.auth_token}";{auth_comment}

  // Prepare the MCP JSON-RPC request
  const request = {{
    jsonrpc: "2.0",
    id: 1,
    method: "tools/call",
    params: {{
      name: "{self.name}",
      arguments: {args_json}
    }}
  }};

  const headers = {{
    "Content-Type": "application/json",
    "Authorization": `Bearer ${{authToken}}`
  }};

  try {{
    const response = await fetch(url, {{
      method: "POST",
      headers: headers,
      body: JSON.stringify(request)
    }});

    const result = await response.json();

    if (result.error) {{
      console.error("Error:", result.error);
      throw new Error(result.error.message || "Tool call failed");
    }}

    console.log("Tool result:", result.result);
    return result.result;
  }} catch (error) {{
    console.error("Error calling tool:", error);
    throw error;
  }}
}}

// Run the function
call{self._pascal_case(self.name)}()
  .then(result => {{
    console.log("Success:", result);
  }})
  .catch(error => {{
    console.error("Failed:", error);
  }});
'''

    def _pascal_case(self, name: str) -> str:
        """Convert tool name to PascalCase for JavaScript function names."""
        import re
        # Split on non-alphanumeric characters
        parts = re.split(r'[^a-zA-Z0-9]', name)
        # Capitalize first letter of each part
        return ''.join(part.capitalize() for part in parts if part)


def to_javascript_client(schema: dict[str, Any], tool_name: str = "tool_name", mcp_url: str | None = None, auth_token: str | None = None) -> str:
    """
    Generate JavaScript client code for calling an MCP tool.

    Args:
        schema: JSON Schema for the tool parameters
        tool_name: Name of the MCP tool
        mcp_url: MCP server URL
        auth_token: Authentication token for MCP server

    Returns:
        JavaScript client code as string
    """
    formatter = JavaScriptClientFormatter(schema, tool_name, mcp_url, auth_token)
    return formatter.format()
