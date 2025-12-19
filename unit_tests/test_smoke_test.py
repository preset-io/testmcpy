"""
Unit tests for testmcpy.smoke_test module.

Tests smoke test functionality:
- Smoke test discovery
- Smoke test execution logic
- Report generation
- Tool validation during smoke tests
- Error handling when tools fail
- Edge cases (empty tools, timeouts, invalid schemas, malformed responses)
"""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from testmcpy.smoke_test import (
    SmokeTestReport,
    SmokeTestResult,
    SmokeTestRunner,
    ToolTestError,
    run_smoke_test,
)
from testmcpy.src.mcp_client import (
    MCPClient,
    MCPTool,
    MCPToolResult,
)

# Fixtures


@pytest.fixture
def mock_mcp_client():
    """Mock MCP client for testing."""
    client = AsyncMock(spec=MCPClient)
    client.base_url = "http://test-server:5000/mcp"
    client.client = MagicMock()  # Mark as initialized
    return client


@pytest.fixture
def sample_tools():
    """Sample tools for testing."""
    return [
        MCPTool(
            name="simple_tool",
            description="A simple tool with no parameters",
            input_schema={},
        ),
        MCPTool(
            name="tool_with_params",
            description="Tool with basic parameters",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "default": 10},
                },
                "required": ["query"],
            },
        ),
        MCPTool(
            name="tool_with_complex_params",
            description="Tool with complex nested object",
            input_schema={
                "type": "object",
                "properties": {
                    "request": {"type": "object", "properties": {"id": {"type": "string"}}}
                },
                "required": ["request"],
            },
        ),
    ]


@pytest.fixture
def runner(mock_mcp_client):
    """Smoke test runner instance."""
    return SmokeTestRunner(mock_mcp_client)


# Test ToolTestError


def test_tool_test_error_creation():
    """Test ToolTestError can be created with all fields."""
    error = ToolTestError(
        message="Tool failed",
        tool_input={"param": "value"},
        tool_output="error output",
        tool_schema={"type": "object"},
    )

    assert str(error) == "Tool failed"
    assert error.tool_input == {"param": "value"}
    assert error.tool_output == "error output"
    assert error.tool_schema == {"type": "object"}


def test_tool_test_error_minimal():
    """Test ToolTestError with minimal fields."""
    error = ToolTestError(message="Minimal error")

    assert str(error) == "Minimal error"
    assert error.tool_input is None
    assert error.tool_output is None
    assert error.tool_schema is None


# Test SmokeTestResult


def test_smoke_test_result_success():
    """Test creating a successful smoke test result."""
    result = SmokeTestResult(
        test_name="test_connection",
        success=True,
        duration_ms=150.5,
        details={"status": "ok"},
    )

    assert result.test_name == "test_connection"
    assert result.success is True
    assert result.duration_ms == 150.5
    assert result.error_message is None
    assert result.details == {"status": "ok"}


def test_smoke_test_result_failure():
    """Test creating a failed smoke test result."""
    result = SmokeTestResult(
        test_name="test_tool",
        success=False,
        duration_ms=50.2,
        error_message="Connection refused",
        tool_input={"param": "value"},
        tool_output=None,
        tool_schema={"type": "object"},
    )

    assert result.test_name == "test_tool"
    assert result.success is False
    assert result.duration_ms == 50.2
    assert result.error_message == "Connection refused"
    assert result.tool_input == {"param": "value"}
    assert result.tool_output is None
    assert result.tool_schema == {"type": "object"}


# Test SmokeTestReport


def test_smoke_test_report_success_rate_full():
    """Test success rate calculation with all tests passing."""
    report = SmokeTestReport(
        server_url="http://test:5000",
        timestamp="2024-01-01T00:00:00Z",
        total_tests=5,
        passed=5,
        failed=0,
        duration_ms=1000.0,
        results=[],
    )

    assert report.success_rate == 100.0


def test_smoke_test_report_success_rate_partial():
    """Test success rate calculation with some failures."""
    report = SmokeTestReport(
        server_url="http://test:5000",
        timestamp="2024-01-01T00:00:00Z",
        total_tests=10,
        passed=7,
        failed=3,
        duration_ms=1000.0,
        results=[],
    )

    assert report.success_rate == 70.0


def test_smoke_test_report_success_rate_zero_tests():
    """Test success rate calculation with no tests."""
    report = SmokeTestReport(
        server_url="http://test:5000",
        timestamp="2024-01-01T00:00:00Z",
        total_tests=0,
        passed=0,
        failed=0,
        duration_ms=0.0,
        results=[],
    )

    assert report.success_rate == 0.0


def test_smoke_test_report_to_dict():
    """Test converting report to dictionary."""
    results = [
        SmokeTestResult(
            test_name="test1",
            success=True,
            duration_ms=100.5,
            details={"key": "value"},
        ),
        SmokeTestResult(
            test_name="test2",
            success=False,
            duration_ms=50.2,
            error_message="Failed",
            tool_input={"param": "value"},
        ),
    ]

    report = SmokeTestReport(
        server_url="http://test:5000",
        timestamp="2024-01-01T00:00:00Z",
        total_tests=2,
        passed=1,
        failed=1,
        duration_ms=150.7,
        results=results,
    )

    report_dict = report.to_dict()

    assert report_dict["server_url"] == "http://test:5000"
    assert report_dict["timestamp"] == "2024-01-01T00:00:00Z"
    assert report_dict["total_tests"] == 2
    assert report_dict["passed"] == 1
    assert report_dict["failed"] == 1
    assert report_dict["duration_ms"] == 150.7
    assert report_dict["success_rate"] == 50.0
    assert len(report_dict["results"]) == 2
    assert report_dict["results"][0]["test_name"] == "test1"
    assert report_dict["results"][0]["success"] is True
    assert report_dict["results"][1]["test_name"] == "test2"
    assert report_dict["results"][1]["success"] is False


# Test SmokeTestRunner - Connection Tests


@pytest.mark.asyncio
async def test_connection_success(runner):
    """Test successful connection test."""
    result = await runner.test_connection()

    assert result == {"status": "connected"}


@pytest.mark.asyncio
async def test_connection_failure_no_client():
    """Test connection failure when client not initialized."""
    client = AsyncMock(spec=MCPClient)
    client.client = None  # Not initialized
    runner = SmokeTestRunner(client)

    with pytest.raises(Exception, match="MCP client not initialized"):
        await runner.test_connection()


# Test SmokeTestRunner - List Tools Tests


@pytest.mark.asyncio
async def test_list_tools_success(runner, sample_tools):
    """Test successful tool listing."""
    runner.client.list_tools.return_value = sample_tools

    result = await runner.test_list_tools()

    assert result["tool_count"] == 3
    assert "simple_tool" in result["tools"]
    assert "tool_with_params" in result["tools"]
    assert "tool_with_complex_params" in result["tools"]


@pytest.mark.asyncio
async def test_list_tools_empty(runner):
    """Test listing tools when no tools available."""
    runner.client.list_tools.return_value = []

    result = await runner.test_list_tools()

    assert result["tool_count"] == 0
    assert result["tools"] == []


# Test Tool Testability Checking


def test_is_tool_testable_simple_tool(runner):
    """Test that simple tools are testable."""
    schema = {"inputSchema": {"type": "object", "properties": {}, "required": []}}

    assert runner._is_tool_testable(schema) is True


def test_is_tool_testable_with_basic_params(runner):
    """Test that tools with basic parameters are testable."""
    schema = {
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer"},
            },
            "required": ["query"],
        }
    }

    assert runner._is_tool_testable(schema) is True


def test_is_tool_testable_with_ref_not_testable(runner):
    """Test that tools with $ref are not testable."""
    schema = {
        "inputSchema": {
            "type": "object",
            "properties": {"request": {"$ref": "#/definitions/Request"}},
            "required": ["request"],
        }
    }

    assert runner._is_tool_testable(schema) is False


def test_is_tool_testable_with_anyof_ref_not_testable(runner):
    """Test that tools with anyOf containing $ref are not testable."""
    schema = {
        "inputSchema": {
            "type": "object",
            "properties": {
                "data": {
                    "anyOf": [
                        {"type": "string"},
                        {"$ref": "#/definitions/ComplexData"},
                    ]
                }
            },
            "required": ["data"],
        }
    }

    assert runner._is_tool_testable(schema) is False


def test_is_tool_testable_with_oneof_ref_not_testable(runner):
    """Test that tools with oneOf containing $ref are not testable."""
    schema = {
        "inputSchema": {
            "type": "object",
            "properties": {
                "input": {
                    "oneOf": [
                        {"type": "number"},
                        {"$ref": "#/definitions/ComplexInput"},
                    ]
                }
            },
            "required": ["input"],
        }
    }

    assert runner._is_tool_testable(schema) is False


def test_is_tool_testable_with_nested_object_not_testable(runner):
    """Test that tools with nested objects are not testable."""
    schema = {
        "inputSchema": {
            "type": "object",
            "properties": {
                "config": {
                    "type": "object",
                    "properties": {"setting": {"type": "string"}},
                    "required": ["setting"],
                }
            },
            "required": ["config"],
        }
    }

    assert runner._is_tool_testable(schema) is False


def test_is_tool_testable_with_id_param_not_testable(runner):
    """Test that tools requiring ID parameters are not testable."""
    test_cases = [
        {"chart_id": {"type": "string"}},
        {"dashboard_id": {"type": "integer"}},
        {"user_uuid": {"type": "string"}},
        {"resource_key": {"type": "string"}},
    ]

    for properties in test_cases:
        schema = {
            "inputSchema": {
                "type": "object",
                "properties": properties,
                "required": list(properties.keys()),
            }
        }
        assert runner._is_tool_testable(schema) is False


def test_is_tool_testable_with_complex_param_names_not_testable(runner):
    """Test that tools with complex parameter names are not testable."""
    complex_names = ["request", "payload", "body", "data", "input"]

    for param_name in complex_names:
        schema = {
            "inputSchema": {
                "type": "object",
                "properties": {param_name: {"type": "object"}},
                "required": [param_name],
            }
        }
        assert runner._is_tool_testable(schema) is False


def test_is_tool_testable_with_identifier_description_not_testable(runner):
    """Test that tools with identifier-like descriptions are not testable."""
    schema = {
        "inputSchema": {
            "type": "object",
            "properties": {
                "resource": {
                    "type": "string",
                    "description": "The unique identifier for the resource",
                }
            },
            "required": ["resource"],
        }
    }

    assert runner._is_tool_testable(schema) is False


# Test Parameter Generation


def test_generate_reasonable_params_empty_schema(runner):
    """Test parameter generation with empty schema."""
    schema = {"inputSchema": {}}

    params = runner._generate_reasonable_params(schema)

    assert params == {}


def test_generate_reasonable_params_with_defaults(runner):
    """Test parameter generation uses default values."""
    schema = {
        "inputSchema": {
            "properties": {
                "format": {"type": "string", "default": "json"},
                "count": {"type": "integer", "default": 5},
            },
            "required": ["format", "count"],
        }
    }

    params = runner._generate_reasonable_params(schema)

    assert params["format"] == "json"
    assert params["count"] == 5


def test_generate_reasonable_params_integer_types(runner):
    """Test parameter generation for integer types."""
    schema = {
        "inputSchema": {
            "properties": {
                "limit": {"type": "integer"},
                "page_size": {"type": "integer"},
                "page": {"type": "integer"},
                "offset": {"type": "integer"},
                "other": {"type": "integer"},
            },
            "required": ["limit", "page_size", "page", "offset", "other"],
        }
    }

    params = runner._generate_reasonable_params(schema)

    assert params["limit"] == 10
    assert params["page_size"] == 10
    assert params["page"] == 0
    assert params["offset"] == 0
    assert params["other"] == 1


def test_generate_reasonable_params_boolean_types(runner):
    """Test parameter generation for boolean types."""
    schema = {
        "inputSchema": {
            "properties": {"enabled": {"type": "boolean"}},
            "required": ["enabled"],
        }
    }

    params = runner._generate_reasonable_params(schema)

    assert params["enabled"] is False


def test_generate_reasonable_params_string_types(runner):
    """Test parameter generation for string types."""
    schema = {
        "inputSchema": {
            "properties": {
                "search": {"type": "string"},
                "query": {"type": "string"},
                "q": {"type": "string"},
                "format": {"type": "string"},
                "other": {"type": "string"},
            },
            "required": ["search", "query", "q", "format", "other"],
        }
    }

    params = runner._generate_reasonable_params(schema)

    assert params["search"] == ""
    assert params["query"] == ""
    assert params["q"] == ""
    assert params["format"] == "json"
    assert params["other"] == ""


def test_generate_reasonable_params_array_and_object(runner):
    """Test parameter generation for array and object types."""
    schema = {
        "inputSchema": {
            "properties": {
                "items": {"type": "array"},
                "config": {"type": "object"},
            },
            "required": ["items", "config"],
        }
    }

    params = runner._generate_reasonable_params(schema)

    assert params["items"] == []
    assert params["config"] == {}


def test_generate_reasonable_params_skip_optional(runner):
    """Test parameter generation skips optional parameters."""
    schema = {
        "inputSchema": {
            "properties": {
                "required_param": {"type": "string"},
                "optional_param": {"type": "string"},
            },
            "required": ["required_param"],
        }
    }

    params = runner._generate_reasonable_params(schema)

    assert "required_param" in params
    assert "optional_param" not in params


def test_generate_reasonable_params_include_common_optional(runner):
    """Test parameter generation includes common optional parameters."""
    schema = {
        "inputSchema": {
            "properties": {
                "limit": {"type": "integer"},
                "page": {"type": "integer"},
                "page_size": {"type": "integer"},
            },
            "required": [],
        }
    }

    params = runner._generate_reasonable_params(schema)

    assert params["limit"] == 10
    assert params["page"] == 0
    assert params["page_size"] == 10


# Test Tool Testing


@pytest.mark.asyncio
async def test_tool_with_reasonable_params_success(runner):
    """Test successful tool execution with reasonable parameters."""
    tool_name = "test_tool"
    tool_schema = {
        "inputSchema": {
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        }
    }

    mock_result = MCPToolResult(
        tool_call_id="test_id",
        content="Success response",
        is_error=False,
    )
    runner.client.call_tool.return_value = mock_result

    details, params, output, schema = await runner.test_tool_with_reasonable_params(
        tool_name, tool_schema
    )

    assert details["tool"] == tool_name
    assert details["parameters"] == {"query": ""}
    assert details["result_type"] == "str"
    assert params == {"query": ""}
    assert output == "Success response"
    assert schema == tool_schema


@pytest.mark.asyncio
async def test_tool_with_reasonable_params_error(runner):
    """Test tool execution that returns an error."""
    tool_name = "failing_tool"
    tool_schema = {"inputSchema": {}}

    mock_result = MCPToolResult(
        tool_call_id="test_id",
        content=None,
        is_error=True,
        error_message="Tool execution failed",
    )
    runner.client.call_tool.return_value = mock_result

    with pytest.raises(ToolTestError, match="Tool execution failed"):
        await runner.test_tool_with_reasonable_params(tool_name, tool_schema)


@pytest.mark.asyncio
async def test_tool_with_reasonable_params_truncates_large_output(runner):
    """Test that large output is truncated."""
    tool_name = "verbose_tool"
    tool_schema = {"inputSchema": {}}

    large_content = "x" * 15000  # More than 10000 chars
    mock_result = MCPToolResult(
        tool_call_id="test_id",
        content=large_content,
        is_error=False,
    )
    runner.client.call_tool.return_value = mock_result

    _, _, output, _ = await runner.test_tool_with_reasonable_params(tool_name, tool_schema)

    assert len(output) <= 10023  # 10000 + "... (truncated)"
    assert output.endswith("... (truncated)")


# Test Run Test Method


@pytest.mark.asyncio
async def test_run_test_success(runner):
    """Test _run_test with successful execution."""

    async def successful_test():
        await asyncio.sleep(0.01)  # Simulate some work
        return {"result": "success"}

    result = await runner._run_test("test_name", successful_test)

    assert result.test_name == "test_name"
    assert result.success is True
    assert result.duration_ms > 0
    assert result.details == {"result": "success"}
    assert result.error_message is None


@pytest.mark.asyncio
async def test_run_test_failure(runner):
    """Test _run_test with exception."""

    async def failing_test():
        raise ValueError("Test failed")

    result = await runner._run_test("failing_test", failing_test)

    assert result.test_name == "failing_test"
    assert result.success is False
    assert result.duration_ms > 0
    assert result.error_message == "Test failed"


@pytest.mark.asyncio
async def test_run_test_tool_test_error(runner):
    """Test _run_test with ToolTestError."""

    async def tool_error_test():
        raise ToolTestError(
            message="Tool failed",
            tool_input={"param": "value"},
            tool_output="error output",
            tool_schema={"type": "object"},
        )

    result = await runner._run_test("tool_test", tool_error_test, is_tool_test=True)

    assert result.test_name == "tool_test"
    assert result.success is False
    assert result.error_message == "Tool failed"
    assert result.tool_input == {"param": "value"}
    assert result.tool_output == "error output"
    assert result.tool_schema == {"type": "object"}


@pytest.mark.asyncio
async def test_run_test_tool_test_success(runner):
    """Test _run_test with successful tool test."""

    async def tool_success_test():
        return (
            {"details": "ok"},
            {"param": "value"},
            "output",
            {"schema": "object"},
        )

    result = await runner._run_test("tool_test", tool_success_test, is_tool_test=True)

    assert result.test_name == "tool_test"
    assert result.success is True
    assert result.details == {"details": "ok"}
    assert result.tool_input == {"param": "value"}
    assert result.tool_output == "output"
    assert result.tool_schema == {"schema": "object"}


# Test Full Smoke Test Execution


@pytest.mark.asyncio
async def test_run_smoke_tests_connection_failure(runner):
    """Test smoke test stops if connection fails."""
    runner.client.client = None  # Simulate uninitialized client

    report = await runner.run_smoke_tests()

    assert report.total_tests == 1
    assert report.passed == 0
    assert report.failed == 1
    assert report.results[0].test_name == "Connection"
    assert report.results[0].success is False


@pytest.mark.asyncio
async def test_run_smoke_tests_list_tools_failure(runner):
    """Test smoke test stops if list tools fails."""
    # Connection succeeds
    runner.client.client = MagicMock()

    # List tools fails
    runner.client.list_tools.side_effect = Exception("Failed to list tools")

    report = await runner.run_smoke_tests()

    assert report.total_tests == 2
    assert report.passed == 1  # Connection passed
    assert report.failed == 1  # List tools failed
    assert report.results[1].test_name == "List Tools"
    assert report.results[1].success is False


@pytest.mark.asyncio
async def test_run_smoke_tests_no_tools(runner):
    """Test smoke test with no tools available."""
    runner.client.client = MagicMock()
    runner.client.list_tools.return_value = []

    report = await runner.run_smoke_tests(test_all_tools=True)

    assert report.total_tests == 2  # Connection + List Tools
    assert report.passed == 2
    assert report.failed == 0


@pytest.mark.asyncio
async def test_run_smoke_tests_skip_tool_tests(runner, sample_tools):
    """Test smoke test with test_all_tools=False."""
    runner.client.client = MagicMock()
    runner.client.list_tools.return_value = sample_tools

    report = await runner.run_smoke_tests(test_all_tools=False)

    assert report.total_tests == 2  # Only Connection + List Tools
    assert report.passed == 2


@pytest.mark.asyncio
async def test_run_smoke_tests_with_testable_tools(runner):
    """Test smoke test with testable tools."""
    runner.client.client = MagicMock()

    testable_tool = MCPTool(
        name="testable_tool",
        description="A testable tool",
        input_schema={
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    )
    runner.client.list_tools.return_value = [testable_tool]

    mock_result = MCPToolResult(
        tool_call_id="test_id",
        content="Success",
        is_error=False,
    )
    runner.client.call_tool.return_value = mock_result

    report = await runner.run_smoke_tests(test_all_tools=True)

    assert report.total_tests == 3  # Connection + List Tools + Tool test
    assert report.passed == 3
    assert report.failed == 0
    assert report.results[2].test_name == "Tool: testable_tool"


@pytest.mark.asyncio
async def test_run_smoke_tests_with_non_testable_tools(runner):
    """Test smoke test skips non-testable tools."""
    runner.client.client = MagicMock()

    non_testable_tool = MCPTool(
        name="complex_tool",
        description="Tool with complex schema",
        input_schema={
            "properties": {"request": {"$ref": "#/definitions/Request"}},
            "required": ["request"],
        },
    )
    runner.client.list_tools.return_value = [non_testable_tool]

    report = await runner.run_smoke_tests(test_all_tools=True)

    assert report.total_tests == 2  # Only Connection + List Tools
    assert report.passed == 2


@pytest.mark.asyncio
async def test_run_smoke_tests_respects_max_tools(runner):
    """Test smoke test respects max_tools_to_test limit."""
    runner.client.client = MagicMock()

    # Create 15 testable tools
    tools = [
        MCPTool(
            name=f"tool_{i}",
            description=f"Tool {i}",
            input_schema={},
        )
        for i in range(15)
    ]
    runner.client.list_tools.return_value = tools

    mock_result = MCPToolResult(
        tool_call_id="test_id",
        content="Success",
        is_error=False,
    )
    runner.client.call_tool.return_value = mock_result

    report = await runner.run_smoke_tests(test_all_tools=True, max_tools_to_test=5)

    # Connection + List Tools + 5 tool tests
    assert report.total_tests == 7
    assert report.passed == 7


@pytest.mark.asyncio
async def test_run_smoke_tests_mixed_results(runner):
    """Test smoke test with mixed success/failure results."""
    runner.client.client = MagicMock()

    tools = [
        MCPTool(name="good_tool", description="Working tool", input_schema={}),
        MCPTool(name="bad_tool", description="Failing tool", input_schema={}),
    ]
    runner.client.list_tools.return_value = tools

    call_count = 0

    async def mock_call_tool(tool_call, timeout=30.0):
        nonlocal call_count
        call_count += 1
        if "good_tool" in tool_call.name:
            return MCPToolResult(tool_call_id="test", content="OK", is_error=False)
        else:
            return MCPToolResult(
                tool_call_id="test",
                content=None,
                is_error=True,
                error_message="Tool failed",
            )

    runner.client.call_tool = mock_call_tool

    report = await runner.run_smoke_tests(test_all_tools=True)

    assert report.total_tests == 4  # Connection + List Tools + 2 tool tests
    assert report.passed == 3  # Connection + List Tools + good_tool
    assert report.failed == 1  # bad_tool
    assert report.success_rate == 75.0


@pytest.mark.asyncio
async def test_run_smoke_tests_report_metadata(runner):
    """Test smoke test report contains correct metadata."""
    runner.client.client = MagicMock()
    runner.client.list_tools.return_value = []

    report = await runner.run_smoke_tests()

    assert report.server_url == "http://test-server:5000/mcp"
    assert report.timestamp  # Should have a timestamp
    assert report.duration_ms > 0  # Should have elapsed time
    # Verify timestamp is in ISO format with Z suffix
    datetime.fromisoformat(report.timestamp.replace("Z", "+00:00"))


# Test run_smoke_test Function


@pytest.mark.asyncio
async def test_run_smoke_test_function():
    """Test the run_smoke_test convenience function."""
    with patch("testmcpy.smoke_test.MCPClient") as mock_client_class:
        mock_client = AsyncMock(spec=MCPClient)
        mock_client.base_url = "http://test:5000"
        mock_client.client = MagicMock()
        mock_client.list_tools.return_value = []
        mock_client_class.return_value = mock_client

        report = await run_smoke_test(
            mcp_url="http://test:5000",
            auth_config={"type": "bearer", "token": "test_token"},
            test_all_tools=True,
            max_tools_to_test=10,
        )

        # Verify client was created with correct params
        mock_client_class.assert_called_once_with(
            base_url="http://test:5000",
            auth={"type": "bearer", "token": "test_token"},
        )

        # Verify client lifecycle
        mock_client.initialize.assert_called_once()
        mock_client.close.assert_called_once()

        # Verify report
        assert report.server_url == "http://test:5000"
        assert report.total_tests >= 2


# Test Edge Cases


@pytest.mark.asyncio
async def test_timeout_during_tool_execution(runner):
    """Test handling of timeout during tool execution."""
    runner.client.client = MagicMock()

    timeout_tool = MCPTool(
        name="timeout_tool",
        description="Tool that times out",
        input_schema={},
    )
    runner.client.list_tools.return_value = [timeout_tool]

    # Simulate timeout
    mock_result = MCPToolResult(
        tool_call_id="test",
        content=None,
        is_error=True,
        error_message="Tool call 'timeout_tool' timed out after 30s",
    )
    runner.client.call_tool.return_value = mock_result

    report = await runner.run_smoke_tests(test_all_tools=True)

    # Should still complete but mark tool as failed
    assert report.total_tests == 3
    assert report.failed == 1
    assert "timed out" in report.results[2].error_message.lower()


@pytest.mark.asyncio
async def test_invalid_tool_schema(runner):
    """Test handling of tools with invalid schemas."""
    runner.client.client = MagicMock()

    # Tool with malformed schema (missing type)
    invalid_tool = MCPTool(
        name="invalid_tool",
        description="Tool with invalid schema",
        input_schema={"properties": {"param": {}}},  # Missing type
    )
    runner.client.list_tools.return_value = [invalid_tool]

    mock_result = MCPToolResult(
        tool_call_id="test",
        content="OK",
        is_error=False,
    )
    runner.client.call_tool.return_value = mock_result

    # Should handle gracefully
    report = await runner.run_smoke_tests(test_all_tools=True)

    assert report.total_tests >= 2  # At least Connection + List Tools


@pytest.mark.asyncio
async def test_tool_returns_none(runner):
    """Test handling of tool that returns None."""
    runner.client.client = MagicMock()

    null_tool = MCPTool(name="null_tool", description="Returns null", input_schema={})
    runner.client.list_tools.return_value = [null_tool]

    mock_result = MCPToolResult(
        tool_call_id="test",
        content=None,
        is_error=False,
    )
    runner.client.call_tool.return_value = mock_result

    report = await runner.run_smoke_tests(test_all_tools=True)

    # Should still pass with null content
    tool_result = next(r for r in report.results if r.test_name == "Tool: null_tool")
    assert tool_result.success is True


@pytest.mark.asyncio
async def test_malformed_tool_response(runner):
    """Test handling of malformed tool response."""
    runner.client.client = MagicMock()

    tool = MCPTool(name="tool", description="Tool", input_schema={})
    runner.client.list_tools.return_value = [tool]

    # Return malformed response
    mock_result = MCPToolResult(
        tool_call_id="test",
        content={"unexpected": "structure", "nested": {"deeply": {"value": 123}}},
        is_error=False,
    )
    runner.client.call_tool.return_value = mock_result

    report = await runner.run_smoke_tests(test_all_tools=True)

    # Should handle gracefully
    tool_result = next(r for r in report.results if r.test_name == "Tool: tool")
    assert tool_result.success is True


@pytest.mark.asyncio
async def test_missing_mcp_server(runner):
    """Test handling when MCP server is not available."""
    runner.client.client = None

    report = await runner.run_smoke_tests()

    assert report.total_tests == 1
    assert report.failed == 1
    assert report.results[0].test_name == "Connection"
    assert "not initialized" in report.results[0].error_message.lower()
