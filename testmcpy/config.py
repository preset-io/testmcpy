"""
Configuration management for testmcpy.

Priority order (highest to lowest):
1. Command-line options (--profile, --mcp-url, etc.)
2. MCP Profile from .mcp_services.yaml
3. .env file in current directory
4. ~/.testmcpy (user config file)
5. Environment variables
6. Built-in defaults
"""

import os
import time
from pathlib import Path
from typing import Any

import httpx

# Import profile configuration
try:
    from .mcp_profiles import MCPProfile, list_available_profiles, load_profile
except ImportError:
    # Fallback if mcp_profiles not available
    def load_profile(profile_id=None):
        return None

    def list_available_profiles():
        return []

    MCPProfile = None


class Config:
    """Manages testmcpy configuration from multiple sources."""

    # Default values
    # Note: We don't set DEFAULT_MODEL or DEFAULT_PROVIDER by default
    # to avoid assuming any particular setup. Users should configure
    # their preferred provider in ~/.testmcpy or via environment variables.
    DEFAULTS = {
        "MCP_URL": "http://localhost:5008/mcp/",
    }

    # Generic keys that should fall back to environment variables
    GENERIC_KEYS = {
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "OLLAMA_BASE_URL",
    }

    # testmcpy-specific keys
    TESTMCPY_KEYS = {
        "MCP_URL",
        "MCP_AUTH_TOKEN",
        "SUPERSET_MCP_TOKEN",  # Legacy, kept for compatibility
        "DEFAULT_MODEL",
        "DEFAULT_PROVIDER",
        # Dynamic token generation config
        "MCP_AUTH_API_URL",
        "MCP_AUTH_API_TOKEN",
        "MCP_AUTH_API_SECRET",
    }

    def __init__(self, profile: str | None = None):
        self._config: dict[str, Any] = {}
        self._sources: dict[str, str] = {}
        self._cached_token: str | None = None
        self._token_expiry: float | None = None
        self._profile: MCPProfile | None = None
        self._profile_id: str | None = profile
        self._load_config()

    def _load_config(self):
        """Load configuration from all sources in priority order."""

        # 1. Load from environment variables first (lowest priority for testmcpy keys)
        for key in self.GENERIC_KEYS | self.TESTMCPY_KEYS:
            value = os.getenv(key)
            if value:
                self._config[key] = value
                self._sources[key] = "Environment"

        # 2. Load from ~/.testmcpy (user config)
        user_config_file = Path.home() / ".testmcpy"
        if user_config_file.exists():
            self._load_env_file(user_config_file, "~/.testmcpy")

        # 3. Load from .env in current directory
        cwd_env_file = Path.cwd() / ".env"
        if cwd_env_file.exists():
            self._load_env_file(cwd_env_file, ".env (current dir)")

        # 4. Load from MCP profile (.mcp_services.yaml) if specified
        if self._profile_id is not None or load_profile() is not None:
            self._load_profile(self._profile_id)

        # 5. Apply defaults for missing values
        for key, default_value in self.DEFAULTS.items():
            if key not in self._config:
                self._config[key] = default_value
                self._sources[key] = "Default"

    def _load_profile(self, profile_id: str | None = None):
        """Load configuration from MCP profile.

        For backward compatibility with single-MCP configs, if a profile has only one MCP,
        we'll use that MCP's URL and auth as the default MCP_URL and auth settings.
        """
        try:
            profile = load_profile(profile_id)
            if not profile:
                return

            self._profile = profile

            # For backward compatibility: if profile has exactly one MCP, use it as default
            if profile.mcps and len(profile.mcps) == 1:
                first_mcp = profile.mcps[0]

                # Set MCP URL
                self._config["MCP_URL"] = first_mcp.mcp_url
                self._sources["MCP_URL"] = f"Profile ({profile.profile_id})"

                # Set auth configuration based on auth type
                if first_mcp.auth.auth_type == "bearer" and first_mcp.auth.token:
                    self._config["MCP_AUTH_TOKEN"] = first_mcp.auth.token
                    self._sources["MCP_AUTH_TOKEN"] = f"Profile ({profile.profile_id})"

                elif first_mcp.auth.auth_type == "jwt":
                    if first_mcp.auth.api_url:
                        self._config["MCP_AUTH_API_URL"] = first_mcp.auth.api_url
                        self._sources["MCP_AUTH_API_URL"] = f"Profile ({profile.profile_id})"
                    if first_mcp.auth.api_token:
                        self._config["MCP_AUTH_API_TOKEN"] = first_mcp.auth.api_token
                        self._sources["MCP_AUTH_API_TOKEN"] = f"Profile ({profile.profile_id})"
                    if first_mcp.auth.api_secret:
                        self._config["MCP_AUTH_API_SECRET"] = first_mcp.auth.api_secret
                        self._sources["MCP_AUTH_API_SECRET"] = f"Profile ({profile.profile_id})"

                # OAuth not yet implemented in auth flow, but store for future use
                elif first_mcp.auth.auth_type == "oauth":
                    # Store OAuth config for future use
                    pass

            # If profile has multiple MCPs, don't set default MCP_URL/auth
            # The API will handle loading all MCPs from the profile

        except Exception as e:
            import warnings

            warnings.warn(f"Failed to load MCP profile '{profile_id}': {e}", stacklevel=2)

    def _load_env_file(self, file_path: Path, source_name: str):
        """Load configuration from an env file."""
        try:
            with open(file_path) as f:
                for line in f:
                    line = line.strip()
                    # Skip comments and empty lines
                    if not line or line.startswith("#"):
                        continue

                    # Parse KEY=VALUE
                    if "=" in line:
                        key, value = line.split("=", 1)
                        key = key.strip()
                        value = value.strip()

                        # Remove quotes if present
                        if value.startswith('"') and value.endswith('"'):
                            value = value[1:-1]
                        elif value.startswith("'") and value.endswith("'"):
                            value = value[1:-1]

                        # Only override if key is relevant and not already set from higher priority
                        if key in self.GENERIC_KEYS | self.TESTMCPY_KEYS:
                            # For generic keys, only override if not from environment
                            if key in self.GENERIC_KEYS:
                                if (
                                    key not in self._config
                                    or self._sources.get(key) != "Environment"
                                ):
                                    self._config[key] = value
                                    self._sources[key] = source_name
                            # For testmcpy-specific keys, always override
                            elif key in self.TESTMCPY_KEYS:
                                self._config[key] = value
                                self._sources[key] = source_name
        except Exception:
            # Silently ignore errors reading config files
            pass

    def get(self, key: str, default: str | None = None) -> str | None:
        """Get a configuration value."""
        return self._config.get(key, default)

    def get_source(self, key: str) -> str:
        """Get the source of a configuration value."""
        return self._sources.get(key, "Not set")

    def get_all(self) -> dict[str, Any]:
        """Get all configuration values."""
        return self._config.copy()

    def get_all_with_sources(self) -> dict[str, tuple]:
        """Get all configuration values with their sources."""
        result = {}
        for key in self._config:
            result[key] = (self._config[key], self._sources.get(key, "Unknown"))
        return result

    @property
    def mcp_url(self) -> str:
        """Get MCP URL."""
        return self.get("MCP_URL", self.DEFAULTS["MCP_URL"])

    def _fetch_jwt_token(self) -> str | None:
        """Fetch JWT token from MCP auth API."""
        api_url = self.get("MCP_AUTH_API_URL")
        api_token = self.get("MCP_AUTH_API_TOKEN")
        api_secret = self.get("MCP_AUTH_API_SECRET")

        if not all([api_url, api_token, api_secret]):
            return None

        try:
            response = httpx.post(
                api_url,
                headers={"Content-Type": "application/json", "Accept": "application/json"},
                json={"name": api_token, "secret": api_secret},
                timeout=10.0,
            )
            response.raise_for_status()
            data = response.json()

            # Extract access token from response
            # Preset API returns {"payload": {"access_token": "..."}}
            if "payload" in data and "access_token" in data["payload"]:
                token = data["payload"]["access_token"]
                # Cache token for 50 minutes (JWT typically expires in 1 hour)
                self._cached_token = token
                self._token_expiry = time.time() + 3000  # 50 minutes
                return token
            elif "access_token" in data:
                token = data["access_token"]
                self._cached_token = token
                self._token_expiry = time.time() + 3000
                return token

        except Exception as e:
            # Log error but don't fail - fall back to static token
            import warnings

            warnings.warn(f"Failed to fetch JWT token: {e}", stacklevel=2)
            return None

    @property
    def mcp_auth_token(self) -> str | None:
        """
        Get MCP auth token with the following priority:
        1. Dynamically generated JWT from MCP_AUTH_API_URL if configured
        2. Static MCP_AUTH_TOKEN or SUPERSET_MCP_TOKEN

        For dynamic tokens, caches the JWT for 50 minutes to avoid excessive API calls.
        """
        # Check if dynamic JWT credentials are configured
        has_dynamic_config = all(
            [
                self.get("MCP_AUTH_API_URL"),
                self.get("MCP_AUTH_API_TOKEN"),
                self.get("MCP_AUTH_API_SECRET"),
            ]
        )

        # If dynamic JWT is configured, use it (with caching)
        if has_dynamic_config:
            # Check if we have a valid cached token
            if self._cached_token and self._token_expiry:
                if time.time() < self._token_expiry:
                    return self._cached_token

            # Try to fetch a new JWT token
            jwt_token = self._fetch_jwt_token()
            if jwt_token:
                return jwt_token
            # If fetch fails, fall through to static token

        # Fall back to static token
        static_token = self.get("MCP_AUTH_TOKEN") or self.get("SUPERSET_MCP_TOKEN")
        if static_token:
            return static_token

        return None

    @property
    def default_model(self) -> str | None:
        """Get default model."""
        return self.get("DEFAULT_MODEL")

    @property
    def default_provider(self) -> str | None:
        """Get default provider."""
        return self.get("DEFAULT_PROVIDER")

    @property
    def anthropic_api_key(self) -> str | None:
        """Get Anthropic API key."""
        return self.get("ANTHROPIC_API_KEY")

    @property
    def openai_api_key(self) -> str | None:
        """Get OpenAI API key."""
        return self.get("OPENAI_API_KEY")


# Global config instance
_config: Config | None = None


def get_config() -> Config:
    """Get the global config instance, creating it if necessary."""
    global _config
    if _config is None:
        _config = Config()
    return _config


def reload_config():
    """Reload configuration from all sources."""
    global _config
    _config = Config()
