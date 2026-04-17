"""
MCP (Model Context Protocol) client implementation using FastMCP.

This module provides a Python client for interacting with MCP services,
specifically designed for testing LLM tool calling capabilities.
"""

import asyncio
import json
import logging
import os
import sys
import time
import warnings
from dataclasses import dataclass
from typing import Any

import httpx
from fastmcp import Client
from fastmcp.client.auth.oauth import OAuth as _FastMCPOAuth
from fastmcp.client.transports import StreamableHttpTransport
from mcp.types import Tool as MCPToolDef

from testmcpy.auth_debugger import AuthDebugger


class PresetOAuth(_FastMCPOAuth):
    """fastmcp OAuth provider patched for use against superset-shell MCP
    servers (Preset production, staging, and local dev).

    Two fixes over the upstream ``fastmcp.client.auth.oauth.OAuth``:

    1. The RFC 8707 ``resource`` indicator is set to the **full** MCP URL
       (e.g. ``https://workspace.us1a.app.preset.io/mcp``) instead of just
       scheme+host. Upstream ``OAuth.__init__`` strips the path when
       building ``server_url``; superset-shell's OAuth server validates
       the resource path and rejects the shorter form with
       ``invalid_request: Resource URL domain does not match this
       server``. mcp-remote (the reference Node client) sends the full
       URL, which is why Claude Desktop works. We match that by patching
       ``self.context.server_url`` post-init — every other consumer of
       ``context.server_url`` runs it through
       ``get_authorization_base_url()`` which strips the path, so this
       only affects the resource indicator.

    2. When ``insecure=True``, ``redirect_handler`` uses
       ``httpx.AsyncClient(verify=False)`` for the authorization-URL
       pre-flight so ``https://localhost`` with a self-signed cert
       doesn't fail before the browser opens.
    """

    # Default scopes to request — matches what the PRM advertises and what
    # mcp-remote (the reference Node client) requests.
    # Note: do NOT include "offline_access" — it causes Auth0 to return a
    # refresh_token alongside the access_token, and superset-shell's token
    # verifier chokes on it (JoseError: Token type mismatch).
    DEFAULT_SCOPES = ["openid", "email", "profile"]

    def __init__(self, mcp_url: str, insecure: bool = False, **kwargs: Any) -> None:
        # Default to standard OIDC scopes if none provided.
        if "scopes" not in kwargs:
            kwargs["scopes"] = self.DEFAULT_SCOPES
        super().__init__(mcp_url, **kwargs)
        # Preserve the path when computing the RFC 8707 resource indicator.
        self.context.server_url = mcp_url
        self._insecure = insecure

    async def redirect_handler(self, authorization_url: str) -> None:
        import webbrowser

        from fastmcp.client.auth.oauth import ClientNotFoundError, logger

        verify = not self._insecure
        async with httpx.AsyncClient(verify=verify) as client:
            response = await client.get(authorization_url, follow_redirects=False)
            if response.status_code == 400:
                raise ClientNotFoundError(
                    "OAuth client not found - cached credentials may be stale"
                )
            if response.status_code not in (200, 302, 303, 307, 308):
                raise RuntimeError(f"Unexpected authorization response: {response.status_code}")

        logger.info(f"OAuth authorization URL: {authorization_url}")
        webbrowser.open(authorization_url)


# Back-compat alias (was named InsecureOAuth in earlier iteration).
InsecureOAuth = PresetOAuth


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


def create_mtls_httpx_factory(
    client_cert: str,
    client_key: str | None = None,
    ca_bundle: str | None = None,
):
    """Create an httpx client factory with mTLS (client certificate) support.

    Args:
        client_cert: Path to client certificate file (.pem or .crt)
        client_key: Path to client private key file (.pem or .key)
        ca_bundle: Path to CA bundle file for server verification
    """
    import ssl

    ssl_context = ssl.create_default_context()
    if ca_bundle:
        ssl_context.load_verify_locations(ca_bundle)
    ssl_context.load_cert_chain(certfile=client_cert, keyfile=client_key)

    def factory(
        headers: dict[str, str] | None = None,
        timeout: httpx.Timeout | None = None,
        auth: httpx.Auth | None = None,
    ) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            headers=headers,
            timeout=timeout,
            auth=auth,
            verify=ssl_context,
        )

    return factory


# Suppress MCP notification validation warnings
logging.getLogger("root").setLevel(logging.ERROR)
warnings.filterwarnings("ignore", message="Failed to validate notification")

logger = logging.getLogger(__name__)

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
            if isinstance(e, (TypeError, NameError, AttributeError)):
                raise
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
    gateway: bool = False  # True if discovered via search_tools gateway

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
        # Can be a BearerAuth instance, the literal "oauth" (triggers fastmcp
        # OAuth auto-discovery), or None for no auth.
        self.auth: BearerAuth | str | None = None  # Will be set in initialize()
        self._token_manager = None  # Optional TokenManager for auto-refresh
        self._extra_headers: dict[str, str] = {}  # For api_key / custom_headers auth

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
            "secret": "***",
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
                        "token_preview": f"***...{token[-4:]}" if len(token) > 4 else "***",
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
        except (KeyError, json.JSONDecodeError, TypeError, ValueError) as e:
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
            "client_secret": "***",
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
                        "token_preview": f"***...{token[-4:]}" if len(token) > 4 else "***",
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
        except (KeyError, json.JSONDecodeError, TypeError, ValueError) as e:
            debugger.log_step("ERROR: OAuth Token Fetch Failed", {"error": str(e)}, success=False)
            debugger.summarize()
            raise MCPError(f"OAuth token fetch error: {e}")

    async def _setup_auth(self) -> BearerAuth | str | None:
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
                    # Use RFC 8414 auto-discovery. Returning the literal string
                    # "oauth" tells fastmcp's Client/transport to instantiate its
                    # OAuth provider (browser flow + callback server + token
                    # cache). Returning None would mean "no auth" and trigger a
                    # 401 from protected servers.
                    print("  [Auth] Using OAuth with auto-discovery", file=sys.stderr)
                    return "oauth"

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

                # Set up TokenManager if refresh_token is available
                refresh_token = self.auth_config.get("refresh_token")
                token_expiry = self.auth_config.get("token_expiry")
                if refresh_token and token_url:
                    from testmcpy.src.token_manager import TokenManager

                    verify_ssl = not self.auth_config.get("insecure", False)
                    self._token_manager = TokenManager(
                        access_token=token,
                        refresh_token=refresh_token,
                        token_url=token_url,
                        expiry=token_expiry,
                        client_id=client_id,
                        client_secret=client_secret,
                        verify_ssl=verify_ssl,
                    )
                    print("  [Auth] TokenManager configured for auto-refresh", file=sys.stderr)

                return BearerAuth(token=token)

            elif auth_type == "api_key":
                # API Key authentication via custom header
                api_key = self.auth_config.get("api_key")
                api_key_env = self.auth_config.get("api_key_env")
                header_name = self.auth_config.get("header_name", "X-API-Key")

                if not api_key and api_key_env:
                    import os

                    api_key = os.environ.get(api_key_env)
                    if not api_key:
                        raise MCPError(f"API key env var '{api_key_env}' not set")

                if not api_key:
                    raise MCPError("API key auth requires 'api_key' or 'api_key_env' field")

                print(
                    f"  [Auth] Using API key authentication (header: {header_name})",
                    file=sys.stderr,
                )
                # Store custom headers for transport configuration
                self._extra_headers = {header_name: api_key}
                return None  # No bearer auth, headers handled separately

            elif auth_type == "custom_headers":
                custom_headers = self.auth_config.get("headers", {})
                if not custom_headers:
                    raise MCPError("Custom headers auth requires 'headers' field")

                print(
                    f"  [Auth] Using custom headers authentication ({len(custom_headers)} headers)",
                    file=sys.stderr,
                )
                self._extra_headers = dict(custom_headers)
                return None  # No bearer auth, headers handled separately

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

                # Check for mTLS configuration
                client_cert = self.auth_config.get("client_cert") if self.auth_config else None
                client_key = self.auth_config.get("client_key") if self.auth_config else None
                ca_bundle = self.auth_config.get("ca_bundle") if self.auth_config else None

                # For OAuth auto-discovery, always use our PresetOAuth subclass
                # (not fastmcp's upstream OAuth) so the RFC 8707 resource
                # indicator includes the /mcp path. Otherwise superset-shell
                # rejects the authorize request with "Resource URL domain does
                # not match this server".
                transport_auth: Any = self.auth
                if transport_auth == "oauth":
                    transport_auth = PresetOAuth(self.base_url, insecure=insecure)

                # Determine the httpx client factory based on SSL config
                httpx_factory = None
                if client_cert:
                    print("  [MCP] mTLS enabled (client certificate)", file=sys.stderr)
                    httpx_factory = create_mtls_httpx_factory(
                        client_cert=client_cert,
                        client_key=client_key,
                        ca_bundle=ca_bundle,
                    )
                elif insecure:
                    print("  [MCP] SSL verification disabled (insecure mode)", file=sys.stderr)
                    httpx_factory = create_insecure_httpx_factory()

                # Build transport kwargs
                transport_kwargs: dict[str, Any] = {
                    "url": self.base_url,
                    "auth": transport_auth,
                }
                if httpx_factory:
                    transport_kwargs["httpx_client_factory"] = httpx_factory
                if self._extra_headers:
                    transport_kwargs["headers"] = self._extra_headers

                transport = StreamableHttpTransport(**transport_kwargs)
                self.client = Client(transport)

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

            # Detect search_tools/call_tool gateway pattern (FastMCP 3.x)
            # If server only exposes gateway tools, expand by calling search_tools
            tool_names = {t.name for t in tools}
            has_gateway = "search_tools" in tool_names and "call_tool" in tool_names
            if has_gateway and len(tools) <= 6:
                try:
                    expanded = await self._expand_gateway_tools(timeout)
                    if expanded:
                        # Keep gateway tools + always-visible tools, add discovered ones
                        existing_names = {t.name for t in tools}
                        for t in expanded:
                            if t.name not in existing_names:
                                tools.append(t)
                        print(
                            f"  [MCP] Expanded {len(expanded)} tools via search_tools gateway "
                            f"(total: {len(tools)})"
                        )
                except (asyncio.TimeoutError, MCPError) as e:
                    print(f"  [MCP] Gateway expansion failed (non-fatal): {e}")

            self._tools_cache = tools
            return tools

        except asyncio.TimeoutError:
            raise MCPTimeoutError(f"Failed to list tools: operation timed out after {timeout}s")
        except MCPError:
            raise  # Re-raise our errors
        except Exception as e:
            raise MCPError(f"Failed to list tools: {e}")

    async def _expand_gateway_tools(self, timeout: float = 30.0) -> list["MCPTool"]:
        """Expand tools via the search_tools gateway (FastMCP 3.x pattern).

        When a server exposes search_tools + call_tool as a gateway, call
        search_tools with a broad query to discover all available tools.
        """
        if not self.client:
            return []

        discovered: list[MCPTool] = []

        # Call search_tools with broad queries to discover all tools
        # Empty query may return nothing, so use category-based searches
        broad_queries = [
            "list dashboard chart dataset sql query schema health info",
            "create generate update delete add save open execute",
            "preview explore link export filter sort",
            "big number pie table pivot mixed handlebars",
            "get data column metric resource database",
            "list_charts generate_dashboard get_chart_data",
            "list_databases get_database_info generate_chart",
        ]
        all_content = []

        for q in broad_queries:
            try:
                result = await asyncio.wait_for(
                    self.client.call_tool("search_tools", {"query": q}),
                    timeout=timeout,
                )
                content = ""
                if hasattr(result, "content"):
                    if isinstance(result.content, list):
                        for item in result.content:
                            if hasattr(item, "text"):
                                content += item.text
                    elif isinstance(result.content, str):
                        content = result.content
                if content:
                    all_content.append(content)
            except (asyncio.TimeoutError, TypeError, ValueError):
                continue

        # Parse all discovered tool definitions
        for content in all_content:
            if content:
                import json as _json

                try:
                    data = _json.loads(content)
                    if isinstance(data, list):
                        for item in data:
                            if isinstance(item, dict) and "name" in item:
                                tool = MCPTool.from_dict(item)
                                tool.gateway = True  # Mark as discovered via gateway
                                discovered.append(tool)
                    elif isinstance(data, dict) and "tools" in data:
                        for item in data["tools"]:
                            if isinstance(item, dict) and "name" in item:
                                tool = MCPTool.from_dict(item)
                                tool.gateway = True
                                discovered.append(tool)
                except (_json.JSONDecodeError, ValueError):
                    pass

        # Deduplicate by name
        seen = set()
        unique = []
        for t in discovered:
            if t.name not in seen:
                seen.add(t.name)
                unique.append(t)

        # Second pass: search for discovered tool names to find neighbors
        if unique:
            second_pass_queries = []
            for i in range(0, len(unique), 3):
                batch = " ".join(t.name for t in unique[i : i + 3])
                second_pass_queries.append(batch)

            for q in second_pass_queries[:5]:  # Limit to 5 extra queries
                try:
                    result = await asyncio.wait_for(
                        self.client.call_tool("search_tools", {"query": q}),
                        timeout=timeout,
                    )
                    content = ""
                    if hasattr(result, "content") and isinstance(result.content, list):
                        for item in result.content:
                            if hasattr(item, "text"):
                                content += item.text
                    if content:
                        import json as _json2

                        try:
                            data = _json2.loads(content)
                            if isinstance(data, list):
                                for item in data:
                                    if (
                                        isinstance(item, dict)
                                        and "name" in item
                                        and item["name"] not in seen
                                    ):
                                        tool = MCPTool.from_dict(item)
                                        tool.gateway = True
                                        unique.append(tool)
                                        seen.add(tool.name)
                        except (_json2.JSONDecodeError, ValueError):
                            pass
                except (asyncio.TimeoutError, TypeError, ValueError):
                    continue

        return unique

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
            # Check if tool exists directly or needs gateway routing
            direct_tool_names = set()
            if self._tools_cache:
                direct_tool_names = {
                    t.name for t in self._tools_cache if t.name not in ("search_tools", "call_tool")
                }

            # Route through call_tool gateway if:
            # 1. The tool isn't directly available
            # 2. The call_tool gateway exists
            gateway_names = set()
            if self._tools_cache:
                gateway_names = {t.name for t in self._tools_cache}
            use_gateway = (
                "call_tool" in gateway_names
                and tool_call.name not in gateway_names
                and tool_call.name not in direct_tool_names
            )

            if use_gateway:
                # Route through call_tool(name=<tool>, arguments=<args>)
                gateway_args = {
                    "name": tool_call.name,
                    "arguments": tool_call.arguments or {},
                }
                result = await asyncio.wait_for(
                    self.client.call_tool("call_tool", gateway_args),
                    timeout=timeout,
                )
            else:
                # Execute directly
                result = await asyncio.wait_for(
                    self.client.call_tool(tool_call.name, tool_call.arguments),
                    timeout=timeout,
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
            # Check for 401 Unauthorized — attempt token refresh and retry once
            error_str = str(e)
            is_401 = "401" in error_str or "Unauthorized" in error_str
            if is_401 and self._token_manager:
                try:
                    from testmcpy.src.token_manager import TokenRefreshError

                    print(
                        f"  [Auth] Got 401 for '{tool_call.name}', refreshing token...",
                        file=sys.stderr,
                    )
                    await self._token_manager.refresh()
                    # Update the BearerAuth with new token
                    self.auth = BearerAuth(token=self._token_manager.access_token)
                    # Retry the call once (recursive with no further retry)
                    saved_manager = self._token_manager
                    self._token_manager = None  # Prevent infinite retry loop
                    try:
                        return await self.call_tool(tool_call, timeout)
                    finally:
                        self._token_manager = saved_manager
                except (TokenRefreshError, httpx.HTTPError) as refresh_err:
                    return MCPToolResult(
                        tool_call_id=tool_call.id or "unknown",
                        content=None,
                        is_error=True,
                        error_message=(
                            f"Tool call '{tool_call.name}' got 401 and token "
                            f"refresh failed: {refresh_err}"
                        ),
                    )

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


class StdioMCPClient:
    """Client for interacting with MCP servers via stdio (subprocess) transport.

    Spawns a subprocess with the given command+args and communicates via
    stdin/stdout using JSON-RPC protocol.  Implements the same interface as
    MCPClient (initialize, list_tools, call_tool, close).
    """

    def __init__(
        self,
        command: str,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
    ):
        self.command = command
        self.args = args or []
        self.env = env
        self._process: asyncio.subprocess.Process | None = None
        self._tools_cache: list[MCPTool] | None = None
        self._request_id = 0
        self._read_lock = asyncio.Lock()

    # -- JSON-RPC helpers ---------------------------------------------------

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    async def _send_request(self, method: str, params: dict[str, Any] | None = None) -> Any:
        """Send a JSON-RPC request and return the result."""
        import json

        if not self._process or self._process.stdin is None or self._process.stdout is None:
            raise MCPError("Stdio process not started. Call initialize() first.")

        request_id = self._next_id()
        request = {"jsonrpc": "2.0", "id": request_id, "method": method}
        if params is not None:
            request["params"] = params

        payload = json.dumps(request) + "\n"
        self._process.stdin.write(payload.encode())
        await self._process.stdin.drain()

        # Read response lines until we get a JSON-RPC response matching our id
        async with self._read_lock:
            loop_start = time.monotonic()
            while True:
                elapsed = time.monotonic() - loop_start
                if elapsed > DEFAULT_TIMEOUT:
                    raise MCPTimeoutError(
                        f"Total elapsed time {elapsed:.1f}s exceeded timeout "
                        f"{DEFAULT_TIMEOUT}s waiting for response to {method}"
                    )
                line = await asyncio.wait_for(
                    self._process.stdout.readline(),
                    timeout=DEFAULT_TIMEOUT,
                )
                if not line:
                    raise MCPConnectionError("Stdio process closed unexpectedly")

                line_str = line.decode().strip()
                if not line_str:
                    continue

                try:
                    response = json.loads(line_str)
                except json.JSONDecodeError:
                    # Skip non-JSON lines (logging output, etc.)
                    continue

                # Match by id
                if isinstance(response, dict) and response.get("id") == request_id:
                    if "error" in response:
                        err = response["error"]
                        raise MCPError(
                            f"JSON-RPC error {err.get('code', '?')}: {err.get('message', 'unknown')}"
                        )
                    return response.get("result")

    # -- Public interface (mirrors MCPClient) --------------------------------

    async def initialize(self, timeout: float = DEFAULT_TIMEOUT) -> dict[str, Any]:
        """Spawn the subprocess and send the MCP initialize handshake."""
        import shutil

        resolved = shutil.which(self.command)
        if resolved is None:
            raise MCPConnectionError(f"Command not found: {self.command}")

        logger.info("Spawning stdio MCP server: %s %s", resolved, self.args)

        env = {**dict(os.environ), **(self.env or {})}
        self._process = await asyncio.create_subprocess_exec(
            resolved,
            *self.args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )

        # MCP initialize handshake
        try:
            result = await asyncio.wait_for(
                self._send_request(
                    "initialize",
                    {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "clientInfo": {"name": "testmcpy", "version": "1.0.0"},
                    },
                ),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            await self.close()
            raise MCPTimeoutError(f"Stdio MCP initialize timed out after {timeout}s")

        # Send initialized notification (no response expected)
        import json

        notif = json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n"
        if self._process.stdin:
            self._process.stdin.write(notif.encode())
            await self._process.stdin.drain()

        return {"status": "connected", "transport": "stdio", "server_info": result}

    async def list_tools(
        self, force_refresh: bool = False, timeout: float = DEFAULT_TIMEOUT
    ) -> list[MCPTool]:
        if not force_refresh and self._tools_cache is not None:
            return self._tools_cache

        try:
            result = await asyncio.wait_for(self._send_request("tools/list"), timeout=timeout)
        except asyncio.TimeoutError:
            raise MCPTimeoutError(f"list_tools timed out after {timeout}s")

        tools: list[MCPTool] = []
        for item in result.get("tools", []):
            tools.append(
                MCPTool(
                    name=item["name"],
                    description=item.get("description", ""),
                    input_schema=item.get("inputSchema", {}),
                    output_schema=item.get("outputSchema"),
                )
            )
        self._tools_cache = tools
        return tools

    async def call_tool(
        self, tool_call: MCPToolCall, timeout: float = DEFAULT_TIMEOUT
    ) -> MCPToolResult:
        try:
            result = await asyncio.wait_for(
                self._send_request(
                    "tools/call",
                    {"name": tool_call.name, "arguments": tool_call.arguments or {}},
                ),
                timeout=timeout,
            )
            return MCPToolResult(
                tool_call_id=tool_call.id or "unknown",
                content=result.get("content"),
                is_error=result.get("isError", False),
            )
        except asyncio.TimeoutError:
            return MCPToolResult(
                tool_call_id=tool_call.id or "unknown",
                content=None,
                is_error=True,
                error_message=f"Tool call '{tool_call.name}' timed out after {timeout}s",
            )
        except MCPError as e:
            return MCPToolResult(
                tool_call_id=tool_call.id or "unknown",
                content=None,
                is_error=True,
                error_message=str(e),
            )

    async def close(self):
        """Kill the subprocess and clean up."""
        if self._process:
            try:
                if self._process.stdin:
                    self._process.stdin.close()
                self._process.terminate()
                try:
                    await asyncio.wait_for(self._process.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    self._process.kill()
                    await self._process.wait()
            except ProcessLookupError:
                pass  # Already exited
            finally:
                self._process = None
                self._tools_cache = None

    async def __aenter__(self):
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
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
