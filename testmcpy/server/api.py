"""
FastAPI server for testmcpy web UI.
"""

import asyncio
import json
import os
import time
import warnings
from collections import defaultdict, deque

# Suppress all deprecation warnings from websockets before any imports
warnings.filterwarnings("ignore", category=DeprecationWarning, module="websockets")
warnings.filterwarnings("ignore", category=DeprecationWarning, module="websockets.legacy")
warnings.filterwarnings("ignore", category=DeprecationWarning, module="uvicorn")

import contextlib  # noqa: E402
from contextlib import asynccontextmanager  # noqa: E402
from datetime import datetime  # noqa: E402
from enum import Enum  # noqa: E402
from pathlib import Path  # noqa: E402
from tempfile import TemporaryDirectory  # noqa: E402
from typing import Any, cast  # noqa: E402
from urllib.parse import urlsplit  # noqa: E402

from fastapi import FastAPI, HTTPException, Query, WebSocket  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402
from sqlalchemy.exc import SQLAlchemyError  # noqa: E402
from starlette.responses import PlainTextResponse  # noqa: E402
from starlette.websockets import WebSocketClose  # noqa: E402

from testmcpy.config import get_config  # noqa: E402
from testmcpy.llm_profiles import (  # noqa: E402
    LLMProfileConfigError,
    LLMProfileNotFoundError,
    resolve_llm_provider_selection,
)
from testmcpy.mcp_profiles import load_profile  # noqa: E402
from testmcpy.scrubber import scrub_obj, scrub_text  # noqa: E402
from testmcpy.server.routers import agent as agent_router  # noqa: E402
from testmcpy.server.routers import analytics as analytics_router  # noqa: E402
from testmcpy.server.routers import auth as auth_router  # noqa: E402
from testmcpy.server.routers import compare as compare_router  # noqa: E402
from testmcpy.server.routers import compatibility as compatibility_router  # noqa: E402
from testmcpy.server.routers import generation_logs as generation_logs_router  # noqa: E402
from testmcpy.server.routers import health as health_router  # noqa: E402
from testmcpy.server.routers import llm as llm_router  # noqa: E402
from testmcpy.server.routers import mcp_profiles as mcp_profiles_router  # noqa: E402
from testmcpy.server.routers import metrics as metrics_router  # noqa: E402
from testmcpy.server.routers import oauth_probe as oauth_probe_router  # noqa: E402
from testmcpy.server.routers import results as results_router  # noqa: E402
from testmcpy.server.routers import runs as runs_router  # noqa: E402
from testmcpy.server.routers import search as search_router  # noqa: E402
from testmcpy.server.routers import security as security_router  # noqa: E402
from testmcpy.server.routers import smoke_reports as smoke_reports_router  # noqa: E402
from testmcpy.server.routers import test_profiles as test_profiles_router  # noqa: E402
from testmcpy.server.routers import tests as tests_router  # noqa: E402
from testmcpy.server.routers import tools as tools_router  # noqa: E402
from testmcpy.server.websocket import strip_mcp_prefix  # noqa: E402
from testmcpy.src.llm_integration import (  # noqa: E402
    BaseSDKProvider,
    ClaudeSDKProvider,
    _claude_result_message_error,
    _close_async_iterator,
    _prepare_agent_chat_context,
    create_llm_provider,
)
from testmcpy.src.mcp_client import MCPClient, MCPConnectionError, MCPToolCall  # noqa: E402


# Enums for validation
class LLMProvider(str, Enum):
    OLLAMA = "ollama"
    OPENAI = "openai"
    OPENROUTER = "openrouter"
    LOCAL = "local"
    ANTHROPIC = "anthropic"
    BEDROCK = "bedrock"
    AWS_BEDROCK = "aws-bedrock"
    GEMINI = "gemini"
    GOOGLE = "google"
    CLAUDE_SDK = "claude-sdk"
    CLAUDE_CLI = "claude-cli"  # Alias → claude-sdk
    CLAUDE_CODE = "claude-code"  # Alias → claude-sdk
    ASSISTANT = "assistant"
    CHATBOT = "chatbot"
    CODEX_SDK = "codex-sdk"
    CODEX_CLI = "codex-cli"
    CODEX = "codex"
    GEMINI_CLI = "gemini-cli"
    GEMINI_SDK = "gemini-sdk"
    XAI = "xai"
    GROK = "grok"


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
    context_trimmed: dict[str, Any] | None = None


# Global state
config = get_config()
mcp_client: MCPClient | None = None  # Default MCP client (for backwards compat)
mcp_clients: dict[str, MCPClient] = {}  # Cache of MCP clients by "{profile_id}:{mcp_name}"
# Per-key locks to prevent concurrent OAuth flows for the same server.
_client_init_locks: dict[str, asyncio.Lock] = {}
active_websockets: list[WebSocket] = []

# Exponential back-off state for failed MCP connections.
# Maps cache_key → (next_retry_monotonic, failure_count)
# No lock needed: the helpers below never await between read and write, so
# each mutation runs atomically on the event loop; the connection-init path
# itself is serialized per key by _client_init_locks.
_connection_backoff: dict[str, tuple[float, int]] = {}
_BACKOFF_BASE = 5.0  # seconds for first retry
_BACKOFF_MAX = 300.0  # cap at 5 minutes


def _backoff_remaining(cache_key: str) -> float:
    """Return seconds until the next retry is allowed, or 0.0 if ready."""
    entry = _connection_backoff.get(cache_key)
    if entry is None:
        return 0.0
    next_retry, _ = entry
    return max(0.0, next_retry - time.monotonic())


def _record_failure(cache_key: str) -> None:
    """Increment failure count and push out the next-retry timestamp."""
    _, count = _connection_backoff.get(cache_key, (0.0, 0))
    delay = min(_BACKOFF_BASE * (2**count), _BACKOFF_MAX)
    _connection_backoff[cache_key] = (time.monotonic() + delay, count + 1)
    print(f"  [MCP] Back-off: '{cache_key}' failure #{count + 1}, next retry in {delay:.0f}s")


def _clear_failure(cache_key: str) -> None:
    """Clear back-off state after a successful connection."""
    _connection_backoff.pop(cache_key, None)


def _get_init_lock(cache_key: str) -> asyncio.Lock:
    """Get or create an asyncio.Lock for a given cache key."""
    if cache_key not in _client_init_locks:
        _client_init_locks[cache_key] = asyncio.Lock()
    return _client_init_locks[cache_key]


def _primary_mcp_provider_kwargs(
    clients_to_use: list[tuple[str, str, MCPClient]],
) -> dict[str, Any]:
    """mcp_url/auth kwargs from the FIRST selected MCP client.

    SDK providers support a single MCP server; the Chat UI sends exactly one
    "profileId:mcpName". Without these kwargs the providers fall back to the
    DEFAULT profile's URL/auth, breaking chat for any other selected profile.
    create_llm_provider filters these out for providers that don't accept them.
    """
    if not clients_to_use:
        return {}
    _profile_id, _mcp_name, client = clients_to_use[0]
    return {"mcp_url": client.base_url, "auth": client.auth_config}


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

        # Enforce back-off before attempting a fresh connection
        remaining = _backoff_remaining(cache_key)
        if remaining > 0:
            raise MCPConnectionError(
                f"MCP server '{mcp_server.name}' is unavailable; retry in {remaining:.0f}s"
            )

        # Lock to prevent concurrent OAuth popups for the same server
        async with _get_init_lock(cache_key):
            # Re-check after acquiring lock
            if cache_key in mcp_clients:
                clients.append((mcp_server.name, mcp_clients[cache_key]))
                continue

            # Re-check back-off (another task may have just failed)
            remaining = _backoff_remaining(cache_key)
            if remaining > 0:
                raise MCPConnectionError(
                    f"MCP server '{mcp_server.name}' is unavailable; retry in {remaining:.0f}s"
                )

            # Create client with auth configuration
            auth_dict = mcp_server.auth.to_dict() if mcp_server.auth else None
            client = MCPClient(mcp_server.mcp_url, auth=auth_dict)
            try:
                await client.initialize()
            except Exception:
                # Intentionally broad: any init failure (auth, network, SDK
                # bug) must record back-off state before re-raising.
                _record_failure(cache_key)
                raise

            _clear_failure(cache_key)
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

    # Enforce back-off before attempting a fresh connection
    remaining = _backoff_remaining(cache_key)
    if remaining > 0:
        raise MCPConnectionError(
            f"MCP server '{mcp_name}' is unavailable; retry in {remaining:.0f}s"
        )

    # Lock to prevent concurrent OAuth popups for the same server
    async with _get_init_lock(cache_key):
        # Re-check after acquiring lock
        if cache_key in mcp_clients:
            return mcp_clients[cache_key]

        # Re-check back-off (another task may have just failed)
        remaining = _backoff_remaining(cache_key)
        if remaining > 0:
            raise MCPConnectionError(
                f"MCP server '{mcp_name}' is unavailable; retry in {remaining:.0f}s"
            )

        # Create client with auth configuration
        auth_dict = mcp_server.auth.to_dict() if mcp_server.auth else None
        client = MCPClient(mcp_server.mcp_url, auth=auth_dict)
        try:
            await client.initialize()
        except Exception:
            # Intentionally broad: any init failure (auth, network, SDK bug)
            # must record back-off state before re-raising.
            _record_failure(cache_key)
            raise

        _clear_failure(cache_key)
        # Cache the client
        mcp_clients[cache_key] = client
        print(
            f"MCP client initialized for '{profile_id}:{mcp_server.name}' at {mcp_server.mcp_url}"
        )

        return client


async def clear_cached_client(cache_key: str, record_failure: bool = True) -> bool:
    """
    Clear a cached MCP client by its cache key.

    Args:
        cache_key: Cache key in format "{profile_id}:{mcp_name}"
        record_failure: When True (default), throttle the next reconnect via
            back-off. Pass False for deliberate re-initialization (e.g. an
            interactive OAuth re-login) where an immediate reconnect is wanted.

    Returns:
        True if a client was cleared, False if no client was cached
    """
    global mcp_clients

    client = mcp_clients.pop(cache_key, None)
    if client:
        if record_failure:
            # Record a failure so the next reconnect is throttled via back-off.
            _record_failure(cache_key)
        try:
            await client.close()
            print(f"Cleared cached client '{cache_key}'")
        except (OSError, RuntimeError) as e:
            print(f"Warning: Failed to close cached client '{cache_key}': {e}")
        return True
    return False


# Marker substring of the ValueError raised by BaseSDKProvider when an
# oauth_auto_discover profile has no cached token (see
# llm_integration.BaseSDKProvider._resolve_mcp_bearer_token).
_OAUTH_TOKEN_ERROR = "No usable cached OAuth token"


def _chat_oauth_login_enabled() -> bool:
    """Feature flag for interactive OAuth login during chat (default ON).

    Disable with TESTMCPY_CHAT_OAUTH_LOGIN=false (or 0/no). Read at call time
    so tests can monkeypatch the environment.
    """
    return os.environ.get("TESTMCPY_CHAT_OAUTH_LOGIN", "true").strip().lower() not in (
        "0",
        "false",
        "no",
    )


async def _relogin_oauth_servers(server_keys: list[str]) -> dict[str, MCPClient]:
    """Deliberate interactive re-auth for the given "profileId:mcpName" keys.

    Drops cached clients WITHOUT recording back-off, clears any pre-existing
    back-off state, and re-initializes. MCPClient.initialize() with
    oauth_auto_discover opens the browser OAuth flow and caches the token via
    the shared FastMCP TokenStorageAdapter backend; duplicate popups are
    prevented by the per-key init locks.

    Returns the fresh clients keyed by cache key so callers can replace any
    references to the old, now-closed client objects.
    """
    new_clients: dict[str, MCPClient] = {}
    for cache_key in server_keys:
        await clear_cached_client(cache_key, record_failure=False)
        _clear_failure(cache_key)  # earlier failures must not block deliberate re-auth
        profile_id, mcp_name = cache_key.split(":", 1)
        client = await get_mcp_client_for_server(profile_id, mcp_name)
        if client:
            new_clients[cache_key] = client
    return new_clients


def _refresh_client_refs(
    new_clients: dict[str, MCPClient],
    clients_to_use: list[tuple[str, str, MCPClient]],
    tool_to_client: dict[str, tuple[MCPClient, str, str]],
) -> tuple[list[tuple[str, str, MCPClient]], dict[str, tuple[MCPClient, str, str]]]:
    """Swap re-logged-in clients into the chat endpoints' lookup structures.

    After _relogin_oauth_servers the old client objects are closed; tool
    execution through tool_to_client must use the replacements.
    """
    refreshed_clients = [
        (pid, name, new_clients.get(f"{pid}:{name}", client))
        for pid, name, client in clients_to_use
    ]
    refreshed_tools = {
        tool: (new_clients.get(f"{pid}:{name}", client), pid, name)
        for tool, (client, pid, name) in tool_to_client.items()
    }
    return refreshed_clients, refreshed_tools


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
    """Check if an error message indicates a fatal connection issue.

    Only returns True for errors where the MCP session is truly dead and
    the cached client must be discarded. Auth errors (401/403) are NOT
    included because the MCPOAuth transport handles token refresh and
    re-auth internally — evicting the client on an expired token would
    just trigger a new browser OAuth popup.
    """
    error_lower = error_msg.lower()
    return (
        "refused" in error_lower
        or "reset by peer" in error_lower
        or "name or service not known" in error_lower
        or "no route to host" in error_lower
        or "failed to connect" in error_lower
        or "failed to initialize" in error_lower
        or "timed out" in error_lower
    )


def _mcp_exception_handler(loop, context):
    """Suppress the RuntimeError from MCP OAuth auth-flow generator cleanup.

    When asyncio.wait_for cancels a child task that holds a FastMCP
    async_auth_flow generator, Python's GC schedules aclose() on the
    abandoned generator in a new event-loop task.  That cleanup task tries
    to release an anyio Lock that was acquired by the original (now-gone)
    child task, which throws RuntimeError("The current task is not holding
    this lock").  This is a known limitation of the upstream MCP library and
    only affects Python 3.10 (on 3.11+ list_tools uses asyncio.timeout which
    keeps everything in the current task and avoids the problem).
    """
    exc = context.get("exception")
    if isinstance(exc, RuntimeError) and "not holding this lock" in str(exc):
        return  # Suppress — already handled at the endpoint level
    loop.default_exception_handler(context)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan event handler for startup and shutdown."""
    global mcp_client, mcp_clients

    import asyncio as _asyncio

    _asyncio.get_event_loop().set_exception_handler(_mcp_exception_handler)

    # Reconcile runs orphaned by a previous crash/restart — the in-memory
    # run registry dies with the process, so stuck 'running' rows would
    # otherwise pollute listings forever.
    try:
        from testmcpy.storage import get_storage

        interrupted = get_storage().mark_stale_runs_interrupted()
        if interrupted:
            print(f"Marked {interrupted} stale running run(s) as interrupted")
    except SQLAlchemyError as e:
        print(f"Warning: could not reconcile stale runs: {e}")

    # …and keep reconciling while we run, so a crashed sibling server (or
    # a row orphaned by an event-loop death that didn't restart the
    # process) flips to 'interrupted' within minutes rather than at the
    # next restart. Heartbeat-only (no started_at fallback): legacy rows
    # without heartbeats carry local-naive timestamps that can't be
    # compared reliably against a UTC cutoff.
    async def _stale_run_sweeper() -> None:
        from testmcpy.storage import get_storage

        while True:
            await _asyncio.sleep(60)
            try:
                get_storage().mark_stale_runs_interrupted(no_heartbeat_older_than_hours=None)
            except _asyncio.CancelledError:
                raise
            except Exception as sweep_err:  # noqa: BLE001 — long-lived loop:
                # any escaping error (not just SQLAlchemyError — e.g. an
                # OSError on first-time DB-path init) would otherwise kill
                # the sweeper permanently and silently, reverting crash
                # reconciliation to startup-only. (PR #90 review)
                print(f"Warning: stale-run sweep failed: {sweep_err}")

    sweeper_task = _asyncio.create_task(_stale_run_sweeper())

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
    sweeper_task.cancel()
    with contextlib.suppress(_asyncio.CancelledError):
        await sweeper_task

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


@app.exception_handler(LLMProfileNotFoundError)
async def llm_profile_not_found_handler(_request, exc: LLMProfileNotFoundError):
    return JSONResponse(status_code=404, content={"detail": scrub_text(str(exc))})


@app.exception_handler(LLMProfileConfigError)
async def llm_profile_config_error_handler(_request, exc: LLMProfileConfigError):
    return JSONResponse(status_code=409, content={"detail": scrub_text(str(exc))})


# The production UI is same-origin. These entries support the local Vite UI
# when it accesses the API directly instead of using Vite's proxy.
_DEFAULT_CORS_ORIGINS = (
    "http://127.0.0.1:3000",
    "http://localhost:3000",
    "http://[::1]:3000",
)


def _get_cors_settings() -> tuple[list[str], bool]:
    """Return configured origins and whether credentialed CORS is safe."""
    configured = os.environ.get("TESTMCPY_CORS_ORIGINS")
    if configured is None:
        return list(_DEFAULT_CORS_ORIGINS), True

    origins = list(
        dict.fromkeys(origin.strip() for origin in configured.split(",") if origin.strip())
    )
    if "*" in origins:
        # Preserve an explicitly requested wildcard without reflecting origins
        # while also permitting credentialed cross-origin requests.
        return ["*"], False
    return origins, True


_cors_origins, _cors_allow_credentials = _get_cors_settings()

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=_cors_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API key auth middleware (activated when TESTMCPY_API_KEY is set)
from testmcpy.server.auth_middleware import APIKeyAuthMiddleware  # noqa: E402

app.add_middleware(APIKeyAuthMiddleware)

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


_DEFAULT_ALLOWED_HOSTS = ("127.0.0.1", "localhost", "::1", "testserver")


def _allowed_request_hosts() -> tuple[str, ...]:
    """Return hostnames accepted by the local UI server."""
    configured = os.environ.get("TESTMCPY_ALLOWED_HOSTS")
    if configured is None:
        return _DEFAULT_ALLOWED_HOSTS
    return tuple(host.strip().lower() for host in configured.split(",") if host.strip())


def _request_host_is_allowed(raw_host: str, allowed_hosts: tuple[str, ...]) -> bool:
    """Match an HTTP Host header without trusting its port or IPv6 brackets."""
    if "*" in allowed_hosts:
        return True
    try:
        hostname = urlsplit(f"//{raw_host}").hostname
    except ValueError:
        return False
    if not hostname:
        return False
    hostname = hostname.lower().rstrip(".")
    for pattern in allowed_hosts:
        normalized = pattern.strip("[]").rstrip(".")
        if normalized.startswith("*."):
            if hostname.endswith(f".{normalized[2:]}"):
                return True
        elif hostname == normalized:
            return True
    return False


class AllowedHostsMiddleware:
    """Reject DNS-rebinding hosts before any HTTP or WebSocket route runs."""

    def __init__(self, asgi_app):
        self.app = asgi_app

    async def __call__(self, scope, receive, send):
        if scope["type"] not in {"http", "websocket"}:
            await self.app(scope, receive, send)
            return
        raw_host = next(
            (
                value.decode("latin-1")
                for key, value in scope.get("headers", [])
                if key.lower() == b"host"
            ),
            "",
        )
        allowed_hosts = _allowed_request_hosts()
        if _request_host_is_allowed(raw_host, allowed_hosts):
            # Origin-sensitive routes may trust request.base_url only after this
            # middleware validates an explicit host. A wildcard host policy does
            # not confer that trust.
            if "*" not in allowed_hosts:
                scope.setdefault("state", {})["testmcpy_trusted_host"] = True
            await self.app(scope, receive, send)
            return
        if scope["type"] == "websocket":
            await WebSocketClose(code=1008, reason="Invalid host header")(scope, receive, send)
            return
        await PlainTextResponse("Invalid host header", status_code=400)(scope, receive, send)


app.add_middleware(AllowedHostsMiddleware)


# Global Exception Handlers - Never let the server crash

from testmcpy.error_handlers import global_exception_handler  # noqa: E402

app.exception_handler(Exception)(global_exception_handler)

# Register routers
app.include_router(agent_router.router)
app.include_router(analytics_router.router)
app.include_router(auth_router.router)
app.include_router(generation_logs_router.router)
app.include_router(llm_router.router)
app.include_router(mcp_profiles_router.router)
app.include_router(results_router.router)
app.include_router(runs_router.router)
app.include_router(smoke_reports_router.router)
app.include_router(test_profiles_router.router)
app.include_router(tests_router.router)
app.include_router(compatibility_router.router)
app.include_router(compare_router.router)
app.include_router(health_router.router)
app.include_router(metrics_router.router)
app.include_router(oauth_probe_router.router)
app.include_router(security_router.router)
app.include_router(tools_router.router)
app.include_router(search_router.router)


# API Routes

_UI_DIST_DIR = Path(__file__).parent.parent / "ui" / "dist"
_INDEX_CACHE_CONTROL = "no-cache"
_HASHED_ASSET_CACHE_CONTROL = "public, max-age=31536000, immutable"


def _serve_ui_index() -> FileResponse | None:
    """Serve the SPA entry point with mandatory revalidation."""
    index_file = _UI_DIST_DIR / "index.html"
    if not index_file.exists():
        return None
    return FileResponse(index_file, headers={"Cache-Control": _INDEX_CACHE_CONTROL})


def _ui_static_path(full_path: str) -> Path | None:
    """Resolve a UI path without allowing encoded or direct parent traversal."""
    root = _UI_DIST_DIR.resolve()
    candidate = (root / full_path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate


@app.get("/")
async def root():
    """Root endpoint - serves the React app."""
    index_response = _serve_ui_index()
    if index_response is not None:
        return index_response
    return {"message": "testmcpy Web UI - Build the React app first"}


@app.get("/health")
async def health_probe():
    """Simple health probe for load balancers and container orchestration."""
    from testmcpy import __version__

    return {"status": "ok", "version": __version__}


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
    """List available models for each provider (sourced from the model registry)."""
    from testmcpy.src.model_registry import get_models_by_provider  # noqa: PLC0415

    def _entries(provider: str) -> list[dict[str, str]]:
        return [
            {"id": m.id, "name": m.name, "description": m.description}
            for m in get_models_by_provider(provider)
            if not m.is_deprecated
        ]

    return {
        "anthropic": _entries("anthropic"),
        # Ollama models are local installs, not in the registry
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
        "openai": _entries("openai"),
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
                                    "gateway": getattr(tool, "gateway", False),
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
                                    "gateway": getattr(tool, "gateway", False),
                                }
                            )

        return all_tools
    except HTTPException:
        raise
    except Exception as e:
        error_msg = scrub_text(str(e))
        # Always evict cached clients on any error — a failed list_tools() call
        # leaves the cached client in a broken state that will repeat the error
        # on every subsequent request until evicted.
        for cache_key in accessed_servers:
            await clear_cached_client(cache_key)
        if is_connection_error(error_msg) or is_auth_error(error_msg):
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


def _normalize_tool_call_id(value: Any) -> str | None:
    """Normalize provider-specific tool call IDs for result matching."""
    return None if value is None or value == "" else str(value)


def _pair_native_tool_results(
    tool_calls: list[dict[str, Any]],
    native_results: list[Any],
) -> dict[int, Any]:
    """Pair native results by ID, falling back only when position is unambiguous."""
    results_by_id: defaultdict[str, deque[Any]] = defaultdict(deque)
    idless_results: deque[Any] = deque()

    for result in native_results:
        raw_id = (
            result.get("tool_call_id")
            if isinstance(result, dict)
            else getattr(result, "tool_call_id", None)
        )
        result_id = _normalize_tool_call_id(raw_id)
        if result_id is None:
            idless_results.append(result)
        else:
            results_by_id[result_id].append(result)

    paired: dict[int, Any] = {}
    unmatched_calls: list[int] = []
    for index, tool_call in enumerate(tool_calls):
        call_id = _normalize_tool_call_id(tool_call.get("id"))
        candidates = results_by_id.get(call_id) if call_id is not None else None
        if candidates:
            paired[index] = candidates.popleft()
        else:
            unmatched_calls.append(index)

    # An ID-less result is safe to assign only when every remaining call and
    # result can be paired one-to-one and no identified result went unmatched.
    if not any(results_by_id.values()) and len(idless_results) == len(unmatched_calls):
        paired.update(zip(unmatched_calls, idless_results, strict=True))

    return paired


def _native_tool_result_fields(native_result: Any) -> tuple[Any, bool, str | None]:
    """Extract the common fields from dict and MCPToolResult values."""
    if isinstance(native_result, dict):
        content = native_result.get("content", native_result.get("result"))
        is_error = bool(native_result.get("is_error", False))
        error = native_result.get("error_message") or native_result.get("error")
        return content, is_error, error

    return (
        getattr(native_result, "content", native_result),
        bool(getattr(native_result, "is_error", False)),
        getattr(native_result, "error_message", None),
    )


def _llm_result_error(result: Any) -> str | None:
    """Return an explicit provider failure without mistaking model text for one."""
    error = getattr(result, "error", None)
    return scrub_text(str(error)) if error else None


def _estimate_chat_tokens(value: Any) -> int:
    """Conservatively estimate tokens for provider-neutral JSON/text input."""
    if value is None:
        return 0
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    return max(1, (len(text) + 2) // 3)


def _budget_chat_history(
    history: list[dict[str, Any]] | None,
    *,
    model: str,
    prompt: str,
    tools: list[dict[str, Any]],
) -> tuple[list[dict[str, str]] | None, dict[str, Any] | None]:
    """Fit recent saved context to the selected model while retaining it in the browser."""
    if not history:
        return None, None

    from testmcpy.src.model_registry import get_model

    valid_history = [
        {"role": message["role"], "content": message["content"]}
        for message in history
        if isinstance(message, dict)
        and message.get("role") in {"system", "user", "assistant"}
        and isinstance(message.get("content"), str)
        and message["content"].strip()
    ]
    if not valid_history:
        return None, None

    model_info = get_model(str(model))
    context_window = model_info.context_window if model_info else 128_000
    output_reserve = model_info.max_output_tokens if model_info else 8_192
    fixed_input_tokens = _estimate_chat_tokens(prompt) + _estimate_chat_tokens(tools) + 2_048
    # Never let history consume more than 70% of the window: system/tool
    # wrappers and provider tokenizers add overhead beyond this approximation.
    history_budget = max(
        0,
        min(
            int(context_window * 0.70),
            context_window - output_reserve - fixed_input_tokens,
        ),
    )

    system_messages = [message for message in valid_history if message["role"] == "system"]
    dialogue = [message for message in valid_history if message["role"] != "system"]
    selected_system: list[dict[str, str]] = []
    remaining = history_budget
    truncated_system = False

    for message in system_messages:
        cost = _estimate_chat_tokens(message["content"]) + 6
        if cost <= remaining:
            selected_system.append(message)
            remaining -= cost
            continue
        if remaining > 32:
            max_chars = max(0, (remaining - 32) * 3)
            selected_system.append(
                {
                    **message,
                    "content": message["content"][:max_chars]
                    + "\n\n[System instruction truncated for this model's context window]",
                }
            )
            remaining = 0
        truncated_system = True
        break

    selected_reversed: list[dict[str, str]] = []
    omitted_messages = 0
    for message in reversed(dialogue):
        cost = _estimate_chat_tokens(message["content"]) + 6
        if cost <= remaining:
            selected_reversed.append(message)
            remaining -= cost
        else:
            omitted_messages += 1

    selected_dialogue = list(reversed(selected_reversed))
    # Stricter providers reject an assistant message without its preceding
    # user turn. Drop it rather than silently reassigning its role.
    while selected_dialogue and selected_dialogue[0]["role"] == "assistant":
        selected_dialogue.pop(0)
        omitted_messages += 1

    trimmed_history = [*selected_system, *selected_dialogue]
    omitted_messages += max(0, len(system_messages) - len(selected_system))
    was_trimmed = omitted_messages > 0 or truncated_system
    if not was_trimmed:
        return trimmed_history, None

    notice = {
        "omitted_messages": omitted_messages,
        "original_messages": len(valid_history),
        "sent_messages": len(trimmed_history),
        "context_window": context_window,
        "model": str(model),
        "system_truncated": truncated_system,
    }
    return trimmed_history or None, notice


# Chat endpoint


@app.post("/api/chat")
async def chat(request: ChatRequest) -> ChatResponse:
    """Send a message to the LLM with MCP tools."""
    provider, model, profile_provider_config = resolve_llm_provider_selection(
        request.provider,
        request.model,
        request.llm_profile,
        fallback_provider=config.default_provider,
        fallback_model=config.default_model,
    )

    if not model or not provider:
        raise HTTPException(
            status_code=400,
            detail="Model and provider must be specified or configured in LLM profile",
        )

    print(f"[Chat] Using provider={provider}, model={model}")

    accessed_servers = []  # Track servers accessed for cache invalidation on error
    llm_provider = None
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
        provider_kwargs = dict(profile_provider_config)
        provider_kwargs.update(_primary_mcp_provider_kwargs(clients_to_use))
        print("[Chat] Initializing LLM provider...")
        try:
            llm_provider = create_llm_provider(provider, model, **provider_kwargs)
            await llm_provider.initialize()
        except ValueError as e:
            if not (_chat_oauth_login_enabled() and _OAUTH_TOKEN_ERROR in str(e)):
                raise
            if llm_provider is not None:
                with contextlib.suppress(Exception):
                    await llm_provider.close()
                llm_provider = None
            print("[Chat] No cached OAuth token; triggering interactive OAuth login...")
            new_clients = await _relogin_oauth_servers(accessed_servers)
            # The old client objects are closed now — swap in the replacements
            # so tool execution doesn't hit a closed client.
            clients_to_use, tool_to_client = _refresh_client_refs(
                new_clients, clients_to_use, tool_to_client
            )
            provider_kwargs.update(_primary_mcp_provider_kwargs(clients_to_use))
            llm_provider = create_llm_provider(provider, model, **provider_kwargs)
            # Single retry; a second failure falls to the existing handlers.
            await llm_provider.initialize()
        print(
            f"[Chat] LLM provider initialized. Generating response with {len(all_tools)} tools..."
        )

        chat_history, context_notice = _budget_chat_history(
            request.history,
            model=str(model),
            prompt=request.message,
            tools=all_tools,
        )

        # Generate response with optional history
        # Use longer timeout (120s) for Claude CLI with MCP tools
        result = await llm_provider.generate_with_tools(
            prompt=request.message, tools=all_tools, timeout=120.0, messages=chat_history
        )
        if provider_error := _llm_result_error(result):
            raise RuntimeError(provider_error)
        print(f"[Chat] Response generated. Tool calls: {len(result.tool_calls)}")

        # Execute tool calls if any. SDK-backed providers may have already
        # executed the entire turn; never replay those state-changing calls.
        tool_calls_with_results = []
        native_tool_results = getattr(result, "tool_results", None) or []
        native_results_by_call = _pair_native_tool_results(result.tool_calls, native_tool_results)
        provider_executes_tools = isinstance(llm_provider, BaseSDKProvider)
        if result.tool_calls:
            for index, tool_call in enumerate(result.tool_calls):
                if native_tool_results or provider_executes_tools:
                    if index not in native_results_by_call:
                        tool_calls_with_results.append(
                            {
                                "name": tool_call["name"],
                                "arguments": tool_call.get("arguments", {}),
                                "id": tool_call.get("id", "unknown"),
                                "result": None,
                                "error": "Provider did not return a result for this tool call",
                                "is_error": True,
                            }
                        )
                        continue

                    native_content, native_is_error, native_error = _native_tool_result_fields(
                        native_results_by_call[index]
                    )

                    tool_calls_with_results.append(
                        {
                            "name": tool_call["name"],
                            "arguments": tool_call.get("arguments", {}),
                            "id": tool_call.get("id", "unknown"),
                            "result": (
                                _serialize_tool_content(native_content)
                                if not native_is_error
                                else None
                            ),
                            "error": native_error if native_is_error else None,
                            "is_error": native_is_error,
                        }
                    )
                    continue

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

        public_result = scrub_obj(
            {
                "response": clean_response,
                "tool_calls": tool_calls_with_results,
                "thinking": result.thinking,
                "token_usage": result.token_usage,
                "cost": result.cost,
                "duration": result.duration,
                "model": model,
                "provider": str(provider.value) if hasattr(provider, "value") else str(provider),
                "context_trimmed": context_notice,
            }
        )
        return ChatResponse(**public_result)

    except Exception as e:
        error_msg = scrub_text(str(e))
        if is_connection_error(error_msg):
            # Clear stale cached clients so retry can get fresh connection
            for cache_key in accessed_servers:
                await clear_cached_client(cache_key)
            raise HTTPException(
                status_code=503,
                detail=f"Service unavailable: Unable to connect to MCP server. {error_msg}",
            )
        raise HTTPException(status_code=500, detail=error_msg)
    finally:
        if llm_provider is not None:
            with contextlib.suppress(Exception):
                await llm_provider.close()


@app.post("/api/chat/stream")
async def chat_stream(request: ChatRequest):
    """Send a message to the LLM with MCP tools, streaming response via SSE.

    Supports agentic multi-turn tool chains: after the LLM calls tools, the results
    are fed back and the LLM can call more tools until it produces a final answer
    (or max_turns is reached). SDK-backed providers loop internally; Claude streams
    directly from its SDK while other completed SDK runs are emitted once. Non-SDK
    providers are looped by this endpoint.
    """
    import asyncio
    import time

    # Cap for the non-SDK manual tool loop implemented by this endpoint. This
    # loop hard-stops at MAX_TURNS, so its progress is shown as "Turn n/10".
    MAX_TURNS = 10
    # SDK-backed providers (Claude) loop internally up to this safety cap
    # (passed to ``build_agent_options`` below); the manual loop does not apply
    # to them. Their turn count is open-ended from the UI's perspective, so the
    # SDK path emits no ``max_turns`` and the UI shows a bare "Turn n".
    SDK_MAX_TURNS = 25

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
        llm_provider = None
        sdk_tmpdir = None
        mcp_proxy = None

        def send_event(event_type: str, data):
            payload = json.dumps(scrub_obj({"type": event_type, "data": data}))
            return f"data: {payload}\n\n"

        # --- Setup: resolve model/provider/profile runtime configuration ---
        accessed_servers: list[str] = []
        try:
            yield send_event("status", "Resolving LLM configuration...")

            provider, model, profile_provider_config = resolve_llm_provider_selection(
                request.provider,
                request.model,
                request.llm_profile,
                fallback_provider=config.default_provider,
                fallback_model=config.default_model,
            )

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

            chat_history, context_notice = _budget_chat_history(
                request.history,
                model=str(model),
                prompt=request.message,
                tools=all_tools,
            )
            if context_notice:
                yield send_event("context_trimmed", context_notice)

            # --- Initialize LLM provider ---
            provider_kwargs: dict = dict(profile_provider_config)
            provider_kwargs.update(_primary_mcp_provider_kwargs(clients_to_use))
            try:
                llm_provider = create_llm_provider(provider, model, **provider_kwargs)
                await llm_provider.initialize()
            except ValueError as e:
                if not (_chat_oauth_login_enabled() and _OAUTH_TOKEN_ERROR in str(e)):
                    raise
                if llm_provider is not None:
                    with contextlib.suppress(Exception):
                        await llm_provider.close()
                    llm_provider = None
                yield send_event("status", "Waiting for OAuth login in browser...")
                new_clients = await _relogin_oauth_servers(accessed_servers)
                # The old client objects are closed now — swap in the replacements
                # so tool execution doesn't hit a closed client.
                clients_to_use, tool_to_client = _refresh_client_refs(
                    new_clients, clients_to_use, tool_to_client
                )
                provider_kwargs.update(_primary_mcp_provider_kwargs(clients_to_use))
                llm_provider = create_llm_provider(provider, model, **provider_kwargs)
                # Single retry; a second failure falls to the existing handlers.
                await llm_provider.initialize()

            # Claude has a dedicated streaming implementation below. Other SDK
            # providers return their completed native agent loop as one result.
            is_claude_sdk_provider = isinstance(llm_provider, ClaudeSDKProvider)
            provider_executes_tools = isinstance(llm_provider, BaseSDKProvider)

            if is_claude_sdk_provider:
                # ============================================================
                # SDK provider path: stream directly from SDK query() generator
                # ============================================================
                yield send_event("status", f"Generating response with {model} (SDK agentic)...")

                from claude_agent_sdk import (
                    AssistantMessage,
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

                claude_provider = cast(ClaudeSDKProvider, llm_provider)
                sdk_tmpdir = TemporaryDirectory(prefix="testmcpy_chat_sdk_")
                mcp_proxy = await claude_provider.start_insecure_mcp_proxy()
                saved_system_prompt, agent_prompt = _prepare_agent_chat_context(
                    request.message,
                    chat_history,
                )
                options = claude_provider.build_agent_options(
                    model=model,
                    cwd=sdk_tmpdir.name,
                    allow_tool_search=True,
                    mcp_url_override=mcp_proxy.url if mcp_proxy is not None else None,
                    saved_system_prompt=saved_system_prompt,
                    max_turns=SDK_MAX_TURNS,
                )

                sdk_turn = 1
                turn_tool_count = 0
                token_usage = None
                total_cost = 0.0
                has_content = False
                tool_id_to_name: dict[str, str] = {}  # tool_use_id → tool name

                # No ``max_turns``: SDK turns are open-ended, so the UI shows a
                # bare "Turn n" rather than a misleading "Turn n/N".
                yield send_event("turn_start", {"turn": sdk_turn})

                pending_tool_calls = []  # Tool calls emitted but no result yet
                sdk_error = None

                sdk_messages = sdk_query(
                    prompt=agent_prompt,
                    options=options,
                )
                try:
                    async for message in sdk_messages:
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
                            yield send_event("turn_start", {"turn": sdk_turn})
                            yield send_event(
                                "status",
                                f"Turn {sdk_turn} — Thinking...",
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
                            if result_error := _claude_result_message_error(message):
                                sdk_error = result_error

                except ClaudeSDKError as exc:
                    # If there are pending tool calls without results,
                    # execute them ourselves via MCP.
                    sdk_error = str(exc) or type(exc).__name__
                finally:
                    await _close_async_iterator(sdk_messages)

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
                                    "id": tc.get("id"),
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
                                    "id": tc.get("id"),
                                    "name": tc["name"],
                                    "result": None,
                                    "error": f"Tool '{tc['name']}' not found",
                                    "is_error": True,
                                    "turn": sdk_turn,
                                },
                            )

                if sdk_error:
                    yield send_event("error", sdk_error)
                    return

                # Close the final turn
                yield send_event(
                    "turn_complete",
                    {"turn": sdk_turn, "tool_count": turn_tool_count},
                )

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
                reached_terminal_answer = False

                # Build conversation history for multi-turn
                conversation: list[dict] = []
                if chat_history:
                    conversation = list(chat_history)

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
                    if provider_error := _llm_result_error(result):
                        yield send_event("error", provider_error)
                        return

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
                        reached_terminal_answer = True
                        break

                    # Execute tool calls and stream results. SDK-backed providers
                    # already executed these calls and must never be replayed.
                    turn_tool_calls = []
                    turn_tool_results = []
                    native_tool_results = getattr(result, "tool_results", None) or []
                    native_results_by_call = _pair_native_tool_results(
                        result.tool_calls, native_tool_results
                    )
                    for index, tool_call in enumerate(result.tool_calls):
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

                        if native_tool_results or provider_executes_tools:
                            if index not in native_results_by_call:
                                tr_data = {
                                    "id": tc_id,
                                    "name": tool_call["name"],
                                    "result": None,
                                    "error": "Provider did not return a result for this tool call",
                                    "is_error": True,
                                    "turn": turn,
                                }
                            else:
                                native_content, native_is_error, native_error = (
                                    _native_tool_result_fields(native_results_by_call[index])
                                )
                                tr_data = {
                                    "id": tc_id,
                                    "name": tool_call["name"],
                                    "result": (
                                        _serialize_tool_content(native_content)
                                        if not native_is_error
                                        else None
                                    ),
                                    "error": native_error if native_is_error else None,
                                    "is_error": native_is_error,
                                    "turn": turn,
                                }
                            yield send_event("tool_result", tr_data)
                            turn_tool_calls.append(tool_call)
                            turn_tool_results.append(tr_data)
                            continue

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

                    if provider_executes_tools:
                        reached_terminal_answer = True
                        break

                    # Build continuation: update conversation and prompt
                    # Add assistant response to conversation
                    conversation.append({"role": "user", "content": current_prompt})
                    conversation.append({"role": "assistant", "content": result.response})
                    current_prompt = _build_continuation_prompt(turn_tool_calls, turn_tool_results)

                if not reached_terminal_answer:
                    yield send_event(
                        "error",
                        f"Stopped after {MAX_TURNS} tool turns before the model produced a final answer.",
                    )
                    return

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
            error_msg = scrub_text(str(e))
            for cache_key in accessed_servers:
                await clear_cached_client(cache_key)
            yield send_event("error", f"Connection error: {error_msg}")
        except LLMProfileConfigError as e:
            yield send_event("error", scrub_text(str(e)))
        except ValueError as e:
            yield send_event("error", scrub_text(str(e)))
        except (RuntimeError, AttributeError, KeyError, TypeError, ImportError) as e:
            # Log full error server-side, send sanitized message to client
            import traceback

            print(f"Chat stream error: {type(e).__name__}: {scrub_text(str(e))}")
            traceback.print_exc()
            yield send_event("error", f"Internal error: {type(e).__name__}")
        finally:
            if mcp_proxy is not None:
                with contextlib.suppress(Exception):
                    await mcp_proxy.close()
            if sdk_tmpdir is not None:
                with contextlib.suppress(Exception):
                    sdk_tmpdir.cleanup()
            if llm_provider is not None:
                with contextlib.suppress(Exception):
                    await llm_provider.close()

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


# Catch-all route for React Router and built UI assets.
@app.get("/{full_path:path}")
async def serve_react_app(full_path: str):
    """Serve React app for all non-API routes (SPA support)."""
    # Don't intercept API routes
    if full_path == "api" or full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="API endpoint not found")

    # Check if it's a static file request
    static_file = _ui_static_path(full_path)
    if static_file is None:
        raise HTTPException(status_code=404, detail="Static asset not found")
    if static_file.exists() and static_file.is_file():
        cache_control = (
            _HASHED_ASSET_CACHE_CONTROL if full_path.startswith("assets/") else _INDEX_CACHE_CONTROL
        )
        return FileResponse(static_file, headers={"Cache-Control": cache_control})

    # Never return HTML for a missing module, stylesheet, image, or other
    # static file. Browsers reject that response as a MIME type mismatch.
    if full_path.startswith("assets/") or Path(full_path).suffix:
        raise HTTPException(status_code=404, detail="Static asset not found")

    # Extensionless paths are client-side routes.
    index_response = _serve_ui_index()
    if index_response is not None:
        return index_response

    return {"message": "testmcpy Web UI - Build the React app first"}
