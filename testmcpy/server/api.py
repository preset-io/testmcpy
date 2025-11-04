"""
FastAPI server for testmcpy web UI.
"""

import json
import re
import warnings
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from fastapi import FastAPI, HTTPException, WebSocket, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

# Suppress websockets deprecation warnings from uvicorn (third-party code)
# uvicorn hasn't updated to websockets 14.0 API yet
warnings.filterwarnings("ignore", category=DeprecationWarning, module="websockets.legacy")
warnings.filterwarnings(
    "ignore", category=DeprecationWarning, module="uvicorn.protocols.websockets"
)

from testmcpy.config import get_config
from testmcpy.evals.base_evaluators import create_evaluator
from testmcpy.mcp_profiles import MCPProfile, MCPServer, load_profile
from testmcpy.src.llm_integration import create_llm_provider
from testmcpy.src.mcp_client import MCPClient, MCPToolCall
from testmcpy.src.test_runner import TestCase, TestRunner


# Pydantic models for request/response
class ChatRequest(BaseModel):
    message: str
    model: str | None = None
    provider: str | None = None
    profiles: list[str] | None = None  # List of MCP profile IDs to use
    history: list[dict[str, Any]] | None = None  # Chat history for context


class ChatResponse(BaseModel):
    response: str
    tool_calls: list[dict[str, Any]] = []
    token_usage: dict[str, int] | None = None
    cost: float = 0.0
    duration: float = 0.0


class TestFileCreate(BaseModel):
    filename: str
    content: str


class TestFileUpdate(BaseModel):
    content: str


class TestRunRequest(BaseModel):
    test_path: str
    model: str | None = None
    provider: str | None = None


class EvalRunRequest(BaseModel):
    prompt: str
    response: str
    tool_calls: list[dict[str, Any]] = []
    model: str | None = None
    provider: str | None = None


class GenerateTestsRequest(BaseModel):
    tool_name: str
    tool_description: str
    tool_schema: dict[str, Any]
    coverage_level: str  # "basic", "mid", "comprehensive"
    custom_instructions: str | None = None
    model: str | None = None
    provider: str | None = None


class FormatSchemaRequest(BaseModel):
    schema: dict[str, Any]
    tool_name: str
    format: str  # e.g., "python_client", "javascript_client", "typescript_client"
    mcp_url: str | None = None  # For curl format with actual values
    auth_token: str | None = None  # For curl format with actual values


class OptimizeDocsRequest(BaseModel):
    tool_name: str
    description: str
    input_schema: dict[str, Any]
    model: str | None = None
    provider: str | None = None


class OptimizeDocsResponse(BaseModel):
    analysis: dict[str, Any]
    suggestions: dict[str, Any]
    original: dict[str, Any]
    cost: float
    duration: float


class ProfileCreateRequest(BaseModel):
    name: str
    description: str
    is_default: bool = False


class ProfileUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    is_default: bool | None = None


class MCPCreateRequest(BaseModel):
    name: str
    mcp_url: str
    auth_type: str  # bearer, jwt, oauth, none
    token: str | None = None
    api_url: str | None = None
    api_token: str | None = None
    api_secret: str | None = None
    client_id: str | None = None
    client_secret: str | None = None
    token_url: str | None = None
    scopes: list[str] | None = None
    timeout: int | None = None
    rate_limit_rpm: int | None = None


class MCPUpdateRequest(BaseModel):
    name: str | None = None
    mcp_url: str | None = None
    auth_type: str | None = None
    token: str | None = None
    api_url: str | None = None
    api_token: str | None = None
    api_secret: str | None = None
    client_id: str | None = None
    client_secret: str | None = None
    token_url: str | None = None
    scopes: list[str] | None = None
    timeout: int | None = None
    rate_limit_rpm: int | None = None


class MCPReorderRequest(BaseModel):
    from_index: int
    to_index: int


# Global state
config = get_config()
mcp_client: MCPClient | None = None  # Default MCP client (for backwards compat)
mcp_clients: dict[str, MCPClient] = {}  # Cache of MCP clients by "{profile_id}:{mcp_name}"
active_websockets: list[WebSocket] = []


# Helper functions for YAML file manipulation


def get_mcp_config_path() -> Path:
    """Get path to .mcp_services.yaml file."""
    # Look in current directory first
    config_path = Path.cwd() / ".mcp_services.yaml"
    if config_path.exists():
        return config_path

    # Check parent directories
    current = Path.cwd()
    for _ in range(5):
        config_file = current / ".mcp_services.yaml"
        if config_file.exists():
            return config_file
        if current.parent == current:
            break
        current = current.parent

    # Default to current directory
    return Path.cwd() / ".mcp_services.yaml"


def load_mcp_yaml() -> dict[str, Any]:
    """Load MCP configuration from YAML file with error handling."""
    config_path = get_mcp_config_path()
    if not config_path.exists():
        return {"default": "local-dev", "profiles": {}}

    try:
        with open(config_path) as f:
            data = yaml.safe_load(f)
            return data or {"default": "local-dev", "profiles": {}}
    except yaml.YAMLError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to parse YAML configuration: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to load configuration file: {str(e)}"
        )


def validate_config(config_data: dict[str, Any]):
    """
    Validate MCP configuration before saving.

    Raises:
        ValueError: If validation fails with detailed error message
    """
    # Check required top-level fields
    if "profiles" not in config_data:
        raise ValueError("Config must have 'profiles' field")

    if not isinstance(config_data["profiles"], dict):
        raise ValueError("'profiles' must be a dictionary")

    # Validate each profile
    for profile_id, profile in config_data["profiles"].items():
        if not isinstance(profile, dict):
            raise ValueError(f"Profile '{profile_id}' must be a dictionary")

        if "name" not in profile:
            raise ValueError(f"Profile '{profile_id}' missing required 'name' field")

        # Validate MCPs if present
        if "mcps" in profile:
            if not isinstance(profile["mcps"], list):
                raise ValueError(f"Profile '{profile_id}' 'mcps' must be a list")

            for idx, mcp in enumerate(profile["mcps"]):
                if not isinstance(mcp, dict):
                    raise ValueError(
                        f"MCP #{idx} in profile '{profile_id}' must be a dictionary"
                    )

                # Check required MCP fields
                if "name" not in mcp:
                    raise ValueError(
                        f"MCP #{idx} in profile '{profile_id}' missing 'name' field"
                    )

                if "mcp_url" not in mcp:
                    raise ValueError(
                        f"MCP '{mcp['name']}' in profile '{profile_id}' missing 'mcp_url' field"
                    )

                if "auth" not in mcp:
                    raise ValueError(
                        f"MCP '{mcp['name']}' in profile '{profile_id}' missing 'auth' field"
                    )

                # Validate auth configuration
                auth = mcp["auth"]
                if not isinstance(auth, dict):
                    raise ValueError(
                        f"MCP '{mcp['name']}' in profile '{profile_id}' 'auth' must be a dictionary"
                    )

                if "type" not in auth:
                    raise ValueError(
                        f"MCP '{mcp['name']}' in profile '{profile_id}' auth missing 'type' field"
                    )

                auth_type = auth["type"]

                # Validate auth type-specific requirements
                if auth_type == "bearer":
                    # Bearer can have optional token
                    pass
                elif auth_type == "jwt":
                    # JWT should have API credentials (optional, can use env vars)
                    pass
                elif auth_type == "oauth":
                    # OAuth should have client credentials (optional, can use env vars)
                    pass
                elif auth_type == "none":
                    # No auth required
                    pass
                else:
                    raise ValueError(
                        f"MCP '{mcp['name']}' in profile '{profile_id}' has invalid auth type: '{auth_type}'. "
                        f"Must be one of: bearer, jwt, oauth, none"
                    )


def clean_config_for_yaml(config_data: dict[str, Any]) -> dict[str, Any]:
    """
    Clean config data for YAML serialization.

    - Removes None values
    - Preserves empty strings and empty lists
    - Deep copies to avoid mutating original

    Args:
        config_data: Configuration dictionary to clean

    Returns:
        Cleaned configuration dictionary
    """
    import copy

    def clean_value(value):
        """Recursively clean a value."""
        if value is None:
            return None
        elif isinstance(value, dict):
            cleaned = {}
            for k, v in value.items():
                cleaned_v = clean_value(v)
                # Only include if not None
                if cleaned_v is not None:
                    cleaned[k] = cleaned_v
            return cleaned if cleaned else None
        elif isinstance(value, list):
            cleaned = [clean_value(item) for item in value]
            # Filter out None values but keep empty strings
            return [item for item in cleaned if item is not None]
        else:
            return value

    # Deep copy to avoid mutating original
    config_copy = copy.deepcopy(config_data)
    cleaned = clean_value(config_copy)

    # Ensure top-level structure is preserved
    if cleaned is None:
        return {"default": "local-dev", "profiles": {}}

    return cleaned


def save_mcp_yaml(config_data: dict[str, Any]):
    """
    Save MCP configuration to YAML file with robust error handling.

    Features:
    - Validates config before saving
    - Creates backup before overwrite
    - Uses atomic write (temp file + rename)
    - Proper YAML formatting (no line wrapping, unicode support)
    - Automatic rollback on failure
    - Reloads profile config after save

    Args:
        config_data: Configuration dictionary to save

    Raises:
        HTTPException: If save fails with detailed error message
    """
    import shutil

    config_path = get_mcp_config_path()
    backup_path = config_path.with_suffix('.yaml.backup')
    temp_path = config_path.with_suffix('.yaml.tmp')

    try:
        # Step 1: Validate config structure
        validate_config(config_data)

        # Step 2: Clean config (remove None values, etc.)
        cleaned_config = clean_config_for_yaml(config_data)

        # Step 3: Create backup of existing file
        if config_path.exists():
            try:
                shutil.copy2(config_path, backup_path)
            except Exception as e:
                # Log warning but continue - backup is not critical
                print(f"Warning: Failed to create backup: {e}")

        # Step 4: Write to temporary file first (atomic operation pattern)
        try:
            with open(temp_path, 'w', encoding='utf-8') as f:
                yaml.dump(
                    cleaned_config,
                    f,
                    default_flow_style=False,
                    sort_keys=False,
                    indent=2,
                    allow_unicode=True,
                    width=float('inf'),  # Prevent line wrapping
                )
        except Exception as e:
            # Clean up temp file if write failed
            if temp_path.exists():
                temp_path.unlink()
            raise ValueError(f"Failed to write YAML: {str(e)}")

        # Step 5: Validate the written YAML can be read back
        try:
            with open(temp_path, 'r', encoding='utf-8') as f:
                yaml.safe_load(f)
        except Exception as e:
            # Clean up invalid temp file
            if temp_path.exists():
                temp_path.unlink()
            raise ValueError(f"Generated invalid YAML: {str(e)}")

        # Step 6: Atomic rename (replaces original file)
        temp_path.replace(config_path)

        # Step 7: Reload profile config to pick up changes
        from testmcpy.mcp_profiles import reload_profile_config
        reload_profile_config()

    except ValueError as e:
        # Validation or YAML errors - restore from backup
        if backup_path.exists() and not config_path.exists():
            try:
                shutil.copy2(backup_path, config_path)
            except Exception as restore_error:
                print(f"Error restoring backup: {restore_error}")
        raise HTTPException(status_code=400, detail=f"Invalid configuration: {str(e)}")

    except Exception as e:
        # Unexpected errors - try to restore from backup
        if backup_path.exists():
            try:
                shutil.copy2(backup_path, config_path)
                print(f"Restored configuration from backup after error: {e}")
            except Exception as restore_error:
                print(f"Failed to restore backup: {restore_error}")

        raise HTTPException(
            status_code=500,
            detail=f"Failed to save configuration: {str(e)}"
        )

    finally:
        # Clean up temporary file if it still exists
        if temp_path.exists():
            try:
                temp_path.unlink()
            except Exception as e:
                print(f"Warning: Failed to clean up temp file: {e}")


def generate_profile_id(name: str, existing_ids: list[str]) -> str:
    """Generate a unique profile ID from a name."""
    # Convert to lowercase, replace spaces with hyphens
    base_id = name.lower().replace(' ', '-').replace('_', '-')
    # Remove non-alphanumeric characters except hyphens
    base_id = ''.join(c for c in base_id if c.isalnum() or c == '-')

    # Ensure uniqueness
    profile_id = base_id
    counter = 1
    while profile_id in existing_ids:
        profile_id = f"{base_id}-{counter}"
        counter += 1

    return profile_id


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
        auth_dict = mcp_server.auth.to_dict()
        client = MCPClient(mcp_server.mcp_url, auth=auth_dict)
        await client.initialize()

        # Cache the client
        mcp_clients[cache_key] = client
        clients.append((mcp_server.name, client))
        print(f"MCP client initialized for profile '{profile_id}', MCP '{mcp_server.name}' at {mcp_server.mcp_url}")

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
    auth_dict = mcp_server.auth.to_dict()
    client = MCPClient(mcp_server.mcp_url, auth=auth_dict)
    await client.initialize()

    # Cache the client
    mcp_clients[cache_key] = client
    print(f"MCP client initialized for '{profile_id}:{mcp_server.name}' at {mcp_server.mcp_url}")

    return client


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan event handler for startup and shutdown."""
    global mcp_client, mcp_clients
    # Startup
    try:
        mcp_client = MCPClient(config.mcp_url)
        await mcp_client.initialize()
        print(f"MCP client initialized at {config.mcp_url}")
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
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

class CSPMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)

        # Set permissive CSP for development (allows ngrok)
        # In production, you'd want to tighten this up
        response.headers["Content-Security-Policy"] = (
            "default-src * 'unsafe-inline' 'unsafe-eval' data: blob:; "
            "script-src * 'unsafe-inline' 'unsafe-eval'; "
            "style-src * 'unsafe-inline'; "
            "img-src * data: blob:; "
            "font-src * data:; "
            "connect-src *; "
        )

        return response

app.add_middleware(CSPMiddleware)


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
    """Health check endpoint."""
    return {
        "status": "healthy",
        "mcp_connected": mcp_client is not None,
        "timestamp": datetime.now().isoformat(),
    }


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


@app.post("/api/mcp/profiles/create-config")
async def create_mcp_config():
    """Create .mcp_services.yaml from the example file."""
    try:
        import shutil

        example_file = Path(".mcp_services.yaml.example")
        config_file = Path(".mcp_services.yaml")

        # Check if config already exists
        if config_file.exists():
            return {
                "success": False,
                "error": "Configuration file already exists at .mcp_services.yaml"
            }

        # Check if example file exists
        if not example_file.exists():
            return {
                "success": False,
                "error": "Example file .mcp_services.yaml.example not found"
            }

        # Copy example to actual config
        shutil.copy(example_file, config_file)

        return {
            "success": True,
            "message": "Created .mcp_services.yaml from example template",
            "path": str(config_file.absolute())
        }

    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to create configuration: {str(e)}"
        }


@app.get("/api/mcp/profiles")
async def list_mcp_profiles():
    """List available MCP profiles from .mcp_services.yaml."""
    from testmcpy.mcp_profiles import get_profile_config

    try:
        profile_config = get_profile_config()
        if not profile_config.has_profiles():
            return {
                "profiles": [],
                "default": None,
                "message": "No .mcp_services.yaml file found",
            }

        profiles_list = []
        for profile_id in profile_config.list_profiles():
            profile = profile_config.get_profile(profile_id)
            if not profile:
                continue

            # Build list of MCPs with masked auth tokens
            mcps_info = []
            for mcp_server in profile.mcps:
                auth_info = {
                    "type": mcp_server.auth.auth_type,
                }

                # Bearer token
                if mcp_server.auth.token:
                    token = mcp_server.auth.token
                    if token and not token.startswith("${"):
                        auth_info["token"] = f"{token[:8]}..." if len(token) > 12 else "***"
                    else:
                        auth_info["token"] = token

                # JWT fields
                if mcp_server.auth.api_url:
                    auth_info["api_url"] = mcp_server.auth.api_url

                if mcp_server.auth.api_token:
                    token = mcp_server.auth.api_token
                    if token and not token.startswith("${"):
                        auth_info["api_token"] = f"{token[:8]}..." if len(token) > 12 else "***"
                    else:
                        auth_info["api_token"] = token

                if mcp_server.auth.api_secret:
                    secret = mcp_server.auth.api_secret
                    if secret and not secret.startswith("${"):
                        auth_info["api_secret"] = "***"
                    else:
                        auth_info["api_secret"] = secret

                # OAuth fields
                if mcp_server.auth.client_id:
                    auth_info["client_id"] = mcp_server.auth.client_id

                if mcp_server.auth.client_secret:
                    secret = mcp_server.auth.client_secret
                    if secret and not secret.startswith("${"):
                        auth_info["client_secret"] = "***"
                    else:
                        auth_info["client_secret"] = secret

                if mcp_server.auth.token_url:
                    auth_info["token_url"] = mcp_server.auth.token_url

                if mcp_server.auth.scopes:
                    auth_info["scopes"] = mcp_server.auth.scopes

                mcps_info.append({
                    "name": mcp_server.name,
                    "mcp_url": mcp_server.mcp_url,
                    "auth": auth_info,
                    "timeout": mcp_server.timeout,
                    "rate_limit_rpm": mcp_server.rate_limit_rpm,
                })

            profiles_list.append({
                "id": profile.profile_id,
                "name": profile.name,
                "description": profile.description,
                "mcps": mcps_info,
                "timeout": profile.timeout,
                "rate_limit_rpm": profile.rate_limit_rpm,
                "is_default": profile.is_default,
            })

        # Get the default profile and server selection
        default_selection = profile_config.get_default_profile_and_server()
        default_selection_str = None
        if default_selection:
            profile_id, mcp_name = default_selection
            default_selection_str = f"{profile_id}:{mcp_name}"

        return {
            "profiles": profiles_list,
            "default": profile_config.default_profile,
            "default_selection": default_selection_str,
        }
    except Exception as e:
        return {
            "profiles": [],
            "default": None,
            "error": str(e),
        }


@app.post("/api/mcp/profiles")
async def create_mcp_profile(request: ProfileCreateRequest):
    """Create a new MCP profile."""
    try:
        config_data = load_mcp_yaml()

        # Generate unique profile ID
        existing_ids = list(config_data.get("profiles", {}).keys())
        profile_id = generate_profile_id(request.name, existing_ids)

        # Create new profile
        new_profile = {
            "name": request.name,
            "description": request.description,
            "mcps": []
        }

        # Add to profiles
        if "profiles" not in config_data:
            config_data["profiles"] = {}

        config_data["profiles"][profile_id] = new_profile

        # Set as default if requested
        if request.is_default:
            config_data["default"] = profile_id

        # Save to file
        save_mcp_yaml(config_data)

        return {
            "success": True,
            "profile_id": profile_id,
            "message": f"Profile '{request.name}' created successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create profile: {str(e)}"
        )


@app.put("/api/mcp/profiles/{profile_id}")
async def update_mcp_profile(profile_id: str, request: ProfileUpdateRequest):
    """Update an existing MCP profile."""
    try:
        config_data = load_mcp_yaml()

        if "profiles" not in config_data or profile_id not in config_data["profiles"]:
            raise HTTPException(status_code=404, detail=f"Profile '{profile_id}' not found")

        profile = config_data["profiles"][profile_id]

        # Update fields
        if request.name is not None:
            profile["name"] = request.name

        if request.description is not None:
            profile["description"] = request.description

        if request.is_default is not None and request.is_default:
            config_data["default"] = profile_id

        # Save to file
        save_mcp_yaml(config_data)

        return {
            "success": True,
            "message": f"Profile '{profile_id}' updated successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update profile '{profile_id}': {str(e)}"
        )


@app.delete("/api/mcp/profiles/{profile_id}")
async def delete_mcp_profile(profile_id: str):
    """Delete an MCP profile."""
    try:
        config_data = load_mcp_yaml()

        if "profiles" not in config_data or profile_id not in config_data["profiles"]:
            raise HTTPException(status_code=404, detail=f"Profile '{profile_id}' not found")

        # Remove profile
        del config_data["profiles"][profile_id]

        # If this was the default, clear default or set to first available
        if config_data.get("default") == profile_id:
            remaining_profiles = list(config_data["profiles"].keys())
            config_data["default"] = remaining_profiles[0] if remaining_profiles else None

        # Save to file
        save_mcp_yaml(config_data)

        # Clear any cached clients for this profile
        global mcp_clients
        keys_to_remove = [key for key in mcp_clients.keys() if key.startswith(f"{profile_id}:")]
        for key in keys_to_remove:
            client = mcp_clients.pop(key, None)
            if client:
                try:
                    await client.close()
                except Exception as e:
                    print(f"Warning: Failed to close MCP client '{key}': {e}")

        return {
            "success": True,
            "message": f"Profile '{profile_id}' deleted successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete profile '{profile_id}': {str(e)}"
        )


@app.post("/api/mcp/profiles/{profile_id}/duplicate")
async def duplicate_mcp_profile(profile_id: str):
    """Duplicate an existing MCP profile."""
    try:
        config_data = load_mcp_yaml()

        if "profiles" not in config_data or profile_id not in config_data["profiles"]:
            raise HTTPException(status_code=404, detail=f"Profile '{profile_id}' not found")

        # Get source profile
        source_profile = config_data["profiles"][profile_id]

        # Generate new profile ID
        existing_ids = list(config_data["profiles"].keys())
        new_name = f"{source_profile.get('name', profile_id)} (Copy)"
        new_profile_id = generate_profile_id(new_name, existing_ids)

        # Create duplicate with deep copy
        import copy
        new_profile = copy.deepcopy(source_profile)
        new_profile["name"] = new_name
        new_profile["description"] = source_profile.get("description", "") + " (Copy)"

        # Add to profiles
        config_data["profiles"][new_profile_id] = new_profile

        # Save to file
        save_mcp_yaml(config_data)

        return {
            "success": True,
            "profile_id": new_profile_id,
            "message": f"Profile duplicated as '{new_name}'"
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to duplicate profile '{profile_id}': {str(e)}"
        )


@app.put("/api/mcp/profiles/default/{profile_id}")
async def set_default_profile(profile_id: str):
    """Set a profile as the default."""
    try:
        config_data = load_mcp_yaml()

        if "profiles" not in config_data or profile_id not in config_data["profiles"]:
            raise HTTPException(status_code=404, detail=f"Profile '{profile_id}' not found")

        config_data["default"] = profile_id

        # Save to file
        save_mcp_yaml(config_data)

        return {
            "success": True,
            "message": f"Profile '{profile_id}' set as default"
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to set default profile to '{profile_id}': {str(e)}"
        )


@app.post("/api/mcp/profiles/{profile_id}/mcps")
async def add_mcp_to_profile(profile_id: str, request: MCPCreateRequest):
    """Add an MCP server to a profile."""
    try:
        config_data = load_mcp_yaml()

        if "profiles" not in config_data or profile_id not in config_data["profiles"]:
            raise HTTPException(status_code=404, detail=f"Profile '{profile_id}' not found")

        profile = config_data["profiles"][profile_id]

        # Validate MCP name is unique within profile
        existing_mcps = profile.get("mcps", [])
        if any(mcp.get("name") == request.name for mcp in existing_mcps):
            raise HTTPException(
                status_code=400,
                detail=f"MCP with name '{request.name}' already exists in profile '{profile_id}'"
            )

        # Build auth config
        auth_config = {"type": request.auth_type}

        if request.auth_type == "bearer" and request.token:
            auth_config["token"] = request.token
        elif request.auth_type == "jwt":
            if request.api_url:
                auth_config["api_url"] = request.api_url
            if request.api_token:
                auth_config["api_token"] = request.api_token
            if request.api_secret:
                auth_config["api_secret"] = request.api_secret
        elif request.auth_type == "oauth":
            if request.client_id:
                auth_config["client_id"] = request.client_id
            if request.client_secret:
                auth_config["client_secret"] = request.client_secret
            if request.token_url:
                auth_config["token_url"] = request.token_url
            if request.scopes:
                auth_config["scopes"] = request.scopes

        # Create new MCP
        new_mcp = {
            "name": request.name,
            "mcp_url": request.mcp_url,
            "auth": auth_config
        }

        if request.timeout is not None:
            new_mcp["timeout"] = request.timeout

        if request.rate_limit_rpm is not None:
            new_mcp["rate_limit_rpm"] = request.rate_limit_rpm

        # Add to profile
        if "mcps" not in profile:
            profile["mcps"] = []

        profile["mcps"].append(new_mcp)

        # Save to file
        save_mcp_yaml(config_data)

        return {
            "success": True,
            "message": f"MCP '{request.name}' added to profile '{profile_id}'"
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to add MCP to profile '{profile_id}': {str(e)}"
        )


@app.put("/api/mcp/profiles/{profile_id}/mcps/{mcp_index}")
async def update_mcp_in_profile(profile_id: str, mcp_index: int, request: MCPUpdateRequest):
    """Update an MCP server in a profile."""
    try:
        config_data = load_mcp_yaml()

        if "profiles" not in config_data or profile_id not in config_data["profiles"]:
            raise HTTPException(status_code=404, detail=f"Profile '{profile_id}' not found")

        profile = config_data["profiles"][profile_id]
        mcps = profile.get("mcps", [])

        if mcp_index < 0 or mcp_index >= len(mcps):
            raise HTTPException(status_code=404, detail=f"MCP at index {mcp_index} not found")

        mcp = mcps[mcp_index]
        old_name = mcp.get("name", "")

        # Update fields
        if request.name is not None:
            # Check for name conflicts (excluding current MCP)
            for idx, existing_mcp in enumerate(mcps):
                if idx != mcp_index and existing_mcp.get("name") == request.name:
                    raise HTTPException(
                        status_code=400,
                        detail=f"MCP with name '{request.name}' already exists in profile '{profile_id}'"
                    )
            mcp["name"] = request.name

        if request.mcp_url is not None:
            mcp["mcp_url"] = request.mcp_url

        # Update auth
        if request.auth_type is not None:
            if "auth" not in mcp:
                mcp["auth"] = {}
            mcp["auth"]["type"] = request.auth_type

            # Clear old auth fields and add new ones
            if request.auth_type == "bearer":
                mcp["auth"] = {"type": "bearer"}
                if request.token is not None:
                    mcp["auth"]["token"] = request.token
            elif request.auth_type == "jwt":
                mcp["auth"] = {"type": "jwt"}
                if request.api_url is not None:
                    mcp["auth"]["api_url"] = request.api_url
                if request.api_token is not None:
                    mcp["auth"]["api_token"] = request.api_token
                if request.api_secret is not None:
                    mcp["auth"]["api_secret"] = request.api_secret
            elif request.auth_type == "oauth":
                mcp["auth"] = {"type": "oauth"}
                if request.client_id is not None:
                    mcp["auth"]["client_id"] = request.client_id
                if request.client_secret is not None:
                    mcp["auth"]["client_secret"] = request.client_secret
                if request.token_url is not None:
                    mcp["auth"]["token_url"] = request.token_url
                if request.scopes is not None:
                    mcp["auth"]["scopes"] = request.scopes
            elif request.auth_type == "none":
                mcp["auth"] = {"type": "none"}

        if request.timeout is not None:
            mcp["timeout"] = request.timeout

        if request.rate_limit_rpm is not None:
            mcp["rate_limit_rpm"] = request.rate_limit_rpm

        # Save to file
        save_mcp_yaml(config_data)

        # Clear cached client for this MCP (use both old and new names)
        global mcp_clients
        old_cache_key = f"{profile_id}:{old_name}"
        new_cache_key = f"{profile_id}:{mcp.get('name', '')}"

        for cache_key in [old_cache_key, new_cache_key]:
            client = mcp_clients.pop(cache_key, None)
            if client:
                try:
                    await client.close()
                except Exception as e:
                    print(f"Warning: Failed to close MCP client '{cache_key}': {e}")

        return {
            "success": True,
            "message": f"MCP at index {mcp_index} updated successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update MCP at index {mcp_index} in profile '{profile_id}': {str(e)}"
        )


@app.delete("/api/mcp/profiles/{profile_id}/mcps/{mcp_index}")
async def delete_mcp_from_profile(profile_id: str, mcp_index: int):
    """Delete an MCP server from a profile."""
    try:
        config_data = load_mcp_yaml()

        if "profiles" not in config_data or profile_id not in config_data["profiles"]:
            raise HTTPException(status_code=404, detail=f"Profile '{profile_id}' not found")

        profile = config_data["profiles"][profile_id]
        mcps = profile.get("mcps", [])

        if mcp_index < 0 or mcp_index >= len(mcps):
            raise HTTPException(status_code=404, detail=f"MCP at index {mcp_index} not found")

        # Get MCP name for cache clearing and response
        mcp_name = mcps[mcp_index].get("name", "")

        # Remove MCP
        del mcps[mcp_index]

        # Save to file
        save_mcp_yaml(config_data)

        # Clear cached client for this MCP
        global mcp_clients
        cache_key = f"{profile_id}:{mcp_name}"
        client = mcp_clients.pop(cache_key, None)
        if client:
            try:
                await client.close()
            except Exception as e:
                print(f"Warning: Failed to close MCP client '{cache_key}': {e}")

        return {
            "success": True,
            "message": f"MCP '{mcp_name}' deleted successfully from profile '{profile_id}'"
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete MCP at index {mcp_index} from profile '{profile_id}': {str(e)}"
        )


@app.put("/api/mcp/profiles/{profile_id}/mcps/reorder")
async def reorder_mcps_in_profile(profile_id: str, request: MCPReorderRequest):
    """Reorder MCPs in a profile."""
    try:
        config_data = load_mcp_yaml()

        if "profiles" not in config_data or profile_id not in config_data["profiles"]:
            raise HTTPException(status_code=404, detail=f"Profile '{profile_id}' not found")

        profile = config_data["profiles"][profile_id]
        mcps = profile.get("mcps", [])

        if request.from_index < 0 or request.from_index >= len(mcps):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid from_index: {request.from_index}. Must be between 0 and {len(mcps)-1}"
            )

        if request.to_index < 0 or request.to_index >= len(mcps):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid to_index: {request.to_index}. Must be between 0 and {len(mcps)-1}"
            )

        # Reorder
        mcp = mcps.pop(request.from_index)
        mcps.insert(request.to_index, mcp)

        # Save to file
        save_mcp_yaml(config_data)

        return {
            "success": True,
            "message": f"MCPs reordered successfully in profile '{profile_id}'"
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to reorder MCPs in profile '{profile_id}': {str(e)}"
        )


@app.get("/api/mcp/profiles/{profile_id}/export")
async def export_profile(profile_id: str):
    """Export a profile as YAML."""
    try:
        config_data = load_mcp_yaml()

        if "profiles" not in config_data or profile_id not in config_data["profiles"]:
            raise HTTPException(status_code=404, detail=f"Profile '{profile_id}' not found")

        profile = config_data["profiles"][profile_id]

        # Create export structure
        export_data = {
            "profiles": {
                profile_id: profile
            }
        }

        # Clean and format for export
        cleaned_data = clean_config_for_yaml(export_data)

        yaml_content = yaml.dump(
            cleaned_data,
            default_flow_style=False,
            sort_keys=False,
            indent=2,
            allow_unicode=True,
            width=float('inf')
        )

        return {
            "success": True,
            "yaml": yaml_content,
            "filename": f"{profile_id}.yaml"
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to export profile '{profile_id}': {str(e)}"
        )


@app.post("/api/mcp/profiles/{profile_id}/test-connection/{mcp_index}")
async def test_mcp_connection(profile_id: str, mcp_index: int):
    """Test connection to an MCP server."""
    try:
        config_data = load_mcp_yaml()

        if "profiles" not in config_data or profile_id not in config_data["profiles"]:
            raise HTTPException(status_code=404, detail=f"Profile '{profile_id}' not found")

        profile = config_data["profiles"][profile_id]
        mcps = profile.get("mcps", [])

        if mcp_index < 0 or mcp_index >= len(mcps):
            raise HTTPException(status_code=404, detail=f"MCP at index {mcp_index} not found")

        mcp_config = mcps[mcp_index]

        # Try to connect
        try:
            # Parse auth config and convert to dict format
            auth_data = mcp_config.get("auth", {})
            auth_type = auth_data.get("type", "none")

            auth_dict = None
            if auth_type == "bearer" and auth_data.get("token"):
                auth_dict = {
                    "type": "bearer",
                    "token": auth_data["token"]
                }
            elif auth_type == "jwt":
                auth_dict = {
                    "type": "jwt",
                    "api_url": auth_data.get("api_url"),
                    "api_token": auth_data.get("api_token"),
                    "api_secret": auth_data.get("api_secret"),
                }
            elif auth_type == "oauth":
                auth_dict = {
                    "type": "oauth",
                    "client_id": auth_data.get("client_id"),
                    "client_secret": auth_data.get("client_secret"),
                    "token_url": auth_data.get("token_url"),
                    "scopes": auth_data.get("scopes", []),
                }
            elif auth_type == "none":
                auth_dict = {"type": "none"}

            # Create temporary client with auth
            test_client = MCPClient(mcp_config["mcp_url"], auth=auth_dict)
            await test_client.initialize()

            # Try to list tools as a connection test
            tools = await test_client.list_tools()

            await test_client.close()

            return {
                "success": True,
                "status": "connected",
                "message": f"Successfully connected to {mcp_config['name']}",
                "tool_count": len(tools)
            }

        except Exception as e:
            return {
                "success": False,
                "status": "error",
                "message": f"Connection failed: {str(e)}"
            }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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
    try:
        all_tools = []

        if profiles:
            # Parse server IDs in format "profileId:mcpName"
            for server_id in profiles:
                if ':' in server_id:
                    # New format: specific server selection
                    profile_id, mcp_name = server_id.split(':', 1)
                    client = await get_mcp_client_for_server(profile_id, mcp_name)
                    if client:
                        tools = await client.list_tools()
                        for tool in tools:
                            all_tools.append({
                                "name": tool.name,
                                "description": tool.description,
                                "input_schema": tool.input_schema,
                                "mcp_source": mcp_name,
                            })
                else:
                    # Legacy format: entire profile (load all servers from profile)
                    clients = await get_mcp_clients_for_profile(server_id)
                    for mcp_name, client in clients:
                        tools = await client.list_tools()
                        for tool in tools:
                            all_tools.append({
                                "name": tool.name,
                                "description": tool.description,
                                "input_schema": tool.input_schema,
                                "mcp_source": mcp_name,
                            })

        return all_tools
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/mcp/resources")
async def list_mcp_resources(profiles: list[str] = Query(default=None)):
    """List all MCP resources. Supports optional ?profiles=xxx&profiles=yyy parameters."""
    try:
        all_resources = []

        if profiles:
            # Parse server IDs in format "profileId:mcpName"
            for server_id in profiles:
                if ':' in server_id:
                    # New format: specific server selection
                    profile_id, mcp_name = server_id.split(':', 1)
                    client = await get_mcp_client_for_server(profile_id, mcp_name)
                    if client:
                        resources = await client.list_resources()
                        for resource in resources:
                            if isinstance(resource, dict):
                                resource["mcp_source"] = mcp_name
                            all_resources.append(resource)
                else:
                    # Legacy format: entire profile
                    clients = await get_mcp_clients_for_profile(server_id)
                    for mcp_name, client in clients:
                        resources = await client.list_resources()
                        for resource in resources:
                            if isinstance(resource, dict):
                                resource["mcp_source"] = mcp_name
                            all_resources.append(resource)

        return all_resources
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/mcp/prompts")
async def list_mcp_prompts(profiles: list[str] = Query(default=None)):
    """List all MCP prompts. Supports optional ?profiles=xxx&profiles=yyy parameters."""
    try:
        all_prompts = []

        if profiles:
            # Parse server IDs in format "profileId:mcpName"
            for server_id in profiles:
                if ':' in server_id:
                    # New format: specific server selection
                    profile_id, mcp_name = server_id.split(':', 1)
                    client = await get_mcp_client_for_server(profile_id, mcp_name)
                    if client:
                        prompts = await client.list_prompts()
                        for prompt in prompts:
                            if isinstance(prompt, dict):
                                prompt["mcp_source"] = mcp_name
                            all_prompts.append(prompt)
                else:
                    # Legacy format: entire profile
                    clients = await get_mcp_clients_for_profile(server_id)
                    for mcp_name, client in clients:
                        prompts = await client.list_prompts()
                        for prompt in prompts:
                            if isinstance(prompt, dict):
                                prompt["mcp_source"] = mcp_name
                            all_prompts.append(prompt)

        return all_prompts
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Chat endpoint


@app.post("/api/chat")
async def chat(request: ChatRequest) -> ChatResponse:
    """Send a message to the LLM with MCP tools."""
    model = request.model or config.default_model
    provider = request.provider or config.default_provider

    try:
        # Determine which MCP clients to use
        clients_to_use = []  # List of (profile_id, mcp_name, client) tuples
        if request.profiles:
            # Parse server IDs in format "profileId:mcpName"
            for server_id in request.profiles:
                if ':' in server_id:
                    # New format: specific server selection
                    profile_id, mcp_name = server_id.split(':', 1)
                    client = await get_mcp_client_for_server(profile_id, mcp_name)
                    if client:
                        clients_to_use.append((profile_id, mcp_name, client))
                else:
                    # Legacy format: entire profile (load all servers from profile)
                    profile_clients = await get_mcp_clients_for_profile(server_id)
                    for mcp_name, client in profile_clients:
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
        llm_provider = create_llm_provider(provider, model)
        await llm_provider.initialize()

        # Generate response with optional history
        result = await llm_provider.generate_with_tools(
            prompt=request.message, tools=all_tools, timeout=30.0, messages=request.history
        )

        # Execute tool calls if any
        tool_calls_with_results = []
        if result.tool_calls:
            for tool_call in result.tool_calls:
                mcp_tool_call = MCPToolCall(
                    name=tool_call["name"],
                    arguments=tool_call.get("arguments", {}),
                    id=tool_call.get("id", "unknown"),
                )

                # Find the appropriate client for this tool
                tool_info = tool_to_client.get(tool_call["name"])
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
            token_usage=result.token_usage,
            cost=result.cost,
            duration=result.duration,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Test file management


@app.get("/api/tests")
async def list_tests():
    """List all test files in the tests directory, including subdirectories."""
    tests_dir = Path.cwd() / "tests"
    if not tests_dir.exists():
        return {"folders": {}, "files": []}

    folders = {}  # folder_name -> list of files
    root_files = []  # files in root tests/ directory

    # Recursively search for YAML files
    for file in tests_dir.rglob("*.yaml"):
        try:
            with open(file) as f:
                content = f.read()
                data = yaml.safe_load(content)

                # Count tests
                test_count = len(data.get("tests", [])) if "tests" in data else 1

                # Get relative path from tests dir
                rel_path = file.relative_to(tests_dir)
                folder_name = str(rel_path.parent) if rel_path.parent != Path(".") else None

                file_info = {
                    "filename": file.name,
                    "relative_path": str(rel_path),
                    "path": str(file),
                    "test_count": test_count,
                    "size": file.stat().st_size,
                    "modified": file.stat().st_mtime,
                }

                if folder_name and folder_name != ".":
                    # File is in a subfolder
                    if folder_name not in folders:
                        folders[folder_name] = []
                    folders[folder_name].append(file_info)
                else:
                    # File is in root
                    root_files.append(file_info)

        except Exception as e:
            print(f"Error reading {file}: {e}")

    # Sort files within each folder by modified time
    for folder in folders:
        folders[folder] = sorted(folders[folder], key=lambda x: x["modified"], reverse=True)

    root_files = sorted(root_files, key=lambda x: x["modified"], reverse=True)

    return {"folders": folders, "files": root_files}


@app.get("/api/tests/{filename:path}")
async def get_test_file(filename: str):
    """Get content of a specific test file (supports paths like 'folder/file.yaml')."""
    tests_dir = Path.cwd() / "tests"
    file_path = tests_dir / filename

    if not file_path.exists() or not file_path.is_relative_to(tests_dir):
        raise HTTPException(status_code=404, detail="Test file not found")

    try:
        with open(file_path) as f:
            content = f.read()

        return {"filename": filename, "content": content, "path": str(file_path)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/tests")
async def create_test_file(request: TestFileCreate):
    """Create a new test file."""
    tests_dir = Path.cwd() / "tests"
    tests_dir.mkdir(exist_ok=True)

    file_path = tests_dir / request.filename

    if file_path.exists():
        raise HTTPException(status_code=400, detail="File already exists")

    # Validate YAML
    try:
        yaml.safe_load(request.content)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid YAML: {str(e)}")

    try:
        with open(file_path, "w") as f:
            f.write(request.content)

        return {
            "message": "Test file created successfully",
            "filename": request.filename,
            "path": str(file_path),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/tests/{filename:path}")
async def update_test_file(filename: str, request: TestFileUpdate):
    """Update an existing test file (supports paths like 'folder/file.yaml')."""
    tests_dir = Path.cwd() / "tests"
    file_path = tests_dir / filename

    if not file_path.exists() or not file_path.is_relative_to(tests_dir):
        raise HTTPException(status_code=404, detail="Test file not found")

    # Validate YAML
    try:
        yaml.safe_load(request.content)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid YAML: {str(e)}")

    try:
        with open(file_path, "w") as f:
            f.write(request.content)

        return {
            "message": "Test file updated successfully",
            "filename": filename,
            "path": str(file_path),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/tests/{filename:path}")
async def delete_test_file(filename: str):
    """Delete a test file (supports paths like 'folder/file.yaml')."""
    tests_dir = Path.cwd() / "tests"
    file_path = tests_dir / filename

    if not file_path.exists() or not file_path.is_relative_to(tests_dir):
        raise HTTPException(status_code=404, detail="Test file not found")

    try:
        file_path.unlink()
        return {"message": "Test file deleted successfully", "filename": filename}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Test execution


@app.post("/api/tests/run")
async def run_tests(request: TestRunRequest):
    """Run test cases from a file."""
    test_path = Path(request.test_path)

    if not test_path.exists():
        raise HTTPException(status_code=404, detail="Test file not found")

    model = request.model or config.default_model
    provider = request.provider or config.default_provider

    try:
        # Load test cases
        with open(test_path) as f:
            if test_path.suffix == ".json":
                data = json.load(f)
            else:
                data = yaml.safe_load(f)

        test_cases = []
        if "tests" in data:
            for test_data in data["tests"]:
                test_cases.append(TestCase.from_dict(test_data))
        else:
            test_cases.append(TestCase.from_dict(data))

        # Run tests
        runner = TestRunner(
            model=model,
            provider=provider,
            mcp_url=config.mcp_url,
            verbose=False,
            hide_tool_output=True,
        )

        results = await runner.run_tests(test_cases)

        # Format results
        return {
            "summary": {
                "total": len(results),
                "passed": sum(1 for r in results if r.passed),
                "failed": sum(1 for r in results if not r.passed),
                "total_cost": sum(r.cost for r in results),
                "total_tokens": sum(
                    r.token_usage.get("total", 0) for r in results if r.token_usage
                ),
            },
            "results": [r.to_dict() for r in results],
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/tests/run-tool/{tool_name}")
async def run_tool_tests(tool_name: str, model: str | None = None, provider: str | None = None):
    """Run all tests for a specific tool."""
    # Sanitize tool name for folder lookup
    safe_tool_name = "".join(c if c.isalnum() or c in ('_', '-') else '_' for c in tool_name)

    tests_dir = Path.cwd() / "tests" / safe_tool_name

    if not tests_dir.exists() or not tests_dir.is_dir():
        raise HTTPException(
            status_code=404,
            detail=f"No test directory found for tool '{tool_name}' (looked for: {tests_dir})"
        )

    # Find all YAML test files in the tool directory
    test_files = list(tests_dir.glob("*.yaml"))

    if not test_files:
        raise HTTPException(
            status_code=404,
            detail=f"No test files found in directory: {tests_dir}"
        )

    model = model or config.default_model
    provider = provider or config.default_provider

    try:
        all_results = []
        total_summary = {
            "total": 0,
            "passed": 0,
            "failed": 0,
            "total_cost": 0.0,
            "total_tokens": 0,
        }

        # Run each test file
        for test_file in test_files:
            with open(test_file) as f:
                data = yaml.safe_load(f)

            test_cases = []
            if "tests" in data:
                for test_data in data["tests"]:
                    test_cases.append(TestCase.from_dict(test_data))
            else:
                test_cases.append(TestCase.from_dict(data))

            # Run tests
            runner = TestRunner(
                model=model,
                provider=provider,
                mcp_url=config.mcp_url,
                verbose=False,
                hide_tool_output=True,
            )

            results = await runner.run_tests(test_cases)

            # Aggregate results
            all_results.extend(results)
            total_summary["total"] += len(results)
            total_summary["passed"] += sum(1 for r in results if r.passed)
            total_summary["failed"] += sum(1 for r in results if not r.passed)
            total_summary["total_cost"] += sum(r.cost for r in results)
            total_summary["total_tokens"] += sum(
                r.token_usage.get("total", 0) for r in results if r.token_usage
            )

        return {
            "summary": total_summary,
            "results": [r.to_dict() for r in all_results],
            "files_tested": [str(f.name) for f in test_files],
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Eval endpoints


@app.post("/api/eval/run")
async def run_eval(request: EvalRunRequest):
    """Run evaluators on a prompt/response pair from chat."""
    try:
        # Extract tool results from tool_calls (chat embeds results in tool_calls)
        from testmcpy.src.mcp_client import MCPToolResult

        print(f"[EVAL DEBUG] Received tool_calls: {request.tool_calls}")

        tool_results = []
        for tool_call in request.tool_calls:
            print(f"[EVAL DEBUG] Processing tool_call: {tool_call.get('name')}")
            print(f"[EVAL DEBUG] - has 'result' key: {'result' in tool_call}")
            print(f"[EVAL DEBUG] - result value: {tool_call.get('result')}")
            print(f"[EVAL DEBUG] - is_error: {tool_call.get('is_error', False)}")

            # Create MCPToolResult from embedded result data
            tool_results.append(
                MCPToolResult(
                    tool_call_id=tool_call.get("id", "unknown"),
                    content=tool_call.get("result"),
                    is_error=tool_call.get("is_error", False),
                    error_message=tool_call.get("error"),
                )
            )

        print(f"[EVAL DEBUG] Created {len(tool_results)} tool_results")

        # Create a context for evaluators
        context = {
            "prompt": request.prompt,
            "response": request.response,
            "tool_calls": request.tool_calls,
            "tool_results": tool_results,
            "metadata": {
                "model": request.model or config.default_model,
                "provider": request.provider or config.default_provider,
            },
        }

        # Build evaluators based on actual tool calls
        default_evaluators = [
            {"name": "execution_successful"},
        ]

        # If tool calls were made, add specific tool validation
        if request.tool_calls and len(request.tool_calls) > 0:
            first_tool = request.tool_calls[0]

            # Check specific tool was called
            default_evaluators.append(
                {"name": "was_mcp_tool_called", "args": {"tool_name": first_tool.get("name")}}
            )

            # Check tool call count
            default_evaluators.append(
                {"name": "tool_call_count", "args": {"expected_count": len(request.tool_calls)}}
            )

            # Validate parameters if present
            if first_tool.get("arguments") and len(first_tool.get("arguments")) > 0:
                default_evaluators.append(
                    {
                        "name": "tool_called_with_parameters",
                        "args": {
                            "tool_name": first_tool.get("name"),
                            "parameters": first_tool.get("arguments"),
                            "partial_match": True,
                        },
                    }
                )
        else:
            # No tools called - just check if any tool was called
            default_evaluators.append({"name": "was_mcp_tool_called"})

        # Run evaluators
        evaluations = []
        all_passed = True
        total_score = 0.0

        for eval_config in default_evaluators:
            try:
                evaluator = create_evaluator(eval_config["name"], **eval_config.get("args", {}))
                eval_result = evaluator.evaluate(context)

                evaluations.append(
                    {
                        "evaluator": evaluator.name,
                        "passed": eval_result.passed,
                        "score": eval_result.score,
                        "reason": eval_result.reason,
                        "details": eval_result.details,
                    }
                )

                if not eval_result.passed:
                    all_passed = False
                total_score += eval_result.score
            except Exception as e:
                # If evaluator fails, mark it as failed but continue
                evaluations.append(
                    {
                        "evaluator": eval_config["name"],
                        "passed": False,
                        "score": 0.0,
                        "reason": f"Evaluator error: {str(e)}",
                        "details": None,
                    }
                )
                all_passed = False

        avg_score = total_score / len(default_evaluators) if default_evaluators else 0.0

        return {
            "passed": all_passed,
            "score": avg_score,
            "reason": "All evaluators passed" if all_passed else "Some evaluators failed",
            "evaluations": evaluations,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Test generation endpoint


@app.post("/api/tests/generate")
async def generate_tests(request: GenerateTestsRequest):
    """Generate tests for an MCP tool using LLM."""
    model = request.model or config.default_model
    provider = request.provider or config.default_provider

    try:
        # Initialize LLM provider
        llm_provider = create_llm_provider(provider, model)
        await llm_provider.initialize()

        # Step 1: Analyze tool and suggest strategies
        analysis_prompt = f"""You are a test engineer analyzing an MCP tool to suggest test strategies.

Tool Name: {request.tool_name}
Description: {request.tool_description}
Schema: {json.dumps(request.tool_schema, indent=2)}

Analyze this tool and suggest:
1. What are the key scenarios to test? (e.g., valid inputs, edge cases, error conditions)
2. What parameters should be varied in tests?
3. What are potential failure modes?
4. What outputs should be validated?

Respond with a structured analysis in JSON format:
{{
  "test_scenarios": [
    {{"name": "scenario name", "description": "what to test", "priority": "high|medium|low"}}
  ],
  "key_parameters": ["param1", "param2"],
  "edge_cases": ["edge case 1", "edge case 2"],
  "validation_points": ["what to check in output"]
}}"""

        analysis_result = await llm_provider.generate_with_tools(
            prompt=analysis_prompt, tools=[], timeout=30.0
        )

        # Parse the analysis
        try:
            # Extract JSON from response
            analysis_text = analysis_result.response
            # Try to find JSON in the response
            json_match = re.search(r"\{[\s\S]*\}", analysis_text)
            if json_match:
                analysis = json.loads(json_match.group())
            else:
                # Fallback to basic structure
                analysis = {
                    "test_scenarios": [
                        {
                            "name": "Basic functionality",
                            "description": "Test basic tool execution",
                            "priority": "high",
                        }
                    ],
                    "key_parameters": [],
                    "edge_cases": [],
                    "validation_points": ["Tool executes successfully"],
                }
        except Exception as e:
            print(f"Failed to parse analysis: {e}")
            analysis = {
                "test_scenarios": [
                    {
                        "name": "Basic functionality",
                        "description": "Test basic tool execution",
                        "priority": "high",
                    }
                ],
                "key_parameters": [],
                "edge_cases": [],
                "validation_points": ["Tool executes successfully"],
            }

        # Step 2: Generate tests based on coverage level
        coverage_config = {
            "basic": {"count": 2, "include_edge_cases": False, "include_errors": False},
            "mid": {"count": 5, "include_edge_cases": True, "include_errors": True},
            "comprehensive": {"count": 12, "include_edge_cases": True, "include_errors": True},
        }

        config_for_level = coverage_config.get(
            request.coverage_level, coverage_config["basic"]
        )

        # Build the test generation prompt
        test_gen_prompt = f"""You are generating test cases for an MCP tool. Generate {config_for_level['count']} test cases in YAML format.

Tool Name: {request.tool_name}
Description: {request.tool_description}
Schema: {json.dumps(request.tool_schema, indent=2)}

Analysis: {json.dumps(analysis, indent=2)}

{"Include edge cases and error scenarios." if config_for_level['include_edge_cases'] else "Focus on common use cases."}
{f"Custom Instructions: {request.custom_instructions}" if request.custom_instructions else ""}

Generate tests in this YAML format:
```yaml
version: "1.0"
tests:
  - name: test_basic_usage
    prompt: "A natural language prompt that would trigger this tool"
    evaluators:
      - name: execution_successful
      - name: was_mcp_tool_called
        args:
          tool_name: "{request.tool_name}"
      - name: tool_called_with_parameters
        args:
          tool_name: "{request.tool_name}"
          parameters:
            param1: "expected_value"
          partial_match: true
```

Important:
1. Each test should have a descriptive name (e.g., test_search_by_id, test_invalid_input)
2. The prompt should be natural language that would make the LLM call this tool
3. Include appropriate evaluators for each test
4. For parameter validation, only include the most important parameters
5. Make prompts realistic and varied

Generate {config_for_level['count']} tests now in YAML format:"""

        test_gen_result = await llm_provider.generate_with_tools(
            prompt=test_gen_prompt, tools=[], timeout=60.0
        )

        # Extract YAML from response
        yaml_content = test_gen_result.response

        # Try to extract YAML from code blocks
        yaml_match = re.search(r"```(?:yaml)?\n([\s\S]*?)\n```", yaml_content)
        if yaml_match:
            yaml_content = yaml_match.group(1)

        # Validate YAML
        try:
            yaml.safe_load(yaml_content)
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=f"Generated invalid YAML: {str(e)}\n\nGenerated content:\n{yaml_content}"
            )

        # Generate filename and folder structure
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        # Sanitize tool name for folder name (remove special chars)
        safe_tool_name = "".join(c if c.isalnum() or c in ('_', '-') else '_' for c in request.tool_name)

        # Create folder structure: tests/<tool_name>/
        tests_dir = Path.cwd() / "tests"
        tool_dir = tests_dir / safe_tool_name
        tool_dir.mkdir(parents=True, exist_ok=True)

        filename = f"{request.coverage_level}_{timestamp}.yaml"
        file_path = tool_dir / filename
        relative_path = f"{safe_tool_name}/{filename}"

        with open(file_path, "w") as f:
            f.write(yaml_content)

        await llm_provider.close()

        return {
            "success": True,
            "filename": relative_path,
            "path": str(file_path),
            "analysis": analysis,
            "test_count": len(yaml.safe_load(yaml_content).get("tests", [])),
            "cost": test_gen_result.cost + analysis_result.cost,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/format")
async def format_schema(request: FormatSchemaRequest):
    """Convert a JSON schema to various formats including client code examples."""
    try:
        from testmcpy.formatters import FORMATS

        format_config = FORMATS.get(request.format)
        if not format_config:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported format: {request.format}. Available formats: {list(FORMATS.keys())}",
            )

        converter = format_config["convert"]

        # For curl and client formats, pass mcp_url and auth_token
        client_formats = ["curl", "python_client", "javascript_client", "typescript_client"]
        if request.format in client_formats:
            # Use provided values or fall back to config
            mcp_url = request.mcp_url or config.mcp_url
            auth_token = request.auth_token or config.mcp_auth_token

            formatted = converter(
                request.schema,
                request.tool_name,
                mcp_url=mcp_url,
                auth_token=auth_token
            )
        else:
            formatted = converter(request.schema, request.tool_name)

        return {
            "success": True,
            "format": request.format,
            "code": formatted,
            "language": format_config["language"],
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/mcp/optimize-docs")
async def optimize_tool_docs(request: OptimizeDocsRequest) -> OptimizeDocsResponse:
    """
    Analyze tool documentation and suggest improvements.

    Uses an LLM to evaluate tool documentation against best practices
    for LLM tool calling and provides actionable suggestions.
    """
    model = request.model or config.default_model
    provider = request.provider or config.default_provider

    if not model or not provider:
        raise HTTPException(
            status_code=400,
            detail="Model and provider must be configured. Set DEFAULT_MODEL and DEFAULT_PROVIDER in config."
        )

    try:
        # Initialize LLM provider (use Haiku for cost efficiency)
        llm_model = model
        if provider == "anthropic" and "haiku" not in model.lower():
            # Use Haiku for analysis to save costs
            llm_model = "claude-haiku-4-5"

        llm_provider = create_llm_provider(provider, llm_model)
        await llm_provider.initialize()

        # Format the input schema for better readability
        schema_str = json.dumps(request.input_schema, indent=2)

        # Build the analysis prompt with structured output
        analysis_prompt = f"""You are an expert at writing tool documentation for LLMs (Large Language Models) that use function/tool calling.

Your task: Analyze this MCP (Model Context Protocol) tool and suggest improvements to help LLMs call it correctly.

TOOL INFORMATION:
==================
Tool Name: {request.tool_name}

Current Description:
{request.description}

Input Schema:
{schema_str}

ANALYSIS FRAMEWORK:
===================
Evaluate the documentation against these criteria:

1. CLARITY (0-100): Is it immediately obvious what this tool does?
   - Does the first sentence clearly state the tool's purpose?
   - Would an LLM understand the exact action this tool performs?
   - Are technical terms explained or self-evident?

2. COMPLETENESS (0-100): Are all parameters well-documented?
   - Is each parameter's purpose clear from the schema?
   - Are types, constraints, and valid values specified?
   - Are required vs optional parameters obvious?

3. ACTIONABILITY (0-100): Would an LLM know when to use this?
   - Is it clear what scenarios this tool is appropriate for?
   - Are there indicators of when NOT to use this tool?
   - Are related/alternative tools mentioned?

4. EXAMPLES (0-100): Are there concrete usage examples?
   - Are there example parameter values?
   - Are there example use cases or scenarios?
   - Would an LLM be able to construct a valid call from the docs?

5. CONSTRAINTS (0-100): Are limitations clearly stated?
   - Are there any prerequisites mentioned?
   - Are error conditions described?
   - Are rate limits, size limits, or other constraints noted?

COMMON ISSUES TO DETECT:
========================
- Vague verbs: "manages", "handles", "processes" → be specific: "creates", "updates", "deletes"
- Missing context: no explanation of when to use vs alternatives
- Parameter confusion: unclear names without descriptions
- Type ambiguity: parameters without clear type/format info
- No examples: abstract descriptions without concrete usage
- Jargon overload: technical terms without explanation
- Ambiguous language: multiple possible interpretations
- Hidden constraints: undocumented limitations or requirements

YOUR TASK:
==========
Provide a detailed analysis in valid JSON format. Return ONLY the JSON object, no markdown formatting, no code blocks.

{{
  "clarity_score": <number 0-100 representing overall quality>,
  "issues": [
    {{
      "category": "<one of: clarity, completeness, actionability, examples, constraints>",
      "severity": "<one of: high, medium, low>",
      "issue": "<specific description of what's wrong>",
      "current": "<the problematic text from current docs>",
      "suggestion": "<actionable advice on how to fix>"
    }}
  ],
  "improved_description": "<Complete rewritten description that includes: (1) Clear statement of what tool does, (2) When to use it, (3) Brief parameter overview, (4) Key constraints. Should be 3-5 sentences, written specifically for LLM consumption.>",
  "improvements": [
    {{
      "issue": "<brief issue name>",
      "before": "<current problematic text>",
      "after": "<improved replacement text>",
      "explanation": "<why this improvement helps LLMs>"
    }}
  ]
}}

IMPORTANT: Return ONLY valid JSON. Do not wrap in markdown code blocks. Start with {{ and end with }}."""

        # Generate analysis - use a mock "tool" to get structured JSON output
        # This works better than asking for raw JSON in many LLMs
        analysis_tool = {
            "name": "submit_analysis",
            "description": "Submit the documentation analysis results",
            "input_schema": {
                "type": "object",
                "properties": {
                    "clarity_score": {
                        "type": "number",
                        "description": "Overall documentation quality score from 0-100"
                    },
                    "issues": {
                        "type": "array",
                        "description": "List of issues found in the documentation",
                        "items": {
                            "type": "object",
                            "properties": {
                                "category": {
                                    "type": "string",
                                    "enum": ["clarity", "completeness", "actionability", "examples", "constraints"],
                                    "description": "Issue category"
                                },
                                "severity": {
                                    "type": "string",
                                    "enum": ["high", "medium", "low"],
                                    "description": "Issue severity"
                                },
                                "issue": {
                                    "type": "string",
                                    "description": "Description of the issue"
                                },
                                "current": {
                                    "type": "string",
                                    "description": "The problematic text from current docs"
                                },
                                "suggestion": {
                                    "type": "string",
                                    "description": "How to fix this issue"
                                }
                            },
                            "required": ["category", "severity", "issue", "suggestion"]
                        }
                    },
                    "improved_description": {
                        "type": "string",
                        "description": "Complete rewritten description that addresses all issues"
                    },
                    "improvements": {
                        "type": "array",
                        "description": "Specific before/after improvements",
                        "items": {
                            "type": "object",
                            "properties": {
                                "issue": {
                                    "type": "string",
                                    "description": "Brief issue name"
                                },
                                "before": {
                                    "type": "string",
                                    "description": "Current problematic text"
                                },
                                "after": {
                                    "type": "string",
                                    "description": "Improved replacement text"
                                },
                                "explanation": {
                                    "type": "string",
                                    "description": "Why this improvement helps LLMs"
                                }
                            },
                            "required": ["issue", "before", "after", "explanation"]
                        }
                    }
                },
                "required": ["clarity_score", "issues", "improved_description", "improvements"]
            }
        }

        # Update prompt to request tool use
        analysis_prompt = f"""You are an expert at writing tool documentation for LLMs (Large Language Models) that use function/tool calling.

Your task: Analyze this MCP (Model Context Protocol) tool and suggest improvements to help LLMs call it correctly.

TOOL INFORMATION:
==================
Tool Name: {request.tool_name}

Current Description:
{request.description}

Input Schema:
{schema_str}

ANALYSIS FRAMEWORK:
===================
Evaluate the documentation against these criteria:

1. CLARITY (0-100): Is it immediately obvious what this tool does?
   - Does the first sentence clearly state the tool's purpose?
   - Would an LLM understand the exact action this tool performs?
   - Are technical terms explained or self-evident?

2. COMPLETENESS (0-100): Are all parameters well-documented?
   - Is each parameter's purpose clear from the schema?
   - Are types, constraints, and valid values specified?
   - Are required vs optional parameters obvious?

3. ACTIONABILITY (0-100): Would an LLM know when to use this?
   - Is it clear what scenarios this tool is appropriate for?
   - Are there indicators of when NOT to use this tool?
   - Are related/alternative tools mentioned?

4. EXAMPLES (0-100): Are there concrete usage examples?
   - Are there example parameter values?
   - Are there example use cases or scenarios?
   - Would an LLM be able to construct a valid call from the docs?

5. CONSTRAINTS (0-100): Are limitations clearly stated?
   - Are there any prerequisites mentioned?
   - Are error conditions described?
   - Are rate limits, size limits, or other constraints noted?

COMMON ISSUES TO DETECT:
========================
- Vague verbs: "manages", "handles", "processes" → be specific: "creates", "updates", "deletes"
- Missing context: no explanation of when to use vs alternatives
- Parameter confusion: unclear names without descriptions
- Type ambiguity: parameters without clear type/format info
- No examples: abstract descriptions without concrete usage
- Jargon overload: technical terms without explanation
- Ambiguous language: multiple possible interpretations
- Hidden constraints: undocumented limitations or requirements

YOUR TASK:
==========
You MUST call the 'submit_analysis' tool with ALL required fields. Do not omit any fields.

REQUIRED FIELDS (all must be provided):

1. clarity_score (number): Overall quality score 0-100

2. issues (array): List of specific problems - MUST include at least 2-3 issues even if docs seem good
   Each issue MUST have: category, severity, issue, current, suggestion
   Example issues to always look for:
   - Missing concrete parameter examples
   - Unclear when to use this vs alternatives
   - Technical jargon without explanation
   - Missing error conditions or constraints
   - Vague verbs like "manages", "handles", "processes"

3. improved_description (string): Complete 3-5 sentence rewrite that includes:
   - Clear statement of what tool does (1 sentence, use specific verbs not "manages/handles")
   - When to use it and key scenarios (1-2 sentences)
   - Brief parameter overview mentioning key parameters by name (1 sentence)
   - Key constraints or limitations (1 sentence)

4. improvements (array): At least 2-3 specific before/after examples
   Each improvement MUST have: issue, before, after, explanation

CRITICAL INSTRUCTIONS:
- You MUST provide ALL four fields with complete data
- Do NOT provide only clarity_score - this will fail validation
- Even if documentation seems good, find at least 2-3 ways to improve it for LLM consumption
- Be critical and thorough - no documentation is perfect

Call the submit_analysis tool NOW with complete data."""

        result = await llm_provider.generate_with_tools(
            prompt=analysis_prompt,
            tools=[analysis_tool],
            timeout=60.0
        )

        # Parse the response - check if LLM used the tool
        try:
            analysis_data = None

            # Debug logging
            print(f"\n=== LLM Response Debug ===")
            print(f"Tool calls count: {len(result.tool_calls) if result.tool_calls else 0}")
            print(f"Response text length: {len(result.response)}")
            print(f"Response preview: {result.response[:200]}")

            # First, check if the LLM made a tool call
            if result.tool_calls and len(result.tool_calls) > 0:
                # LLM used the submit_analysis tool - perfect!
                print(f"Tool calls: {result.tool_calls}")
                tool_call = result.tool_calls[0]
                print(f"Tool call name: {tool_call.get('name')}")
                print(f"Tool call keys: {list(tool_call.keys())}")

                if tool_call.get("name") == "submit_analysis":
                    # Anthropic uses "arguments" key, some providers use "input"
                    analysis_data = tool_call.get("arguments") or tool_call.get("input", {})
                    print(f"✓ LLM used tool call for structured output")
                    print(f"  Arguments keys: {list(analysis_data.keys())}")
                    print(f"  Score: {analysis_data.get('clarity_score')}")
                    print(f"  Issues found: {len(analysis_data.get('issues', []))}")

                    # Validate that LLM provided all required fields
                    missing_fields = []
                    if not analysis_data.get('clarity_score'):
                        missing_fields.append('clarity_score')
                    if not analysis_data.get('issues') or len(analysis_data.get('issues', [])) == 0:
                        missing_fields.append('issues (must have at least 1 issue)')
                    if not analysis_data.get('improved_description'):
                        missing_fields.append('improved_description')
                    if not analysis_data.get('improvements') or len(analysis_data.get('improvements', [])) == 0:
                        missing_fields.append('improvements (must have at least 1 improvement)')

                    if missing_fields:
                        error_msg = f"LLM provided incomplete data. Missing required fields: {', '.join(missing_fields)}"
                        print(f"✗ {error_msg}")
                        raise ValueError(error_msg)
                else:
                    print(f"✗ Unexpected tool call: {tool_call.get('name')}")

            # If no tool call, try to parse JSON from response text
            if not analysis_data:
                print("No tool call found, attempting to parse JSON from response text")
                response_text = result.response.strip()

                # Remove any markdown code blocks
                response_text = re.sub(r'```(?:json)?\s*', '', response_text)
                response_text = re.sub(r'```\s*$', '', response_text)

                # Try to find JSON object (handle nested braces properly)
                start_idx = response_text.find('{')
                if start_idx == -1:
                    raise ValueError("No JSON object found in response")

                # Count braces to find matching closing brace
                brace_count = 0
                end_idx = -1
                for i in range(start_idx, len(response_text)):
                    if response_text[i] == '{':
                        brace_count += 1
                    elif response_text[i] == '}':
                        brace_count -= 1
                        if brace_count == 0:
                            end_idx = i + 1
                            break

                if end_idx == -1:
                    raise ValueError("Unmatched braces in JSON response")

                json_str = response_text[start_idx:end_idx]
                analysis_data = json.loads(json_str)

            # Validate and fix required fields
            if "clarity_score" not in analysis_data or not isinstance(analysis_data["clarity_score"], (int, float)):
                print("Warning: Missing or invalid clarity_score, using default 50")
                analysis_data["clarity_score"] = 50
            if "issues" not in analysis_data or not isinstance(analysis_data["issues"], list):
                print("Warning: Missing or invalid issues array")
                analysis_data["issues"] = []
            if "improved_description" not in analysis_data or not analysis_data["improved_description"]:
                print("Warning: Missing improved_description, using original")
                analysis_data["improved_description"] = request.description
            if "improvements" not in analysis_data or not isinstance(analysis_data["improvements"], list):
                print("Warning: Missing improvements array")
                analysis_data["improvements"] = []

            # Ensure each issue has required fields
            for issue in analysis_data["issues"]:
                if "category" not in issue:
                    issue["category"] = "clarity"
                if "severity" not in issue:
                    issue["severity"] = "medium"
                if "issue" not in issue:
                    issue["issue"] = "Documentation issue"
                if "current" not in issue:
                    issue["current"] = ""
                if "suggestion" not in issue:
                    issue["suggestion"] = ""

        except Exception as e:
            # Fallback to basic response if parsing fails
            print(f"✗ Failed to parse LLM response: {e}")
            print(f"Response text (first 500 chars): {result.response[:500]}")
            print(f"Tool calls: {result.tool_calls}")
            analysis_data = {
                "clarity_score": 50,
                "issues": [{
                    "category": "clarity",
                    "severity": "high",
                    "issue": "LLM response parsing failed - check server logs for details",
                    "current": request.description,
                    "suggestion": f"Error: {str(e)}"
                }],
                "improved_description": request.description,
                "improvements": []
            }

        await llm_provider.close()

        # Build response
        return OptimizeDocsResponse(
            analysis={
                "score": analysis_data.get("clarity_score", 50),
                "clarity": "good" if analysis_data.get("clarity_score", 50) >= 75 else ("fair" if analysis_data.get("clarity_score", 50) >= 50 else "poor"),
                "issues": analysis_data.get("issues", [])
            },
            suggestions={
                "improved_description": analysis_data.get("improved_description", request.description),
                "improvements": analysis_data.get("improvements", [])
            },
            original={
                "tool_name": request.tool_name,
                "description": request.description,
                "input_schema": request.input_schema
            },
            cost=result.cost,
            duration=result.duration
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to optimize documentation: {str(e)}")


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
