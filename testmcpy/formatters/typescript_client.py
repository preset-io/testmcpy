"""TypeScript client code generator for MCP tool calls."""

import json
from typing import Any

from .base import SchemaFormatter, generate_example
from .typescript import TypeScriptFormatter


class TypeScriptClientFormatter(SchemaFormatter):
    """Generates TypeScript client code for calling MCP tools."""

    def __init__(self, schema: dict[str, Any], tool_name: str = "tool_name", mcp_url: str | None = None, auth_token: str | None = None):
        super().__init__(schema, tool_name)
        self.mcp_url = mcp_url or "http://localhost:8000/mcp"
        self.auth_token = auth_token or "your_auth_token"

    def format(self) -> str:
        """Generate TypeScript client code for calling the MCP tool."""
        # Generate example arguments
        example_args = generate_example(self.schema)

        # Generate TypeScript interface for parameters
        ts_formatter = TypeScriptFormatter(self.schema, f"{self._pascal_case(self.name)}Params")
        interface_def = ts_formatter.format()

        # Format the arguments as JSON for TypeScript
        args_json = json.dumps(example_args, indent=2)

        # Prepare auth comment based on whether auth token is provided
        auth_comment = "" if self.auth_token and self.auth_token != "your_auth_token" else "  // Replace with your auth token if needed"

        return f'''/**
 * Generated client code for MCP tool: {self.name}
 * MCP Service: {self.mcp_url}
 *
 * This is a standalone, runnable script for calling the '{self.name}' tool.
 * Run with: tsx script.ts (or compile with tsc and run with node)
 */

// Type definitions for the tool parameters
{interface_def}

/**
 * MCP JSON-RPC request type
 */
interface MCPRequest {{
  jsonrpc: "2.0";
  id: number;
  method: string;
  params: {{
    name: string;
    arguments: Record<string, unknown>;
  }};
}}

/**
 * Call the {self.name} MCP tool using HTTP transport
 */
async function call{self._pascal_case(self.name)}(
  arguments: {self._pascal_case(self.name)}Params
): Promise<unknown> {{
  // MCP server configuration
  const url = "{self.mcp_url}";
  const authToken = "{self.auth_token}";{auth_comment}

  // Prepare the MCP JSON-RPC request
  const request: MCPRequest = {{
    jsonrpc: "2.0",
    id: 1,
    method: "tools/call",
    params: {{
      name: "{self.name}",
      arguments: arguments as Record<string, unknown>
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

// Example usage with type-safe parameters
const exampleParams: {self._pascal_case(self.name)}Params = {args_json};

call{self._pascal_case(self.name)}(exampleParams)
  .then(result => {{
    console.log("Success:", result);
  }})
  .catch(error => {{
    console.error("Failed:", error);
  }});
'''

    def _pascal_case(self, name: str) -> str:
        """Convert tool name to PascalCase for TypeScript type names."""
        import re
        # Split on non-alphanumeric characters
        parts = re.split(r'[^a-zA-Z0-9]', name)
        # Capitalize first letter of each part
        return ''.join(part.capitalize() for part in parts if part)


def to_typescript_client(schema: dict[str, Any], tool_name: str = "tool_name", mcp_url: str | None = None, auth_token: str | None = None) -> str:
    """
    Generate TypeScript client code for calling an MCP tool.

    Args:
        schema: JSON Schema for the tool parameters
        tool_name: Name of the MCP tool
        mcp_url: MCP server URL
        auth_token: Authentication token for MCP server

    Returns:
        TypeScript client code as string
    """
    formatter = TypeScriptClientFormatter(schema, tool_name, mcp_url, auth_token)
    return formatter.format()
