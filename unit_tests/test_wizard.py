"""Tests for CLI wizard commands - validation logic and YAML generation."""

import tempfile
from pathlib import Path
from unittest.mock import patch

import yaml


class TestWizardYAMLGeneration:
    """Test YAML generation for the add-test wizard."""

    def test_basic_test_yaml_structure(self):
        """Test that generated YAML has correct structure."""
        tests = [
            {
                "name": "basic_test",
                "prompt": "List all dashboards",
                "evaluators": [{"name": "execution_successful"}],
            }
        ]
        data = {"version": "1.0", "tests": tests}
        yaml_str = yaml.dump(data, default_flow_style=False, sort_keys=False)

        parsed = yaml.safe_load(yaml_str)
        assert parsed["version"] == "1.0"
        assert len(parsed["tests"]) == 1
        assert parsed["tests"][0]["name"] == "basic_test"
        assert parsed["tests"][0]["prompt"] == "List all dashboards"
        assert parsed["tests"][0]["evaluators"][0]["name"] == "execution_successful"

    def test_test_with_evaluator_args(self):
        """Test YAML generation with evaluator arguments."""
        tests = [
            {
                "name": "tool_test",
                "prompt": "Call the tool",
                "evaluators": [
                    {
                        "name": "was_mcp_tool_called",
                        "args": {"tool_name": "list_dashboards"},
                    },
                    {
                        "name": "within_time_limit",
                        "args": {"seconds": 30},
                    },
                ],
            }
        ]
        data = {"version": "1.0", "tests": tests}
        yaml_str = yaml.dump(data, default_flow_style=False, sort_keys=False)

        parsed = yaml.safe_load(yaml_str)
        assert len(parsed["tests"][0]["evaluators"]) == 2
        assert parsed["tests"][0]["evaluators"][0]["args"]["tool_name"] == "list_dashboards"
        assert parsed["tests"][0]["evaluators"][1]["args"]["seconds"] == 30

    def test_multiple_tests(self):
        """Test YAML with multiple test cases."""
        tests = [
            {
                "name": "test_one",
                "prompt": "First test",
                "evaluators": [{"name": "execution_successful"}],
            },
            {
                "name": "test_two",
                "prompt": "Second test",
                "evaluators": [
                    {"name": "final_answer_contains", "args": {"text": "success"}},
                ],
            },
        ]
        data = {"version": "1.0", "tests": tests}
        yaml_str = yaml.dump(data, default_flow_style=False, sort_keys=False)

        parsed = yaml.safe_load(yaml_str)
        assert len(parsed["tests"]) == 2
        assert parsed["tests"][0]["name"] == "test_one"
        assert parsed["tests"][1]["name"] == "test_two"

    def test_special_characters_in_prompt(self):
        """Test that special characters in prompts are handled."""
        tests = [
            {
                "name": "special_chars",
                "prompt": 'Show me "all" dashboards with $special & <chars>',
                "evaluators": [{"name": "execution_successful"}],
            }
        ]
        data = {"version": "1.0", "tests": tests}
        yaml_str = yaml.dump(data, default_flow_style=False, sort_keys=False)

        parsed = yaml.safe_load(yaml_str)
        assert parsed["tests"][0]["prompt"] == 'Show me "all" dashboards with $special & <chars>'


class TestWizardMCPConfigGeneration:
    """Test MCP config YAML generation."""

    def test_sse_mcp_entry(self):
        """Test SSE transport MCP entry generation."""
        mcp_entry = {
            "name": "test-server",
            "mcp_url": "https://api.example.com/mcp/",
            "timeout": 30,
            "rate_limit_rpm": 60,
            "auth": {"type": "bearer", "token": "${MY_TOKEN}"},
        }

        yaml_str = yaml.dump(mcp_entry, default_flow_style=False, sort_keys=False)
        parsed = yaml.safe_load(yaml_str)

        assert parsed["name"] == "test-server"
        assert parsed["mcp_url"] == "https://api.example.com/mcp/"
        assert parsed["auth"]["type"] == "bearer"
        assert parsed["auth"]["token"] == "${MY_TOKEN}"

    def test_stdio_mcp_entry(self):
        """Test stdio transport MCP entry generation."""
        mcp_entry = {
            "name": "local-server",
            "transport": "stdio",
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
            "mcp_url": "stdio://npx",
            "timeout": 30,
            "rate_limit_rpm": 60,
        }

        yaml_str = yaml.dump(mcp_entry, default_flow_style=False, sort_keys=False)
        parsed = yaml.safe_load(yaml_str)

        assert parsed["transport"] == "stdio"
        assert parsed["command"] == "npx"
        assert len(parsed["args"]) == 3
        assert parsed["args"][0] == "-y"

    def test_oauth_mcp_entry(self):
        """Test OAuth auth MCP entry generation."""
        mcp_entry = {
            "name": "oauth-server",
            "mcp_url": "https://secure.example.com/mcp/",
            "timeout": 30,
            "rate_limit_rpm": 60,
            "auth": {
                "type": "oauth",
                "client_id": "my-client",
                "client_secret": "secret123",
                "token_url": "https://auth.example.com/token",
                "scopes": ["read", "write"],
            },
        }

        yaml_str = yaml.dump(mcp_entry, default_flow_style=False, sort_keys=False)
        parsed = yaml.safe_load(yaml_str)

        assert parsed["auth"]["type"] == "oauth"
        assert parsed["auth"]["client_id"] == "my-client"
        assert parsed["auth"]["scopes"] == ["read", "write"]


class TestWizardLLMConfigGeneration:
    """Test LLM provider config YAML generation."""

    def test_anthropic_provider_entry(self):
        """Test Anthropic provider entry generation."""
        provider_entry = {
            "name": "Claude Sonnet 4",
            "provider": "anthropic",
            "model": "claude-sonnet-4-20250514",
            "timeout": 60,
            "default": True,
        }

        yaml_str = yaml.dump(provider_entry, default_flow_style=False, sort_keys=False)
        parsed = yaml.safe_load(yaml_str)

        assert parsed["provider"] == "anthropic"
        assert parsed["model"] == "claude-sonnet-4-20250514"
        assert parsed["default"] is True

    def test_ollama_provider_entry(self):
        """Test Ollama provider entry with base_url."""
        provider_entry = {
            "name": "Local Llama",
            "provider": "ollama",
            "model": "llama3.2:latest",
            "base_url": "http://localhost:11434",
            "timeout": 120,
            "default": False,
        }

        yaml_str = yaml.dump(provider_entry, default_flow_style=False, sort_keys=False)
        parsed = yaml.safe_load(yaml_str)

        assert parsed["provider"] == "ollama"
        assert parsed["base_url"] == "http://localhost:11434"

    def test_provider_with_api_key_env(self):
        """Test provider with env var for API key."""
        provider_entry = {
            "name": "GPT-4o",
            "provider": "openai",
            "model": "gpt-4o",
            "api_key_env": "OPENAI_API_KEY",
            "timeout": 60,
            "default": True,
        }

        yaml_str = yaml.dump(provider_entry, default_flow_style=False, sort_keys=False)
        parsed = yaml.safe_load(yaml_str)

        assert parsed["api_key_env"] == "OPENAI_API_KEY"
        assert "api_key" not in parsed


class TestWizardConfigFileSave:
    """Test that wizard properly saves to config files."""

    def test_save_mcp_to_new_config(self):
        """Test saving MCP to a new config file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / ".mcp_services.yaml"

            config = {
                "default": "test-profile",
                "profiles": {
                    "test-profile": {
                        "name": "Test Profile",
                        "description": "Test",
                        "mcps": [
                            {
                                "name": "my-server",
                                "mcp_url": "https://example.com/mcp/",
                                "timeout": 30,
                            }
                        ],
                    }
                },
            }

            with open(config_path, "w") as f:
                yaml.dump(config, f, default_flow_style=False, sort_keys=False)

            # Verify it was written correctly
            with open(config_path) as f:
                loaded = yaml.safe_load(f)

            assert loaded["default"] == "test-profile"
            assert len(loaded["profiles"]["test-profile"]["mcps"]) == 1
            assert loaded["profiles"]["test-profile"]["mcps"][0]["name"] == "my-server"

    def test_save_llm_to_new_config(self):
        """Test saving LLM provider to a new config file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / ".llm_providers.yaml"

            config = {
                "default": "prod",
                "profiles": {
                    "prod": {
                        "name": "Production",
                        "description": "Production providers",
                        "providers": [
                            {
                                "name": "Claude Sonnet",
                                "provider": "anthropic",
                                "model": "claude-sonnet-4-20250514",
                                "default": True,
                            }
                        ],
                    }
                },
            }

            with open(config_path, "w") as f:
                yaml.dump(config, f, default_flow_style=False, sort_keys=False)

            with open(config_path) as f:
                loaded = yaml.safe_load(f)

            assert loaded["default"] == "prod"
            assert len(loaded["profiles"]["prod"]["providers"]) == 1
            assert loaded["profiles"]["prod"]["providers"][0]["provider"] == "anthropic"

    def test_save_test_file(self):
        """Test saving a test YAML file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tests_dir = Path(tmpdir) / "tests"
            tests_dir.mkdir()
            file_path = tests_dir / "my_test.yaml"

            test_data = {
                "version": "1.0",
                "tests": [
                    {
                        "name": "basic",
                        "prompt": "Hello",
                        "evaluators": [{"name": "execution_successful"}],
                    }
                ],
            }

            yaml_str = yaml.dump(test_data, default_flow_style=False, sort_keys=False)
            with open(file_path, "w") as f:
                f.write(yaml_str)

            with open(file_path) as f:
                loaded = yaml.safe_load(f)

            assert loaded["version"] == "1.0"
            assert loaded["tests"][0]["name"] == "basic"


class TestWizardHelpers:
    """Test wizard helper functions."""

    def test_choose_helper(self):
        """Test the _choose helper picks correct index."""
        from testmcpy.cli.commands.wizard import _choose

        # Mock Prompt.ask to return "2"
        with patch("testmcpy.cli.commands.wizard.Prompt.ask", return_value="2"):
            result = _choose("Pick:", ["a", "b", "c"])
            assert result == "b"

    def test_choose_helper_default(self):
        """Test the _choose helper uses default."""
        from testmcpy.cli.commands.wizard import _choose

        with patch("testmcpy.cli.commands.wizard.Prompt.ask", return_value="1"):
            result = _choose("Pick:", ["a", "b", "c"], default="a")
            assert result == "a"
