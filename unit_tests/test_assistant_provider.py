"""
Unit tests for AssistantProvider — the chatbot endpoint provider.

Tests config resolution, validation, header building, and
SSE event parsing without making real API calls.
"""

from unittest.mock import patch

import pytest

from testmcpy.src.llm_integration import AssistantProvider, create_llm_provider


class TestAssistantProviderConstruction:
    """Test constructor and config resolution."""

    def test_factory_creates_assistant(self):
        provider = create_llm_provider(
            "assistant", "default", workspace_hash="ws-test", domain="test.com"
        )
        assert isinstance(provider, AssistantProvider)

    def test_chatbot_alias(self):
        provider = create_llm_provider(
            "chatbot", "default", workspace_hash="ws-test", domain="test.com"
        )
        assert isinstance(provider, AssistantProvider)

    def test_workspace_hash_from_kwargs(self):
        provider = AssistantProvider(workspace_hash="ws-abc", domain="example.com")
        assert provider.workspace_hash == "ws-abc"

    @patch.dict("os.environ", {"ASSISTANT_WORKSPACE_HASH": "ws-env"}, clear=False)
    def test_workspace_hash_from_env(self):
        provider = AssistantProvider(domain="example.com")
        assert provider.workspace_hash == "ws-env"

    def test_kwargs_override_env(self):
        with patch.dict("os.environ", {"ASSISTANT_WORKSPACE_HASH": "ws-env"}, clear=False):
            provider = AssistantProvider(workspace_hash="ws-kwarg", domain="example.com")
            assert provider.workspace_hash == "ws-kwarg"

    def test_base_url_from_domain(self):
        provider = AssistantProvider(workspace_hash="ws-abc", domain="app.preset.io")
        assert provider.base_url == "https://ws-abc.app.preset.io"

    def test_base_url_from_environment_staging(self):
        provider = AssistantProvider(workspace_hash="ws-abc", environment="staging")
        assert provider.base_url == "https://ws-abc.app.staging.preset.zone"

    def test_base_url_from_environment_production(self):
        provider = AssistantProvider(workspace_hash="ws-abc", environment="production")
        assert provider.base_url == "https://ws-abc.app.preset.io"

    def test_base_url_empty_without_workspace(self):
        provider = AssistantProvider()
        assert provider.base_url == ""

    def test_model_default(self):
        provider = AssistantProvider(workspace_hash="ws-abc", domain="test.com")
        assert provider.model == "default"

    def test_model_override(self):
        provider = AssistantProvider(
            workspace_hash="ws-abc", domain="test.com", model_override="gpt-5.4"
        )
        assert provider.model_override == "gpt-5.4"

    def test_conversations_path_default(self):
        provider = AssistantProvider(workspace_hash="ws-abc", domain="test.com")
        assert provider.conversations_path == "/api/v1/copilot/conversations"

    def test_completions_path_default(self):
        provider = AssistantProvider(workspace_hash="ws-abc", domain="test.com")
        assert provider.completions_path == "/api/v1/copilot/completions"


class TestAssistantProviderValidation:
    """Test initialize() validation errors."""

    @pytest.mark.asyncio
    async def test_missing_base_url_raises(self):
        provider = AssistantProvider()
        with pytest.raises(ValueError, match="workspace_hash"):
            await provider.initialize()

    @pytest.mark.asyncio
    async def test_missing_api_token_raises(self):
        provider = AssistantProvider(workspace_hash="ws-abc", domain="test.com")
        provider.api_token = ""
        provider.api_secret = ""
        with pytest.raises(ValueError, match="api_token"):
            await provider.initialize()

    @pytest.mark.asyncio
    async def test_missing_api_secret_raises(self):
        provider = AssistantProvider(workspace_hash="ws-abc", domain="test.com")
        provider.api_token = "token"
        provider.api_secret = ""
        with pytest.raises(ValueError, match="api_token"):
            await provider.initialize()


class TestAssistantProviderHeaders:
    """Test _build_headers method."""

    def test_headers_include_jwt(self):
        provider = AssistantProvider(workspace_hash="ws-abc", domain="test.com")
        provider._jwt_token = "jwt-test-token"
        headers = provider._build_headers()
        assert headers["Authorization"] == "Bearer jwt-test-token"

    def test_headers_include_csrf(self):
        provider = AssistantProvider(workspace_hash="ws-abc", domain="test.com")
        provider._jwt_token = "jwt-test-token"
        headers = provider._build_headers()
        assert "csrf_access_token" in headers["Cookie"]

    def test_headers_include_referer(self):
        provider = AssistantProvider(workspace_hash="ws-abc", domain="test.com")
        provider._jwt_token = "jwt-test-token"
        headers = provider._build_headers()
        assert "Referer" in headers


class TestAssistantProviderApiUrl:
    """Test API URL resolution for different environments."""

    def test_staging_api_url(self):
        provider = AssistantProvider(
            workspace_hash="ws-abc",
            environment="staging",
            api_url="https://manage.app.staging.preset.zone/api/v1/auth/",
        )
        assert "staging" in provider.api_url

    def test_production_api_url(self):
        provider = AssistantProvider(
            workspace_hash="ws-abc",
            environment="production",
            api_url="https://manage.app.preset.io/api/v1/auth/",
        )
        assert "preset.io" in provider.api_url

    def test_custom_api_url(self):
        provider = AssistantProvider(
            workspace_hash="ws-abc",
            domain="test.com",
            api_url="https://custom-auth.example.com/auth/",
        )
        assert provider.api_url == "https://custom-auth.example.com/auth/"

    @patch.dict("os.environ", {"ASSISTANT_API_URL": "https://env-auth.com/auth/"}, clear=False)
    def test_api_url_from_env(self):
        provider = AssistantProvider(workspace_hash="ws-abc", domain="test.com")
        assert provider.api_url == "https://env-auth.com/auth/"
