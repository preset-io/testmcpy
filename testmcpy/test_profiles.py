"""
Test Profile Management.

Manages test suite configurations with profile-based organization.
Allows users to define different test setups for different scenarios.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class TestConfig:
    """Configuration for a test suite."""

    name: str
    description: str
    tests_dir: str = "tests"  # Directory containing test files
    evaluators: list[str] = field(default_factory=list)  # Default evaluators
    timeout: int = 120
    parallel: bool = False
    max_retries: int = 0
    default: bool = False  # Mark this as default test config

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "description": self.description,
            "tests_dir": self.tests_dir,
            "evaluators": self.evaluators,
            "timeout": self.timeout,
            "parallel": self.parallel,
            "max_retries": self.max_retries,
            "default": self.default,
        }


@dataclass
class TestProfile:
    """Test profile containing test configurations."""

    profile_id: str
    name: str
    description: str
    test_configs: list[TestConfig] = field(default_factory=list)

    def get_default_config(self) -> TestConfig | None:
        """Get the default test config in this profile."""
        for config in self.test_configs:
            if config.default:
                return config
        # If no default marked, return first one
        return self.test_configs[0] if self.test_configs else None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "description": self.description,
            "test_configs": [c.to_dict() for c in self.test_configs],
        }


@dataclass
class TestProfileConfig:
    """Container for all test profiles."""

    profiles: dict[str, TestProfile] = field(default_factory=dict)
    default_profile_id: str | None = None
    global_settings: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Load profiles from .test_profiles.yaml if available."""
        self._load_profiles()

    def _load_profiles(self):
        """Load profiles from .test_profiles.yaml file."""
        config_path = Path.cwd() / ".test_profiles.yaml"

        if not config_path.exists():
            return

        try:
            with open(config_path) as f:
                data = yaml.safe_load(f)

            if not data:
                return

            # Load default profile
            self.default_profile_id = data.get("default")

            # Load global settings
            self.global_settings = data.get("global", {})

            # Load profiles
            profiles_data = data.get("profiles", {})
            for profile_id, profile_data in profiles_data.items():
                test_configs = []
                for config_data in profile_data.get("test_configs", []):
                    config = TestConfig(
                        name=config_data.get("name", ""),
                        description=config_data.get("description", ""),
                        tests_dir=config_data.get("tests_dir", "tests"),
                        evaluators=config_data.get("evaluators", []),
                        timeout=config_data.get("timeout", 120),
                        parallel=config_data.get("parallel", False),
                        max_retries=config_data.get("max_retries", 0),
                        default=config_data.get("default", False),
                    )
                    test_configs.append(config)

                profile = TestProfile(
                    profile_id=profile_id,
                    name=profile_data.get("name", profile_id),
                    description=profile_data.get("description", ""),
                    test_configs=test_configs,
                )
                self.profiles[profile_id] = profile

        except Exception as e:
            print(f"Warning: Failed to load test profiles from {config_path}: {e}")

    def save(self):
        """Save profiles to .test_profiles.yaml file."""
        config_path = Path.cwd() / ".test_profiles.yaml"

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
            raise Exception(f"Failed to save test profiles: {e}")

    def has_profiles(self) -> bool:
        """Check if any profiles are loaded."""
        return len(self.profiles) > 0

    def list_profiles(self) -> list[str]:
        """List all profile IDs."""
        return list(self.profiles.keys())

    def get_profile(self, profile_id: str | None = None) -> TestProfile | None:
        """Get a profile by ID. If None, returns default profile."""
        if profile_id is None:
            profile_id = self.default_profile_id

        if profile_id is None:
            return None

        return self.profiles.get(profile_id)

    def add_profile(self, profile: TestProfile):
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
_test_profile_config: TestProfileConfig | None = None


def get_test_profile_config() -> TestProfileConfig:
    """Get or create global test profile configuration instance."""
    global _test_profile_config
    if _test_profile_config is None:
        _test_profile_config = TestProfileConfig()
    return _test_profile_config


def reload_test_profile_config():
    """Force reload of test profile configuration."""
    global _test_profile_config
    _test_profile_config = TestProfileConfig()
    return _test_profile_config


def load_test_profile(profile_id: str | None = None) -> TestProfile | None:
    """
    Load a test profile by ID.

    Args:
        profile_id: Profile ID to load. If None, loads default profile.

    Returns:
        TestProfile if found, None otherwise.
    """
    config = get_test_profile_config()
    return config.get_profile(profile_id)


def list_available_test_profiles() -> list[str]:
    """List all available test profile IDs."""
    config = get_test_profile_config()
    return config.list_profiles()


def get_default_test_profile_id() -> str | None:
    """Get the default test profile ID."""
    config = get_test_profile_config()
    return config.default_profile_id
