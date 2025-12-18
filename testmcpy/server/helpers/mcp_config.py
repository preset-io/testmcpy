"""MCP configuration file helpers."""

import copy
import shutil
from pathlib import Path
from typing import Any

import yaml
from fastapi import HTTPException


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
    if "profiles" not in config_data:
        raise ValueError("Config must have 'profiles' field")

    if not isinstance(config_data["profiles"], dict):
        raise ValueError("'profiles' must be a dictionary")

    for profile_id, profile in config_data["profiles"].items():
        if not isinstance(profile, dict):
            raise ValueError(f"Profile '{profile_id}' must be a dictionary")

        if "name" not in profile:
            raise ValueError(f"Profile '{profile_id}' missing required 'name' field")

        if "mcps" in profile:
            if not isinstance(profile["mcps"], list):
                raise ValueError(f"Profile '{profile_id}' 'mcps' must be a list")

            for idx, mcp in enumerate(profile["mcps"]):
                if not isinstance(mcp, dict):
                    raise ValueError(f"MCP #{idx} in profile '{profile_id}' must be a dictionary")

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
    """

    def clean_value(value):
        """Recursively clean a value."""
        if value is None:
            return None
        elif isinstance(value, dict):
            cleaned = {}
            for k, v in value.items():
                cleaned_v = clean_value(v)
                if cleaned_v is not None:
                    cleaned[k] = cleaned_v
            return cleaned if cleaned else None
        elif isinstance(value, list):
            cleaned = [clean_value(item) for item in value]
            return [item for item in cleaned if item is not None]
        else:
            return value

    config_copy = copy.deepcopy(config_data)
    cleaned = clean_value(config_copy)

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
    - Automatic rollback on failure
    - Reloads profile config after save
    """
    config_path = get_mcp_config_path()
    backup_path = config_path.with_suffix(".yaml.backup")
    temp_path = config_path.with_suffix(".yaml.tmp")

    try:
        validate_config(config_data)
        cleaned_config = clean_config_for_yaml(config_data)

        if config_path.exists():
            try:
                shutil.copy2(config_path, backup_path)
            except Exception as e:
                print(f"Warning: Failed to create backup: {e}")

        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                yaml.dump(
                    cleaned_config,
                    f,
                    default_flow_style=False,
                    sort_keys=False,
                    indent=2,
                    allow_unicode=True,
                    width=float("inf"),
                )
        except Exception as e:
            if temp_path.exists():
                temp_path.unlink()
            raise ValueError(f"Failed to write YAML: {str(e)}")

        try:
            with open(temp_path, encoding="utf-8") as f:
                yaml.safe_load(f)
        except Exception as e:
            if temp_path.exists():
                temp_path.unlink()
            raise ValueError(f"Generated invalid YAML: {str(e)}")

        temp_path.replace(config_path)

        from testmcpy.mcp_profiles import reload_profile_config

        reload_profile_config()

    except ValueError as e:
        if backup_path.exists() and not config_path.exists():
            try:
                shutil.copy2(backup_path, config_path)
            except Exception as restore_error:
                print(f"Error restoring backup: {restore_error}")
        raise HTTPException(status_code=400, detail=f"Invalid configuration: {str(e)}")

    except Exception as e:
        if backup_path.exists():
            try:
                shutil.copy2(backup_path, config_path)
                print(f"Restored configuration from backup after error: {e}")
            except Exception as restore_error:
                print(f"Failed to restore backup: {restore_error}")

        raise HTTPException(status_code=500, detail=f"Failed to save configuration: {str(e)}")

    finally:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except Exception as e:
                print(f"Warning: Failed to clean up temp file: {e}")


def generate_profile_id(name: str, existing_ids: list[str]) -> str:
    """Generate a unique profile ID from a name."""
    base_id = name.lower().replace(" ", "-").replace("_", "-")
    base_id = "".join(c for c in base_id if c.isalnum() or c == "-")

    profile_id = base_id
    counter = 1
    while profile_id in existing_ids:
        profile_id = f"{base_id}-{counter}"
        counter += 1

    return profile_id
