"""
MCP (Model Context Protocol) client implementation using FastMCP.

This module provides a Python client for interacting with MCP services,
specifically designed for testing LLM tool calling capabilities.
"""

import asyncio
import os
import logging
import warnings
from pathlib import Path
from typing import Dict, List, Any, Optional, Union
from dataclasses import dataclass
from fastmcp import Client
from mcp.types import Tool as MCPToolDef
import httpx

from testmcpy.config import get_config

# Suppress MCP notification validation warnings
logging.getLogger('root').setLevel(logging.ERROR)
warnings.filterwarnings('ignore', message='Failed to validate notification')


class MCPError(Exception):
    """Base exception for MCP-related errors."""
    pass


class BearerAuth(httpx.Auth):
    """Bearer token authentication for httpx."""

    def __init__(self, token: str):
        self.token = token

    def auth_flow(self, request):
        request.headers["Authorization"] = f"Bearer {self.token}"
        yield request


@dataclass
class MCPTool:
    """Represents an MCP tool definition."""
    name: str
    description: str
    input_schema: Dict[str, Any]

    @classmethod
    def from_mcp_tool(cls, tool: MCPToolDef) -> "MCPTool":
        """Create MCPTool from MCP Tool definition."""
        return cls(
            name=tool.name,
            description=tool.description or "",
            input_schema=tool.inputSchema or {}
        )

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MCPTool":
        """Create MCPTool from dictionary."""
        return cls(
            name=data["name"],
            description=data.get("description", ""),
            input_schema=data.get("inputSchema", {})
        )


@dataclass
class MCPToolCall:
    """Represents a tool call to be executed."""
    name: str
    arguments: Dict[str, Any]
    id: Optional[str] = None


@dataclass
class MCPToolResult:
    """Result from executing an MCP tool."""
    tool_call_id: str
    content: Any
    is_error: bool = False
    error_message: Optional[str] = None


class MCPClient:
    """Client for interacting with MCP services using FastMCP."""

    def __init__(self, base_url: Optional[str] = None):
        # Use MCP_URL from config if not provided
        if base_url is None:
            config = get_config()
            base_url = config.mcp_url
        self.base_url = base_url
        self.client = None
        self._tools_cache: Optional[List[MCPTool]] = None
        self.auth = self._load_auth_token()

    def _load_auth_token(self) -> Optional[BearerAuth]:
        """Load bearer token from config."""
        config = get_config()
        token = config.mcp_auth_token
        if token:
            return BearerAuth(token=token)
        return None

    async def initialize(self) -> Dict[str, Any]:
        """Initialize the MCP session using FastMCP client."""
        try:
            self.client = Client(self.base_url, auth=self.auth)
            await self.client.__aenter__()
            # Test connection
            await self.client.ping()
            return {"status": "connected"}
        except Exception as e:
            raise MCPError(f"Failed to initialize MCP client: {e}")

    async def list_tools(self, force_refresh: bool = False) -> List[MCPTool]:
        """List available MCP tools."""
        if not force_refresh and self._tools_cache is not None:
            return self._tools_cache

        if not self.client:
            raise MCPError("MCP client not initialized. Call initialize() first.")

        try:
            tools_response = await self.client.list_tools()
            tools = []

            # Handle different response formats
            if hasattr(tools_response, 'tools'):
                tool_list = tools_response.tools
            elif isinstance(tools_response, list):
                tool_list = tools_response
            else:
                tool_list = []

            for tool in tool_list:
                if hasattr(tool, 'name'):
                    tools.append(MCPTool.from_mcp_tool(tool))
                elif isinstance(tool, dict):
                    tools.append(MCPTool.from_dict(tool))

            self._tools_cache = tools
            return tools
        except Exception as e:
            raise MCPError(f"Failed to list tools: {e}")

    async def call_tool(self, tool_call: MCPToolCall) -> MCPToolResult:
        """Execute an MCP tool call."""
        if not self.client:
            raise MCPError("MCP client not initialized. Call initialize() first.")

        try:
            result = await self.client.call_tool(tool_call.name, tool_call.arguments)

            return MCPToolResult(
                tool_call_id=tool_call.id or "unknown",
                content=result.content,
                is_error=result.isError if hasattr(result, 'isError') else False,
                error_message=None
            )
        except Exception as e:
            return MCPToolResult(
                tool_call_id=tool_call.id or "unknown",
                content=None,
                is_error=True,
                error_message=str(e)
            )

    async def batch_call_tools(self, tool_calls: List[MCPToolCall]) -> List[MCPToolResult]:
        """Execute multiple tool calls."""
        results = []
        for tool_call in tool_calls:
            result = await self.call_tool(tool_call)
            results.append(result)
        return results

    async def list_resources(self) -> List[Dict[str, Any]]:
        """List available MCP resources."""
        if not self.client:
            raise MCPError("MCP client not initialized. Call initialize() first.")

        try:
            resources_response = await self.client.list_resources()
            return [{"name": r.name, "description": r.description, "uri": r.uri}
                   for r in resources_response.resources]
        except Exception as e:
            raise MCPError(f"Failed to list resources: {e}")

    async def read_resource(self, uri: str) -> Dict[str, Any]:
        """Read a specific MCP resource."""
        if not self.client:
            raise MCPError("MCP client not initialized. Call initialize() first.")

        try:
            result = await self.client.read_resource(uri)
            return {"content": result.contents}
        except Exception as e:
            raise MCPError(f"Failed to read resource {uri}: {e}")

    async def list_prompts(self) -> List[Dict[str, Any]]:
        """List available MCP prompts."""
        if not self.client:
            raise MCPError("MCP client not initialized. Call initialize() first.")

        try:
            prompts_response = await self.client.list_prompts()
            return [{"name": p.name, "description": p.description}
                   for p in prompts_response.prompts]
        except Exception as e:
            raise MCPError(f"Failed to list prompts: {e}")

    async def get_prompt(self, name: str, arguments: Optional[Dict[str, Any]] = None) -> str:
        """Get a specific prompt."""
        if not self.client:
            raise MCPError("MCP client not initialized. Call initialize() first.")

        try:
            result = await self.client.get_prompt(name, arguments or {})
            # Extract text from prompt messages
            text_parts = []
            for message in result.messages:
                if hasattr(message, 'content'):
                    if isinstance(message.content, str):
                        text_parts.append(message.content)
                    elif hasattr(message.content, 'text'):
                        text_parts.append(message.content.text)
            return "\n".join(text_parts)
        except Exception as e:
            raise MCPError(f"Failed to get prompt {name}: {e}")

    async def close(self):
        """Close the MCP client connection."""
        if self.client:
            try:
                await self.client.__aexit__(None, None, None)
            except:
                pass
            self.client = None

    async def __aenter__(self):
        """Async context manager entry."""
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()


class MCPTester:
    """Simple tester for MCP connections."""

    def __init__(self):
        pass

    async def test_connection(self, base_url: str) -> Dict[str, Any]:
        """Test MCP service connection."""
        try:
            async with MCPClient(base_url) as client:
                tools = await client.list_tools()
                return {
                    "connected": True,
                    "tools_count": len(tools),
                    "tools": [{"name": t.name, "description": t.description} for t in tools]
                }
        except Exception as e:
            return {
                "connected": False,
                "error": str(e)
            }


async def test_mcp_connection():
    """Test function for MCP connection."""
    tester = MCPTester()
    result = await tester.test_connection("http://localhost:5008/mcp")
    print(f"Connection test result: {result}")
    return result


if __name__ == "__main__":
    asyncio.run(test_mcp_connection())