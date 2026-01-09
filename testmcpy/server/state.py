"""
Global state and helper functions for the testmcpy API.
"""

import copy
from pathlib import Path
from typing import Any

import yaml
from fastapi import HTTPException, WebSocket

from testmcpy.auth_flow_recorder import AuthFlowRecorder
from testmcpy.config import get_config
from testmcpy.mcp_profiles import load_profile, reload_profile_config
from testmcpy.src.mcp_client import MCPClient


# Centralized timeout configuration
class TimeoutConfig:
    """Centralized timeout values for the application."""

    DEFAULT_HTTP = 30.0  # Default HTTP request timeout
    MCP_CONNECT = 10.0  # MCP connection timeout
    MCP_TOOL_CALL = 60.0  # Tool execution timeout
    LLM_REQUEST = 120.0  # LLM API request timeout
    AUTH_DEBUG = 30.0  # Auth debugging timeout
    SMOKE_TEST = 60.0  # Smoke test timeout


# Global state
config = get_config()
mcp_client: MCPClient | None = None  # Default MCP client (for backwards compat)
mcp_clients: dict[str, MCPClient] = {}  # Cache of MCP clients by "{profile_id}:{mcp_name}"
active_websockets: list[WebSocket] = []
auth_flow_recorder = AuthFlowRecorder()  # Global auth flow recorder instance


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
        raise HTTPException(status_code=500, detail=f"Failed to parse YAML configuration: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load configuration file: {str(e)}")


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
                    raise ValueError(f"MCP #{idx} in profile '{profile_id}' must be a dictionary")

                # Check required MCP fields
                if "name" not in mcp:
                    raise ValueError(f"MCP #{idx} in profile '{profile_id}' missing 'name' field")

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
                if auth_type not in ("bearer", "jwt", "oauth", "none"):
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
    backup_path = config_path.with_suffix(".yaml.backup")
    temp_path = config_path.with_suffix(".yaml.tmp")

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
            with open(temp_path, "w", encoding="utf-8") as f:
                yaml.dump(
                    cleaned_config,
                    f,
                    default_flow_style=False,
                    sort_keys=False,
                    indent=2,
                    allow_unicode=True,
                    width=float("inf"),  # Prevent line wrapping
                )
        except Exception as e:
            # Clean up temp file if write failed
            if temp_path.exists():
                temp_path.unlink()
            raise ValueError(f"Failed to write YAML: {str(e)}")

        # Step 5: Validate the written YAML can be read back
        try:
            with open(temp_path, encoding="utf-8") as f:
                yaml.safe_load(f)
        except Exception as e:
            # Clean up invalid temp file
            if temp_path.exists():
                temp_path.unlink()
            raise ValueError(f"Generated invalid YAML: {str(e)}")

        # Step 6: Atomic rename (replaces original file)
        temp_path.replace(config_path)

        # Step 7: Reload profile config to pick up changes
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

        raise HTTPException(status_code=500, detail=f"Failed to save configuration: {str(e)}")

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
    base_id = name.lower().replace(" ", "-").replace("_", "-")
    # Remove non-alphanumeric characters except hyphens
    base_id = "".join(c for c in base_id if c.isalnum() or c == "-")

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
    auth_dict = mcp_server.auth.to_dict()
    client = MCPClient(mcp_server.mcp_url, auth=auth_dict)
    await client.initialize()

    # Cache the client
    mcp_clients[cache_key] = client
    print(f"MCP client initialized for '{profile_id}:{mcp_server.name}' at {mcp_server.mcp_url}")

    return client


async def get_or_create_mcp_client(profile_selection: str) -> MCPClient | None:
    """
    Get or create MCP client for the selected profile.

    Args:
        profile_selection: Either "profile_id" or "profile_id:mcp_name" format

    Returns:
        MCPClient instance or None if not found
    """
    if ":" in profile_selection:
        profile_id, mcp_name = profile_selection.split(":", 1)
        return await get_mcp_client_for_server(profile_id, mcp_name)
    else:
        clients = await get_mcp_clients_for_profile(profile_selection)
        return clients[0][1] if clients else None


def get_mcp_clients() -> dict[str, MCPClient]:
    """Get the MCP clients dictionary."""
    return mcp_clients


def get_default_mcp_client() -> MCPClient | None:
    """Get the default MCP client."""
    return mcp_client


async def close_all_clients():
    """Close all MCP clients (for shutdown)."""
    global mcp_client, mcp_clients

    if mcp_client:
        await mcp_client.close()

    for cache_key, client in mcp_clients.items():
        try:
            await client.close()
            print(f"Closed MCP client '{cache_key}'")
        except Exception as e:
            print(f"Error closing client '{cache_key}': {e}")
