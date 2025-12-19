"""
Unit tests for testmcpy.config module.

Tests configuration loading from multiple sources:
- Environment variables
- User config file (~/.testmcpy)
- Current directory .env file
- Profile configurations (MCP, LLM, Test)
- Default values
"""

from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

import pytest

from testmcpy.config import Config, get_config, reload_config


@pytest.fixture
def clean_env(monkeypatch):
    """Clean environment variables for testing."""
    # Remove all testmcpy-related env vars
    env_vars = [
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "OLLAMA_BASE_URL",
        "DEFAULT_MODEL",
        "DEFAULT_PROVIDER",
    ]
    for var in env_vars:
        monkeypatch.delenv(var, raising=False)
    return monkeypatch


@pytest.fixture
def mock_profile_modules():
    """Mock profile loading modules."""
    with (
        patch("testmcpy.config.load_profile") as mock_load_profile,
        patch("testmcpy.config.load_llm_profile") as mock_load_llm_profile,
        patch("testmcpy.config.load_test_profile") as mock_load_test_profile,
    ):
        # Default: return None for all profiles
        mock_load_profile.return_value = None
        mock_load_llm_profile.return_value = None
        mock_load_test_profile.return_value = None
        yield {
            "load_profile": mock_load_profile,
            "load_llm_profile": mock_load_llm_profile,
            "load_test_profile": mock_load_test_profile,
        }


class TestConfigInitialization:
    """Test Config class initialization and basic functionality."""

    def test_config_initialization_with_no_sources(self, clean_env, mock_profile_modules):
        """Test Config initialization with no configuration sources."""
        with patch("pathlib.Path.exists", return_value=False):
            config = Config()

            # Should be initialized with empty config
            assert config._config == {}
            assert config._sources == {}
            assert config._profile is None
            assert config._llm_profile is None
            assert config._test_profile is None

    def test_config_initialization_with_profile_ids(self, clean_env, mock_profile_modules):
        """Test Config initialization with profile IDs."""
        with patch("pathlib.Path.exists", return_value=False):
            config = Config(profile="test-mcp", llm_profile="test-llm", test_profile="test-suite")

            assert config._profile_id == "test-mcp"
            assert config._llm_profile_id == "test-llm"
            assert config._test_profile_id == "test-suite"

            # Verify profile loaders were called with correct IDs
            mock_profile_modules["load_profile"].assert_called_once_with("test-mcp")
            mock_profile_modules["load_llm_profile"].assert_called_once_with("test-llm")
            mock_profile_modules["load_test_profile"].assert_called_once_with("test-suite")

    def test_config_defaults_applied(self, clean_env, mock_profile_modules):
        """Test that default values are applied."""
        with patch("pathlib.Path.exists", return_value=False):
            # Set some defaults
            with patch.object(Config, "DEFAULTS", {"TEST_KEY": "test_value"}):
                config = Config()

                assert config.get("TEST_KEY") == "test_value"
                assert config.get_source("TEST_KEY") == "Default"


class TestEnvironmentVariables:
    """Test configuration loading from environment variables."""

    def test_generic_keys_from_environment(self, clean_env, mock_profile_modules):
        """Test loading generic keys from environment variables."""
        clean_env.setenv("ANTHROPIC_API_KEY", "test-anthropic-key")
        clean_env.setenv("OPENAI_API_KEY", "test-openai-key")
        clean_env.setenv("OLLAMA_BASE_URL", "http://localhost:11434")

        with patch("pathlib.Path.exists", return_value=False):
            config = Config()

            assert config.get("ANTHROPIC_API_KEY") == "test-anthropic-key"
            assert config.get("OPENAI_API_KEY") == "test-openai-key"
            assert config.get("OLLAMA_BASE_URL") == "http://localhost:11434"
            assert config.get_source("ANTHROPIC_API_KEY") == "Environment"
            assert config.get_source("OPENAI_API_KEY") == "Environment"
            assert config.get_source("OLLAMA_BASE_URL") == "Environment"

    def test_testmcpy_keys_from_environment(self, clean_env, mock_profile_modules):
        """Test loading testmcpy-specific keys from environment variables."""
        clean_env.setenv("DEFAULT_MODEL", "claude-3-opus")
        clean_env.setenv("DEFAULT_PROVIDER", "anthropic")

        with patch("pathlib.Path.exists", return_value=False):
            config = Config()

            assert config.get("DEFAULT_MODEL") == "claude-3-opus"
            assert config.get("DEFAULT_PROVIDER") == "anthropic"
            assert config.get_source("DEFAULT_MODEL") == "Environment"

    def test_environment_variables_ignored_if_not_in_keys(self, clean_env, mock_profile_modules):
        """Test that environment variables not in GENERIC_KEYS or TESTMCPY_KEYS are ignored."""
        clean_env.setenv("RANDOM_VAR", "random-value")

        with patch("pathlib.Path.exists", return_value=False):
            config = Config()

            assert config.get("RANDOM_VAR") is None


class TestEnvFileLoading:
    """Test configuration loading from .env files."""

    def test_load_user_config_file(self, clean_env, mock_profile_modules):
        """Test loading from ~/.testmcpy."""
        env_content = """
# User config file
ANTHROPIC_API_KEY=user-anthropic-key
DEFAULT_MODEL=claude-3-sonnet
"""

        def mock_exists_func(path_instance):
            return ".testmcpy" in str(path_instance)

        with (
            patch.object(Path, "exists", mock_exists_func),
            patch("builtins.open", mock_open(read_data=env_content)),
        ):
            config = Config()

            assert config.get("ANTHROPIC_API_KEY") == "user-anthropic-key"
            assert config.get("DEFAULT_MODEL") == "claude-3-sonnet"
            assert config.get_source("ANTHROPIC_API_KEY") == "~/.testmcpy"
            assert config.get_source("DEFAULT_MODEL") == "~/.testmcpy"

    def test_load_cwd_env_file(self, clean_env, mock_profile_modules):
        """Test loading from current directory .env file."""
        env_content = """
OPENAI_API_KEY=cwd-openai-key
DEFAULT_PROVIDER=openai
"""

        def mock_exists_func(path_instance):
            return ".env" in str(path_instance) and ".testmcpy" not in str(path_instance)

        with (
            patch.object(Path, "exists", mock_exists_func),
            patch("builtins.open", mock_open(read_data=env_content)),
        ):
            config = Config()

            assert config.get("OPENAI_API_KEY") == "cwd-openai-key"
            assert config.get("DEFAULT_PROVIDER") == "openai"
            assert config.get_source("OPENAI_API_KEY") == ".env (current dir)"

    def test_env_file_with_quotes(self, clean_env, mock_profile_modules):
        """Test parsing .env file with quoted values."""
        env_content = """
ANTHROPIC_API_KEY="quoted-key-double"
OPENAI_API_KEY='quoted-key-single'
OLLAMA_BASE_URL=http://localhost:11434
"""
        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("builtins.open", mock_open(read_data=env_content)),
        ):
            config = Config()

            assert config.get("ANTHROPIC_API_KEY") == "quoted-key-double"
            assert config.get("OPENAI_API_KEY") == "quoted-key-single"
            assert config.get("OLLAMA_BASE_URL") == "http://localhost:11434"

    def test_env_file_with_comments_and_empty_lines(self, clean_env, mock_profile_modules):
        """Test parsing .env file with comments and empty lines."""
        env_content = """
# This is a comment
ANTHROPIC_API_KEY=test-key

# Another comment
DEFAULT_MODEL=claude-3-opus
"""
        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("builtins.open", mock_open(read_data=env_content)),
        ):
            config = Config()

            assert config.get("ANTHROPIC_API_KEY") == "test-key"
            assert config.get("DEFAULT_MODEL") == "claude-3-opus"

    def test_env_file_with_malformed_lines(self, clean_env, mock_profile_modules):
        """Test that malformed lines in .env file are skipped."""
        env_content = """
ANTHROPIC_API_KEY=valid-key
MALFORMED_LINE_WITHOUT_EQUALS
DEFAULT_MODEL=claude-3-opus
"""
        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("builtins.open", mock_open(read_data=env_content)),
        ):
            config = Config()

            assert config.get("ANTHROPIC_API_KEY") == "valid-key"
            assert config.get("DEFAULT_MODEL") == "claude-3-opus"

    def test_env_file_read_error_silently_ignored(self, clean_env, mock_profile_modules):
        """Test that errors reading .env file are silently ignored."""
        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("builtins.open", side_effect=OSError("File read error")),
        ):
            # Should not raise exception
            config = Config()
            assert config._config == {}


class TestConfigPriority:
    """Test configuration priority order."""

    def test_cwd_env_overrides_user_config(self, clean_env, mock_profile_modules):
        """Test that .env in current directory overrides ~/.testmcpy."""
        user_config_content = "ANTHROPIC_API_KEY=user-key"
        cwd_env_content = "ANTHROPIC_API_KEY=cwd-key"

        with patch("pathlib.Path.exists", return_value=True), patch("builtins.open") as mock_file:
            # Mock file reads for different paths
            def open_side_effect(path, *args, **kwargs):
                if ".testmcpy" in str(path):
                    return mock_open(read_data=user_config_content)()
                elif ".env" in str(path):
                    return mock_open(read_data=cwd_env_content)()
                raise FileNotFoundError()

            mock_file.side_effect = open_side_effect

            config = Config()

            # .env should override ~/.testmcpy for TESTMCPY_KEYS
            assert config.get("ANTHROPIC_API_KEY") == "cwd-key"
            assert config.get_source("ANTHROPIC_API_KEY") == ".env (current dir)"

    def test_environment_not_overridden_by_config_files_for_generic_keys(
        self, clean_env, mock_profile_modules
    ):
        """Test that environment variables for generic keys are not overridden by config files."""
        clean_env.setenv("ANTHROPIC_API_KEY", "env-key")

        env_content = "ANTHROPIC_API_KEY=file-key"
        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("builtins.open", mock_open(read_data=env_content)),
        ):
            config = Config()

            # Environment should NOT be overridden for generic keys
            assert config.get("ANTHROPIC_API_KEY") == "env-key"
            assert config.get_source("ANTHROPIC_API_KEY") == "Environment"

    def test_testmcpy_keys_overridden_by_config_files(self, clean_env, mock_profile_modules):
        """Test that testmcpy-specific keys from environment are overridden by config files."""
        clean_env.setenv("DEFAULT_MODEL", "env-model")

        env_content = "DEFAULT_MODEL=file-model"
        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("builtins.open", mock_open(read_data=env_content)),
        ):
            config = Config()

            # Config file should override environment for TESTMCPY_KEYS
            assert config.get("DEFAULT_MODEL") == "file-model"
            assert config.get_source("DEFAULT_MODEL") in ["~/.testmcpy", ".env (current dir)"]


class TestLLMProfileIntegration:
    """Test LLM profile integration."""

    def test_llm_profile_sets_default_model_and_provider(self, clean_env):
        """Test that LLM profile sets DEFAULT_MODEL and DEFAULT_PROVIDER."""
        # Create mock LLM profile
        mock_provider = MagicMock()
        mock_provider.model = "claude-3-opus-20240229"
        mock_provider.provider = "anthropic"

        mock_llm_profile = MagicMock()
        mock_llm_profile.name = "Production"
        mock_llm_profile.get_default_provider.return_value = mock_provider

        with (
            patch("pathlib.Path.exists", return_value=False),
            patch("testmcpy.config.load_llm_profile", return_value=mock_llm_profile),
        ):
            config = Config(llm_profile="production")

            assert config.get("DEFAULT_MODEL") == "claude-3-opus-20240229"
            assert config.get("DEFAULT_PROVIDER") == "anthropic"
            assert config.get_source("DEFAULT_MODEL") == "LLM Profile (Production)"
            assert config.get_source("DEFAULT_PROVIDER") == "LLM Profile (Production)"

    def test_llm_profile_does_not_override_existing_config(self, clean_env):
        """Test that LLM profile doesn't override already-set config values."""
        env_content = "DEFAULT_MODEL=file-model\nDEFAULT_PROVIDER=file-provider"

        mock_provider = MagicMock()
        mock_provider.model = "claude-3-opus"
        mock_provider.provider = "anthropic"

        mock_llm_profile = MagicMock()
        mock_llm_profile.name = "Production"
        mock_llm_profile.get_default_provider.return_value = mock_provider

        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("builtins.open", mock_open(read_data=env_content)),
            patch("testmcpy.config.load_llm_profile", return_value=mock_llm_profile),
        ):
            config = Config(llm_profile="production")

            # Config file values should take precedence
            assert config.get("DEFAULT_MODEL") == "file-model"
            assert config.get("DEFAULT_PROVIDER") == "file-provider"

    def test_llm_profile_loading_failure_warning(self, clean_env):
        """Test that LLM profile loading failure issues a warning."""
        with (
            patch("pathlib.Path.exists", return_value=False),
            patch("testmcpy.config.load_llm_profile", side_effect=Exception("Profile not found")),
            patch("warnings.warn") as mock_warn,
        ):
            Config(llm_profile="nonexistent")

            # Should issue warning
            mock_warn.assert_called_once()
            assert "Failed to load LLM profile" in str(mock_warn.call_args[0][0])

    def test_llm_profile_with_no_default_provider(self, clean_env):
        """Test LLM profile when no default provider is configured."""
        mock_llm_profile = MagicMock()
        mock_llm_profile.get_default_provider.return_value = None

        with (
            patch("pathlib.Path.exists", return_value=False),
            patch("testmcpy.config.load_llm_profile", return_value=mock_llm_profile),
        ):
            config = Config(llm_profile="test")

            # Should not set DEFAULT_MODEL or DEFAULT_PROVIDER
            assert config.get("DEFAULT_MODEL") is None
            assert config.get("DEFAULT_PROVIDER") is None


class TestMCPProfileIntegration:
    """Test MCP profile integration."""

    def test_mcp_profile_loaded_and_stored(self, clean_env):
        """Test that MCP profile is loaded and stored."""
        mock_mcp_profile = MagicMock()
        mock_mcp_profile.name = "Development"

        with (
            patch("pathlib.Path.exists", return_value=False),
            patch("testmcpy.config.load_profile", return_value=mock_mcp_profile),
        ):
            config = Config(profile="dev")

            assert config._profile == mock_mcp_profile

    def test_mcp_profile_loading_failure_warning(self, clean_env):
        """Test that MCP profile loading failure issues a warning."""
        with (
            patch("pathlib.Path.exists", return_value=False),
            patch("testmcpy.config.load_profile", side_effect=Exception("Profile not found")),
            patch("warnings.warn") as mock_warn,
        ):
            Config(profile="nonexistent")

            # Should issue warning
            mock_warn.assert_called_once()
            assert "Failed to load MCP profile" in str(mock_warn.call_args[0][0])

    def test_get_default_mcp_server_with_default_marked(self, clean_env):
        """Test getting default MCP server when one is marked as default."""
        mock_server1 = MagicMock()
        mock_server1.default = False
        mock_server1.mcp_url = "http://server1.com"

        mock_server2 = MagicMock()
        mock_server2.default = True
        mock_server2.mcp_url = "http://server2.com"

        mock_profile = MagicMock()
        mock_profile.mcps = [mock_server1, mock_server2]

        with (
            patch("pathlib.Path.exists", return_value=False),
            patch("testmcpy.config.load_profile", return_value=mock_profile),
        ):
            config = Config(profile="test")

            default_server = config.get_default_mcp_server()
            assert default_server == mock_server2
            assert config.get_mcp_url() == "http://server2.com"

    def test_get_default_mcp_server_first_when_none_marked(self, clean_env):
        """Test getting first MCP server when none is marked as default."""
        mock_server1 = MagicMock()
        mock_server1.default = False
        mock_server1.mcp_url = "http://server1.com"

        mock_server2 = MagicMock()
        mock_server2.default = False
        mock_server2.mcp_url = "http://server2.com"

        mock_profile = MagicMock()
        mock_profile.mcps = [mock_server1, mock_server2]

        with (
            patch("pathlib.Path.exists", return_value=False),
            patch("testmcpy.config.load_profile", return_value=mock_profile),
        ):
            config = Config(profile="test")

            default_server = config.get_default_mcp_server()
            assert default_server == mock_server1

    def test_get_default_mcp_server_none_when_no_profile(self, clean_env):
        """Test getting default MCP server returns None when no profile."""
        with (
            patch("pathlib.Path.exists", return_value=False),
            patch("testmcpy.config.load_profile", return_value=None),
        ):
            config = Config()

            assert config.get_default_mcp_server() is None
            assert config.get_mcp_url() is None

    def test_get_default_mcp_server_none_when_no_mcps(self, clean_env):
        """Test getting default MCP server returns None when profile has no MCPs."""
        mock_profile = MagicMock()
        mock_profile.mcps = []

        with (
            patch("pathlib.Path.exists", return_value=False),
            patch("testmcpy.config.load_profile", return_value=mock_profile),
        ):
            config = Config(profile="test")

            assert config.get_default_mcp_server() is None
            assert config.get_mcp_url() is None


class TestTestProfileIntegration:
    """Test profile integration."""

    def test_test_profile_loaded_and_stored(self, clean_env):
        """Test that test profile is loaded and stored."""
        mock_test_profile = MagicMock()
        mock_test_profile.name = "Integration Tests"

        with (
            patch("pathlib.Path.exists", return_value=False),
            patch("testmcpy.config.load_test_profile", return_value=mock_test_profile),
        ):
            config = Config(test_profile="integration")

            assert config._test_profile == mock_test_profile

    def test_test_profile_loading_failure_warning(self, clean_env):
        """Test that test profile loading failure issues a warning."""
        with (
            patch("pathlib.Path.exists", return_value=False),
            patch("testmcpy.config.load_test_profile", side_effect=Exception("Profile not found")),
            patch("warnings.warn") as mock_warn,
        ):
            Config(test_profile="nonexistent")

            # Should issue warning
            mock_warn.assert_called_once()
            assert "Failed to load Test profile" in str(mock_warn.call_args[0][0])

    def test_get_default_test_config(self, clean_env):
        """Test getting default test config from test profile."""
        mock_test_config = MagicMock()
        mock_test_profile = MagicMock()
        mock_test_profile.get_default_config.return_value = mock_test_config

        with (
            patch("pathlib.Path.exists", return_value=False),
            patch("testmcpy.config.load_test_profile", return_value=mock_test_profile),
        ):
            config = Config(test_profile="test")

            default_config = config.get_default_test_config()
            assert default_config == mock_test_config

    def test_get_default_test_config_none_when_no_profile(self, clean_env):
        """Test getting default test config returns None when no profile."""
        with (
            patch("pathlib.Path.exists", return_value=False),
            patch("testmcpy.config.load_test_profile", return_value=None),
        ):
            config = Config()

            assert config.get_default_test_config() is None


class TestConfigProperties:
    """Test Config property accessors."""

    def test_default_model_property(self, clean_env, mock_profile_modules):
        """Test default_model property."""
        env_content = "DEFAULT_MODEL=claude-3-opus"
        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("builtins.open", mock_open(read_data=env_content)),
        ):
            config = Config()

            assert config.default_model == "claude-3-opus"

    def test_default_provider_property(self, clean_env, mock_profile_modules):
        """Test default_provider property."""
        env_content = "DEFAULT_PROVIDER=anthropic"
        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("builtins.open", mock_open(read_data=env_content)),
        ):
            config = Config()

            assert config.default_provider == "anthropic"

    def test_anthropic_api_key_property(self, clean_env, mock_profile_modules):
        """Test anthropic_api_key property."""
        clean_env.setenv("ANTHROPIC_API_KEY", "test-key")
        with patch("pathlib.Path.exists", return_value=False):
            config = Config()

            assert config.anthropic_api_key == "test-key"

    def test_openai_api_key_property(self, clean_env, mock_profile_modules):
        """Test openai_api_key property."""
        clean_env.setenv("OPENAI_API_KEY", "test-key")
        with patch("pathlib.Path.exists", return_value=False):
            config = Config()

            assert config.openai_api_key == "test-key"

    def test_properties_return_none_when_not_set(self, clean_env, mock_profile_modules):
        """Test that properties return None when config values not set."""
        with patch("pathlib.Path.exists", return_value=False):
            config = Config()

            assert config.default_model is None
            assert config.default_provider is None
            assert config.anthropic_api_key is None
            assert config.openai_api_key is None


class TestConfigGetters:
    """Test Config getter methods."""

    def test_get_with_default(self, clean_env, mock_profile_modules):
        """Test get method with default value."""
        with patch("pathlib.Path.exists", return_value=False):
            config = Config()

            assert config.get("NONEXISTENT_KEY", "default-value") == "default-value"

    def test_get_without_default(self, clean_env, mock_profile_modules):
        """Test get method without default value."""
        with patch("pathlib.Path.exists", return_value=False):
            config = Config()

            assert config.get("NONEXISTENT_KEY") is None

    def test_get_existing_value(self, clean_env, mock_profile_modules):
        """Test get method for existing value."""
        clean_env.setenv("ANTHROPIC_API_KEY", "test-key")
        with patch("pathlib.Path.exists", return_value=False):
            config = Config()

            assert config.get("ANTHROPIC_API_KEY") == "test-key"

    def test_get_source_for_existing_key(self, clean_env, mock_profile_modules):
        """Test get_source method for existing key."""
        clean_env.setenv("ANTHROPIC_API_KEY", "test-key")
        with patch("pathlib.Path.exists", return_value=False):
            config = Config()

            assert config.get_source("ANTHROPIC_API_KEY") == "Environment"

    def test_get_source_for_nonexistent_key(self, clean_env, mock_profile_modules):
        """Test get_source method for nonexistent key."""
        with patch("pathlib.Path.exists", return_value=False):
            config = Config()

            assert config.get_source("NONEXISTENT_KEY") == "Not set"

    def test_get_all(self, clean_env, mock_profile_modules):
        """Test get_all method."""
        clean_env.setenv("ANTHROPIC_API_KEY", "test-key")
        clean_env.setenv("OPENAI_API_KEY", "openai-key")

        with patch("pathlib.Path.exists", return_value=False):
            config = Config()

            all_config = config.get_all()
            assert all_config["ANTHROPIC_API_KEY"] == "test-key"
            assert all_config["OPENAI_API_KEY"] == "openai-key"

            # Should be a copy
            all_config["NEW_KEY"] = "new-value"
            assert config.get("NEW_KEY") is None

    def test_get_all_with_sources(self, clean_env, mock_profile_modules):
        """Test get_all_with_sources method."""
        clean_env.setenv("ANTHROPIC_API_KEY", "test-key")

        with patch("pathlib.Path.exists", return_value=False):
            config = Config()

            all_with_sources = config.get_all_with_sources()
            assert all_with_sources["ANTHROPIC_API_KEY"] == ("test-key", "Environment")


class TestGetDefaultLLMProvider:
    """Test get_default_llm_provider method."""

    def test_get_default_llm_provider(self, clean_env):
        """Test getting default LLM provider from profile."""
        mock_provider = MagicMock()
        mock_llm_profile = MagicMock()
        mock_llm_profile.get_default_provider.return_value = mock_provider

        with (
            patch("pathlib.Path.exists", return_value=False),
            patch("testmcpy.config.load_llm_profile", return_value=mock_llm_profile),
        ):
            config = Config(llm_profile="test")

            assert config.get_default_llm_provider() == mock_provider

    def test_get_default_llm_provider_none_when_no_profile(self, clean_env):
        """Test getting default LLM provider returns None when no profile."""
        with (
            patch("pathlib.Path.exists", return_value=False),
            patch("testmcpy.config.load_llm_profile", return_value=None),
        ):
            config = Config()

            assert config.get_default_llm_provider() is None


class TestGlobalConfigInstance:
    """Test global config instance management."""

    def test_get_config_creates_instance(self, clean_env, mock_profile_modules):
        """Test that get_config() creates a global instance."""
        # Reset global config
        import testmcpy.config as config_module

        config_module._config = None

        with patch("pathlib.Path.exists", return_value=False):
            config = get_config()

            assert config is not None
            assert isinstance(config, Config)

    def test_get_config_returns_same_instance(self, clean_env, mock_profile_modules):
        """Test that get_config() returns the same instance."""
        import testmcpy.config as config_module

        config_module._config = None

        with patch("pathlib.Path.exists", return_value=False):
            config1 = get_config()
            config2 = get_config()

            assert config1 is config2

    def test_reload_config_creates_new_instance(self, clean_env, mock_profile_modules):
        """Test that reload_config() creates a new instance."""
        import testmcpy.config as config_module

        config_module._config = None

        with patch("pathlib.Path.exists", return_value=False):
            config1 = get_config()
            reload_config()
            config2 = get_config()

            assert config1 is not config2


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_empty_env_file(self, clean_env, mock_profile_modules):
        """Test handling of empty .env file."""
        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("builtins.open", mock_open(read_data="")),
        ):
            # Should not raise exception
            config = Config()
            assert config._config == {}

    def test_env_file_with_only_comments(self, clean_env, mock_profile_modules):
        """Test handling of .env file with only comments."""
        env_content = """
# Comment 1
# Comment 2
# Comment 3
"""
        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("builtins.open", mock_open(read_data=env_content)),
        ):
            config = Config()
            assert config._config == {}

    def test_env_file_with_whitespace_only_lines(self, clean_env, mock_profile_modules):
        """Test handling of .env file with whitespace-only lines."""
        env_content = """


\t\t
ANTHROPIC_API_KEY=test-key

"""
        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("builtins.open", mock_open(read_data=env_content)),
        ):
            config = Config()
            assert config.get("ANTHROPIC_API_KEY") == "test-key"

    def test_env_file_with_multiple_equals_signs(self, clean_env, mock_profile_modules):
        """Test handling of values with multiple equals signs."""
        env_content = "ANTHROPIC_API_KEY=value=with=equals"
        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("builtins.open", mock_open(read_data=env_content)),
        ):
            config = Config()
            assert config.get("ANTHROPIC_API_KEY") == "value=with=equals"

    def test_env_file_with_empty_value(self, clean_env, mock_profile_modules):
        """Test handling of empty values in .env file."""
        env_content = "ANTHROPIC_API_KEY="
        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("builtins.open", mock_open(read_data=env_content)),
        ):
            config = Config()
            assert config.get("ANTHROPIC_API_KEY") == ""

    def test_profile_loading_with_none_profile_id(self, clean_env):
        """Test profile loading with None as profile_id."""
        with (
            patch("pathlib.Path.exists", return_value=False),
            patch("testmcpy.config.load_profile") as mock_load,
            patch("testmcpy.config.load_llm_profile") as mock_load_llm,
            patch("testmcpy.config.load_test_profile") as mock_load_test,
        ):
            mock_load.return_value = None
            mock_load_llm.return_value = None
            mock_load_test.return_value = None

            Config(profile=None, llm_profile=None, test_profile=None)

            # Should still call loaders (they handle None internally)
            mock_load.assert_called_once_with(None)
            mock_load_llm.assert_called_once_with(None)
            mock_load_test.assert_called_once_with(None)

    def test_config_with_all_sources_combined(self, clean_env):
        """Test configuration with all sources providing values."""
        # 1. Environment variables
        clean_env.setenv("ANTHROPIC_API_KEY", "env-key")
        clean_env.setenv("DEFAULT_MODEL", "env-model")

        # 2. User config file
        user_config_content = """
OPENAI_API_KEY=user-openai-key
DEFAULT_MODEL=user-model
"""

        # 3. CWD .env file
        cwd_env_content = """
OLLAMA_BASE_URL=http://localhost:11434
DEFAULT_MODEL=cwd-model
"""

        # 4. LLM profile
        mock_provider = MagicMock()
        mock_provider.model = "profile-model"
        mock_provider.provider = "anthropic"
        mock_llm_profile = MagicMock()
        mock_llm_profile.name = "Production"
        mock_llm_profile.get_default_provider.return_value = mock_provider

        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("builtins.open") as mock_file,
            patch("testmcpy.config.load_llm_profile", return_value=mock_llm_profile),
        ):

            def open_side_effect(path, *args, **kwargs):
                if ".testmcpy" in str(path):
                    return mock_open(read_data=user_config_content)()
                elif ".env" in str(path):
                    return mock_open(read_data=cwd_env_content)()
                raise FileNotFoundError()

            mock_file.side_effect = open_side_effect

            config = Config(llm_profile="production")

            # Verify priority order
            # ANTHROPIC_API_KEY: Environment (generic key, not overridden)
            assert config.get("ANTHROPIC_API_KEY") == "env-key"
            assert config.get_source("ANTHROPIC_API_KEY") == "Environment"

            # DEFAULT_MODEL: CWD .env (testmcpy key, overridden by file)
            assert config.get("DEFAULT_MODEL") == "cwd-model"

            # OPENAI_API_KEY: User config (only set there)
            assert config.get("OPENAI_API_KEY") == "user-openai-key"

            # OLLAMA_BASE_URL: CWD .env (only set there)
            assert config.get("OLLAMA_BASE_URL") == "http://localhost:11434"
