"""
Unit tests for MCPClient authentication functionality.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from testmcpy.src.mcp_client import MCPClient, MCPError, BearerAuth


class TestMCPClientAuth:
    """Test MCPClient authentication parameter handling."""

    @pytest.mark.asyncio
    async def test_init_with_auth_parameter(self):
        """Test that auth parameter is stored correctly."""
        auth = {"type": "bearer", "token": "test-token"}
        client = MCPClient(base_url="http://localhost:5008/mcp", auth=auth)

        assert client.auth_config == auth
        assert client.base_url == "http://localhost:5008/mcp"
        assert client.auth is None  # Not set until initialize()

    @pytest.mark.asyncio
    async def test_init_without_auth_parameter(self):
        """Test that auth_config is None when not provided."""
        client = MCPClient(base_url="http://localhost:5008/mcp")

        assert client.auth_config is None
        assert client.auth is None

    @pytest.mark.asyncio
    async def test_bearer_auth_from_parameter(self):
        """Test bearer token authentication from parameter."""
        auth = {"type": "bearer", "token": "test-bearer-token"}
        client = MCPClient(base_url="http://localhost:5008/mcp", auth=auth)

        # Call _setup_auth directly
        bearer_auth = await client._setup_auth()

        assert isinstance(bearer_auth, BearerAuth)
        assert bearer_auth.token == "test-bearer-token"

    @pytest.mark.asyncio
    async def test_bearer_auth_missing_token(self):
        """Test bearer auth error when token is missing."""
        auth = {"type": "bearer"}
        client = MCPClient(base_url="http://localhost:5008/mcp", auth=auth)

        with pytest.raises(MCPError, match="Bearer auth requires 'token' field"):
            await client._setup_auth()

    @pytest.mark.asyncio
    async def test_jwt_auth_missing_fields(self):
        """Test JWT auth error when required fields are missing."""
        auth = {"type": "jwt", "api_url": "http://example.com"}
        client = MCPClient(base_url="http://localhost:5008/mcp", auth=auth)

        with pytest.raises(MCPError, match="JWT auth requires"):
            await client._setup_auth()

    @pytest.mark.asyncio
    async def test_oauth_auth_missing_fields(self):
        """Test OAuth auth error when required fields are missing."""
        auth = {"type": "oauth", "client_id": "test-id"}
        client = MCPClient(base_url="http://localhost:5008/mcp", auth=auth)

        with pytest.raises(MCPError, match="OAuth auth requires"):
            await client._setup_auth()

    @pytest.mark.asyncio
    async def test_no_auth_explicit(self):
        """Test explicit no authentication."""
        auth = {"type": "none"}
        client = MCPClient(base_url="http://localhost:5008/mcp", auth=auth)

        bearer_auth = await client._setup_auth()

        assert bearer_auth is None

    @pytest.mark.asyncio
    async def test_unknown_auth_type(self):
        """Test error for unknown auth type."""
        auth = {"type": "invalid"}
        client = MCPClient(base_url="http://localhost:5008/mcp", auth=auth)

        with pytest.raises(MCPError, match="Unknown auth type: invalid"):
            await client._setup_auth()

    @pytest.mark.asyncio
    @patch("testmcpy.src.mcp_client.httpx.AsyncClient")
    async def test_jwt_token_fetch_success(self, mock_async_client):
        """Test successful JWT token fetch."""
        # Mock the HTTP response
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "payload": {"access_token": "jwt-token-123"}
        }

        mock_client_instance = AsyncMock()
        mock_client_instance.post = AsyncMock(return_value=mock_response)
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock()

        mock_async_client.return_value = mock_client_instance

        auth = {
            "type": "jwt",
            "api_url": "http://example.com/auth",
            "api_token": "token",
            "api_secret": "secret"
        }
        client = MCPClient(base_url="http://localhost:5008/mcp", auth=auth)

        bearer_auth = await client._setup_auth()

        assert isinstance(bearer_auth, BearerAuth)
        assert bearer_auth.token == "jwt-token-123"

    @pytest.mark.asyncio
    @patch("testmcpy.src.mcp_client.httpx.AsyncClient")
    async def test_oauth_token_fetch_success(self, mock_async_client):
        """Test successful OAuth token fetch."""
        # Mock the HTTP response
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"access_token": "oauth-token-456"}

        mock_client_instance = AsyncMock()
        mock_client_instance.post = AsyncMock(return_value=mock_response)
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock()

        mock_async_client.return_value = mock_client_instance

        auth = {
            "type": "oauth",
            "client_id": "client-id",
            "client_secret": "client-secret",
            "token_url": "http://example.com/oauth/token",
            "scopes": ["read", "write"]
        }
        client = MCPClient(base_url="http://localhost:5008/mcp", auth=auth)

        bearer_auth = await client._setup_auth()

        assert isinstance(bearer_auth, BearerAuth)
        assert bearer_auth.token == "oauth-token-456"

    @pytest.mark.asyncio
    @patch("testmcpy.src.mcp_client.get_config")
    async def test_fallback_to_config(self, mock_get_config):
        """Test fallback to config-based authentication."""
        # Mock config
        mock_config = MagicMock()
        mock_config.get.side_effect = lambda key, default=None: {
            "MCP_AUTH_TOKEN": "config-token-123"
        }.get(key, default)
        mock_config.mcp_auth_token = "config-token-123"

        mock_get_config.return_value = mock_config

        # No auth parameter provided
        client = MCPClient(base_url="http://localhost:5008/mcp")

        bearer_auth = await client._setup_auth()

        assert isinstance(bearer_auth, BearerAuth)
        assert bearer_auth.token == "config-token-123"

    @pytest.mark.asyncio
    async def test_auth_config_to_dict(self):
        """Test AuthConfig.to_dict() helper method."""
        from testmcpy.mcp_profiles import AuthConfig

        # Test bearer
        auth_config = AuthConfig(auth_type="bearer", token="test-token")
        auth_dict = auth_config.to_dict()
        assert auth_dict == {"type": "bearer", "token": "test-token"}

        # Test JWT
        auth_config = AuthConfig(
            auth_type="jwt",
            api_url="http://api.example.com",
            api_token="token",
            api_secret="secret"
        )
        auth_dict = auth_config.to_dict()
        assert auth_dict == {
            "type": "jwt",
            "api_url": "http://api.example.com",
            "api_token": "token",
            "api_secret": "secret"
        }

        # Test OAuth
        auth_config = AuthConfig(
            auth_type="oauth",
            client_id="client-id",
            client_secret="client-secret",
            token_url="http://oauth.example.com/token",
            scopes=["read", "write"]
        )
        auth_dict = auth_config.to_dict()
        assert auth_dict == {
            "type": "oauth",
            "client_id": "client-id",
            "client_secret": "client-secret",
            "token_url": "http://oauth.example.com/token",
            "scopes": ["read", "write"]
        }

        # Test none
        auth_config = AuthConfig(auth_type="none")
        auth_dict = auth_config.to_dict()
        assert auth_dict == {"type": "none"}
