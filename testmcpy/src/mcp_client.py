"""
MCP (Model Context Protocol) client implementation using FastMCP.

This module provides a Python client for interacting with MCP services,
specifically designed for testing LLM tool calling capabilities.
"""

import asyncio
import logging
import warnings
from dataclasses import dataclass
from typing import Any

import httpx
from fastmcp import Client
from mcp.types import Tool as MCPToolDef

from testmcpy.config import get_config

# Suppress MCP notification validation warnings
logging.getLogger("root").setLevel(logging.ERROR)
warnings.filterwarnings("ignore", message="Failed to validate notification")


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
    input_schema: dict[str, Any]

    @classmethod
    def from_mcp_tool(cls, tool: MCPToolDef) -> "MCPTool":
        """Create MCPTool from MCP Tool definition."""
        return cls(
            name=tool.name, description=tool.description or "", input_schema=tool.inputSchema or {}
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MCPTool":
        """Create MCPTool from dictionary."""
        return cls(
            name=data["name"],
            description=data.get("description", ""),
            input_schema=data.get("inputSchema", {}),
        )


@dataclass
class MCPToolCall:
    """Represents a tool call to be executed."""

    name: str
    arguments: dict[str, Any]
    id: str | None = None


@dataclass
class MCPToolResult:
    """Result from executing an MCP tool."""

    tool_call_id: str
    content: Any
    is_error: bool = False
    error_message: str | None = None


class MCPClient:
    """Client for interacting with MCP services using FastMCP."""

    def __init__(self, base_url: str | None = None, auth: dict[str, Any] | None = None):
        # Use MCP_URL from config if not provided
        if base_url is None:
            config = get_config()
            base_url = config.mcp_url
        self.base_url = base_url
        self.auth_config = auth  # Store the auth config
        self.client = None
        self._tools_cache: list[MCPTool] | None = None
        self.auth: BearerAuth | None = None  # Will be set in initialize()

    async def _fetch_jwt_token(self, api_url: str, api_token: str, api_secret: str) -> str:
        """Fetch JWT token from API.

        Args:
            api_url: JWT API endpoint URL
            api_token: API token for authentication
            api_secret: API secret for authentication

        Returns:
            JWT access token

        Raises:
            MCPError: If token fetch fails
        """
        import sys

        try:
            print(f"  [Auth] Fetching JWT token from: {api_url}", file=sys.stderr)

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    api_url,
                    headers={"Content-Type": "application/json", "Accept": "application/json"},
                    json={"name": api_token, "secret": api_secret},
                    timeout=10.0,
                )
                response.raise_for_status()
                data = response.json()

                # Extract access token from response
                # Supports both {"payload": {"access_token": "..."}} and {"access_token": "..."}
                if "payload" in data and "access_token" in data["payload"]:
                    token = data["payload"]["access_token"]
                elif "access_token" in data:
                    token = data["access_token"]
                else:
                    raise MCPError("No access_token found in JWT response")

                print(f"  [Auth] JWT token fetched successfully (length: {len(token)})", file=sys.stderr)
                return token

        except httpx.HTTPError as e:
            raise MCPError(f"Failed to fetch JWT token: {e}")
        except Exception as e:
            raise MCPError(f"JWT token fetch error: {e}")

    async def _fetch_oauth_token(
        self,
        client_id: str,
        client_secret: str,
        token_url: str,
        scopes: list[str] | None = None
    ) -> str:
        """Fetch OAuth access token using client credentials flow.

        Args:
            client_id: OAuth client ID
            client_secret: OAuth client secret
            token_url: OAuth token endpoint URL
            scopes: Optional list of OAuth scopes

        Returns:
            OAuth access token

        Raises:
            MCPError: If token fetch fails
        """
        import sys

        try:
            print(f"  [Auth] Fetching OAuth token from: {token_url}", file=sys.stderr)

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    token_url,
                    data={
                        "grant_type": "client_credentials",
                        "client_id": client_id,
                        "client_secret": client_secret,
                        "scope": " ".join(scopes) if scopes else "",
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                    timeout=10.0,
                )
                response.raise_for_status()
                data = response.json()

                if "access_token" not in data:
                    raise MCPError("No access_token found in OAuth response")

                token = data["access_token"]
                print(f"  [Auth] OAuth token fetched successfully (length: {len(token)})", file=sys.stderr)
                return token

        except httpx.HTTPError as e:
            raise MCPError(f"Failed to fetch OAuth token: {e}")
        except Exception as e:
            raise MCPError(f"OAuth token fetch error: {e}")

    async def _setup_auth(self) -> BearerAuth | None:
        """Set up authentication based on config or provided auth dict.

        This method supports multiple authentication types:
        - bearer: Direct bearer token
        - jwt: Dynamic JWT token fetched from API
        - oauth: OAuth client credentials flow
        - none: No authentication

        If auth_config was provided in __init__, it takes priority.
        Otherwise, falls back to config-based authentication.

        Returns:
            BearerAuth instance if authentication is configured, None otherwise
        """
        import sys

        # If auth was provided in __init__, use it
        if self.auth_config:
            auth_type = self.auth_config.get("type", "none")

            if auth_type == "bearer":
                token = self.auth_config.get("token")
                if not token:
                    raise MCPError("Bearer auth requires 'token' field")

                print("  [Auth] Using bearer token from parameter", file=sys.stderr)
                token_preview = token[:20] + "..." + token[-8:] if len(token) > 28 else token
                print(f"  [Auth] Token: {token_preview}", file=sys.stderr)
                return BearerAuth(token=token)

            elif auth_type == "jwt":
                api_url = self.auth_config.get("api_url")
                api_token = self.auth_config.get("api_token")
                api_secret = self.auth_config.get("api_secret")

                if not all([api_url, api_token, api_secret]):
                    raise MCPError("JWT auth requires 'api_url', 'api_token', and 'api_secret' fields")

                print("  [Auth] Using dynamic JWT authentication from parameter", file=sys.stderr)
                token = await self._fetch_jwt_token(api_url, api_token, api_secret)
                return BearerAuth(token=token)

            elif auth_type == "oauth":
                client_id = self.auth_config.get("client_id")
                client_secret = self.auth_config.get("client_secret")
                token_url = self.auth_config.get("token_url")
                scopes = self.auth_config.get("scopes", [])

                if not all([client_id, client_secret, token_url]):
                    raise MCPError("OAuth auth requires 'client_id', 'client_secret', and 'token_url' fields")

                print("  [Auth] Using OAuth authentication from parameter", file=sys.stderr)
                token = await self._fetch_oauth_token(client_id, client_secret, token_url, scopes)
                return BearerAuth(token=token)

            elif auth_type == "none":
                print("  [Auth] No authentication (explicit)", file=sys.stderr)
                return None

            else:
                raise MCPError(f"Unknown auth type: {auth_type}")

        # Otherwise, fall back to config (existing behavior)
        config = get_config()

        # Check for dynamic JWT configuration
        has_dynamic_jwt = all(
            [
                config.get("MCP_AUTH_API_URL"),
                config.get("MCP_AUTH_API_TOKEN"),
                config.get("MCP_AUTH_API_SECRET"),
            ]
        )

        # Check for static token
        has_static_token = config.get("MCP_AUTH_TOKEN") or config.get("SUPERSET_MCP_TOKEN")

        # Log auth method being used
        if has_dynamic_jwt:
            print("  [Auth] Using dynamic JWT authentication from config", file=sys.stderr)
            api_url = config.get("MCP_AUTH_API_URL")
            api_token = config.get("MCP_AUTH_API_TOKEN")
            api_secret = config.get("MCP_AUTH_API_SECRET")
            token = await self._fetch_jwt_token(api_url, api_token, api_secret)
            return BearerAuth(token=token)
        elif has_static_token:
            print("  [Auth] Using static bearer token from config", file=sys.stderr)
            token = config.mcp_auth_token
            if token:
                token_preview = token[:20] + "..." + token[-8:] if len(token) > 28 else token
                print(f"  [Auth] Token: {token_preview}", file=sys.stderr)
                return BearerAuth(token=token)
        else:
            print("  [Auth] No authentication configured", file=sys.stderr)

        return None

    async def initialize(self) -> dict[str, Any]:
        """Initialize the MCP session using FastMCP client."""
        import sys

        try:
            # Set up authentication first
            self.auth = await self._setup_auth()

            print(f"  [MCP] Connecting to MCP service at {self.base_url}", file=sys.stderr)
            self.client = Client(self.base_url, auth=self.auth)
            await self.client.__aenter__()

            print("  [MCP] Testing connection...", file=sys.stderr)
            # Test connection
            await self.client.ping()
            print("  [MCP] Connection successful", file=sys.stderr)
            return {"status": "connected"}
        except Exception as e:
            print(f"  [MCP] Connection failed: {e}", file=sys.stderr)
            raise MCPError(f"Failed to initialize MCP client: {e}")

    async def list_tools(self, force_refresh: bool = False) -> list[MCPTool]:
        """List available MCP tools."""
        if not force_refresh and self._tools_cache is not None:
            return self._tools_cache

        if not self.client:
            raise MCPError("MCP client not initialized. Call initialize() first.")

        try:
            tools_response = await self.client.list_tools()
            tools = []

            # Handle different response formats
            if hasattr(tools_response, "tools"):
                tool_list = tools_response.tools
            elif isinstance(tools_response, list):
                tool_list = tools_response
            else:
                tool_list = []

            for tool in tool_list:
                if hasattr(tool, "name"):
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
                is_error=result.isError if hasattr(result, "isError") else False,
                error_message=None,
            )
        except Exception as e:
            return MCPToolResult(
                tool_call_id=tool_call.id or "unknown",
                content=None,
                is_error=True,
                error_message=str(e),
            )

    async def batch_call_tools(self, tool_calls: list[MCPToolCall]) -> list[MCPToolResult]:
        """Execute multiple tool calls."""
        results = []
        for tool_call in tool_calls:
            result = await self.call_tool(tool_call)
            results.append(result)
        return results

    async def list_resources(self) -> list[dict[str, Any]]:
        """List available MCP resources."""
        if not self.client:
            raise MCPError("MCP client not initialized. Call initialize() first.")

        try:
            resources_response = await self.client.list_resources()

            # Handle different response formats
            if hasattr(resources_response, "resources"):
                resource_list = resources_response.resources
            elif isinstance(resources_response, list):
                resource_list = resources_response
            else:
                resource_list = []

            return [
                {"name": r.name, "description": getattr(r, "description", ""), "uri": str(r.uri)}
                for r in resource_list
            ]
        except Exception as e:
            raise MCPError(f"Failed to list resources: {e}")

    async def read_resource(self, uri: str) -> dict[str, Any]:
        """Read a specific MCP resource."""
        if not self.client:
            raise MCPError("MCP client not initialized. Call initialize() first.")

        try:
            result = await self.client.read_resource(uri)
            return {"content": result.contents}
        except Exception as e:
            raise MCPError(f"Failed to read resource {uri}: {e}")

    async def list_prompts(self) -> list[dict[str, Any]]:
        """List available MCP prompts."""
        if not self.client:
            raise MCPError("MCP client not initialized. Call initialize() first.")

        try:
            prompts_response = await self.client.list_prompts()

            # Handle different response formats
            if hasattr(prompts_response, "prompts"):
                prompt_list = prompts_response.prompts
            elif isinstance(prompts_response, list):
                prompt_list = prompts_response
            else:
                prompt_list = []

            return [
                {"name": p.name, "description": getattr(p, "description", "")} for p in prompt_list
            ]
        except Exception as e:
            raise MCPError(f"Failed to list prompts: {e}")

    async def get_prompt(self, name: str, arguments: dict[str, Any] | None = None) -> str:
        """Get a specific prompt."""
        if not self.client:
            raise MCPError("MCP client not initialized. Call initialize() first.")

        try:
            result = await self.client.get_prompt(name, arguments or {})
            # Extract text from prompt messages
            text_parts = []
            for message in result.messages:
                if hasattr(message, "content"):
                    if isinstance(message.content, str):
                        text_parts.append(message.content)
                    elif hasattr(message.content, "text"):
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

    async def test_connection(self, base_url: str) -> dict[str, Any]:
        """Test MCP service connection."""
        try:
            async with MCPClient(base_url) as client:
                tools = await client.list_tools()
                return {
                    "connected": True,
                    "tools_count": len(tools),
                    "tools": [{"name": t.name, "description": t.description} for t in tools],
                }
        except Exception as e:
            return {"connected": False, "error": str(e)}


async def test_mcp_connection():
    """Test function for MCP connection."""
    tester = MCPTester()
    result = await tester.test_connection("http://localhost:5008/mcp")
    print(f"Connection test result: {result}")
    return result


if __name__ == "__main__":
    asyncio.run(test_mcp_connection())
