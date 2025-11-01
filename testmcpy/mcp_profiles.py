"""
MCP Service Profile Configuration.

Supports loading MCP service configurations from YAML files with multiple
profiles (dev, staging, prod, etc.) and environment variable substitution.
"""

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class AuthConfig:
    """Authentication configuration for MCP service."""

    auth_type: str  # bearer, oauth, jwt, none
    token: str | None = None
    # JWT fields
    api_url: str | None = None
    api_token: str | None = None
    api_secret: str | None = None
    # OAuth fields
    client_id: str | None = None
    client_secret: str | None = None
    token_url: str | None = None
    scopes: list[str] = field(default_factory=list)


@dataclass
class MCPProfile:
    """MCP Service profile configuration."""

    name: str
    profile_id: str
    mcp_url: str
    auth: AuthConfig
    timeout: int = 30
    rate_limit_rpm: int = 60


class MCPProfileConfig:
    """Manages MCP service profile configurations."""

    def __init__(self, config_path: str | None = None):
        """
        Initialize profile configuration.

        Args:
            config_path: Path to YAML config file. Defaults to .mcp_services.yaml
                        in current directory or parent directories.
        """
        self.config_path = self._find_config_file(config_path)
        self.profiles: dict[str, MCPProfile] = {}
        self.default_profile: str | None = None
        self.global_config: dict[str, Any] = {}

        if self.config_path:
            self._load_config()

    def _find_config_file(self, config_path: str | None = None) -> Path | None:
        """
        Find MCP services configuration file.

        Searches in order:
        1. Provided config_path
        2. .mcp_services.yaml in current directory
        3. .mcp_services.yaml in parent directories (up to 5 levels)
        4. ~/.mcp_services.yaml (user home)
        """
        if config_path:
            path = Path(config_path)
            if path.exists():
                return path
            return None

        # Check current directory and parents
        current = Path.cwd()
        for _ in range(5):
            config_file = current / ".mcp_services.yaml"
            if config_file.exists():
                return config_file
            if current.parent == current:
                break
            current = current.parent

        # Check user home
        home_config = Path.home() / ".mcp_services.yaml"
        if home_config.exists():
            return home_config

        return None

    def _substitute_env_vars(self, value: Any) -> Any:
        """
        Recursively substitute environment variables in config values.

        Supports ${VAR_NAME} and ${VAR_NAME:-default_value} syntax.
        """
        if isinstance(value, str):
            # Match ${VAR_NAME} or ${VAR_NAME:-default}
            pattern = r"\$\{([^}:]+)(?::-([^}]*))?\}"

            def replace_var(match):
                var_name = match.group(1)
                default_value = match.group(2) if match.group(2) is not None else ""
                return os.environ.get(var_name, default_value)

            return re.sub(pattern, replace_var, value)

        elif isinstance(value, dict):
            return {k: self._substitute_env_vars(v) for k, v in value.items()}

        elif isinstance(value, list):
            return [self._substitute_env_vars(item) for item in value]

        return value

    def _load_config(self):
        """Load and parse YAML configuration file."""
        if not self.config_path:
            return

        try:
            with open(self.config_path) as f:
                raw_config = yaml.safe_load(f)

            if not raw_config:
                return

            # Substitute environment variables
            config = self._substitute_env_vars(raw_config)

            # Load default profile
            self.default_profile = config.get("default", "local")

            # Load global settings
            self.global_config = config.get("global", {})

            # Load profiles
            profiles_config = config.get("profiles", {})
            for profile_id, profile_data in profiles_config.items():
                self.profiles[profile_id] = self._parse_profile(profile_id, profile_data)

        except Exception as e:
            print(f"Warning: Failed to load MCP profile config from {self.config_path}: {e}")

    def _parse_profile(self, profile_id: str, data: dict[str, Any]) -> MCPProfile:
        """Parse a single profile from configuration."""
        # Parse auth configuration
        auth_data = data.get("auth", {})
        auth_type = auth_data.get("type", "none")

        auth = AuthConfig(
            auth_type=auth_type,
            token=auth_data.get("token"),
            # JWT
            api_url=auth_data.get("api_url"),
            api_token=auth_data.get("api_token"),
            api_secret=auth_data.get("api_secret"),
            # OAuth
            client_id=auth_data.get("client_id"),
            client_secret=auth_data.get("client_secret"),
            token_url=auth_data.get("token_url"),
            scopes=auth_data.get("scopes", []),
        )

        # Get timeout from profile or global config
        timeout = data.get("timeout", self.global_config.get("timeout", 30))

        # Get rate limit from profile or global config
        rate_limit = data.get("rate_limit", self.global_config.get("rate_limit", {}))
        rate_limit_rpm = (
            rate_limit.get("requests_per_minute", 60) if isinstance(rate_limit, dict) else 60
        )

        return MCPProfile(
            name=data.get("name", profile_id),
            profile_id=profile_id,
            mcp_url=data["mcp_url"],
            auth=auth,
            timeout=timeout,
            rate_limit_rpm=rate_limit_rpm,
        )

    def get_profile(self, profile_id: str | None = None) -> MCPProfile | None:
        """
        Get a profile by ID.

        Args:
            profile_id: Profile ID to retrieve. If None, returns default profile.

        Returns:
            MCPProfile if found, None otherwise.
        """
        if not profile_id:
            profile_id = self.default_profile

        return self.profiles.get(profile_id)

    def list_profiles(self) -> list[str]:
        """Get list of available profile IDs."""
        return list(self.profiles.keys())

    def has_profiles(self) -> bool:
        """Check if any profiles are configured."""
        return len(self.profiles) > 0


# Global instance
_profile_config: MCPProfileConfig | None = None


def get_profile_config() -> MCPProfileConfig:
    """Get or create global profile configuration instance."""
    global _profile_config
    if _profile_config is None:
        _profile_config = MCPProfileConfig()
    return _profile_config


def load_profile(profile_id: str | None = None) -> MCPProfile | None:
    """
    Load an MCP profile by ID.

    Args:
        profile_id: Profile ID to load. If None, loads default profile.

    Returns:
        MCPProfile if found, None otherwise.
    """
    config = get_profile_config()
    return config.get_profile(profile_id)


def list_available_profiles() -> list[str]:
    """Get list of available profile IDs."""
    config = get_profile_config()
    return config.list_profiles()
