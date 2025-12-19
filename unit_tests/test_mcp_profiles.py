"""Unit tests for MCP profiles module."""

from pathlib import Path
from unittest.mock import patch

import yaml

from testmcpy.mcp_profiles import (
    AuthConfig,
    MCPProfile,
    MCPProfileConfig,
    MCPServer,
    get_profile_config,
    list_available_profiles,
    load_mcp_profiles,
    load_profile,
    reload_profile_config,
)


class TestAuthConfig:
    """Tests for AuthConfig dataclass."""

    def test_auth_config_none(self):
        """Test AuthConfig with no authentication."""
        auth = AuthConfig(auth_type="none")
        assert auth.auth_type == "none"
        assert auth.token is None
        assert auth.to_dict() == {"type": "none"}

    def test_auth_config_bearer(self):
        """Test AuthConfig with bearer token."""
        auth = AuthConfig(auth_type="bearer", token="secret-token")
        assert auth.auth_type == "bearer"
        assert auth.token == "secret-token"
        assert auth.to_dict() == {"type": "bearer", "token": "secret-token"}

    def test_auth_config_bearer_no_token(self):
        """Test AuthConfig with bearer type but no token."""
        auth = AuthConfig(auth_type="bearer")
        result = auth.to_dict()
        assert result == {"type": "bearer"}

    def test_auth_config_jwt(self):
        """Test AuthConfig with JWT authentication."""
        auth = AuthConfig(
            auth_type="jwt",
            api_url="https://api.example.com",
            api_token="token123",
            api_secret="secret456",
        )
        result = auth.to_dict()
        assert result["type"] == "jwt"
        assert result["api_url"] == "https://api.example.com"
        assert result["api_token"] == "token123"
        assert result["api_secret"] == "secret456"

    def test_auth_config_oauth(self):
        """Test AuthConfig with OAuth authentication."""
        auth = AuthConfig(
            auth_type="oauth",
            client_id="client123",
            client_secret="secret456",
            token_url="https://oauth.example.com/token",
            scopes=["read", "write"],
        )
        result = auth.to_dict()
        assert result["type"] == "oauth"
        assert result["client_id"] == "client123"
        assert result["client_secret"] == "secret456"
        assert result["token_url"] == "https://oauth.example.com/token"
        assert result["scopes"] == ["read", "write"]

    def test_auth_config_oauth_auto_discover(self):
        """Test AuthConfig with OAuth auto-discovery enabled."""
        auth = AuthConfig(
            auth_type="oauth",
            client_id="client123",
            client_secret="secret456",
            oauth_auto_discover=True,
        )
        result = auth.to_dict()
        assert result["oauth_auto_discover"] is True

    def test_auth_config_insecure_ssl(self):
        """Test AuthConfig with insecure SSL option."""
        auth = AuthConfig(auth_type="bearer", token="token", insecure=True)
        result = auth.to_dict()
        assert result["insecure"] is True

    def test_auth_config_insecure_false_not_included(self):
        """Test that insecure=False is not included in output."""
        auth = AuthConfig(auth_type="bearer", token="token", insecure=False)
        result = auth.to_dict()
        assert "insecure" not in result


class TestMCPServer:
    """Tests for MCPServer dataclass."""

    def test_mcp_server_basic(self):
        """Test basic MCPServer creation."""
        auth = AuthConfig(auth_type="none")
        server = MCPServer(
            name="test-server",
            mcp_url="http://localhost:8000",
            auth=auth,
        )
        assert server.name == "test-server"
        assert server.mcp_url == "http://localhost:8000"
        assert server.timeout == 30
        assert server.rate_limit_rpm == 60
        assert server.default is False

    def test_mcp_server_custom_settings(self):
        """Test MCPServer with custom timeout and rate limit."""
        auth = AuthConfig(auth_type="bearer", token="token")
        server = MCPServer(
            name="custom-server",
            mcp_url="http://api.example.com",
            auth=auth,
            timeout=60,
            rate_limit_rpm=120,
            default=True,
        )
        assert server.timeout == 60
        assert server.rate_limit_rpm == 120
        assert server.default is True


class TestMCPProfile:
    """Tests for MCPProfile dataclass."""

    def test_mcp_profile_single_server(self):
        """Test MCPProfile with a single server."""
        auth = AuthConfig(auth_type="none")
        server = MCPServer(name="server1", mcp_url="http://localhost:8000", auth=auth)
        profile = MCPProfile(
            name="Test Profile",
            profile_id="test-profile",
            description="A test profile",
            mcps=[server],
        )
        assert profile.name == "Test Profile"
        assert profile.profile_id == "test-profile"
        assert profile.description == "A test profile"
        assert len(profile.mcps) == 1
        assert profile.mcps[0].name == "server1"

    def test_mcp_profile_multiple_servers(self):
        """Test MCPProfile with multiple servers."""
        auth = AuthConfig(auth_type="none")
        server1 = MCPServer(name="server1", mcp_url="http://localhost:8000", auth=auth)
        server2 = MCPServer(name="server2", mcp_url="http://localhost:8001", auth=auth)
        profile = MCPProfile(
            name="Multi Server",
            profile_id="multi",
            description="Multiple servers",
            mcps=[server1, server2],
        )
        assert len(profile.mcps) == 2


class TestMCPProfileConfig:
    """Tests for MCPProfileConfig class."""

    def test_no_config_file(self):
        """Test initialization when no config file exists."""
        with patch.object(Path, "exists", return_value=False):
            config = MCPProfileConfig()
            assert config.config_path is None
            assert len(config.profiles) == 0
            assert config.default_profile is None

    def test_explicit_config_path(self, tmp_path):
        """Test initialization with explicit config path."""
        config_file = tmp_path / "mcp_config.yaml"
        config_content = {
            "default": "dev",
            "profiles": {
                "dev": {
                    "name": "Development",
                    "mcp_url": "http://localhost:8000",
                    "auth": {"type": "none"},
                }
            },
        }
        config_file.write_text(yaml.dump(config_content))

        config = MCPProfileConfig(config_path=str(config_file))
        assert config.config_path == config_file
        assert len(config.profiles) == 1

    def test_explicit_config_path_not_exists(self):
        """Test initialization with explicit but non-existent config path."""
        config = MCPProfileConfig(config_path="/nonexistent/path.yaml")
        assert config.config_path is None
        assert len(config.profiles) == 0

    def test_find_config_in_cwd(self, tmp_path, monkeypatch):
        """Test finding config file in current working directory."""
        monkeypatch.chdir(tmp_path)
        config_file = tmp_path / ".mcp_services.yaml"
        config_content = {
            "default": "local",
            "profiles": {
                "local": {
                    "name": "Local",
                    "mcp_url": "http://localhost:8000",
                    "auth": {"type": "none"},
                }
            },
        }
        config_file.write_text(yaml.dump(config_content))

        config = MCPProfileConfig()
        assert config.config_path == config_file

    def test_load_basic_config(self, tmp_path):
        """Test loading a basic configuration file."""
        config_file = tmp_path / "config.yaml"
        config_content = {
            "default": "dev",
            "profiles": {
                "dev": {
                    "name": "Development",
                    "description": "Dev environment",
                    "mcp_url": "http://localhost:8000",
                    "auth": {"type": "none"},
                }
            },
        }
        config_file.write_text(yaml.dump(config_content))

        config = MCPProfileConfig(config_path=str(config_file))
        assert config.default_profile == "dev"
        assert "dev" in config.profiles
        profile = config.profiles["dev"]
        assert profile.name == "Development"
        assert profile.description == "Dev environment"
        assert len(profile.mcps) == 1
        assert profile.mcps[0].mcp_url == "http://localhost:8000"

    def test_load_config_with_multiple_profiles(self, tmp_path):
        """Test loading config with multiple profiles."""
        config_file = tmp_path / "config.yaml"
        config_content = {
            "default": "dev",
            "profiles": {
                "dev": {
                    "name": "Development",
                    "mcp_url": "http://localhost:8000",
                    "auth": {"type": "none"},
                },
                "prod": {
                    "name": "Production",
                    "mcp_url": "https://api.example.com",
                    "auth": {"type": "bearer", "token": "prod-token"},
                },
            },
        }
        config_file.write_text(yaml.dump(config_content))

        config = MCPProfileConfig(config_path=str(config_file))
        assert len(config.profiles) == 2
        assert "dev" in config.profiles
        assert "prod" in config.profiles

    def test_load_config_with_mcps_array(self, tmp_path):
        """Test loading config with multiple MCPs in a profile."""
        config_file = tmp_path / "config.yaml"
        config_content = {
            "default": "multi",
            "profiles": {
                "multi": {
                    "name": "Multi MCP",
                    "mcps": [
                        {
                            "name": "MCP1",
                            "mcp_url": "http://localhost:8000",
                            "auth": {"type": "none"},
                        },
                        {
                            "name": "MCP2",
                            "mcp_url": "http://localhost:8001",
                            "auth": {"type": "bearer", "token": "token2"},
                            "default": True,
                        },
                    ],
                }
            },
        }
        config_file.write_text(yaml.dump(config_content))

        config = MCPProfileConfig(config_path=str(config_file))
        profile = config.profiles["multi"]
        assert len(profile.mcps) == 2
        assert profile.mcps[0].name == "MCP1"
        assert profile.mcps[1].name == "MCP2"
        assert profile.mcps[1].default is True

    def test_load_config_empty_file(self, tmp_path):
        """Test loading an empty config file."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("")

        config = MCPProfileConfig(config_path=str(config_file))
        assert len(config.profiles) == 0

    def test_load_config_invalid_yaml(self, tmp_path):
        """Test loading a malformed YAML file."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("invalid: yaml: content: [[[")

        config = MCPProfileConfig(config_path=str(config_file))
        assert len(config.profiles) == 0

    def test_load_config_profiles_not_dict(self, tmp_path):
        """Test handling when 'profiles' is not a dictionary."""
        config_file = tmp_path / "config.yaml"
        config_content = {"default": "dev", "profiles": ["not", "a", "dict"]}
        config_file.write_text(yaml.dump(config_content))

        config = MCPProfileConfig(config_path=str(config_file))
        assert len(config.profiles) == 0

    def test_load_config_profile_data_not_dict(self, tmp_path):
        """Test handling when profile data is not a dictionary."""
        config_file = tmp_path / "config.yaml"
        config_content = {"default": "dev", "profiles": {"dev": "not a dict"}}
        config_file.write_text(yaml.dump(config_content))

        config = MCPProfileConfig(config_path=str(config_file))
        assert len(config.profiles) == 0

    def test_load_config_missing_mcp_url_in_array(self, tmp_path):
        """Test handling MCPs array with missing mcp_url."""
        config_file = tmp_path / "config.yaml"
        config_content = {
            "default": "test",
            "profiles": {
                "test": {
                    "name": "Test",
                    "mcps": [
                        {"name": "MCP1"},  # Missing mcp_url
                        {
                            "name": "MCP2",
                            "mcp_url": "http://localhost:8000",
                            "auth": {"type": "none"},
                        },
                    ],
                }
            },
        }
        config_file.write_text(yaml.dump(config_content))

        config = MCPProfileConfig(config_path=str(config_file))
        profile = config.profiles["test"]
        # Should only load MCP2
        assert len(profile.mcps) == 1
        assert profile.mcps[0].name == "MCP2"

    def test_load_config_mcps_not_list(self, tmp_path):
        """Test handling when mcps is not a list."""
        config_file = tmp_path / "config.yaml"
        config_content = {
            "default": "test",
            "profiles": {"test": {"name": "Test", "mcps": "not a list"}},
        }
        config_file.write_text(yaml.dump(config_content))

        config = MCPProfileConfig(config_path=str(config_file))
        profile = config.profiles["test"]
        assert len(profile.mcps) == 0

    def test_load_config_mcp_entry_not_dict(self, tmp_path):
        """Test handling when MCP entry is not a dictionary."""
        config_file = tmp_path / "config.yaml"
        config_content = {
            "default": "test",
            "profiles": {
                "test": {
                    "name": "Test",
                    "mcps": [
                        "not a dict",
                        {
                            "name": "MCP2",
                            "mcp_url": "http://localhost:8000",
                            "auth": {"type": "none"},
                        },
                    ],
                }
            },
        }
        config_file.write_text(yaml.dump(config_content))

        config = MCPProfileConfig(config_path=str(config_file))
        profile = config.profiles["test"]
        # Should only load MCP2
        assert len(profile.mcps) == 1
        assert profile.mcps[0].name == "MCP2"

    def test_env_var_substitution_simple(self, tmp_path, monkeypatch):
        """Test environment variable substitution with simple syntax."""
        monkeypatch.setenv("TEST_TOKEN", "secret-token-123")
        config_file = tmp_path / "config.yaml"
        config_content = {
            "default": "dev",
            "profiles": {
                "dev": {
                    "name": "Development",
                    "mcp_url": "http://localhost:8000",
                    "auth": {"type": "bearer", "token": "${TEST_TOKEN}"},
                }
            },
        }
        config_file.write_text(yaml.dump(config_content))

        config = MCPProfileConfig(config_path=str(config_file))
        profile = config.profiles["dev"]
        assert profile.mcps[0].auth.token == "secret-token-123"

    def test_env_var_substitution_with_default(self, tmp_path):
        """Test environment variable substitution with default value."""
        config_file = tmp_path / "config.yaml"
        config_content = {
            "default": "dev",
            "profiles": {
                "dev": {
                    "name": "Development",
                    "mcp_url": "http://localhost:8000",
                    "auth": {
                        "type": "bearer",
                        "token": "${NONEXISTENT_VAR:-default-token}",
                    },
                }
            },
        }
        config_file.write_text(yaml.dump(config_content))

        config = MCPProfileConfig(config_path=str(config_file))
        profile = config.profiles["dev"]
        assert profile.mcps[0].auth.token == "default-token"

    def test_env_var_substitution_missing_no_default(self, tmp_path):
        """Test environment variable substitution when var is missing and no default."""
        config_file = tmp_path / "config.yaml"
        config_content = {
            "default": "dev",
            "profiles": {
                "dev": {
                    "name": "Development",
                    "mcp_url": "http://localhost:8000",
                    "auth": {"type": "bearer", "token": "${NONEXISTENT_VAR}"},
                }
            },
        }
        config_file.write_text(yaml.dump(config_content))

        config = MCPProfileConfig(config_path=str(config_file))
        profile = config.profiles["dev"]
        # Should default to empty string
        assert profile.mcps[0].auth.token == ""

    def test_env_var_substitution_nested_dict(self, tmp_path, monkeypatch):
        """Test environment variable substitution in nested dictionaries."""
        monkeypatch.setenv("API_URL", "https://api.example.com")
        monkeypatch.setenv("API_TOKEN", "token123")
        config_file = tmp_path / "config.yaml"
        config_content = {
            "default": "dev",
            "profiles": {
                "dev": {
                    "name": "Development",
                    "mcp_url": "http://localhost:8000",
                    "auth": {
                        "type": "jwt",
                        "api_url": "${API_URL}",
                        "api_token": "${API_TOKEN}",
                    },
                }
            },
        }
        config_file.write_text(yaml.dump(config_content))

        config = MCPProfileConfig(config_path=str(config_file))
        profile = config.profiles["dev"]
        assert profile.mcps[0].auth.api_url == "https://api.example.com"
        assert profile.mcps[0].auth.api_token == "token123"

    def test_env_var_substitution_in_list(self, tmp_path, monkeypatch):
        """Test environment variable substitution in lists."""
        monkeypatch.setenv("SCOPE1", "read")
        monkeypatch.setenv("SCOPE2", "write")
        config_file = tmp_path / "config.yaml"
        config_content = {
            "default": "dev",
            "profiles": {
                "dev": {
                    "name": "Development",
                    "mcp_url": "http://localhost:8000",
                    "auth": {
                        "type": "oauth",
                        "scopes": ["${SCOPE1}", "${SCOPE2}"],
                    },
                }
            },
        }
        config_file.write_text(yaml.dump(config_content))

        config = MCPProfileConfig(config_path=str(config_file))
        profile = config.profiles["dev"]
        assert profile.mcps[0].auth.scopes == ["read", "write"]

    def test_global_timeout_config(self, tmp_path):
        """Test global timeout configuration."""
        config_file = tmp_path / "config.yaml"
        config_content = {
            "default": "dev",
            "global": {"timeout": 60},
            "profiles": {
                "dev": {
                    "name": "Development",
                    "mcp_url": "http://localhost:8000",
                    "auth": {"type": "none"},
                }
            },
        }
        config_file.write_text(yaml.dump(config_content))

        config = MCPProfileConfig(config_path=str(config_file))
        profile = config.profiles["dev"]
        assert profile.timeout == 60
        assert profile.mcps[0].timeout == 60

    def test_profile_timeout_overrides_global(self, tmp_path):
        """Test that profile timeout overrides global timeout."""
        config_file = tmp_path / "config.yaml"
        config_content = {
            "default": "dev",
            "global": {"timeout": 60},
            "profiles": {
                "dev": {
                    "name": "Development",
                    "mcp_url": "http://localhost:8000",
                    "auth": {"type": "none"},
                    "timeout": 120,
                }
            },
        }
        config_file.write_text(yaml.dump(config_content))

        config = MCPProfileConfig(config_path=str(config_file))
        profile = config.profiles["dev"]
        assert profile.timeout == 120

    def test_global_rate_limit_config(self, tmp_path):
        """Test global rate limit configuration."""
        config_file = tmp_path / "config.yaml"
        config_content = {
            "default": "dev",
            "global": {"rate_limit": {"requests_per_minute": 120}},
            "profiles": {
                "dev": {
                    "name": "Development",
                    "mcp_url": "http://localhost:8000",
                    "auth": {"type": "none"},
                }
            },
        }
        config_file.write_text(yaml.dump(config_content))

        config = MCPProfileConfig(config_path=str(config_file))
        profile = config.profiles["dev"]
        assert profile.rate_limit_rpm == 120
        assert profile.mcps[0].rate_limit_rpm == 120

    def test_profile_rate_limit_overrides_global(self, tmp_path):
        """Test that profile rate limit overrides global rate limit."""
        config_file = tmp_path / "config.yaml"
        config_content = {
            "default": "dev",
            "global": {"rate_limit": {"requests_per_minute": 120}},
            "profiles": {
                "dev": {
                    "name": "Development",
                    "mcp_url": "http://localhost:8000",
                    "auth": {"type": "none"},
                    "rate_limit": {"requests_per_minute": 240},
                }
            },
        }
        config_file.write_text(yaml.dump(config_content))

        config = MCPProfileConfig(config_path=str(config_file))
        profile = config.profiles["dev"]
        assert profile.rate_limit_rpm == 240

    def test_get_profile_by_id(self, tmp_path):
        """Test getting a profile by ID."""
        config_file = tmp_path / "config.yaml"
        config_content = {
            "default": "dev",
            "profiles": {
                "dev": {
                    "name": "Development",
                    "mcp_url": "http://localhost:8000",
                    "auth": {"type": "none"},
                },
                "prod": {
                    "name": "Production",
                    "mcp_url": "https://api.example.com",
                    "auth": {"type": "bearer", "token": "token"},
                },
            },
        }
        config_file.write_text(yaml.dump(config_content))

        config = MCPProfileConfig(config_path=str(config_file))
        profile = config.get_profile("prod")
        assert profile is not None
        assert profile.profile_id == "prod"
        assert profile.name == "Production"

    def test_get_profile_default(self, tmp_path):
        """Test getting default profile when no ID specified."""
        config_file = tmp_path / "config.yaml"
        config_content = {
            "default": "dev",
            "profiles": {
                "dev": {
                    "name": "Development",
                    "mcp_url": "http://localhost:8000",
                    "auth": {"type": "none"},
                },
                "prod": {
                    "name": "Production",
                    "mcp_url": "https://api.example.com",
                    "auth": {"type": "bearer", "token": "token"},
                },
            },
        }
        config_file.write_text(yaml.dump(config_content))

        config = MCPProfileConfig(config_path=str(config_file))
        profile = config.get_profile()
        assert profile is not None
        assert profile.profile_id == "dev"

    def test_get_profile_not_found(self, tmp_path):
        """Test getting a profile that doesn't exist."""
        config_file = tmp_path / "config.yaml"
        config_content = {
            "default": "dev",
            "profiles": {
                "dev": {
                    "name": "Development",
                    "mcp_url": "http://localhost:8000",
                    "auth": {"type": "none"},
                }
            },
        }
        config_file.write_text(yaml.dump(config_content))

        config = MCPProfileConfig(config_path=str(config_file))
        profile = config.get_profile("nonexistent")
        assert profile is None

    def test_list_profiles(self, tmp_path):
        """Test listing available profiles."""
        config_file = tmp_path / "config.yaml"
        config_content = {
            "default": "dev",
            "profiles": {
                "dev": {
                    "name": "Development",
                    "mcp_url": "http://localhost:8000",
                    "auth": {"type": "none"},
                },
                "staging": {
                    "name": "Staging",
                    "mcp_url": "https://staging.example.com",
                    "auth": {"type": "none"},
                },
                "prod": {
                    "name": "Production",
                    "mcp_url": "https://api.example.com",
                    "auth": {"type": "bearer", "token": "token"},
                },
            },
        }
        config_file.write_text(yaml.dump(config_content))

        config = MCPProfileConfig(config_path=str(config_file))
        profiles = config.list_profiles()
        assert len(profiles) == 3
        assert "dev" in profiles
        assert "staging" in profiles
        assert "prod" in profiles

    def test_has_profiles_true(self, tmp_path):
        """Test has_profiles returns True when profiles exist."""
        config_file = tmp_path / "config.yaml"
        config_content = {
            "default": "dev",
            "profiles": {
                "dev": {
                    "name": "Development",
                    "mcp_url": "http://localhost:8000",
                    "auth": {"type": "none"},
                }
            },
        }
        config_file.write_text(yaml.dump(config_content))

        config = MCPProfileConfig(config_path=str(config_file))
        assert config.has_profiles() is True

    def test_has_profiles_false(self):
        """Test has_profiles returns False when no profiles exist."""
        with patch.object(Path, "exists", return_value=False):
            config = MCPProfileConfig()
            assert config.has_profiles() is False

    def test_get_default_profile_and_server(self, tmp_path):
        """Test getting default profile and server."""
        config_file = tmp_path / "config.yaml"
        config_content = {
            "default": "dev",
            "profiles": {
                "dev": {
                    "name": "Development",
                    "mcps": [
                        {
                            "name": "MCP1",
                            "mcp_url": "http://localhost:8000",
                            "auth": {"type": "none"},
                        },
                        {
                            "name": "MCP2",
                            "mcp_url": "http://localhost:8001",
                            "auth": {"type": "none"},
                            "default": True,
                        },
                    ],
                }
            },
        }
        config_file.write_text(yaml.dump(config_content))

        config = MCPProfileConfig(config_path=str(config_file))
        result = config.get_default_profile_and_server()
        assert result is not None
        profile_id, server_name = result
        assert profile_id == "dev"
        assert server_name == "MCP2"

    def test_get_default_profile_and_server_first_when_none_marked(self, tmp_path):
        """Test that first server is returned when none marked as default."""
        config_file = tmp_path / "config.yaml"
        config_content = {
            "default": "dev",
            "profiles": {
                "dev": {
                    "name": "Development",
                    "mcps": [
                        {
                            "name": "MCP1",
                            "mcp_url": "http://localhost:8000",
                            "auth": {"type": "none"},
                        },
                        {
                            "name": "MCP2",
                            "mcp_url": "http://localhost:8001",
                            "auth": {"type": "none"},
                        },
                    ],
                }
            },
        }
        config_file.write_text(yaml.dump(config_content))

        config = MCPProfileConfig(config_path=str(config_file))
        result = config.get_default_profile_and_server()
        assert result is not None
        profile_id, server_name = result
        assert profile_id == "dev"
        assert server_name == "MCP1"

    def test_get_default_profile_and_server_none(self):
        """Test get_default_profile_and_server when no profiles exist."""
        with patch.object(Path, "exists", return_value=False):
            config = MCPProfileConfig()
            result = config.get_default_profile_and_server()
            assert result is None

    def test_get_default_profile_and_server_profile_has_no_servers(self, tmp_path):
        """Test get_default_profile_and_server when profile has no servers."""
        config_file = tmp_path / "config.yaml"
        config_content = {
            "default": "dev",
            "profiles": {"dev": {"name": "Development", "mcps": []}},
        }
        config_file.write_text(yaml.dump(config_content))

        config = MCPProfileConfig(config_path=str(config_file))
        result = config.get_default_profile_and_server()
        assert result is None

    def test_backward_compatibility_single_mcp(self, tmp_path):
        """Test backward compatibility with single MCP format (no mcps array)."""
        config_file = tmp_path / "config.yaml"
        config_content = {
            "default": "dev",
            "profiles": {
                "dev": {
                    "name": "Development",
                    "mcp_url": "http://localhost:8000",
                    "auth": {"type": "bearer", "token": "token123"},
                }
            },
        }
        config_file.write_text(yaml.dump(config_content))

        config = MCPProfileConfig(config_path=str(config_file))
        profile = config.profiles["dev"]
        assert len(profile.mcps) == 1
        assert profile.mcps[0].name == "Development"
        assert profile.mcps[0].mcp_url == "http://localhost:8000"
        assert profile.mcps[0].default is True
        assert profile.mcps[0].auth.token == "token123"

    def test_parse_auth_none_when_missing(self, tmp_path):
        """Test that auth defaults to 'none' when not provided."""
        config_file = tmp_path / "config.yaml"
        config_content = {
            "default": "dev",
            "profiles": {"dev": {"name": "Development", "mcp_url": "http://localhost:8000"}},
        }
        config_file.write_text(yaml.dump(config_content))

        config = MCPProfileConfig(config_path=str(config_file))
        profile = config.profiles["dev"]
        assert profile.mcps[0].auth.auth_type == "none"

    def test_parse_auth_none_when_null(self, tmp_path):
        """Test that auth defaults to 'none' when explicitly null."""
        config_file = tmp_path / "config.yaml"
        config_content = {
            "default": "dev",
            "profiles": {
                "dev": {
                    "name": "Development",
                    "mcp_url": "http://localhost:8000",
                    "auth": None,
                }
            },
        }
        config_file.write_text(yaml.dump(config_content))

        config = MCPProfileConfig(config_path=str(config_file))
        profile = config.profiles["dev"]
        assert profile.mcps[0].auth.auth_type == "none"

    def test_raw_config_stored(self, tmp_path):
        """Test that raw config is stored before env var substitution."""
        config_file = tmp_path / "config.yaml"
        config_content = {
            "default": "dev",
            "profiles": {
                "dev": {
                    "name": "Development",
                    "mcp_url": "http://localhost:8000",
                    "auth": {"type": "bearer", "token": "${TOKEN}"},
                }
            },
        }
        config_file.write_text(yaml.dump(config_content))

        config = MCPProfileConfig(config_path=str(config_file))
        assert config.raw_config is not None
        assert config.raw_config["profiles"]["dev"]["auth"]["token"] == "${TOKEN}"


class TestModuleLevelFunctions:
    """Tests for module-level convenience functions."""

    def test_get_profile_config_singleton(self):
        """Test that get_profile_config returns singleton instance."""
        # Reset the global instance
        import testmcpy.mcp_profiles as mcp_module

        mcp_module._profile_config = None

        config1 = get_profile_config()
        config2 = get_profile_config()
        assert config1 is config2

    def test_reload_profile_config(self, tmp_path, monkeypatch):
        """Test that reload_profile_config creates new instance."""

        monkeypatch.chdir(tmp_path)
        config_file = tmp_path / ".mcp_services.yaml"
        config_content = {
            "default": "dev",
            "profiles": {
                "dev": {
                    "name": "Development",
                    "mcp_url": "http://localhost:8000",
                    "auth": {"type": "none"},
                }
            },
        }
        config_file.write_text(yaml.dump(config_content))

        config1 = get_profile_config()
        config2 = reload_profile_config()
        assert config1 is not config2
        assert len(config2.profiles) == 1

    def test_load_profile(self, tmp_path):
        """Test load_profile module function."""
        import testmcpy.mcp_profiles as mcp_module

        config_file = tmp_path / "config.yaml"
        config_content = {
            "default": "dev",
            "profiles": {
                "dev": {
                    "name": "Development",
                    "mcp_url": "http://localhost:8000",
                    "auth": {"type": "none"},
                }
            },
        }
        config_file.write_text(yaml.dump(config_content))

        mcp_module._profile_config = MCPProfileConfig(config_path=str(config_file))

        profile = load_profile("dev")
        assert profile is not None
        assert profile.profile_id == "dev"

    def test_load_profile_default(self, tmp_path):
        """Test load_profile with no ID uses default."""
        import testmcpy.mcp_profiles as mcp_module

        config_file = tmp_path / "config.yaml"
        config_content = {
            "default": "prod",
            "profiles": {
                "dev": {
                    "name": "Development",
                    "mcp_url": "http://localhost:8000",
                    "auth": {"type": "none"},
                },
                "prod": {
                    "name": "Production",
                    "mcp_url": "https://api.example.com",
                    "auth": {"type": "bearer", "token": "token"},
                },
            },
        }
        config_file.write_text(yaml.dump(config_content))

        mcp_module._profile_config = MCPProfileConfig(config_path=str(config_file))

        profile = load_profile()
        assert profile is not None
        assert profile.profile_id == "prod"

    def test_list_available_profiles(self, tmp_path):
        """Test list_available_profiles module function."""
        import testmcpy.mcp_profiles as mcp_module

        config_file = tmp_path / "config.yaml"
        config_content = {
            "default": "dev",
            "profiles": {
                "dev": {
                    "name": "Development",
                    "mcp_url": "http://localhost:8000",
                    "auth": {"type": "none"},
                },
                "prod": {
                    "name": "Production",
                    "mcp_url": "https://api.example.com",
                    "auth": {"type": "bearer", "token": "token"},
                },
            },
        }
        config_file.write_text(yaml.dump(config_content))

        mcp_module._profile_config = MCPProfileConfig(config_path=str(config_file))

        profiles = list_available_profiles()
        assert len(profiles) == 2
        assert "dev" in profiles
        assert "prod" in profiles

    def test_load_mcp_profiles(self, tmp_path):
        """Test load_mcp_profiles module function."""
        import testmcpy.mcp_profiles as mcp_module

        config_file = tmp_path / "config.yaml"
        config_content = {
            "default": "dev",
            "global": {"timeout": 60},
            "profiles": {
                "dev": {
                    "name": "Development",
                    "mcp_url": "http://localhost:8000",
                    "auth": {"type": "none"},
                }
            },
        }
        config_file.write_text(yaml.dump(config_content))

        mcp_module._profile_config = MCPProfileConfig(config_path=str(config_file))

        config = load_mcp_profiles()
        assert config is not None
        assert config["default"] == "dev"
        assert "profiles" in config
        assert "global" in config

    def test_load_mcp_profiles_no_config(self):
        """Test load_mcp_profiles when no config file exists."""
        import testmcpy.mcp_profiles as mcp_module

        with patch.object(Path, "exists", return_value=False):
            mcp_module._profile_config = MCPProfileConfig()

            config = load_mcp_profiles()
            assert config is None

    def test_load_mcp_profiles_with_env_substitution(self, tmp_path, monkeypatch):
        """Test load_mcp_profiles performs env var substitution."""
        import testmcpy.mcp_profiles as mcp_module

        monkeypatch.setenv("MY_TOKEN", "secret123")
        config_file = tmp_path / "config.yaml"
        config_content = {
            "default": "dev",
            "profiles": {
                "dev": {
                    "name": "Development",
                    "mcp_url": "http://localhost:8000",
                    "auth": {"type": "bearer", "token": "${MY_TOKEN}"},
                }
            },
        }
        config_file.write_text(yaml.dump(config_content))

        mcp_module._profile_config = MCPProfileConfig(config_path=str(config_file))

        config = load_mcp_profiles()
        assert config["profiles"]["dev"]["auth"]["token"] == "secret123"


class TestEdgeCases:
    """Tests for edge cases and error conditions."""

    def test_empty_profiles_section(self, tmp_path):
        """Test handling of empty profiles section."""
        config_file = tmp_path / "config.yaml"
        config_content = {"default": "dev", "profiles": {}}
        config_file.write_text(yaml.dump(config_content))

        config = MCPProfileConfig(config_path=str(config_file))
        assert len(config.profiles) == 0
        assert config.has_profiles() is False

    def test_missing_profiles_section(self, tmp_path):
        """Test handling when profiles section is missing."""
        config_file = tmp_path / "config.yaml"
        config_content = {"default": "dev"}
        config_file.write_text(yaml.dump(config_content))

        config = MCPProfileConfig(config_path=str(config_file))
        assert len(config.profiles) == 0

    def test_missing_default_section(self, tmp_path):
        """Test handling when default section is missing."""
        config_file = tmp_path / "config.yaml"
        config_content = {
            "profiles": {
                "dev": {
                    "name": "Development",
                    "mcp_url": "http://localhost:8000",
                    "auth": {"type": "none"},
                }
            }
        }
        config_file.write_text(yaml.dump(config_content))

        config = MCPProfileConfig(config_path=str(config_file))
        # Should default to "local-dev" when not specified
        assert config.default_profile == "local-dev"

    def test_profile_with_no_name_uses_profile_id(self, tmp_path):
        """Test that profile name defaults to profile_id when not specified."""
        config_file = tmp_path / "config.yaml"
        config_content = {
            "default": "dev",
            "profiles": {"dev": {"mcp_url": "http://localhost:8000", "auth": {"type": "none"}}},
        }
        config_file.write_text(yaml.dump(config_content))

        config = MCPProfileConfig(config_path=str(config_file))
        profile = config.profiles["dev"]
        assert profile.name == "dev"

    def test_mcp_with_no_name_gets_default(self, tmp_path):
        """Test that MCP name defaults to 'Unnamed MCP' when not specified."""
        config_file = tmp_path / "config.yaml"
        config_content = {
            "default": "dev",
            "profiles": {
                "dev": {"mcps": [{"mcp_url": "http://localhost:8000", "auth": {"type": "none"}}]}
            },
        }
        config_file.write_text(yaml.dump(config_content))

        config = MCPProfileConfig(config_path=str(config_file))
        profile = config.profiles["dev"]
        assert profile.mcps[0].name == "Unnamed MCP"

    def test_default_profile_not_in_profiles(self, tmp_path):
        """Test when default profile doesn't exist in profiles."""
        config_file = tmp_path / "config.yaml"
        config_content = {
            "default": "nonexistent",
            "profiles": {
                "dev": {
                    "name": "Development",
                    "mcp_url": "http://localhost:8000",
                    "auth": {"type": "none"},
                }
            },
        }
        config_file.write_text(yaml.dump(config_content))

        config = MCPProfileConfig(config_path=str(config_file))
        assert config.default_profile == "nonexistent"
        result = config.get_default_profile_and_server()
        assert result is None

    def test_profile_parsing_exception_handled(self, tmp_path):
        """Test that profile parsing exceptions are handled gracefully."""
        config_file = tmp_path / "config.yaml"
        # Create a profile that will cause an exception during parsing
        config_content = {
            "default": "dev",
            "profiles": {
                "dev": {
                    "name": "Development",
                    "mcp_url": "http://localhost:8000",
                    "auth": {"type": "none"},
                },
                "broken": {
                    # Missing critical fields that might cause issues
                    "timeout": "invalid"  # Invalid type
                },
            },
        }
        config_file.write_text(yaml.dump(config_content))

        config = MCPProfileConfig(config_path=str(config_file))
        # Should have loaded dev but skipped broken
        assert "dev" in config.profiles
        # broken may or may not be loaded depending on how strictly it's validated

    def test_rate_limit_not_dict(self, tmp_path):
        """Test handling when rate_limit is not a dictionary."""
        config_file = tmp_path / "config.yaml"
        config_content = {
            "default": "dev",
            "profiles": {
                "dev": {
                    "name": "Development",
                    "mcp_url": "http://localhost:8000",
                    "auth": {"type": "none"},
                    "rate_limit": "not a dict",
                }
            },
        }
        config_file.write_text(yaml.dump(config_content))

        config = MCPProfileConfig(config_path=str(config_file))
        profile = config.profiles["dev"]
        # Should default to 60
        assert profile.rate_limit_rpm == 60

    def test_multiple_default_mcps_first_wins(self, tmp_path):
        """Test that when multiple MCPs are marked default, first one wins."""
        config_file = tmp_path / "config.yaml"
        config_content = {
            "default": "dev",
            "profiles": {
                "dev": {
                    "name": "Development",
                    "mcps": [
                        {
                            "name": "MCP1",
                            "mcp_url": "http://localhost:8000",
                            "auth": {"type": "none"},
                            "default": True,
                        },
                        {
                            "name": "MCP2",
                            "mcp_url": "http://localhost:8001",
                            "auth": {"type": "none"},
                            "default": True,
                        },
                    ],
                }
            },
        }
        config_file.write_text(yaml.dump(config_content))

        config = MCPProfileConfig(config_path=str(config_file))
        result = config.get_default_profile_and_server()
        assert result is not None
        profile_id, server_name = result
        assert server_name == "MCP1"
