"""Unit tests for StdioMCPClient (mocked subprocess)."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from testmcpy.src.mcp_client import (
    MCPConnectionError,
    MCPError,
    MCPToolCall,
    StdioMCPClient,
)


class FakeProcess:
    """Fake asyncio subprocess for testing."""

    def __init__(self, responses=None):
        self.stdin = MagicMock()
        self.stdin.write = MagicMock()
        self.stdin.drain = AsyncMock()
        self.stdin.close = MagicMock()
        self.stdout = MagicMock()
        self.stderr = MagicMock()
        self._responses = list(responses or [])
        self._call_count = 0
        self.returncode = 0

        # Set up readline to return responses in order
        async def _readline():
            if self._call_count < len(self._responses):
                resp = self._responses[self._call_count]
                self._call_count += 1
                return (json.dumps(resp) + "\n").encode()
            return b""

        self.stdout.readline = _readline

    def terminate(self):
        pass

    def kill(self):
        pass

    async def wait(self):
        return 0


@pytest.fixture
def make_client():
    """Factory to create a StdioMCPClient with a fake process."""

    def _make(responses=None):
        client = StdioMCPClient(command="fake-mcp", args=["--test"])
        client._process = FakeProcess(responses or [])
        return client

    return _make


class TestStdioMCPClientInit:
    """Test StdioMCPClient construction."""

    def test_init_defaults(self):
        client = StdioMCPClient(command="npx")
        assert client.command == "npx"
        assert client.args == []
        assert client.env is None
        assert client._process is None

    def test_init_with_args(self):
        client = StdioMCPClient(command="python", args=["-m", "my_mcp"])
        assert client.args == ["-m", "my_mcp"]


class TestStdioMCPClientSendRequest:
    """Test the JSON-RPC request/response cycle."""

    @pytest.mark.asyncio
    async def test_send_request_success(self, make_client):
        response = {"jsonrpc": "2.0", "id": 1, "result": {"tools": []}}
        client = make_client([response])

        result = await client._send_request("tools/list")
        assert result == {"tools": []}

        # Verify stdin was written to
        client._process.stdin.write.assert_called_once()
        written = client._process.stdin.write.call_args[0][0]
        parsed = json.loads(written.decode())
        assert parsed["method"] == "tools/list"
        assert parsed["id"] == 1

    @pytest.mark.asyncio
    async def test_send_request_error(self, make_client):
        response = {
            "jsonrpc": "2.0",
            "id": 1,
            "error": {"code": -32600, "message": "Invalid request"},
        }
        client = make_client([response])

        with pytest.raises(MCPError, match="Invalid request"):
            await client._send_request("bad/method")

    @pytest.mark.asyncio
    async def test_send_request_no_process(self):
        client = StdioMCPClient(command="fake")
        with pytest.raises(MCPError, match="not started"):
            await client._send_request("test")


class TestStdioMCPClientListTools:
    """Test list_tools method."""

    @pytest.mark.asyncio
    async def test_list_tools(self, make_client):
        tools_response = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "tools": [
                    {
                        "name": "get_weather",
                        "description": "Get weather data",
                        "inputSchema": {
                            "type": "object",
                            "properties": {"city": {"type": "string"}},
                        },
                    },
                    {
                        "name": "get_time",
                        "description": "Get current time",
                        "inputSchema": {"type": "object", "properties": {}},
                    },
                ]
            },
        }
        client = make_client([tools_response])

        tools = await client.list_tools()
        assert len(tools) == 2
        assert tools[0].name == "get_weather"
        assert tools[1].name == "get_time"

    @pytest.mark.asyncio
    async def test_list_tools_cached(self, make_client):
        tools_response = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {"tools": [{"name": "t1", "description": "T1", "inputSchema": {}}]},
        }
        client = make_client([tools_response])

        tools1 = await client.list_tools()
        # Second call should use cache (no more responses available)
        tools2 = await client.list_tools()
        assert tools1 == tools2

    @pytest.mark.asyncio
    async def test_list_tools_force_refresh(self, make_client):
        resp1 = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {"tools": [{"name": "t1", "description": "T1", "inputSchema": {}}]},
        }
        resp2 = {
            "jsonrpc": "2.0",
            "id": 2,
            "result": {
                "tools": [
                    {"name": "t1", "description": "T1", "inputSchema": {}},
                    {"name": "t2", "description": "T2", "inputSchema": {}},
                ]
            },
        }
        client = make_client([resp1, resp2])

        tools1 = await client.list_tools()
        assert len(tools1) == 1

        tools2 = await client.list_tools(force_refresh=True)
        assert len(tools2) == 2


class TestStdioMCPClientCallTool:
    """Test call_tool method."""

    @pytest.mark.asyncio
    async def test_call_tool_success(self, make_client):
        response = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "content": [{"type": "text", "text": "Hello!"}],
                "isError": False,
            },
        }
        client = make_client([response])

        tool_call = MCPToolCall(name="greet", arguments={"name": "World"})
        result = await client.call_tool(tool_call)

        assert not result.is_error
        assert result.content == [{"type": "text", "text": "Hello!"}]

    @pytest.mark.asyncio
    async def test_call_tool_error_response(self, make_client):
        response = {
            "jsonrpc": "2.0",
            "id": 1,
            "error": {"code": -32000, "message": "Tool failed"},
        }
        client = make_client([response])

        tool_call = MCPToolCall(name="broken", arguments={})
        result = await client.call_tool(tool_call)

        assert result.is_error
        assert "Tool failed" in result.error_message


class TestStdioMCPClientClose:
    """Test close method."""

    @pytest.mark.asyncio
    async def test_close(self, make_client):
        client = make_client([])
        assert client._process is not None
        await client.close()
        assert client._process is None
        assert client._tools_cache is None

    @pytest.mark.asyncio
    async def test_close_when_no_process(self):
        client = StdioMCPClient(command="fake")
        # Should not raise
        await client.close()


class TestStdioMCPClientInitialize:
    """Test initialize method."""

    @pytest.mark.asyncio
    async def test_initialize_command_not_found(self):
        client = StdioMCPClient(command="nonexistent_command_xyz_12345")
        with pytest.raises(MCPConnectionError, match="Command not found"):
            await client.initialize()
