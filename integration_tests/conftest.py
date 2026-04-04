"""Core fixtures for integration tests."""

from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def mock_mcp_client():
    """Create a mock MCP client with standard tool/resource/prompt responses."""
    client = AsyncMock()
    client.connected = True
    client.base_url = "http://mock-mcp:3000/mcp"

    # Mock tool objects with proper attributes
    tool = MagicMock()
    tool.name = "health_check"
    tool.description = "Check health"
    tool.input_schema = {"type": "object", "properties": {}}
    tool.output_schema = None

    tool2 = MagicMock()
    tool2.name = "get_data"
    tool2.description = "Get data from source"
    tool2.input_schema = {
        "type": "object",
        "properties": {"id": {"type": "string"}},
        "required": ["id"],
    }
    tool2.output_schema = None

    client.list_tools.return_value = [tool, tool2]
    client.list_resources.return_value = []
    client.list_prompts.return_value = []

    call_result = MagicMock()
    call_result.content = "OK"
    call_result.is_error = False
    client.call_tool.return_value = call_result

    # Auth mock
    client.auth = MagicMock()
    client.auth.token = "mock-token-12345"

    return client


@pytest.fixture
def tmp_workspace(tmp_path):
    """Create a minimal workspace with config files."""
    (tmp_path / ".mcp_services.yaml").write_text(
        "default: test\n"
        "profiles:\n"
        "  test:\n"
        "    name: Test\n"
        "    description: Test profile\n"
        "    mcps:\n"
        "    - name: Test MCP\n"
        "      mcp_url: http://mock:3000/mcp\n"
        "      auth:\n"
        "        type: none\n"
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / ".results").mkdir()
    (tmp_path / "tests" / ".smoke_reports").mkdir()
    (tmp_path / ".generation_logs").mkdir()
    return tmp_path
