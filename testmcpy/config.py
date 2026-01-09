"""
Configuration management for testmcpy.

Priority order (highest to lowest):
1. Command-line options (--profile, --llm-profile, --test-profile, etc.)
2. Profiles from .mcp_services.yaml, .llm_providers.yaml, .test_profiles.yaml
3. .env file in current directory
4. ~/.testmcpy (user config file)
5. Environment variables
6. Built-in defaults
"""

import os
from pathlib import Path
from typing import Any

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

# Import LLM profile configuration
try:
    from .llm_profiles import LLMProfile, list_available_llm_profiles, load_llm_profile
except ImportError:
    # Fallback if llm_profiles not available
    def load_llm_profile(profile_id=None):
        return None

    def list_available_llm_profiles():
        return []

    LLMProfile = None

# Import Test profile configuration
try:
    from .test_profiles import TestProfile, list_available_test_profiles, load_test_profile
except ImportError:
    # Fallback if test_profiles not available
    def load_test_profile(profile_id=None):
        return None

    def list_available_test_profiles():
        return []

    TestProfile = None


class Config:
    """Manages testmcpy configuration from multiple sources."""

    # Default values
    # Note: DEFAULT_MODEL and DEFAULT_PROVIDER are deprecated.
    # Use .llm_providers.yaml to configure LLM models and providers instead.
    DEFAULTS = {}

    # Generic keys that should fall back to environment variables
    GENERIC_KEYS = {
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "OLLAMA_BASE_URL",
    }

    # testmcpy-specific keys (deprecated, use LLM profiles instead)
    TESTMCPY_KEYS = {
        "DEFAULT_MODEL",  # Deprecated: Use .llm_providers.yaml
        "DEFAULT_PROVIDER",  # Deprecated: Use .llm_providers.yaml
    }

    def __init__(
        self,
        profile: str | None = None,
        llm_profile: str | None = None,
        test_profile: str | None = None,
    ):
        self._config: dict[str, Any] = {}
        self._sources: dict[str, str] = {}
        self._profile: MCPProfile | None = None
        self._profile_id: str | None = profile
        self._llm_profile: LLMProfile | None = None
        self._llm_profile_id: str | None = llm_profile
        self._test_profile: TestProfile | None = None
        self._test_profile_id: str | None = test_profile
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

        # 4. Load from MCP profile (.mcp_services.yaml)
        # Always try to load - if profile_id is None, it loads the default profile
        self._load_profile(self._profile_id)

        # 5. Load from LLM profile (.llm_providers.yaml)
        self._load_llm_profile(self._llm_profile_id)

        # 6. Load from Test profile (.test_profiles.yaml)
        self._load_test_profile(self._test_profile_id)

        # 7. Apply defaults for missing values
        for key, default_value in self.DEFAULTS.items():
            if key not in self._config:
                self._config[key] = default_value
                self._sources[key] = "Default"

    def _load_profile(self, profile_id: str | None = None):
        """Load configuration from MCP profile.

        Note: MCP profiles are loaded directly from .mcp_services.yaml
        This method just stores the profile reference for use by other components.
        """
        try:
            profile = load_profile(profile_id)
            if not profile:
                return

            self._profile = profile

        except Exception as e:
            import warnings

            warnings.warn(f"Failed to load MCP profile '{profile_id}': {e}", stacklevel=2)

    def _load_llm_profile(self, profile_id: str | None = None):
        """Load configuration from LLM profile.

        Note: LLM profiles are loaded directly from .llm_providers.yaml
        This method just stores the profile reference for use by other components.
        """
        try:
            profile = load_llm_profile(profile_id)
            if not profile:
                return

            self._llm_profile = profile

            # If profile has a default provider, update config
            default_provider = profile.get_default_provider()
            if default_provider:
                if "DEFAULT_MODEL" not in self._config:
                    self._config["DEFAULT_MODEL"] = default_provider.model
                    self._sources["DEFAULT_MODEL"] = f"LLM Profile ({profile.name})"
                if "DEFAULT_PROVIDER" not in self._config:
                    self._config["DEFAULT_PROVIDER"] = default_provider.provider
                    self._sources["DEFAULT_PROVIDER"] = f"LLM Profile ({profile.name})"

        except Exception as e:
            import warnings

            warnings.warn(f"Failed to load LLM profile '{profile_id}': {e}", stacklevel=2)

    def _load_test_profile(self, profile_id: str | None = None):
        """Load configuration from Test profile.

        Note: Test profiles are loaded directly from .test_profiles.yaml
        This method just stores the profile reference for use by other components.
        """
        try:
            profile = load_test_profile(profile_id)
            if not profile:
                return

            self._test_profile = profile

        except Exception as e:
            import warnings

            warnings.warn(f"Failed to load Test profile '{profile_id}': {e}", stacklevel=2)

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

    def get_default_mcp_server(self):
        """
        Get the default MCP server from the loaded profile.

        Returns the MCPServer object that is marked as default, or the first one if none marked.
        Returns None if no profile or no MCP servers.
        """
        if not self._profile or not self._profile.mcps:
            return None

        # Check if any MCP server is marked as default
        for mcp in self._profile.mcps:
            if mcp.default:
                return mcp

        # No default marked, return first one
        return self._profile.mcps[0]

    def get_mcp_url(self) -> str | None:
        """
        Get MCP URL from the loaded profile.

        Returns the MCP URL from:
        1. The MCP server marked with default: true in the profile
        2. The first MCP server if no default is marked
        3. None if no profile or no MCP servers
        """
        mcp = self.get_default_mcp_server()
        return mcp.mcp_url if mcp else None

    def get_default_llm_provider(self):
        """
        Get the default LLM provider from the loaded profile.

        Returns the LLMProviderConfig object that is marked as default, or the first one if none marked.
        Returns None if no profile or no LLM providers.
        """
        if not self._llm_profile:
            return None

        return self._llm_profile.get_default_provider()

    def get_default_test_config(self):
        """
        Get the default test config from the loaded profile.

        Returns the TestConfig object that is marked as default, or the first one if none marked.
        Returns None if no profile or no test configs.
        """
        if not self._test_profile:
            return None

        return self._test_profile.get_default_config()


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
