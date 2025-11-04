"""Python client code generator for MCP tool calls."""

import json
from typing import Any

from .base import SchemaFormatter, generate_example


class PythonClientFormatter(SchemaFormatter):
    """Generates Python client code for calling MCP tools."""

    def __init__(self, schema: dict[str, Any], tool_name: str = "tool_name", mcp_url: str | None = None, auth_token: str | None = None):
        super().__init__(schema, tool_name)
        self.mcp_url = mcp_url or "http://localhost:8000/mcp"
        self.auth_token = auth_token or "your_auth_token"

    def format(self) -> str:
        """Generate Python client code for calling the MCP tool."""
        # Generate example arguments
        example_args = generate_example(self.schema)

        # Format the arguments for Python code
        args_str = self._format_args(example_args, indent=1)

        # Prepare auth header comment based on whether auth token is provided
        auth_comment = "" if self.auth_token and self.auth_token != "your_auth_token" else "  # Replace with your auth token if needed"

        return f'''#!/usr/bin/env python3
"""
Generated client code for MCP tool: {self.name}
MCP Service: {self.mcp_url}

This is a standalone, runnable script for calling the '{self.name}' tool.
Install dependencies: pip install aiohttp
"""

import asyncio
import aiohttp


async def call_{self._safe_name(self.name)}():
    """Call the {self.name} MCP tool using HTTP transport."""

    # MCP server configuration
    url = "{self.mcp_url}"
    auth_token = "{self.auth_token}"{auth_comment}

    # Prepare the MCP JSON-RPC request
    request = {{
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {{
            "name": "{self.name}",
            "arguments": {args_str}
        }}
    }}

    headers = {{
        "Content-Type": "application/json",
        "Authorization": f"Bearer {{auth_token}}"
    }}

    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=request, headers=headers) as response:
            result = await response.json()

            if "error" in result:
                print(f"Error: {{result['error']}}")
                raise Exception(result["error"])

            print(f"Tool result: {{result.get('result')}}")
            return result.get("result")


if __name__ == "__main__":
    # Run the async function
    asyncio.run(call_{self._safe_name(self.name)}())
'''

    def _safe_name(self, name: str) -> str:
        """Convert tool name to safe Python identifier."""
        import re
        # Replace non-alphanumeric characters with underscore
        safe = re.sub(r'[^a-zA-Z0-9_]', '_', name)
        # Ensure it doesn't start with a number
        if safe and safe[0].isdigit():
            safe = f"tool_{safe}"
        return safe or "tool"

    def _format_args(self, args: dict[str, Any], indent: int = 0) -> str:
        """Format arguments as Python dict literal."""
        if not args:
            return "{}"

        indent_str = "    " * indent
        lines = []

        for key, value in args.items():
            formatted_value = self._format_value(value, indent + 1)
            lines.append(f'{indent_str}    "{key}": {formatted_value},')

        return "{\n" + "\n".join(lines) + f"\n{indent_str}}}"

    def _format_value(self, value: Any, indent: int = 0) -> str:
        """Format a single value for Python code."""
        if value is None:
            return "None"
        elif isinstance(value, bool):
            return str(value)
        elif isinstance(value, (int, float)):
            return str(value)
        elif isinstance(value, str):
            # Escape quotes and backslashes
            escaped = value.replace("\\", "\\\\").replace('"', '\\"')
            return f'"{escaped}"'
        elif isinstance(value, list):
            if not value:
                return "[]"
            indent_str = "    " * indent
            items = [f"{indent_str}    {self._format_value(item, indent + 1)}" for item in value]
            return "[\n" + ",\n".join(items) + f"\n{indent_str}]"
        elif isinstance(value, dict):
            return self._format_args(value, indent)
        else:
            return repr(value)


def to_python_client(schema: dict[str, Any], tool_name: str = "tool_name", mcp_url: str | None = None, auth_token: str | None = None) -> str:
    """
    Generate Python client code for calling an MCP tool.

    Args:
        schema: JSON Schema for the tool parameters
        tool_name: Name of the MCP tool
        mcp_url: MCP server URL
        auth_token: Authentication token for MCP server

    Returns:
        Python client code as string
    """
    formatter = PythonClientFormatter(schema, tool_name, mcp_url, auth_token)
    return formatter.format()
