"""
Unit tests for the MCP health check endpoint logic.

Tests the health status detection, timeout handling,
and response structure.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def mock_mcp_server():
    """Create a mock MCP server configuration."""
    server = MagicMock()
    server.name = "test-server"
    server.mcp_url = "http://localhost:8080/mcp"
    server.auth = None
    return server


@pytest.fixture
def mock_profile():
    """Create a mock MCP profile."""
    profile = MagicMock()
    profile.name = "Test Profile"
    profile.mcps = []
    return profile


@pytest.mark.asyncio
async def test_ping_server_healthy(mock_mcp_server):
    """Test that a healthy server returns correct status."""
    from testmcpy.server.routers.health import _ping_server

    mock_tool = MagicMock()
    mock_tool.name = "test_tool"

    with patch("testmcpy.src.mcp_client.MCPClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.initialize = AsyncMock()
        mock_client.list_tools = AsyncMock(return_value=[mock_tool, mock_tool])
        mock_client.close = AsyncMock()
        mock_client_cls.return_value = mock_client

        result = await _ping_server(mock_mcp_server, "profile-1", "Test Profile")

    assert result["status"] == "healthy"
    assert result["tool_count"] == 2
    assert result["response_time_ms"] is not None
    assert result["error"] is None
    assert result["server_name"] == "test-server"
    assert result["profile_id"] == "profile-1"


@pytest.mark.asyncio
async def test_ping_server_timeout(mock_mcp_server):
    """Test that a timed-out server returns timeout status."""
    from testmcpy.server.routers.health import _ping_server

    with patch("testmcpy.src.mcp_client.MCPClient") as mock_client_cls:
        mock_client = AsyncMock()

        async def slow_init():
            await asyncio.sleep(20)  # Will be cancelled by timeout

        mock_client.initialize = slow_init
        mock_client_cls.return_value = mock_client

        # Use a very short timeout
        with patch("testmcpy.server.routers.health.PING_TIMEOUT", 0.01):
            result = await _ping_server(mock_mcp_server, "profile-1", "Test Profile")

    assert result["status"] == "timeout"
    assert result["error"] is not None
    assert "Timed out" in result["error"]


@pytest.mark.asyncio
async def test_ping_server_connection_error(mock_mcp_server):
    """Test that a connection error returns unreachable status."""
    from testmcpy.server.routers.health import _ping_server

    with patch("testmcpy.src.mcp_client.MCPClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.initialize = AsyncMock(side_effect=ConnectionError("Connection refused"))
        mock_client_cls.return_value = mock_client

        result = await _ping_server(mock_mcp_server, "profile-1", "Test Profile")

    assert result["status"] == "unreachable"
    assert "Connection refused" in result["error"]


@pytest.mark.asyncio
async def test_ping_server_runtime_error(mock_mcp_server):
    """Test that a runtime error returns error status."""
    from testmcpy.server.routers.health import _ping_server

    with patch("testmcpy.src.mcp_client.MCPClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.initialize = AsyncMock(side_effect=RuntimeError("Protocol error"))
        mock_client_cls.return_value = mock_client

        result = await _ping_server(mock_mcp_server, "profile-1", "Test Profile")

    assert result["status"] == "error"
    assert "Protocol error" in result["error"]


@pytest.mark.asyncio
async def test_ping_server_includes_checked_at(mock_mcp_server):
    """Test that checked_at timestamp is always present."""
    from testmcpy.server.routers.health import _ping_server

    with patch("testmcpy.src.mcp_client.MCPClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.initialize = AsyncMock(side_effect=RuntimeError("test"))
        mock_client_cls.return_value = mock_client

        result = await _ping_server(mock_mcp_server, "profile-1", "Test Profile")

    assert result["checked_at"] is not None
