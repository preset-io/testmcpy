"""
LLM Provider Profile Management.

Manages multiple LLM provider configurations with profile-based organization.
Similar to MCP profiles, allows users to define different LLM setups for different environments.
"""

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


def _substitute_env_vars(value: Any) -> Any:
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
        return {k: _substitute_env_vars(v) for k, v in value.items()}

    elif isinstance(value, list):
        return [_substitute_env_vars(item) for item in value]

    return value


@dataclass
class LLMProviderConfig:
    """Configuration for a single LLM provider."""

    name: str
    provider: str  # anthropic, openai, ollama, local, claude-sdk, claude-cli
    model: str
    api_key: str | None = None  # Direct API key (stored in config)
    api_key_env: str | None = None  # Environment variable name for API key
    base_url: str | None = None  # For OpenAI-compatible APIs or Ollama
    timeout: int = 60
    default: bool = False  # Mark this as default provider in the profile

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        result = {
            "name": self.name,
            "provider": self.provider,
            "model": self.model,
            "timeout": self.timeout,
            "default": self.default,
        }
        # Only include non-None optional fields
        if self.api_key:
            result["api_key"] = self.api_key
        if self.api_key_env:
            result["api_key_env"] = self.api_key_env
        if self.base_url:
            result["base_url"] = self.base_url
        return result


@dataclass
class LLMProfile:
    """LLM profile containing multiple provider configurations."""

    profile_id: str
    name: str
    description: str
    providers: list[LLMProviderConfig] = field(default_factory=list)

    def get_default_provider(self) -> LLMProviderConfig | None:
        """Get the default provider in this profile."""
        for provider in self.providers:
            if provider.default:
                return provider
        # If no default marked, return first one
        return self.providers[0] if self.providers else None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "description": self.description,
            "providers": [p.to_dict() for p in self.providers],
        }


@dataclass
class LLMProfileConfig:
    """Container for all LLM profiles."""

    profiles: dict[str, LLMProfile] = field(default_factory=dict)
    default_profile_id: str | None = None
    global_settings: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Load profiles from .llm_providers.yaml if available."""
        self._load_profiles()

    def _load_profiles(self):
        """Load profiles from .llm_providers.yaml file."""
        config_path = Path.cwd() / ".llm_providers.yaml"

        if not config_path.exists():
            return

        try:
            with open(config_path) as f:
                data = yaml.safe_load(f)

            if not data:
                return

            # Substitute environment variables
            data = _substitute_env_vars(data)

            # Load default profile
            self.default_profile_id = data.get("default")

            # Load global settings
            self.global_settings = data.get("global", {})

            # Load profiles
            profiles_data = data.get("profiles", {})
            for profile_id, profile_data in profiles_data.items():
                providers = []
                for provider_data in profile_data.get("providers", []):
                    provider = LLMProviderConfig(
                        name=provider_data.get("name", ""),
                        provider=provider_data.get("provider", "anthropic"),
                        model=provider_data.get("model", ""),
                        api_key=provider_data.get("api_key"),
                        api_key_env=provider_data.get("api_key_env"),
                        base_url=provider_data.get("base_url"),
                        timeout=provider_data.get("timeout", 60),
                        default=provider_data.get("default", False),
                    )
                    providers.append(provider)

                profile = LLMProfile(
                    profile_id=profile_id,
                    name=profile_data.get("name", profile_id),
                    description=profile_data.get("description", ""),
                    providers=providers,
                )
                self.profiles[profile_id] = profile

        except Exception as e:
            print(f"Warning: Failed to load LLM profiles from {config_path}: {e}")

    def save(self):
        """Save profiles to .llm_providers.yaml file."""
        config_path = Path.cwd() / ".llm_providers.yaml"

        data = {
            "default": self.default_profile_id,
            "profiles": {},
            "global": self.global_settings,
        }

        for profile_id, profile in self.profiles.items():
            data["profiles"][profile_id] = profile.to_dict()

        # Create backup
        if config_path.exists():
            backup_path = config_path.with_suffix(".yaml.backup")
            try:
                import shutil

                shutil.copy2(config_path, backup_path)
            except Exception as e:
                print(f"Warning: Failed to create backup: {e}")

        # Write new config
        try:
            with open(config_path, "w") as f:
                yaml.dump(data, f, default_flow_style=False, sort_keys=False)
        except Exception as e:
            raise Exception(f"Failed to save LLM profiles: {e}")

    def has_profiles(self) -> bool:
        """Check if any profiles are loaded."""
        return len(self.profiles) > 0

    def list_profiles(self) -> list[str]:
        """List all profile IDs."""
        return list(self.profiles.keys())

    def get_profile(self, profile_id: str | None = None) -> LLMProfile | None:
        """Get a profile by ID. If None, returns default profile."""
        if profile_id is None:
            profile_id = self.default_profile_id

        if profile_id is None:
            return None

        return self.profiles.get(profile_id)

    def add_profile(self, profile: LLMProfile):
        """Add or update a profile."""
        self.profiles[profile.profile_id] = profile

    def remove_profile(self, profile_id: str):
        """Remove a profile."""
        if profile_id in self.profiles:
            del self.profiles[profile_id]
            if self.default_profile_id == profile_id:
                self.default_profile_id = None

    def set_default_profile(self, profile_id: str):
        """Set the default profile."""
        if profile_id in self.profiles:
            self.default_profile_id = profile_id
        else:
            raise ValueError(f"Profile '{profile_id}' not found")


# Global instance
_llm_profile_config: LLMProfileConfig | None = None


def get_llm_profile_config() -> LLMProfileConfig:
    """Get or create global LLM profile configuration instance."""
    global _llm_profile_config
    if _llm_profile_config is None:
        _llm_profile_config = LLMProfileConfig()
    return _llm_profile_config


def reload_llm_profile_config():
    """Force reload of LLM profile configuration."""
    global _llm_profile_config
    _llm_profile_config = LLMProfileConfig()
    return _llm_profile_config


def load_llm_profile(profile_id: str | None = None) -> LLMProfile | None:
    """
    Load an LLM profile by ID.

    Args:
        profile_id: Profile ID to load. If None, loads default profile.

    Returns:
        LLMProfile if found, None otherwise.
    """
    config = get_llm_profile_config()
    return config.get_profile(profile_id)


def list_available_llm_profiles() -> list[str]:
    """List all available LLM profile IDs."""
    config = get_llm_profile_config()
    return config.list_profiles()


def get_default_llm_profile_id() -> str | None:
    """Get the default LLM profile ID."""
    config = get_llm_profile_config()
    return config.default_profile_id
