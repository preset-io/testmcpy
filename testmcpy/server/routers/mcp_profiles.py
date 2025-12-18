"""MCP profile management endpoints."""

import copy
import re
from pathlib import Path

import yaml
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from testmcpy.server.helpers import (
    clean_config_for_yaml,
    generate_profile_id,
    load_mcp_yaml,
    save_mcp_yaml,
)
from testmcpy.src.mcp_client import MCPClient

router = APIRouter(prefix="/api/mcp", tags=["mcp-profiles"])


# Pydantic models for MCP profile requests
class AuthType:
    NONE = "none"
    BEARER = "bearer"
    JWT = "jwt"
    OAUTH = "oauth"


class AuthConfig(BaseModel):
    type: str
    token: str | None = None
    api_url: str | None = None
    api_token: str | None = None
    api_secret: str | None = None
    client_id: str | None = None
    client_secret: str | None = None
    token_url: str | None = None
    scopes: list[str] | None = None
    insecure: bool = False
    oauth_auto_discover: bool = False


class ProfileCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str = Field(default="", max_length=1000)
    set_as_default: bool = False

    @field_validator("name")
    @classmethod
    def validate_name(cls, v):
        if not re.match(r"^[a-zA-Z0-9_-]+$", v):
            raise ValueError(
                "Profile name must contain only alphanumeric characters, hyphens, and underscores"
            )
        if ".." in v or "/" in v or "\\" in v:
            raise ValueError("Profile name cannot contain path traversal characters")
        if "\x00" in v:
            raise ValueError("Profile name cannot contain null bytes")
        return v


class ProfileUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    set_as_default: bool | None = None


class MCPCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    mcp_url: str
    auth: AuthConfig
    timeout: int | None = None
    rate_limit_rpm: int | None = None


class MCPUpdateRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    mcp_url: str | None = None
    auth: AuthConfig | None = None
    timeout: int | None = None
    rate_limit_rpm: int | None = None


class MCPReorderRequest(BaseModel):
    from_index: int
    to_index: int


# Helper to get the mcp_clients dict from api module
def get_mcp_clients() -> dict[str, MCPClient]:
    """Get the global mcp_clients dict from api module."""
    from testmcpy.server import api

    return api.mcp_clients


@router.post("/profiles/create-config")
async def create_mcp_config():
    """Create .mcp_services.yaml with a default template."""
    try:
        config_file = Path.cwd() / ".mcp_services.yaml"

        if config_file.exists():
            return {
                "success": False,
                "error": "Configuration file already exists at .mcp_services.yaml",
            }

        # Default template
        default_template = """# MCP Services Configuration
# Documentation: https://github.com/preset-io/testmcpy

# Default profile to use when none specified
default: my-profile

# Profile definitions
profiles:
  my-profile:
    # Display name for the profile
    name: My MCP Server
    description: My MCP server configuration

    # MCP servers in this profile (list format with -)
    mcps:
      - name: My Server
        # URL of the MCP server
        mcp_url: http://localhost:3000/mcp

        # Authentication (optional)
        # auth:
        #   type: bearer
        #   token: your-bearer-token

        # For JWT auth:
        # auth:
        #   type: jwt
        #   api_url: https://api.example.com/auth/
        #   api_token: your-api-token
        #   api_secret: your-api-secret

# Global settings (optional)
global:
  timeout: 30
  rate_limit:
    requests_per_minute: 60
"""

        config_file.write_text(default_template)

        # Reload the profile config cache
        from testmcpy.mcp_profiles import reload_profile_config

        reload_profile_config()

        return {
            "success": True,
            "message": "Created .mcp_services.yaml with default template",
            "path": str(config_file.absolute()),
        }

    except Exception as e:
        return {"success": False, "error": f"Failed to create configuration: {str(e)}"}


@router.get("/profiles")
async def list_mcp_profiles():
    """List available MCP profiles from .mcp_services.yaml."""
    from testmcpy.mcp_profiles import reload_profile_config

    try:
        # Always reload to pick up file changes
        profile_config = reload_profile_config()
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

                mcps_info.append(
                    {
                        "name": mcp_server.name,
                        "mcp_url": mcp_server.mcp_url,
                        "auth": auth_info,
                        "timeout": mcp_server.timeout,
                        "rate_limit_rpm": mcp_server.rate_limit_rpm,
                    }
                )

            # Check if this profile is the default
            is_default = profile.profile_id == profile_config.default_profile

            profiles_list.append(
                {
                    "id": profile.profile_id,
                    "name": profile.name,
                    "description": profile.description,
                    "mcps": mcps_info,
                    "timeout": profile.timeout,
                    "rate_limit_rpm": profile.rate_limit_rpm,
                    "is_default": is_default,
                }
            )

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


@router.get("/profiles/{profile_id}/auth")
async def get_profile_auth(profile_id: str):
    """Get unmasked auth config for a profile (for auth debugger)."""
    from testmcpy.mcp_profiles import get_profile_config

    try:
        profile_config = get_profile_config()
        profile = profile_config.get_profile(profile_id)

        if not profile:
            raise HTTPException(status_code=404, detail=f"Profile '{profile_id}' not found")

        if not profile.mcps:
            raise HTTPException(
                status_code=400, detail=f"Profile '{profile_id}' has no MCP servers"
            )

        auth = profile.mcps[0].auth
        if not auth:
            raise HTTPException(
                status_code=400, detail=f"Profile '{profile_id}' has no auth configured"
            )

        return {
            "type": auth.auth_type,
            "mcp_url": profile.mcps[0].mcp_url,
            "api_url": auth.api_url,
            "api_token": auth.api_token,
            "api_secret": auth.api_secret,
            "token_url": auth.token_url,
            "client_id": auth.client_id,
            "client_secret": auth.client_secret,
            "scopes": auth.scopes,
            "token": auth.token,
            "oauth_auto_discover": auth.oauth_auto_discover,
            "insecure": auth.insecure,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/profiles")
async def create_mcp_profile(request: ProfileCreateRequest):
    """Create a new MCP profile."""
    try:
        config_data = load_mcp_yaml()

        # Generate unique profile ID
        existing_ids = list(config_data.get("profiles", {}).keys())
        profile_id = generate_profile_id(request.name, existing_ids)

        # Create new profile
        new_profile = {"name": request.name, "description": request.description, "mcps": []}

        # Add to profiles
        if "profiles" not in config_data:
            config_data["profiles"] = {}

        config_data["profiles"][profile_id] = new_profile

        # Set as default if requested
        if request.set_as_default:
            config_data["default"] = profile_id

        # Save to file
        save_mcp_yaml(config_data)

        return {
            "success": True,
            "profile_id": profile_id,
            "message": f"Profile '{request.name}' created successfully",
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create profile: {str(e)}")


@router.put("/profiles/{profile_id}")
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

        if request.set_as_default is not None and request.set_as_default:
            config_data["default"] = profile_id

        # Save to file
        save_mcp_yaml(config_data)

        return {"success": True, "message": f"Profile '{profile_id}' updated successfully"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to update profile '{profile_id}': {str(e)}"
        )


@router.delete("/profiles/{profile_id}")
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
        mcp_clients = get_mcp_clients()
        keys_to_remove = [key for key in mcp_clients.keys() if key.startswith(f"{profile_id}:")]
        for key in keys_to_remove:
            client = mcp_clients.pop(key, None)
            if client:
                try:
                    await client.close()
                except Exception as e:
                    print(f"Warning: Failed to close MCP client '{key}': {e}")

        return {"success": True, "message": f"Profile '{profile_id}' deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to delete profile '{profile_id}': {str(e)}"
        )


@router.post("/profiles/{profile_id}/duplicate")
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
            "message": f"Profile duplicated as '{new_name}'",
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to duplicate profile '{profile_id}': {str(e)}"
        )


@router.put("/profiles/default/{profile_id}")
async def set_default_profile(profile_id: str):
    """Set a profile as the default."""
    try:
        config_data = load_mcp_yaml()

        if "profiles" not in config_data or profile_id not in config_data["profiles"]:
            raise HTTPException(status_code=404, detail=f"Profile '{profile_id}' not found")

        config_data["default"] = profile_id

        # Save to file
        save_mcp_yaml(config_data)

        return {"success": True, "message": f"Profile '{profile_id}' set as default"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to set default profile to '{profile_id}': {str(e)}"
        )


@router.post("/profiles/{profile_id}/mcps")
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
                detail=f"MCP with name '{request.name}' already exists in profile '{profile_id}'",
            )

        # Build auth config from nested object
        auth_config = {"type": request.auth.type}

        if request.auth.token:
            auth_config["token"] = request.auth.token
        if request.auth.api_url:
            auth_config["api_url"] = request.auth.api_url
        if request.auth.api_token:
            auth_config["api_token"] = request.auth.api_token
        if request.auth.api_secret:
            auth_config["api_secret"] = request.auth.api_secret
        if request.auth.client_id:
            auth_config["client_id"] = request.auth.client_id
        if request.auth.client_secret:
            auth_config["client_secret"] = request.auth.client_secret
        if request.auth.token_url:
            auth_config["token_url"] = request.auth.token_url
        if request.auth.scopes:
            auth_config["scopes"] = request.auth.scopes
        if request.auth.oauth_auto_discover:
            auth_config["oauth_auto_discover"] = request.auth.oauth_auto_discover
        if request.auth.insecure:
            auth_config["insecure"] = request.auth.insecure

        # Create new MCP
        new_mcp = {"name": request.name, "mcp_url": request.mcp_url, "auth": auth_config}

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

        return {"success": True, "message": f"MCP '{request.name}' added to profile '{profile_id}'"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to add MCP to profile '{profile_id}': {str(e)}"
        )


@router.put("/profiles/{profile_id}/mcps/reorder")
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
                detail=f"Invalid from_index: {request.from_index}. Must be between 0 and {len(mcps) - 1}",
            )

        if request.to_index < 0 or request.to_index >= len(mcps):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid to_index: {request.to_index}. Must be between 0 and {len(mcps) - 1}",
            )

        # Reorder
        mcp = mcps.pop(request.from_index)
        mcps.insert(request.to_index, mcp)

        # Save to file
        save_mcp_yaml(config_data)

        return {
            "success": True,
            "message": f"MCPs reordered successfully in profile '{profile_id}'",
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to reorder MCPs in profile '{profile_id}': {str(e)}"
        )


@router.put("/profiles/{profile_id}/mcps/{mcp_index}")
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
                        detail=f"MCP with name '{request.name}' already exists in profile '{profile_id}'",
                    )
            mcp["name"] = request.name

        if request.mcp_url is not None:
            mcp["mcp_url"] = request.mcp_url

        # Update auth
        if request.auth is not None:
            auth_config = {"type": request.auth.type}

            if request.auth.token:
                auth_config["token"] = request.auth.token
            if request.auth.api_url:
                auth_config["api_url"] = request.auth.api_url
            if request.auth.api_token:
                auth_config["api_token"] = request.auth.api_token
            if request.auth.api_secret:
                auth_config["api_secret"] = request.auth.api_secret
            if request.auth.client_id:
                auth_config["client_id"] = request.auth.client_id
            if request.auth.client_secret:
                auth_config["client_secret"] = request.auth.client_secret
            if request.auth.token_url:
                auth_config["token_url"] = request.auth.token_url
            if request.auth.scopes:
                auth_config["scopes"] = request.auth.scopes
            if request.auth.oauth_auto_discover:
                auth_config["oauth_auto_discover"] = request.auth.oauth_auto_discover
            if request.auth.insecure:
                auth_config["insecure"] = request.auth.insecure

            mcp["auth"] = auth_config

        if request.timeout is not None:
            mcp["timeout"] = request.timeout

        if request.rate_limit_rpm is not None:
            mcp["rate_limit_rpm"] = request.rate_limit_rpm

        # Save to file
        save_mcp_yaml(config_data)

        # Clear cached client for this MCP (use both old and new names)
        mcp_clients = get_mcp_clients()
        old_cache_key = f"{profile_id}:{old_name}"
        new_cache_key = f"{profile_id}:{mcp.get('name', '')}"

        for cache_key in [old_cache_key, new_cache_key]:
            client = mcp_clients.pop(cache_key, None)
            if client:
                try:
                    await client.close()
                except Exception as e:
                    print(f"Warning: Failed to close MCP client '{cache_key}': {e}")

        return {"success": True, "message": f"MCP at index {mcp_index} updated successfully"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update MCP at index {mcp_index} in profile '{profile_id}': {str(e)}",
        )


@router.delete("/profiles/{profile_id}/mcps/{mcp_index}")
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
        mcp_clients = get_mcp_clients()
        cache_key = f"{profile_id}:{mcp_name}"
        client = mcp_clients.pop(cache_key, None)
        if client:
            try:
                await client.close()
            except Exception as e:
                print(f"Warning: Failed to close MCP client '{cache_key}': {e}")

        return {
            "success": True,
            "message": f"MCP '{mcp_name}' deleted successfully from profile '{profile_id}'",
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete MCP at index {mcp_index} from profile '{profile_id}': {str(e)}",
        )


@router.get("/profiles/{profile_id}/export")
async def export_profile(profile_id: str):
    """Export a profile as YAML."""
    try:
        config_data = load_mcp_yaml()

        if "profiles" not in config_data or profile_id not in config_data["profiles"]:
            raise HTTPException(status_code=404, detail=f"Profile '{profile_id}' not found")

        profile = config_data["profiles"][profile_id]

        # Create export structure
        export_data = {"profiles": {profile_id: profile}}

        # Clean and format for export
        cleaned_data = clean_config_for_yaml(export_data)

        yaml_content = yaml.dump(
            cleaned_data,
            default_flow_style=False,
            sort_keys=False,
            indent=2,
            allow_unicode=True,
            width=float("inf"),
        )

        return {"success": True, "yaml": yaml_content, "filename": f"{profile_id}.yaml"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to export profile '{profile_id}': {str(e)}"
        )


@router.post("/profiles/{profile_id}/test-connection/{mcp_index}")
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
                auth_dict = {"type": "bearer", "token": auth_data["token"]}
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
                    "oauth_auto_discover": auth_data.get("oauth_auto_discover", False),
                    "insecure": auth_data.get("insecure", False),
                }
            elif auth_type == "none":
                auth_dict = {"type": "none"}

            # Create temporary client with auth
            test_client = MCPClient(mcp_config["mcp_url"], auth=auth_dict)
            await test_client.initialize()

            # Try to list tools as a connection test
            tools = await test_client.list_tools()

            await test_client.close()

            # Clear cached client for this MCP to force fresh JWT token on next request
            mcp_clients = get_mcp_clients()
            cache_key = f"{profile_id}:{mcp_config['name']}"
            old_client = mcp_clients.pop(cache_key, None)
            if old_client:
                try:
                    await old_client.close()
                    print(f"Cleared cached client '{cache_key}' after successful test")
                except Exception as e:
                    print(f"Warning: Failed to close old cached client '{cache_key}': {e}")

            return {
                "success": True,
                "status": "connected",
                "message": f"Successfully connected to {mcp_config['name']}",
                "tool_count": len(tools),
            }

        except Exception as e:
            return {"success": False, "status": "error", "message": f"Connection failed: {str(e)}"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
