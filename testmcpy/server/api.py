"""
FastAPI server for testmcpy web UI.
"""

import warnings

# Suppress all deprecation warnings from websockets before any imports
warnings.filterwarnings("ignore", category=DeprecationWarning, module="websockets")
warnings.filterwarnings("ignore", category=DeprecationWarning, module="websockets.legacy")
warnings.filterwarnings("ignore", category=DeprecationWarning, module="uvicorn")

from contextlib import asynccontextmanager  # noqa: E402
from datetime import datetime  # noqa: E402
from enum import Enum  # noqa: E402
from pathlib import Path  # noqa: E402
from typing import Any  # noqa: E402

from fastapi import FastAPI, HTTPException, Query, WebSocket  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from testmcpy.config import get_config  # noqa: E402
from testmcpy.mcp_profiles import load_profile  # noqa: E402
from testmcpy.server.routers import auth as auth_router  # noqa: E402
from testmcpy.server.routers import generation_logs as generation_logs_router  # noqa: E402
from testmcpy.server.routers import llm as llm_router  # noqa: E402
from testmcpy.server.routers import mcp_profiles as mcp_profiles_router  # noqa: E402
from testmcpy.server.routers import results as results_router  # noqa: E402
from testmcpy.server.routers import smoke_reports as smoke_reports_router  # noqa: E402
from testmcpy.server.routers import test_profiles as test_profiles_router  # noqa: E402
from testmcpy.server.routers import tests as tests_router  # noqa: E402
from testmcpy.server.routers import tools as tools_router  # noqa: E402
from testmcpy.server.websocket import strip_mcp_prefix  # noqa: E402
from testmcpy.src.llm_integration import create_llm_provider  # noqa: E402
from testmcpy.src.mcp_client import MCPClient, MCPToolCall  # noqa: E402


# Enums for validation
class LLMProvider(str, Enum):
    OLLAMA = "ollama"
    OPENAI = "openai"
    LOCAL = "local"
    ANTHROPIC = "anthropic"
    CLAUDE_SDK = "claude-sdk"
    CLAUDE_CLI = "claude-cli"
    CODEX_CLI = "codex-cli"


class AuthType(str, Enum):
    NONE = "none"
    BEARER = "bearer"
    JWT = "jwt"
    OAUTH = "oauth"


# Pydantic models for request/response
class AuthConfig(BaseModel):
    type: AuthType
    token: str | None = None
    api_url: str | None = None
    api_token: str | None = None
    api_secret: str | None = None
    client_id: str | None = None
    client_secret: str | None = None
    token_url: str | None = None
    scopes: list[str] | None = None
    insecure: bool = False  # Skip SSL verification
    oauth_auto_discover: bool = False  # Use RFC 8414 auto-discovery for OAuth


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    model: str | None = None
    provider: LLMProvider | None = None
    llm_profile: str | None = None  # LLM profile ID to use
    profiles: list[str] | None = None  # List of MCP profile IDs to use
    history: list[dict[str, Any]] | None = None  # Chat history for context


class ChatResponse(BaseModel):
    response: str
    tool_calls: list[dict[str, Any]] = []
    thinking: str | None = None  # Extended thinking content (Claude 4 models)
    token_usage: dict[str, int] | None = None
    cost: float = 0.0
    duration: float = 0.0
    model: str | None = None  # Model used for this response
    provider: str | None = None  # Provider used (anthropic, openai, etc.)


# Global state
config = get_config()
mcp_client: MCPClient | None = None  # Default MCP client (for backwards compat)
mcp_clients: dict[str, MCPClient] = {}  # Cache of MCP clients by "{profile_id}:{mcp_name}"
active_websockets: list[WebSocket] = []


async def get_mcp_clients_for_profile(profile_id: str) -> list[tuple[str, MCPClient]]:
    """
    Get or create MCP clients for all MCP servers in a profile.

    Returns:
        List of tuples (mcp_name, MCPClient) for all MCPs in the profile
    """
    global mcp_clients

    # Load profile
    profile = load_profile(profile_id)
    if not profile:
        raise ValueError(f"Profile '{profile_id}' not found in .mcp_services.yaml")

    clients = []

    # Handle case where profile has no MCPs (backward compatibility check)
    if not profile.mcps:
        raise ValueError(f"Profile '{profile_id}' has no MCP servers configured")

    # Initialize a client for each MCP server in the profile
    for mcp_server in profile.mcps:
        cache_key = f"{profile_id}:{mcp_server.name}"

        # Return cached client if exists
        if cache_key in mcp_clients:
            clients.append((mcp_server.name, mcp_clients[cache_key]))
            continue

        # Create client with auth configuration
        auth_dict = mcp_server.auth.to_dict() if mcp_server.auth else None
        client = MCPClient(mcp_server.mcp_url, auth=auth_dict)
        await client.initialize()

        # Cache the client
        mcp_clients[cache_key] = client
        clients.append((mcp_server.name, client))
        print(
            f"MCP client initialized for profile '{profile_id}', MCP '{mcp_server.name}' at {mcp_server.mcp_url}"
        )

    return clients


async def get_mcp_client_for_server(profile_id: str, mcp_name: str) -> MCPClient | None:
    """
    Get or create MCP client for a specific MCP server in a profile.

    Args:
        profile_id: The profile ID
        mcp_name: The name of the specific MCP server within the profile

    Returns:
        MCPClient instance or None if not found
    """
    global mcp_clients

    # Load profile
    profile = load_profile(profile_id)
    if not profile:
        print(f"Profile '{profile_id}' not found")
        return None

    # Find the specific MCP server
    mcp_server = None
    for server in profile.mcps:
        if server.name == mcp_name:
            mcp_server = server
            break

    if not mcp_server:
        print(f"MCP server '{mcp_name}' not found in profile '{profile_id}'")
        return None

    # Check cache
    cache_key = f"{profile_id}:{mcp_server.name}"
    if cache_key in mcp_clients:
        return mcp_clients[cache_key]

    # Create client with auth configuration
    auth_dict = mcp_server.auth.to_dict() if mcp_server.auth else None
    client = MCPClient(mcp_server.mcp_url, auth=auth_dict)
    await client.initialize()

    # Cache the client
    mcp_clients[cache_key] = client
    print(f"MCP client initialized for '{profile_id}:{mcp_server.name}' at {mcp_server.mcp_url}")

    return client


async def clear_cached_client(cache_key: str) -> bool:
    """
    Clear a cached MCP client by its cache key.

    Args:
        cache_key: Cache key in format "{profile_id}:{mcp_name}"

    Returns:
        True if a client was cleared, False if no client was cached
    """
    global mcp_clients

    client = mcp_clients.pop(cache_key, None)
    if client:
        try:
            await client.close()
            print(f"Cleared cached client '{cache_key}' (stale JWT token)")
        except Exception as e:
            print(f"Warning: Failed to close cached client '{cache_key}': {e}")
        return True
    return False


def is_auth_error(error_msg: str) -> bool:
    """Check if an error message indicates an authentication failure."""
    error_lower = error_msg.lower()
    return (
        "401" in error_lower
        or "403" in error_lower
        or "unauthorized" in error_lower
        or "forbidden" in error_lower
        or "not connect" in error_lower
    )


def is_connection_error(error_msg: str) -> bool:
    """Check if an error message indicates a connection issue (auth, timeout, or connection failure)."""
    error_lower = error_msg.lower()
    return (
        is_auth_error(error_msg)
        or "timeout" in error_lower
        or "timed out" in error_lower
        or "connection" in error_lower
        or "refused" in error_lower
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan event handler for startup and shutdown."""
    global mcp_client, mcp_clients
    # Startup
    try:
        mcp_url = config.get_mcp_url()
        if mcp_url:
            mcp_client = MCPClient(mcp_url)
            await mcp_client.initialize()
            print(f"MCP client initialized at {mcp_url}")
        else:
            print("No default MCP URL configured")
    except Exception as e:
        print(f"Warning: Failed to initialize MCP client: {e}")

    yield

    # Shutdown
    if mcp_client:
        await mcp_client.close()

    # Close all profile clients (cache keys are "{profile_id}:{mcp_name}")
    for cache_key, client in mcp_clients.items():
        try:
            await client.close()
            print(f"Closed MCP client '{cache_key}'")
        except Exception as e:
            print(f"Error closing client '{cache_key}': {e}")


# Initialize FastAPI app
app = FastAPI(
    title="testmcpy Web UI",
    description="Web interface for testing MCP services with LLMs",
    version="1.0.0",
    lifespan=lifespan,
)

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify exact origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add middleware to set CSP headers for ngrok compatibility
from starlette.middleware.base import BaseHTTPMiddleware  # noqa: E402


class CSPMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)

        # Set permissive CSP for development (allows ngrok)
        # In production, you'd want to tighten this up
        response.headers["Content-Security-Policy"] = (
            "default-src * 'unsafe-inline' 'unsafe-eval' data: blob:; "
            "script-src * 'unsafe-inline' 'unsafe-eval' blob:; "
            "worker-src * blob:; "
            "style-src * 'unsafe-inline'; "
            "img-src * data: blob:; "
            "font-src * data:; "
            "connect-src *; "
        )

        return response


app.add_middleware(CSPMiddleware)


# Global Exception Handlers - Never let the server crash

from testmcpy.error_handlers import global_exception_handler  # noqa: E402

app.exception_handler(Exception)(global_exception_handler)

# Register routers
app.include_router(auth_router.router)
app.include_router(generation_logs_router.router)
app.include_router(llm_router.router)
app.include_router(mcp_profiles_router.router)
app.include_router(results_router.router)
app.include_router(smoke_reports_router.router)
app.include_router(test_profiles_router.router)
app.include_router(tests_router.router)
app.include_router(tools_router.router)


# API Routes


@app.get("/")
async def root():
    """Root endpoint - serves the React app."""
    ui_dir = Path(__file__).parent.parent / "ui" / "dist"
    index_file = ui_dir / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {"message": "testmcpy Web UI - Build the React app first"}


@app.get("/api/health")
async def health_check():
    """Health check endpoint with detailed status."""
    from testmcpy.mcp_profiles import get_profile_config

    # Check if MCP config exists
    has_config = False
    profile_count = 0
    mcp_server_count = 0

    try:
        profile_config = get_profile_config()
        if profile_config.has_profiles():
            has_config = True
            profile_ids = profile_config.list_profiles()
            profile_count = len(profile_ids)
            for profile_id in profile_ids:
                profile = profile_config.get_profile(profile_id)
                if profile:
                    mcp_server_count += len(profile.mcps)
    except Exception:
        pass

    return {
        "status": "healthy",
        "mcp_connected": mcp_client is not None,
        "mcp_clients_cached": len(mcp_clients),
        "has_config": has_config,
        "profile_count": profile_count,
        "mcp_server_count": mcp_server_count,
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/api/version")
async def get_version():
    """Get the testmcpy version."""
    from testmcpy import __version__

    return {"version": __version__}


@app.get("/api/config")
async def get_configuration():
    """Get current configuration."""
    all_config = config.get_all_with_sources()

    # Mask sensitive values
    masked_config = {}
    for key, (value, source) in all_config.items():
        if "API_KEY" in key or "TOKEN" in key or "SECRET" in key:
            if value:
                masked_value = f"{value[:8]}...{value[-4:]}" if len(value) > 12 else "***"
            else:
                masked_value = None
        else:
            masked_value = value

        masked_config[key] = {"value": masked_value, "source": source}

    return masked_config


@app.get("/api/models")
async def list_models():
    """List available models for each provider."""
    return {
        "anthropic": [
            {
                "id": "claude-sonnet-4-5",
                "name": "Claude Sonnet 4.5",
                "description": "Latest Sonnet 4.5 (most capable)",
            },
            {
                "id": "claude-haiku-4-5",
                "name": "Claude Haiku 4.5",
                "description": "Latest Haiku 4.5 (fast & efficient)",
            },
            {
                "id": "claude-opus-4-1",
                "name": "Claude Opus 4.1",
                "description": "Latest Opus 4.1 (most powerful)",
            },
            {
                "id": "claude-haiku-4-5",
                "name": "Claude 3.5 Haiku",
                "description": "Legacy Haiku 3.5",
            },
        ],
        "ollama": [
            {
                "id": "llama3.1:8b",
                "name": "Llama 3.1 8B",
                "description": "Meta's Llama 3.1 8B (good balance)",
            },
            {
                "id": "llama3.1:70b",
                "name": "Llama 3.1 70B",
                "description": "Meta's Llama 3.1 70B (more capable)",
            },
            {
                "id": "qwen2.5:14b",
                "name": "Qwen 2.5 14B",
                "description": "Alibaba's Qwen 2.5 14B (strong coding)",
            },
            {"id": "mistral:7b", "name": "Mistral 7B", "description": "Mistral 7B (efficient)"},
        ],
        "openai": [
            {
                "id": "gpt-4o",
                "name": "GPT-4 Optimized",
                "description": "GPT-4 Optimized (recommended)",
            },
            {"id": "gpt-4-turbo", "name": "GPT-4 Turbo", "description": "GPT-4 Turbo"},
            {"id": "gpt-4", "name": "GPT-4", "description": "GPT-4 (original)"},
            {
                "id": "gpt-3.5-turbo",
                "name": "GPT-3.5 Turbo",
                "description": "GPT-3.5 Turbo (faster, cheaper)",
            },
        ],
    }


# MCP Tools, Resources, Prompts


@app.get("/api/mcp/tools")
async def list_mcp_tools(profiles: list[str] = Query(default=None)):
    """List all MCP tools with their schemas. Supports optional ?profiles=xxx&profiles=yyy parameters."""
    accessed_servers = []  # Track servers accessed for cache invalidation on error
    try:
        all_tools = []

        if profiles:
            # Parse server IDs in format "profileId:mcpName"
            for server_id in profiles:
                if ":" in server_id:
                    # New format: specific server selection
                    profile_id, mcp_name = server_id.split(":", 1)
                    accessed_servers.append(f"{profile_id}:{mcp_name}")
                    client = await get_mcp_client_for_server(profile_id, mcp_name)
                    if client:
                        tools = await client.list_tools()
                        for tool in tools:
                            all_tools.append(
                                {
                                    "name": tool.name,
                                    "description": tool.description,
                                    "input_schema": tool.input_schema,
                                    "output_schema": tool.output_schema,
                                    "mcp_source": mcp_name,
                                }
                            )
                else:
                    # Legacy format: entire profile (load all servers from profile)
                    clients = await get_mcp_clients_for_profile(server_id)
                    for mcp_name, client in clients:
                        accessed_servers.append(f"{server_id}:{mcp_name}")
                        tools = await client.list_tools()
                        for tool in tools:
                            all_tools.append(
                                {
                                    "name": tool.name,
                                    "description": tool.description,
                                    "input_schema": tool.input_schema,
                                    "output_schema": tool.output_schema,
                                    "mcp_source": mcp_name,
                                }
                            )

        return all_tools
    except HTTPException:
        raise
    except Exception as e:
        error_msg = str(e)
        if is_connection_error(error_msg):
            # Clear stale cached clients so retry can get fresh connection
            for cache_key in accessed_servers:
                await clear_cached_client(cache_key)
            raise HTTPException(
                status_code=503,
                detail=f"Service unavailable: Unable to connect to MCP server. {error_msg}",
            )
        raise HTTPException(status_code=500, detail=error_msg)


@app.get("/api/mcp/resources")
async def list_mcp_resources(profiles: list[str] = Query(default=None)):
    """List all MCP resources. Supports optional ?profiles=xxx&profiles=yyy parameters."""
    all_resources = []

    if profiles:
        # Parse server IDs in format "profileId:mcpName"
        for server_id in profiles:
            if ":" in server_id:
                # New format: specific server selection
                profile_id, mcp_name = server_id.split(":", 1)
                try:
                    client = await get_mcp_client_for_server(profile_id, mcp_name)
                    if client:
                        resources = await client.list_resources()
                        for resource in resources:
                            if isinstance(resource, dict):
                                resource["mcp_source"] = mcp_name
                            all_resources.append(resource)
                except Exception as e:
                    # Server doesn't support resources or connection failed - skip silently
                    print(f"Warning: Could not list resources from {mcp_name}: {e}")
            else:
                # Legacy format: entire profile
                try:
                    clients = await get_mcp_clients_for_profile(server_id)
                    for mcp_name, client in clients:
                        try:
                            resources = await client.list_resources()
                            for resource in resources:
                                if isinstance(resource, dict):
                                    resource["mcp_source"] = mcp_name
                                all_resources.append(resource)
                        except Exception as e:
                            print(f"Warning: Could not list resources from {mcp_name}: {e}")
                except Exception as e:
                    print(f"Warning: Could not get clients for profile {server_id}: {e}")

    return all_resources


@app.get("/api/mcp/prompts")
async def list_mcp_prompts(profiles: list[str] = Query(default=None)):
    """List all MCP prompts. Supports optional ?profiles=xxx&profiles=yyy parameters."""
    all_prompts = []

    if profiles:
        # Parse server IDs in format "profileId:mcpName"
        for server_id in profiles:
            if ":" in server_id:
                # New format: specific server selection
                profile_id, mcp_name = server_id.split(":", 1)
                try:
                    client = await get_mcp_client_for_server(profile_id, mcp_name)
                    if client:
                        prompts = await client.list_prompts()
                        for prompt in prompts:
                            if isinstance(prompt, dict):
                                prompt["mcp_source"] = mcp_name
                            all_prompts.append(prompt)
                except Exception as e:
                    # Server doesn't support prompts or connection failed - skip silently
                    print(f"Warning: Could not list prompts from {mcp_name}: {e}")
            else:
                # Legacy format: entire profile
                try:
                    clients = await get_mcp_clients_for_profile(server_id)
                    for mcp_name, client in clients:
                        try:
                            prompts = await client.list_prompts()
                            for prompt in prompts:
                                if isinstance(prompt, dict):
                                    prompt["mcp_source"] = mcp_name
                                all_prompts.append(prompt)
                        except Exception as e:
                            print(f"Warning: Could not list prompts from {mcp_name}: {e}")
                except Exception as e:
                    print(f"Warning: Could not get clients for profile {server_id}: {e}")

    return all_prompts


# Chat endpoint


@app.post("/api/chat")
async def chat(request: ChatRequest) -> ChatResponse:
    """Send a message to the LLM with MCP tools."""
    # Get model, provider, and api_key from LLM profile if specified
    api_key = None
    if request.llm_profile:
        from testmcpy.llm_profiles import load_llm_profile

        llm_profile = load_llm_profile(request.llm_profile)
        if llm_profile:
            # If specific model/provider requested, find matching config
            if request.model and request.provider:
                # Find provider config matching the request
                for provider_config in llm_profile.providers:
                    if provider_config.model == request.model and provider_config.provider == str(
                        request.provider.value
                    ):
                        api_key = provider_config.api_key
                        break
                model = request.model
                provider = request.provider
            else:
                # Use default provider
                default_provider_config = llm_profile.get_default_provider()
                if default_provider_config:
                    model = request.model or default_provider_config.model
                    provider = request.provider or default_provider_config.provider
                    api_key = default_provider_config.api_key
                else:
                    model = request.model or config.default_model
                    provider = request.provider or config.default_provider
        else:
            model = request.model or config.default_model
            provider = request.provider or config.default_provider
    else:
        model = request.model or config.default_model
        provider = request.provider or config.default_provider

    if not model or not provider:
        raise HTTPException(
            status_code=400,
            detail="Model and provider must be specified or configured in LLM profile",
        )

    print(f"[Chat] Using provider={provider}, model={model}")

    accessed_servers = []  # Track servers accessed for cache invalidation on error
    try:
        # Determine which MCP clients to use
        clients_to_use = []  # List of (profile_id, mcp_name, client) tuples

        # Use specified profiles or fall back to default profile
        profiles_to_use = request.profiles
        if not profiles_to_use:
            # Load default profile from config
            from testmcpy.server.helpers.mcp_config import load_mcp_yaml

            mcp_config = load_mcp_yaml()
            default_profile = mcp_config.get("default")
            if default_profile:
                profiles_to_use = [default_profile]
                print(f"[Chat] Using default profile: {default_profile}")

        if profiles_to_use:
            # Parse server IDs in format "profileId:mcpName"
            for server_id in profiles_to_use:
                if ":" in server_id:
                    # New format: specific server selection
                    profile_id, mcp_name = server_id.split(":", 1)
                    accessed_servers.append(f"{profile_id}:{mcp_name}")
                    client = await get_mcp_client_for_server(profile_id, mcp_name)
                    if client:
                        clients_to_use.append((profile_id, mcp_name, client))
                else:
                    # Legacy format: entire profile (load all servers from profile)
                    profile_clients = await get_mcp_clients_for_profile(server_id)
                    for mcp_name, client in profile_clients:
                        accessed_servers.append(f"{server_id}:{mcp_name}")
                        clients_to_use.append((server_id, mcp_name, client))

        # Gather tools from all clients
        all_tools = []
        tool_to_client = {}  # Map tool name to (client, profile_id, mcp_name) for execution

        for profile_id, mcp_name, client in clients_to_use:
            tools = await client.list_tools()
            for tool in tools:
                # Track which client provides this tool (last wins if duplicate names)
                tool_to_client[tool.name] = (client, profile_id, mcp_name)

                # Add tool to list
                all_tools.append(
                    {
                        "type": "function",
                        "function": {
                            "name": tool.name,
                            "description": tool.description,
                            "parameters": tool.input_schema,
                        },
                    }
                )

        # Initialize LLM provider
        print(f"[Chat] Creating LLM provider: {provider}")
        provider_kwargs = {}
        if api_key:
            provider_kwargs["api_key"] = api_key
        llm_provider = create_llm_provider(provider, model, **provider_kwargs)
        print("[Chat] Initializing LLM provider...")
        await llm_provider.initialize()
        print(
            f"[Chat] LLM provider initialized. Generating response with {len(all_tools)} tools..."
        )

        # Generate response with optional history
        # Use longer timeout (120s) for Claude CLI with MCP tools
        result = await llm_provider.generate_with_tools(
            prompt=request.message, tools=all_tools, timeout=120.0, messages=request.history
        )
        print(f"[Chat] Response generated. Tool calls: {len(result.tool_calls)}")

        # Execute tool calls if any
        tool_calls_with_results = []
        if result.tool_calls:
            for tool_call in result.tool_calls:
                # Strip MCP prefix from tool name if present (e.g., mcp__testmcpy__list_charts -> list_charts)
                actual_tool_name = strip_mcp_prefix(tool_call["name"])
                mcp_tool_call = MCPToolCall(
                    name=actual_tool_name,
                    arguments=tool_call.get("arguments", {}),
                    id=tool_call.get("id", "unknown"),
                )

                # Find the appropriate client for this tool (using stripped name)
                tool_info = tool_to_client.get(actual_tool_name)
                if not tool_info:
                    # Tool not found in any client
                    tool_call_with_result = {
                        "name": tool_call["name"],
                        "arguments": tool_call.get("arguments", {}),
                        "id": tool_call.get("id", "unknown"),
                        "result": None,
                        "error": f"Tool '{tool_call['name']}' not found in any MCP profile",
                        "is_error": True,
                    }
                    tool_calls_with_results.append(tool_call_with_result)
                    continue

                # Extract client info
                client_for_tool, profile_id, mcp_name = tool_info

                # Execute tool call
                tool_result = await client_for_tool.call_tool(mcp_tool_call)

                # Add result to tool call
                tool_call_with_result = {
                    "name": tool_call["name"],
                    "arguments": tool_call.get("arguments", {}),
                    "id": tool_call.get("id", "unknown"),
                    "result": tool_result.content if not tool_result.is_error else None,
                    "error": tool_result.error_message if tool_result.is_error else None,
                    "is_error": tool_result.is_error,
                }
                tool_calls_with_results.append(tool_call_with_result)

        await llm_provider.close()

        # Clean up response - remove tool execution messages since we show them separately
        clean_response = result.response
        if tool_calls_with_results:
            # Remove lines that start with "Tool <name> executed" or "Tool <name> failed"
            lines = clean_response.split("\n")
            filtered_lines = []
            skip_next = False
            for line in lines:
                # Skip tool execution status lines
                if line.strip().startswith("Tool ") and (
                    " executed successfully" in line or " failed" in line
                ):
                    skip_next = True
                    continue
                # Skip the raw content line after tool execution
                if skip_next and (line.strip().startswith("[") or line.strip().startswith("{")):
                    skip_next = False
                    continue
                skip_next = False
                filtered_lines.append(line)

            clean_response = "\n".join(filtered_lines).strip()

        return ChatResponse(
            response=clean_response,
            tool_calls=tool_calls_with_results,
            thinking=result.thinking,
            token_usage=result.token_usage,
            cost=result.cost,
            duration=result.duration,
            model=model,
            provider=str(provider.value) if hasattr(provider, "value") else str(provider),
        )

    except Exception as e:
        error_msg = str(e)
        if is_connection_error(error_msg):
            # Clear stale cached clients so retry can get fresh connection
            for cache_key in accessed_servers:
                await clear_cached_client(cache_key)
            raise HTTPException(
                status_code=503,
                detail=f"Service unavailable: Unable to connect to MCP server. {error_msg}",
            )
        raise HTTPException(status_code=500, detail=error_msg)


# WebSocket endpoint for streaming test execution
from testmcpy.server.websocket import handle_test_websocket  # noqa: E402


@app.websocket("/ws/tests")
async def websocket_tests(websocket: WebSocket):
    """WebSocket endpoint for streaming test execution with real-time logs."""
    await handle_test_websocket(websocket)


# Catch-all route for React Router (must be before static files)
@app.get("/{full_path:path}")
async def serve_react_app(full_path: str):
    """Serve React app for all non-API routes (SPA support)."""
    # Don't intercept API routes
    if full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="API endpoint not found")

    # Serve index.html for all other routes (client-side routing)
    ui_dir = Path(__file__).parent.parent / "ui" / "dist"
    index_file = ui_dir / "index.html"

    # Check if it's a static file request
    static_file = ui_dir / full_path
    if static_file.exists() and static_file.is_file():
        return FileResponse(static_file)

    # Otherwise serve index.html for React Router
    if index_file.exists():
        return FileResponse(index_file)

    return {"message": "testmcpy Web UI - Build the React app first"}
