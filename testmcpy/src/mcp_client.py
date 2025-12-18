"""
MCP (Model Context Protocol) client implementation using FastMCP.

This module provides a Python client for interacting with MCP services,
specifically designed for testing LLM tool calling capabilities.
"""

import asyncio
import logging
import sys
import warnings
from dataclasses import dataclass
from typing import Any

import httpx
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from mcp.types import Tool as MCPToolDef

from testmcpy.auth_debugger import AuthDebugger


def create_insecure_httpx_factory():
    """Create an httpx client factory that skips SSL verification."""

    def factory(
        headers: dict[str, str] | None = None,
        timeout: httpx.Timeout | None = None,
        auth: httpx.Auth | None = None,
    ) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            headers=headers,
            timeout=timeout,
            auth=auth,
            verify=False,  # Skip SSL verification
        )

    return factory


# Suppress MCP notification validation warnings
logging.getLogger("root").setLevel(logging.ERROR)
warnings.filterwarnings("ignore", message="Failed to validate notification")

# Default timeout for MCP operations (30 seconds)
DEFAULT_TIMEOUT = 30.0
MAX_RETRIES = 3
RETRY_DELAY = 1.0  # seconds
BACKOFF_FACTOR = 2.0  # exponential backoff


class MCPError(Exception):
    """Base exception for MCP-related errors."""

    pass


class MCPTimeoutError(MCPError):
    """Exception raised when an MCP operation times out."""

    pass


class MCPConnectionError(MCPError):
    """Exception raised when unable to connect to MCP service."""

    pass


async def retry_with_backoff(
    func, *args, max_retries=MAX_RETRIES, timeout=DEFAULT_TIMEOUT, **kwargs
):
    """
    Retry an async function with exponential backoff.

    Args:
        func: Async function to retry
        *args: Positional arguments for func
        max_retries: Maximum number of retry attempts
        timeout: Timeout in seconds for each attempt
        **kwargs: Keyword arguments for func

    Returns:
        Result from successful function call

    Raises:
        MCPTimeoutError: If operation times out
        MCPError: If all retries are exhausted
    """
    last_exception = None

    for attempt in range(max_retries):
        try:
            # Apply timeout to the operation
            return await asyncio.wait_for(func(*args, **kwargs), timeout=timeout)
        except asyncio.TimeoutError:
            last_exception = MCPTimeoutError(
                f"Operation timed out after {timeout}s (attempt {attempt + 1}/{max_retries})"
            )
            if attempt < max_retries - 1:
                delay = RETRY_DELAY * (BACKOFF_FACTOR**attempt)
                await asyncio.sleep(delay)
        except Exception as e:
            last_exception = e
            if attempt < max_retries - 1:
                delay = RETRY_DELAY * (BACKOFF_FACTOR**attempt)
                await asyncio.sleep(delay)
            else:
                break

    # All retries exhausted
    raise last_exception if last_exception else MCPError("Operation failed after retries")


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
    output_schema: dict[str, Any] | None = None

    @classmethod
    def from_mcp_tool(cls, tool: MCPToolDef) -> "MCPTool":
        """Create MCPTool from MCP Tool definition."""
        return cls(
            name=tool.name,
            description=tool.description or "",
            input_schema=tool.inputSchema or {},
            output_schema=getattr(tool, "outputSchema", None),
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MCPTool":
        """Create MCPTool from dictionary."""
        return cls(
            name=data["name"],
            description=data.get("description", ""),
            input_schema=data.get("inputSchema", {}),
            output_schema=data.get("outputSchema"),
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
        # base_url must be provided via CLI arguments or .mcp_services.yaml
        self.base_url = base_url
        self.auth_config = auth  # Store the auth config
        self.client = None
        self._tools_cache: list[MCPTool] | None = None
        self.auth: BearerAuth | None = None  # Will be set in initialize()

    async def _fetch_jwt_token(
        self,
        api_url: str,
        api_token: str,
        api_secret: str,
        debug: bool = False,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> str:
        """Fetch JWT token from API.

        Args:
            api_url: JWT API endpoint URL
            api_token: API token for authentication
            api_secret: API secret for authentication
            debug: Enable detailed debug logging
            timeout: Request timeout in seconds

        Returns:
            JWT access token

        Raises:
            MCPError: If token fetch fails
            MCPTimeoutError: If request times out
        """
        import sys

        debugger = AuthDebugger(enabled=debug)

        # Step 1: Prepare request
        request_data = {
            "api_url": api_url,
            "name": api_token,
            "secret": api_secret,
        }
        debugger.log_step("1. JWT Request Prepared", request_data)

        try:
            if not debug:
                print(f"  [Auth] Fetching JWT token from: {api_url}", file=sys.stderr)

            # Step 2: Send request
            debugger.log_step(
                "2. Sending POST to JWT API Endpoint",
                {
                    "url": api_url,
                    "headers": {"Content-Type": "application/json", "Accept": "application/json"},
                    "body": {"name": api_token, "secret": "***"},
                },
            )

            # Check if SSL verification should be disabled
            verify_ssl = True
            if self.auth_config and self.auth_config.get("insecure", False):
                verify_ssl = False

            async with httpx.AsyncClient(verify=verify_ssl) as client:
                try:
                    response = await asyncio.wait_for(
                        client.post(
                            api_url,
                            headers={
                                "Content-Type": "application/json",
                                "Accept": "application/json",
                            },
                            json={"name": api_token, "secret": api_secret},
                            timeout=timeout,
                        ),
                        timeout=timeout + 5.0,  # Give extra buffer for connection
                    )
                except asyncio.TimeoutError:
                    raise MCPTimeoutError(f"JWT token request timed out after {timeout}s")

                # Step 3: Response received
                debugger.log_step(
                    "3. Response Received",
                    {
                        "status_code": response.status_code,
                        "headers": dict(response.headers),
                    },
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

                # Step 4: Token extracted
                debugger.log_step(
                    "4. Token Extracted",
                    {
                        "token_length": len(token),
                        "token_preview": token[:20] + "..." if len(token) > 20 else token,
                        "response_structure": "payload.access_token"
                        if "payload" in data
                        else "access_token",
                    },
                    success=True,
                )

                if not debug:
                    print(
                        f"  [Auth] JWT token fetched successfully (length: {len(token)})",
                        file=sys.stderr,
                    )

                debugger.summarize()
                return token

        except MCPTimeoutError:
            raise  # Re-raise timeout errors
        except httpx.HTTPError as e:
            error_info = {
                "error": str(e),
                "status_code": getattr(e.response, "status_code", "N/A")
                if hasattr(e, "response")
                else "N/A",
                "response_body": getattr(e.response, "text", "N/A")
                if hasattr(e, "response")
                else "N/A",
            }
            debugger.log_step("ERROR: HTTP Request Failed", error_info, success=False)
            debugger.summarize()
            raise MCPError(f"Failed to fetch JWT token: {e}")
        except Exception as e:
            debugger.log_step("ERROR: JWT Token Fetch Failed", {"error": str(e)}, success=False)
            debugger.summarize()
            raise MCPError(f"JWT token fetch error: {e}")

    async def _fetch_oauth_token(
        self,
        client_id: str,
        client_secret: str,
        token_url: str,
        scopes: list[str] | None = None,
        debug: bool = False,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> str:
        """Fetch OAuth access token using client credentials flow.

        Args:
            client_id: OAuth client ID
            client_secret: OAuth client secret
            token_url: OAuth token endpoint URL
            scopes: Optional list of OAuth scopes
            debug: Enable detailed debug logging
            timeout: Request timeout in seconds

        Returns:
            OAuth access token

        Raises:
            MCPError: If token fetch fails
            MCPTimeoutError: If request times out
        """
        import sys

        debugger = AuthDebugger(enabled=debug)

        # Step 1: Prepare request
        request_data = {
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": " ".join(scopes) if scopes else "",
        }
        debugger.log_step("1. OAuth Request Prepared", request_data)

        try:
            if not debug:
                print(f"  [Auth] Fetching OAuth token from: {token_url}", file=sys.stderr)

            # Step 2: Send request
            debugger.log_step(
                "2. Sending POST to Token Endpoint",
                {
                    "url": token_url,
                    "headers": {"Content-Type": "application/x-www-form-urlencoded"},
                    "grant_type": "client_credentials",
                    "client_id": client_id,
                    "scope": " ".join(scopes) if scopes else "",
                },
            )

            async with httpx.AsyncClient() as client:
                try:
                    response = await asyncio.wait_for(
                        client.post(
                            token_url,
                            data={
                                "grant_type": "client_credentials",
                                "client_id": client_id,
                                "client_secret": client_secret,
                                "scope": " ".join(scopes) if scopes else "",
                            },
                            headers={"Content-Type": "application/x-www-form-urlencoded"},
                            timeout=timeout,
                        ),
                        timeout=timeout + 5.0,  # Give extra buffer for connection
                    )
                except asyncio.TimeoutError:
                    raise MCPTimeoutError(f"OAuth token request timed out after {timeout}s")

                # Step 3: Response received
                debugger.log_step(
                    "3. Response Received",
                    {
                        "status_code": response.status_code,
                        "headers": dict(response.headers),
                    },
                )

                response.raise_for_status()
                data = response.json()

                if "access_token" not in data:
                    raise MCPError("No access_token found in OAuth response")

                token = data["access_token"]

                # Step 4: Token extracted
                debugger.log_step(
                    "4. Token Extracted",
                    {
                        "token_length": len(token),
                        "token_preview": token[:20] + "..." if len(token) > 20 else token,
                        "expires_in": data.get("expires_in", "unknown"),
                        "scope": data.get("scope", "unknown"),
                        "token_type": data.get("token_type", "unknown"),
                    },
                    success=True,
                )

                if not debug:
                    print(
                        f"  [Auth] OAuth token fetched successfully (length: {len(token)})",
                        file=sys.stderr,
                    )

                debugger.summarize()
                return token

        except MCPTimeoutError:
            raise  # Re-raise timeout errors
        except httpx.HTTPError as e:
            error_info = {
                "error": str(e),
                "status_code": getattr(e.response, "status_code", "N/A")
                if hasattr(e, "response")
                else "N/A",
                "response_body": getattr(e.response, "text", "N/A")
                if hasattr(e, "response")
                else "N/A",
            }
            debugger.log_step("ERROR: HTTP Request Failed", error_info, success=False)
            debugger.summarize()
            raise MCPError(f"Failed to fetch OAuth token: {e}")
        except Exception as e:
            debugger.log_step("ERROR: OAuth Token Fetch Failed", {"error": str(e)}, success=False)
            debugger.summarize()
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
                    raise MCPError(
                        "JWT auth requires 'api_url', 'api_token', and 'api_secret' fields"
                    )

                print("  [Auth] Using dynamic JWT authentication from parameter", file=sys.stderr)
                token = await self._fetch_jwt_token(api_url, api_token, api_secret)
                return BearerAuth(token=token)

            elif auth_type == "oauth":
                oauth_auto_discover = self.auth_config.get("oauth_auto_discover", False)

                if oauth_auto_discover:
                    # Use RFC 8414 auto-discovery - the fastmcp Client handles this
                    print("  [Auth] Using OAuth with auto-discovery", file=sys.stderr)
                    # Return None - let the fastmcp Client handle OAuth discovery
                    return None

                client_id = self.auth_config.get("client_id")
                client_secret = self.auth_config.get("client_secret")
                token_url = self.auth_config.get("token_url")
                scopes = self.auth_config.get("scopes", [])

                if not all([client_id, client_secret, token_url]):
                    raise MCPError(
                        "OAuth auth requires 'client_id', 'client_secret', and 'token_url' fields (or enable oauth_auto_discover)"
                    )

                print("  [Auth] Using OAuth authentication from parameter", file=sys.stderr)
                token = await self._fetch_oauth_token(client_id, client_secret, token_url, scopes)
                return BearerAuth(token=token)

            elif auth_type == "none":
                print("  [Auth] No authentication (explicit)", file=sys.stderr)
                return None

            else:
                raise MCPError(f"Unknown auth type: {auth_type}")

        # No config-based auth available
        # Authentication must be provided via auth parameter, CLI arguments, or .mcp_services.yaml
        print("  [Auth] No authentication configured", file=sys.stderr)
        return None

    async def initialize(self, timeout: float = DEFAULT_TIMEOUT) -> dict[str, Any]:
        """Initialize the MCP session using FastMCP client.

        Args:
            timeout: Timeout for initialization operations

        Returns:
            Dict with status information

        Raises:
            MCPConnectionError: If connection fails
            MCPTimeoutError: If initialization times out
        """
        import sys

        try:
            # Set up authentication first (with timeout)
            try:
                self.auth = await asyncio.wait_for(self._setup_auth(), timeout=timeout)
            except asyncio.TimeoutError:
                raise MCPTimeoutError(f"Authentication setup timed out after {timeout}s")

            print(f"  [MCP] Connecting to MCP service at {self.base_url}", file=sys.stderr)

            try:
                # Check if we need to skip SSL verification
                insecure = self.auth_config.get("insecure", False) if self.auth_config else False

                if insecure:
                    print("  [MCP] SSL verification disabled (insecure mode)", file=sys.stderr)
                    # Create transport with insecure httpx factory
                    transport = StreamableHttpTransport(
                        url=self.base_url,
                        auth=self.auth,
                        httpx_client_factory=create_insecure_httpx_factory(),
                    )
                    self.client = Client(transport, auth=self.auth)
                else:
                    self.client = Client(self.base_url, auth=self.auth)

                await asyncio.wait_for(self.client.__aenter__(), timeout=timeout)
            except asyncio.TimeoutError:
                raise MCPTimeoutError(f"MCP client connection timed out after {timeout}s")
            except Exception as e:
                raise MCPConnectionError(f"Failed to connect to MCP service: {e}")

            print("  [MCP] Testing connection...", file=sys.stderr)
            # Test connection with ping
            try:
                await asyncio.wait_for(self.client.ping(), timeout=min(10.0, timeout))
                print("  [MCP] Connection successful", file=sys.stderr)
                return {"status": "connected", "url": self.base_url}
            except asyncio.TimeoutError:
                raise MCPTimeoutError("MCP ping timed out")
            except Exception as e:
                # Connection established but ping failed - still usable
                print(
                    f"  [MCP] Warning: Ping failed but connection may still work: {e}",
                    file=sys.stderr,
                )
                return {"status": "connected_no_ping", "url": self.base_url, "warning": str(e)}

        except (MCPTimeoutError, MCPConnectionError):
            raise  # Re-raise our specific errors
        except Exception as e:
            print(f"  [MCP] Connection failed: {e}", file=sys.stderr)
            # Clean up partial connections
            if self.client:
                try:
                    await self.close()
                except Exception:
                    pass  # Ignore cleanup errors during connection failure
            raise MCPConnectionError(f"Failed to initialize MCP client: {e}")

    async def list_tools(
        self, force_refresh: bool = False, timeout: float = DEFAULT_TIMEOUT
    ) -> list[MCPTool]:
        """List available MCP tools.

        Args:
            force_refresh: Force refresh of cached tools
            timeout: Timeout for the operation

        Returns:
            List of available tools

        Raises:
            MCPError: If client not initialized
            MCPTimeoutError: If operation times out
        """
        if not force_refresh and self._tools_cache is not None:
            return self._tools_cache

        if not self.client:
            raise MCPError("MCP client not initialized. Call initialize() first.")

        try:
            # Wrap in timeout
            tools_response = await asyncio.wait_for(self.client.list_tools(), timeout=timeout)
            tools = []

            # Handle different response formats
            if hasattr(tools_response, "tools"):
                tool_list = tools_response.tools
            elif isinstance(tools_response, list):
                tool_list = tools_response
            else:
                tool_list = []

            for tool in tool_list:
                try:
                    if hasattr(tool, "name"):
                        tools.append(MCPTool.from_mcp_tool(tool))
                    elif isinstance(tool, dict):
                        tools.append(MCPTool.from_dict(tool))
                except Exception as e:
                    # Log error but continue processing other tools
                    print(f"Warning: Failed to parse tool: {e}", file=sys.stderr)
                    continue

            self._tools_cache = tools
            return tools

        except asyncio.TimeoutError:
            raise MCPTimeoutError(f"Failed to list tools: operation timed out after {timeout}s")
        except MCPError:
            raise  # Re-raise our errors
        except Exception as e:
            raise MCPError(f"Failed to list tools: {e}")

    async def call_tool(
        self, tool_call: MCPToolCall, timeout: float = DEFAULT_TIMEOUT
    ) -> MCPToolResult:
        """Execute an MCP tool call.

        This method never raises exceptions - all errors are returned as MCPToolResult with is_error=True.
        This ensures the UI never freezes on tool call failures.

        Args:
            tool_call: The tool call to execute
            timeout: Timeout for the operation

        Returns:
            MCPToolResult with either success content or error information
        """
        if not self.client:
            return MCPToolResult(
                tool_call_id=tool_call.id or "unknown",
                content=None,
                is_error=True,
                error_message="MCP client not initialized. Call initialize() first.",
            )

        try:
            # Execute with timeout
            result = await asyncio.wait_for(
                self.client.call_tool(tool_call.name, tool_call.arguments), timeout=timeout
            )

            return MCPToolResult(
                tool_call_id=tool_call.id or "unknown",
                content=result.content,
                is_error=result.isError if hasattr(result, "isError") else False,
                error_message=None,
            )

        except asyncio.TimeoutError:
            return MCPToolResult(
                tool_call_id=tool_call.id or "unknown",
                content=None,
                is_error=True,
                error_message=f"Tool call '{tool_call.name}' timed out after {timeout}s",
            )
        except Exception as e:
            return MCPToolResult(
                tool_call_id=tool_call.id or "unknown",
                content=None,
                is_error=True,
                error_message=f"Tool call '{tool_call.name}' failed: {str(e)}",
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
        """Close the MCP client connection.

        This method never raises exceptions to ensure clean shutdown.
        """
        if self.client:
            try:
                await asyncio.wait_for(
                    self.client.__aexit__(None, None, None),
                    timeout=5.0,  # Don't wait too long on close
                )
            except asyncio.TimeoutError:
                print("Warning: MCP client close timed out", file=sys.stderr)
            except Exception as e:
                print(f"Warning: Error closing MCP client: {e}", file=sys.stderr)
            finally:
                self.client = None
                self._tools_cache = None  # Clear cache on close

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
