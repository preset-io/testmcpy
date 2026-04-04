"""
FastAPI server for testmcpy web UI.
"""

import os
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
from fastapi.responses import FileResponse, StreamingResponse  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from testmcpy.config import get_config  # noqa: E402
from testmcpy.mcp_profiles import load_profile  # noqa: E402
from testmcpy.server.routers import agent as agent_router  # noqa: E402
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
    CLAUDE_CLI = "claude-cli"  # Alias → claude-sdk
    CLAUDE_CODE = "claude-code"  # Alias → claude-sdk
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
app.include_router(agent_router.router)
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


def _serialize_tool_content(content):
    """Serialize MCP tool result content to JSON-safe format."""
    if content is None:
        return None
    if isinstance(content, (str, int, float, bool)):
        return content
    if isinstance(content, dict):
        return content
    # Handle lists — could be plain JSON or MCP TextContent objects
    if isinstance(content, list):
        # Check if items need serialization (MCP content objects)
        if content and hasattr(content[0], "text"):
            parts = []
            for item in content:
                if hasattr(item, "text"):
                    parts.append(item.text)
                elif hasattr(item, "data"):
                    parts.append(str(item.data))
                else:
                    parts.append(str(item))
            return "\n".join(parts) if parts else ""
        return content  # Plain JSON list
    if hasattr(content, "text"):
        return content.text
    return str(content)


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
                    "result": _serialize_tool_content(tool_result.content)
                    if not tool_result.is_error
                    else None,
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


@app.post("/api/chat/stream")
async def chat_stream(request: ChatRequest):
    """Send a message to the LLM with MCP tools, streaming response via SSE.

    Supports agentic multi-turn tool chains: after the LLM calls tools, the results
    are fed back and the LLM can call more tools until it produces a final answer
    (or max_turns is reached). ClaudeSDKProvider loops internally; all other
    providers are looped by this endpoint.
    """
    import asyncio
    import json
    import time

    MAX_TURNS = 10

    def _clean_response(text: str, has_tool_calls: bool) -> str:
        """Strip tool execution status lines injected by some providers."""
        if not has_tool_calls:
            return text
        lines = text.split("\n")
        filtered: list[str] = []
        skip_next = False
        for line in lines:
            if line.strip().startswith("Tool ") and (
                " executed successfully" in line or " failed" in line
            ):
                skip_next = True
                continue
            if skip_next and (line.strip().startswith("[") or line.strip().startswith("{")):
                skip_next = False
                continue
            skip_next = False
            filtered.append(line)
        return "\n".join(filtered).strip()

    def _build_continuation_prompt(tool_calls_list, tool_results_list) -> str:
        """Build a continuation prompt from tool call/result pairs."""
        parts: list[str] = []
        for tc, tr in zip(tool_calls_list, tool_results_list, strict=False):
            name = strip_mcp_prefix(tc["name"])
            args_str = json.dumps(tc.get("arguments", {}), indent=2)
            if tr["is_error"]:
                parts.append(f"- {name}({args_str}): ERROR - {tr['error']}")
            else:
                result_val = tr["result"]
                result_str = (
                    json.dumps(result_val)
                    if isinstance(result_val, (dict, list))
                    else str(result_val)
                )
                if len(result_str) > 2000:
                    result_str = result_str[:2000] + "... [truncated]"
                parts.append(f"- {name}({args_str}): {result_str}")

        return (
            "Tool execution results:\n"
            + "\n".join(parts)
            + "\n\nAnalyze these results. If you need more information, call additional tools. "
            "Otherwise, provide your final answer to the user's original question."
        )

    async def generate():
        start_time = time.time()

        def send_event(event_type: str, data):
            payload = json.dumps({"type": event_type, "data": data})
            return f"data: {payload}\n\n"

        # --- Setup: resolve model/provider/api_key ---
        api_key = None
        accessed_servers: list[str] = []
        try:
            yield send_event("status", "Resolving LLM configuration...")

            if request.llm_profile:
                from testmcpy.llm_profiles import load_llm_profile

                llm_profile = load_llm_profile(request.llm_profile)
                if llm_profile:
                    if request.model and request.provider:
                        for provider_config in llm_profile.providers:
                            if (
                                provider_config.model == request.model
                                and provider_config.provider == str(request.provider.value)
                            ):
                                api_key = provider_config.api_key
                                break
                        model = request.model
                        provider = request.provider
                    else:
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
                yield send_event(
                    "error", "Model and provider must be specified or configured in LLM profile"
                )
                return

            provider_str = str(provider.value) if hasattr(provider, "value") else str(provider)

            # --- Gather MCP tools ---
            yield send_event("status", "Connecting to MCP servers...")
            clients_to_use: list[tuple] = []
            profiles_to_use = request.profiles
            if not profiles_to_use:
                from testmcpy.server.helpers.mcp_config import load_mcp_yaml

                mcp_config = load_mcp_yaml()
                default_profile = mcp_config.get("default")
                if default_profile:
                    profiles_to_use = [default_profile]

            if profiles_to_use:
                for server_id in profiles_to_use:
                    if ":" in server_id:
                        profile_id, mcp_name = server_id.split(":", 1)
                        accessed_servers.append(f"{profile_id}:{mcp_name}")
                        client = await get_mcp_client_for_server(profile_id, mcp_name)
                        if client:
                            clients_to_use.append((profile_id, mcp_name, client))
                    else:
                        profile_clients = await get_mcp_clients_for_profile(server_id)
                        for mcp_name, client in profile_clients:
                            accessed_servers.append(f"{server_id}:{mcp_name}")
                            clients_to_use.append((server_id, mcp_name, client))

            all_tools: list[dict] = []
            tool_to_client: dict = {}
            for profile_id, mcp_name, client in clients_to_use:
                tools = await client.list_tools()
                for tool in tools:
                    tool_to_client[tool.name] = (client, profile_id, mcp_name)
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

            yield send_event(
                "status", f"Loaded {len(all_tools)} tools. Initializing {provider_str}..."
            )

            # --- Initialize LLM provider ---
            provider_kwargs: dict = {}
            if api_key:
                provider_kwargs["api_key"] = api_key
            llm_provider = create_llm_provider(provider, model, **provider_kwargs)
            await llm_provider.initialize()

            # --- Detect if provider is SDK-based (handles its own agentic loop) ---
            from testmcpy.src.llm_integration import ClaudeSDKProvider

            is_sdk_provider = isinstance(llm_provider, ClaudeSDKProvider)

            if is_sdk_provider:
                # ============================================================
                # SDK provider path: stream directly from SDK query() generator
                # ============================================================
                yield send_event("status", f"Generating response with {model} (SDK agentic)...")

                from claude_agent_sdk import (
                    AssistantMessage,
                    ClaudeAgentOptions,
                    ClaudeSDKError,
                    ResultMessage,
                    TextBlock,
                    ThinkingBlock,
                    ToolUseBlock,
                    UserMessage,
                )
                from claude_agent_sdk import (
                    query as sdk_query,
                )
                from claude_agent_sdk.types import ToolResultBlock

                # Build SDK options directly (bypass provider.generate_with_tools)
                mcp_config = llm_provider._mcp_server_config
                mcp_servers = {}
                if mcp_config:
                    mcp_servers["mcp-service"] = mcp_config

                clean_env = {
                    k: v
                    for k, v in os.environ.items()
                    if not k.startswith("CLAUDE_CODE") and k != "CLAUDECODE"
                }
                clean_env["ANTHROPIC_API_KEY"] = ""

                options = ClaudeAgentOptions(
                    model=model,
                    permission_mode="bypassPermissions",
                    mcp_servers=mcp_servers,
                    max_turns=25,
                    env=clean_env,
                )

                sdk_turn = 1
                turn_tool_count = 0
                token_usage = None
                total_cost = 0.0
                has_content = False
                tool_id_to_name: dict[str, str] = {}  # tool_use_id → tool name

                yield send_event("turn_start", {"turn": sdk_turn, "max_turns": MAX_TURNS})

                # Patch SDK message parser to skip unknown message types
                # (e.g. rate_limit_event) instead of throwing MessageParseError
                import claude_agent_sdk._internal.message_parser as _sdk_parser

                _original_parse = _sdk_parser.parse_message

                def _patched_parse(data):
                    try:
                        return _original_parse(data)
                    except ClaudeSDKError:
                        msg_type = data.get("type", "?") if isinstance(data, dict) else "?"
                        print(f"[SDK] Skipping unknown message type: {msg_type}")
                        return None

                _sdk_parser.parse_message = _patched_parse

                pending_tool_calls = []  # Tool calls emitted but no result yet

                try:
                    async for message in sdk_query(prompt=request.message, options=options):
                        if message is None:
                            continue
                        if isinstance(message, AssistantMessage):
                            for block in message.content:
                                if isinstance(block, ThinkingBlock):
                                    if sdk_turn > 1 and not has_content:
                                        yield send_event(
                                            "thinking",
                                            f"\n--- Turn {sdk_turn} ---\n",
                                        )
                                    # Stream thinking in chunks
                                    text = block.thinking
                                    for i in range(0, len(text), 80):
                                        yield send_event("thinking", text[i : i + 80])
                                elif isinstance(block, TextBlock):
                                    has_content = True
                                    # Stream response tokens
                                    text = block.text
                                    for i in range(0, len(text), 3):
                                        yield send_event("token", text[i : i + 3])
                                elif isinstance(block, ToolUseBlock):
                                    turn_tool_count += 1
                                    tool_id_to_name[block.id] = block.name
                                    pending_tool_calls.append(
                                        {
                                            "name": block.name,
                                            "arguments": block.input,
                                            "id": block.id,
                                        }
                                    )
                                    yield send_event(
                                        "tool_call",
                                        {
                                            "id": block.id,
                                            "name": block.name,
                                            "arguments": block.input,
                                            "turn": sdk_turn,
                                        },
                                    )

                        elif isinstance(message, UserMessage):
                            # Tool results from SDK-executed tools
                            pending_tool_calls.clear()  # Results received
                            if isinstance(message.content, list):
                                for block in message.content:
                                    if isinstance(block, ToolResultBlock):
                                        raw = block.content or ""
                                        content = _serialize_tool_content(raw)
                                        is_error = block.is_error or False
                                        tool_name = tool_id_to_name.get(
                                            block.tool_use_id, block.tool_use_id
                                        )
                                        yield send_event(
                                            "tool_result",
                                            {
                                                "id": block.tool_use_id,
                                                "name": tool_name,
                                                "result": content if not is_error else None,
                                                "error": str(content) if is_error else None,
                                                "is_error": is_error,
                                                "turn": sdk_turn,
                                            },
                                        )

                            # New turn: tool results received, next assistant
                            # message will be a new turn
                            yield send_event(
                                "turn_complete",
                                {"turn": sdk_turn, "tool_count": turn_tool_count},
                            )
                            sdk_turn += 1
                            turn_tool_count = 0
                            has_content = False
                            yield send_event(
                                "turn_start",
                                {"turn": sdk_turn, "max_turns": MAX_TURNS},
                            )
                            yield send_event(
                                "status",
                                f"Turn {sdk_turn}/{MAX_TURNS} — Thinking...",
                            )

                        elif isinstance(message, ResultMessage):
                            if message.usage:
                                usage = message.usage
                                token_usage = {
                                    "prompt": (
                                        usage.get("input_tokens", 0)
                                        + usage.get("cache_read_input_tokens", 0)
                                        + usage.get("cache_creation_input_tokens", 0)
                                    ),
                                    "completion": usage.get("output_tokens", 0),
                                    "total": (
                                        usage.get("input_tokens", 0)
                                        + usage.get("cache_read_input_tokens", 0)
                                        + usage.get("cache_creation_input_tokens", 0)
                                        + usage.get("output_tokens", 0)
                                    ),
                                }
                            if message.total_cost_usd is not None:
                                total_cost = message.total_cost_usd

                except ClaudeSDKError:
                    # Non-fatal: rate_limit_event or other unknown types.
                    # If there are pending tool calls without results,
                    # execute them ourselves via MCP.
                    pass
                finally:
                    _sdk_parser.parse_message = _original_parse

                # If SDK stream died with pending tool calls, execute them via MCP
                if pending_tool_calls:
                    yield send_event(
                        "status",
                        f"Executing {len(pending_tool_calls)} tool(s) via MCP...",
                    )
                    for tc in pending_tool_calls:
                        actual_name = strip_mcp_prefix(tc["name"])
                        tool_info = tool_to_client.get(actual_name)
                        if tool_info:
                            client_for_tool = tool_info[0]
                            mcp_tc = MCPToolCall(
                                name=actual_name,
                                arguments=tc.get("arguments", {}),
                                id=tc.get("id", "unknown"),
                            )
                            tr = await client_for_tool.call_tool(mcp_tc)
                            yield send_event(
                                "tool_result",
                                {
                                    "name": tc["name"],
                                    "result": _serialize_tool_content(tr.content)
                                    if not tr.is_error
                                    else None,
                                    "error": tr.error_message if tr.is_error else None,
                                    "is_error": tr.is_error,
                                    "turn": sdk_turn,
                                },
                            )
                        else:
                            yield send_event(
                                "tool_result",
                                {
                                    "name": tc["name"],
                                    "result": None,
                                    "error": f"Tool '{tc['name']}' not found",
                                    "is_error": True,
                                    "turn": sdk_turn,
                                },
                            )

                # Close the final turn
                yield send_event(
                    "turn_complete",
                    {"turn": sdk_turn, "tool_count": turn_tool_count},
                )

                await llm_provider.close()

                duration = time.time() - start_time
                yield send_event(
                    "complete",
                    {
                        "token_usage": token_usage,
                        "cost": total_cost,
                        "duration": duration,
                        "model": model,
                        "provider": provider_str,
                        "total_turns": sdk_turn,
                    },
                )

            else:
                # ============================================================
                # Non-SDK provider path: external agentic loop
                # ============================================================
                total_token_usage: dict[str, int] = {}
                total_cost: float = 0.0
                total_turns = 0

                # Build conversation history for multi-turn
                conversation: list[dict] = []
                if request.history:
                    conversation = list(request.history)

                current_prompt = request.message

                for turn in range(1, MAX_TURNS + 1):
                    total_turns = turn
                    yield send_event("turn_start", {"turn": turn, "max_turns": MAX_TURNS})
                    yield send_event(
                        "status",
                        f"Turn {turn}/{MAX_TURNS} — Generating with {model}...",
                    )

                    result = await llm_provider.generate_with_tools(
                        prompt=current_prompt,
                        tools=all_tools,
                        timeout=120.0,
                        messages=conversation if conversation else None,
                    )

                    # Accumulate token usage
                    if result.token_usage:
                        for k, v in result.token_usage.items():
                            total_token_usage[k] = total_token_usage.get(k, 0) + v
                    total_cost += result.cost or 0.0

                    # Stream thinking (with turn separator for turn > 1)
                    if result.thinking:
                        if turn > 1:
                            yield send_event("thinking", f"\n--- Turn {turn} ---\n")
                        chunk_size = 80
                        for i in range(0, len(result.thinking), chunk_size):
                            chunk = result.thinking[i : i + chunk_size]
                            yield send_event("thinking", chunk)
                            await asyncio.sleep(0.005)

                    # Stream response tokens
                    clean_response = _clean_response(result.response, bool(result.tool_calls))
                    if clean_response:
                        if turn > 1:
                            yield send_event("token", "\n\n")
                        for i in range(0, len(clean_response), 3):
                            chunk = clean_response[i : i + 3]
                            yield send_event("token", chunk)
                            await asyncio.sleep(0.008)

                    # If no tool calls, we're done
                    if not result.tool_calls:
                        yield send_event("turn_complete", {"turn": turn, "tool_count": 0})
                        break

                    # Execute tool calls and stream results
                    turn_tool_calls = []
                    turn_tool_results = []
                    for tool_call in result.tool_calls:
                        actual_tool_name = strip_mcp_prefix(tool_call["name"])
                        tc_id = tool_call.get("id", f"tc_{turn}_{actual_tool_name}")
                        yield send_event(
                            "tool_call",
                            {
                                "id": tc_id,
                                "name": tool_call["name"],
                                "arguments": tool_call.get("arguments", {}),
                                "turn": turn,
                            },
                        )
                        yield send_event(
                            "status",
                            f"Turn {turn}/{MAX_TURNS} — Executing: {actual_tool_name}...",
                        )

                        tool_info = tool_to_client.get(actual_tool_name)
                        if not tool_info:
                            tr_data = {
                                "id": tc_id,
                                "name": tool_call["name"],
                                "result": None,
                                "error": f"Tool '{tool_call['name']}' not found in any MCP profile",
                                "is_error": True,
                                "turn": turn,
                            }
                            yield send_event("tool_result", tr_data)
                            turn_tool_calls.append(tool_call)
                            turn_tool_results.append(tr_data)
                            continue

                        client_for_tool = tool_info[0]
                        mcp_tool_call = MCPToolCall(
                            name=actual_tool_name,
                            arguments=tool_call.get("arguments", {}),
                            id=tool_call.get("id", "unknown"),
                        )
                        tool_result = await client_for_tool.call_tool(mcp_tool_call)
                        tr_data = {
                            "id": tc_id,
                            "name": tool_call["name"],
                            "result": _serialize_tool_content(tool_result.content)
                            if not tool_result.is_error
                            else None,
                            "error": tool_result.error_message if tool_result.is_error else None,
                            "is_error": tool_result.is_error,
                            "turn": turn,
                        }
                        yield send_event("tool_result", tr_data)
                        turn_tool_calls.append(tool_call)
                        turn_tool_results.append(tr_data)

                    yield send_event(
                        "turn_complete",
                        {"turn": turn, "tool_count": len(turn_tool_calls)},
                    )

                    # Build continuation: update conversation and prompt
                    # Add assistant response to conversation
                    conversation.append({"role": "user", "content": current_prompt})
                    conversation.append({"role": "assistant", "content": result.response})
                    current_prompt = _build_continuation_prompt(turn_tool_calls, turn_tool_results)

                await llm_provider.close()

                duration = time.time() - start_time
                yield send_event(
                    "complete",
                    {
                        "token_usage": total_token_usage or result.token_usage,
                        "cost": total_cost,
                        "duration": duration,
                        "model": model,
                        "provider": provider_str,
                        "total_turns": total_turns,
                    },
                )

        except (ConnectionError, TimeoutError, OSError) as e:
            error_msg = str(e)
            for cache_key in accessed_servers:
                await clear_cached_client(cache_key)
            yield send_event("error", f"Connection error: {error_msg}")
        except ValueError as e:
            yield send_event("error", str(e))
        except (RuntimeError, AttributeError, KeyError, TypeError, ImportError) as e:
            # Log full error server-side, send sanitized message to client
            import traceback

            print(f"Chat stream error: {type(e).__name__}: {e}")
            traceback.print_exc()
            yield send_event("error", f"Internal error: {type(e).__name__}")

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


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
