"""
MCP Service Profile Configuration.

Supports loading MCP service configurations from YAML files with multiple
profiles. Each profile can contain MULTIPLE MCP servers, allowing you to:
- Group MCPs by environment (dev/staging/prod)
- Group MCPs by workflow (data-pipeline, analytics, etc.)
- Mix different MCP servers for your specific use case
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
    oauth_auto_discover: bool = False  # Use RFC 8414 auto-discovery for OAuth
    # SSL options
    insecure: bool = False  # Disable SSL verification for self-signed certificates

    def to_dict(self) -> dict[str, Any]:
        """Convert AuthConfig to dict for MCPClient auth parameter.

        Returns:
            Dictionary with auth configuration suitable for MCPClient.
        """
        auth_dict = {"type": self.auth_type}

        if self.auth_type == "bearer" and self.token:
            auth_dict["token"] = self.token
        elif self.auth_type == "jwt":
            if self.api_url:
                auth_dict["api_url"] = self.api_url
            if self.api_token:
                auth_dict["api_token"] = self.api_token
            if self.api_secret:
                auth_dict["api_secret"] = self.api_secret
        elif self.auth_type == "oauth":
            if self.oauth_auto_discover:
                auth_dict["oauth_auto_discover"] = True
            if self.client_id:
                auth_dict["client_id"] = self.client_id
            if self.client_secret:
                auth_dict["client_secret"] = self.client_secret
            if self.token_url:
                auth_dict["token_url"] = self.token_url
            if self.scopes:
                auth_dict["scopes"] = self.scopes

        # Include SSL options if configured
        if self.insecure:
            auth_dict["insecure"] = self.insecure

        return auth_dict


@dataclass
class MCPServer:
    """Individual MCP server configuration."""

    name: str
    mcp_url: str
    auth: AuthConfig
    timeout: int = 30
    rate_limit_rpm: int = 60
    default: bool = False  # Mark this MCP server as default in the profile


@dataclass
class MCPProfile:
    """MCP Profile containing multiple MCP servers."""

    name: str
    profile_id: str
    description: str
    mcps: list[MCPServer]
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
        self.raw_config: dict[str, Any] = {}

        if self.config_path:
            self._load_config()

    def _find_config_file(self, config_path: str | None = None) -> Path | None:
        """
        Find MCP services configuration file.

        Looks for .mcp_services.yaml in the current working directory.
        """
        if config_path:
            path = Path(config_path)
            if path.exists():
                return path
            return None

        # Check current directory only (same as llm_profiles)
        config_file = Path.cwd() / ".mcp_services.yaml"
        if config_file.exists():
            return config_file

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

            # Store raw config for API access
            self.raw_config = raw_config

            # Substitute environment variables
            config = self._substitute_env_vars(raw_config)

            # Load default profile
            self.default_profile = config.get("default", "local-dev")

            # Load global settings
            self.global_config = config.get("global", {})

            # Load profiles
            profiles_config = config.get("profiles", {})
            if not isinstance(profiles_config, dict):
                print(
                    f"Warning: 'profiles' in config should be a dict, got {type(profiles_config).__name__}"
                )
                return

            for profile_id, profile_data in profiles_config.items():
                if not isinstance(profile_data, dict):
                    print(
                        f"Warning: Skipping profile '{profile_id}' - invalid format (expected dict)"
                    )
                    continue
                try:
                    self.profiles[profile_id] = self._parse_profile(profile_id, profile_data)
                except Exception as e:
                    print(f"Warning: Failed to parse profile '{profile_id}': {e}")
                    continue

        except yaml.YAMLError as e:
            print(f"Warning: Invalid YAML in {self.config_path}: {e}")
        except Exception as e:
            print(f"Warning: Failed to load MCP profile config from {self.config_path}: {e}")

    def _parse_auth(self, auth_data: dict[str, Any] | None) -> AuthConfig:
        """Parse auth configuration."""
        if not auth_data or not isinstance(auth_data, dict):
            return AuthConfig(auth_type="none")
        auth_type = auth_data.get("type", "none")

        return AuthConfig(
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
            oauth_auto_discover=auth_data.get("oauth_auto_discover", False),
            # SSL options
            insecure=auth_data.get("insecure", False),
        )

    def _parse_profile(self, profile_id: str, data: dict[str, Any]) -> MCPProfile:
        """Parse a single profile from configuration."""
        # Get timeout from profile or global config
        timeout = data.get("timeout", self.global_config.get("timeout", 30))

        # Get rate limit from profile or global config
        rate_limit = data.get("rate_limit", self.global_config.get("rate_limit", {}))
        rate_limit_rpm = (
            rate_limit.get("requests_per_minute", 60) if isinstance(rate_limit, dict) else 60
        )

        # Parse MCP servers
        mcps = []
        mcps_data = data.get("mcps", [])

        if not mcps_data:
            # Backward compatibility: if no 'mcps' array, treat as single MCP
            if "mcp_url" in data:
                mcp_server = MCPServer(
                    name=data.get("name", profile_id),
                    mcp_url=data["mcp_url"],
                    auth=self._parse_auth(data.get("auth", {})),
                    timeout=timeout,
                    rate_limit_rpm=rate_limit_rpm,
                    default=True,  # Single MCP is always default
                )
                mcps.append(mcp_server)
        else:
            # New format: multiple MCPs per profile
            if not isinstance(mcps_data, list):
                print(
                    f"Warning: 'mcps' in profile '{profile_id}' should be a list, got {type(mcps_data).__name__}"
                )
                mcps_data = []

            for idx, mcp_data in enumerate(mcps_data):
                if not isinstance(mcp_data, dict):
                    print(
                        f"Warning: Skipping MCP entry {idx} in profile '{profile_id}' - invalid format"
                    )
                    continue
                mcp_url = mcp_data.get("mcp_url")
                if not mcp_url:
                    print(
                        f"Warning: Skipping MCP entry {idx} in profile '{profile_id}' - missing 'mcp_url'"
                    )
                    continue
                mcp_server = MCPServer(
                    name=mcp_data.get("name", "Unnamed MCP"),
                    mcp_url=mcp_url,
                    auth=self._parse_auth(mcp_data.get("auth", {})),
                    timeout=mcp_data.get("timeout", timeout),
                    rate_limit_rpm=mcp_data.get("rate_limit_rpm", rate_limit_rpm),
                    default=mcp_data.get("default", False),  # Check for default flag
                )
                mcps.append(mcp_server)

        return MCPProfile(
            name=data.get("name", profile_id),
            profile_id=profile_id,
            description=data.get("description", ""),
            mcps=mcps,
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

    def get_default_profile_and_server(self) -> tuple[str, str] | None:
        """
        Get the default profile and server IDs.

        Returns:
            Tuple of (profile_id, mcp_name) if default found, None otherwise.
            Uses the top-level default profile setting.
        """
        # Use top-level default profile
        if self.default_profile:
            profile = self.get_profile(self.default_profile)
            if profile and len(profile.mcps) > 0:
                # Get the default MCP server (marked default or first one)
                default_mcp = None
                for mcp in profile.mcps:
                    if mcp.default:
                        default_mcp = mcp
                        break
                if not default_mcp:
                    default_mcp = profile.mcps[0]
                return (self.default_profile, default_mcp.name)

        return None


# Global instance
_profile_config: MCPProfileConfig | None = None


def get_profile_config() -> MCPProfileConfig:
    """Get or create global profile configuration instance."""
    global _profile_config
    if _profile_config is None:
        _profile_config = MCPProfileConfig()
    return _profile_config


def reload_profile_config():
    """Force reload of profile configuration."""
    global _profile_config
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


def load_mcp_profiles() -> dict[str, Any] | None:
    """
    Load raw MCP profiles configuration from YAML file.

    Returns:
        Dictionary with 'profiles', 'default', and 'global' keys,
        or None if no config file found.
    """
    config = get_profile_config()
    if not config.config_path:
        return None

    try:
        with open(config.config_path) as f:
            raw_config = yaml.safe_load(f)

        if not raw_config:
            return None

        # Substitute environment variables
        return config._substitute_env_vars(raw_config)
    except Exception as e:
        print(f"Warning: Failed to load MCP profiles config: {e}")
        return None
