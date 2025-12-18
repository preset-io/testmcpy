"""
Smoke testing for MCP servers.

This module provides functionality to run basic health checks and smoke tests
on MCP servers to verify they're working correctly.
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from testmcpy.src.mcp_client import MCPClient, MCPToolCall


class ToolTestError(Exception):
    """Exception for tool test failures that includes input/output details."""

    def __init__(
        self,
        message: str,
        tool_input: dict[str, Any] | None = None,
        tool_output: Any | None = None,
        tool_schema: dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.tool_input = tool_input
        self.tool_output = tool_output
        self.tool_schema = tool_schema


@dataclass
class SmokeTestResult:
    """Result from a single smoke test."""

    test_name: str
    success: bool
    duration_ms: float
    error_message: str | None = None
    details: dict[str, Any] | None = None
    # Detailed tool call information
    tool_input: dict[str, Any] | None = None  # Parameters sent to tool
    tool_output: Any | None = None  # Response from tool
    tool_schema: dict[str, Any] | None = None  # Tool's input schema


@dataclass
class SmokeTestReport:
    """Complete smoke test report."""

    server_url: str
    timestamp: str
    total_tests: int
    passed: int
    failed: int
    duration_ms: float
    results: list[SmokeTestResult]

    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage."""
        if self.total_tests == 0:
            return 0.0
        return (self.passed / self.total_tests) * 100

    def to_dict(self) -> dict:
        """Convert report to dictionary."""
        return {
            "server_url": self.server_url,
            "timestamp": self.timestamp,
            "total_tests": self.total_tests,
            "passed": self.passed,
            "failed": self.failed,
            "duration_ms": self.duration_ms,
            "success_rate": round(self.success_rate, 2),
            "results": [
                {
                    "test_name": r.test_name,
                    "success": r.success,
                    "duration_ms": round(r.duration_ms, 2),
                    "error_message": r.error_message,
                    "details": r.details,
                    "tool_input": r.tool_input,
                    "tool_output": r.tool_output,
                    "tool_schema": r.tool_schema,
                }
                for r in self.results
            ],
        }


class SmokeTestRunner:
    """Runs smoke tests against an MCP server."""

    def __init__(self, mcp_client: MCPClient):
        self.client = mcp_client
        self.results: list[SmokeTestResult] = []

    async def _run_test(
        self,
        test_name: str,
        test_func,
        is_tool_test: bool = False,
    ) -> SmokeTestResult:
        """Run a single test and capture results."""
        start = asyncio.get_event_loop().time()
        try:
            result = await test_func()
            duration_ms = (asyncio.get_event_loop().time() - start) * 1000

            if is_tool_test and isinstance(result, tuple):
                # Tool test returns (details, input, output, schema)
                details, tool_input, tool_output, tool_schema = result
                return SmokeTestResult(
                    test_name=test_name,
                    success=True,
                    duration_ms=duration_ms,
                    details=details,
                    tool_input=tool_input,
                    tool_output=tool_output,
                    tool_schema=tool_schema,
                )
            else:
                return SmokeTestResult(
                    test_name=test_name,
                    success=True,
                    duration_ms=duration_ms,
                    details=result,
                )
        except ToolTestError as e:
            # Tool test error with input/output details
            duration_ms = (asyncio.get_event_loop().time() - start) * 1000
            return SmokeTestResult(
                test_name=test_name,
                success=False,
                duration_ms=duration_ms,
                error_message=str(e),
                tool_input=e.tool_input,
                tool_output=e.tool_output,
                tool_schema=e.tool_schema,
            )
        except Exception as e:
            duration_ms = (asyncio.get_event_loop().time() - start) * 1000
            return SmokeTestResult(
                test_name=test_name,
                success=False,
                duration_ms=duration_ms,
                error_message=str(e),
            )

    async def test_connection(self) -> dict:
        """Test basic MCP connection."""
        if not self.client.client:
            raise Exception("MCP client not initialized")
        return {"status": "connected"}

    async def test_list_tools(self) -> dict:
        """Test listing available tools."""
        tools = await self.client.list_tools()
        return {"tool_count": len(tools), "tools": [t.name for t in tools]}

    async def test_tool_with_reasonable_params(
        self, tool_name: str, tool_schema: dict
    ) -> tuple[dict, dict, Any, dict]:
        """Test a tool with reasonable default parameters.

        Returns:
            Tuple of (details_dict, input_params, output_content, schema)
        """
        # Generate reasonable parameters based on schema
        params = self._generate_reasonable_params(tool_schema)

        # Call the tool
        tool_call = MCPToolCall(
            id=f"smoke_test_{tool_name}",
            name=tool_name,
            arguments=params,
        )

        result = await self.client.call_tool(tool_call, timeout=30.0)

        if result.is_error:
            # Still capture the input/output even on error
            raise ToolTestError(
                message=result.error_message or "Tool call failed",
                tool_input=params,
                tool_output=result.content,
                tool_schema=tool_schema,
            )

        # Truncate large outputs for storage
        output_content = result.content
        if isinstance(output_content, str) and len(output_content) > 10000:
            output_content = output_content[:10000] + "... (truncated)"

        details = {
            "tool": tool_name,
            "parameters": params,
            "result_type": type(result.content).__name__,
            "result_length": len(str(result.content)) if result.content else 0,
        }

        return details, params, output_content, tool_schema

    def _is_tool_testable(self, tool_schema: dict) -> bool:
        """Check if a tool can be tested with simple parameter generation.

        Returns False if the tool has:
        - Complex nested object parameters (including $ref or anyOf with $ref)
        - Required ID parameters (chart_id, dashboard_id, etc.) that need real values
        - Required string parameters that can't have sensible defaults
        - Required "request" parameters (common pattern for complex inputs)
        """
        input_schema = tool_schema.get("inputSchema", {})
        properties = input_schema.get("properties", {})
        required = input_schema.get("required", [])

        # Common ID parameter patterns that need real values
        id_param_patterns = ["_id", "id", "_uuid", "uuid", "_key", "key"]

        # Common complex request parameter names
        complex_param_names = ["request", "payload", "body", "data", "input"]

        for param_name in required:
            param_def = properties.get(param_name, {})

            # Check if this is a required parameter with a complex name pattern
            if param_name.lower() in complex_param_names:
                return False

            # Check if this is a complex object with $ref
            if "$ref" in param_def:
                return False

            # Check if it uses anyOf (union type) - often indicates complex schemas
            if "anyOf" in param_def:
                # Check if any option in anyOf has $ref
                for option in param_def.get("anyOf", []):
                    if "$ref" in option:
                        return False

            # Check if it uses oneOf (union type) - similar to anyOf
            if "oneOf" in param_def:
                for option in param_def.get("oneOf", []):
                    if "$ref" in option:
                        return False

            # Check if it's an object type (which might have nested requirements)
            if param_def.get("type") == "object":
                # Check if it has properties with required fields
                nested_props = param_def.get("properties", {})
                nested_required = param_def.get("required", [])
                if nested_required or nested_props:
                    return False

            # Check if it's a required string parameter that looks like an ID
            if param_def.get("type") == "string":
                param_lower = param_name.lower()
                # Skip tools with required ID-like parameters
                for pattern in id_param_patterns:
                    if pattern in param_lower:
                        return False
                # Also skip required string params without defaults
                # (they likely need specific values we can't guess)
                if param_def.get("default") is None:
                    # Check if description suggests it's a required identifier
                    desc = param_def.get("description", "").lower()
                    if any(word in desc for word in ["id", "identifier", "name", "key", "slug"]):
                        return False

            # Check for required integer parameters that look like IDs
            if param_def.get("type") == "integer":
                param_lower = param_name.lower()
                for pattern in id_param_patterns:
                    if pattern in param_lower:
                        return False

        return True

    def _generate_reasonable_params(self, tool_schema: dict) -> dict:
        """Generate reasonable parameter values based on tool schema."""
        params = {}
        input_schema = tool_schema.get("inputSchema", {})
        properties = input_schema.get("properties", {})
        required = input_schema.get("required", [])

        for param_name, param_def in properties.items():
            # Only process required parameters and commonly needed optional ones
            if param_name not in required:
                # Skip optional parameters unless they're commonly needed
                if param_name not in ["limit", "page", "page_size"]:
                    continue

            param_type = param_def.get("type", "string")
            param_default = param_def.get("default")

            if param_default is not None:
                params[param_name] = param_default
            elif param_type == "integer":
                # Use reasonable defaults for common integer params
                if param_name in ["limit", "page_size"]:
                    params[param_name] = 10
                elif param_name in ["page", "offset"]:
                    params[param_name] = 0
                else:
                    params[param_name] = 1
            elif param_type == "boolean":
                params[param_name] = False
            elif param_type == "string":
                # Use reasonable defaults for common string params
                if param_name in ["search", "query", "q"]:
                    params[param_name] = ""
                elif param_name in ["format"]:
                    params[param_name] = "json"
                else:
                    params[param_name] = ""
            elif param_type == "array":
                params[param_name] = []
            elif param_type == "object":
                params[param_name] = {}

        return params

    async def run_smoke_tests(
        self,
        test_all_tools: bool = True,
        max_tools_to_test: int = 10,
    ) -> SmokeTestReport:
        """
        Run comprehensive smoke tests on the MCP server.

        Args:
            test_all_tools: Whether to test all tools or just basic operations
            max_tools_to_test: Maximum number of tools to test (to avoid long-running tests)

        Returns:
            SmokeTestReport with all test results
        """
        start_time = asyncio.get_event_loop().time()
        self.results = []

        # Test 1: Connection
        result = await self._run_test("Connection", self.test_connection)
        self.results.append(result)

        if not result.success:
            # If connection fails, stop here
            return self._create_report(start_time)

        # Test 2: List Tools
        result = await self._run_test("List Tools", self.test_list_tools)
        self.results.append(result)

        if not result.success or not test_all_tools:
            return self._create_report(start_time)

        # Test 3+: Test individual tools with reasonable parameters
        tools = await self.client.list_tools()

        # Filter to testable tools only
        testable_tools = []
        for tool in tools:
            tool_schema = {
                "inputSchema": tool.input_schema if hasattr(tool, "input_schema") else {}
            }
            if self._is_tool_testable(tool_schema):
                testable_tools.append((tool, tool_schema))

        # Limit number of tools tested
        tools_to_test = testable_tools[:max_tools_to_test]

        for tool, tool_schema in tools_to_test:
            result = await self._run_test(
                f"Tool: {tool.name}",
                lambda t=tool, s=tool_schema: self.test_tool_with_reasonable_params(t.name, s),
                is_tool_test=True,
            )
            self.results.append(result)

        return self._create_report(start_time)

    def _create_report(self, start_time: float) -> SmokeTestReport:
        """Create smoke test report from results."""
        duration_ms = (asyncio.get_event_loop().time() - start_time) * 1000
        passed = sum(1 for r in self.results if r.success)
        failed = sum(1 for r in self.results if not r.success)

        return SmokeTestReport(
            server_url=self.client.base_url,
            timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            total_tests=len(self.results),
            passed=passed,
            failed=failed,
            duration_ms=duration_ms,
            results=self.results,
        )


async def run_smoke_test(
    mcp_url: str,
    auth_config: dict | None = None,
    test_all_tools: bool = True,
    max_tools_to_test: int = 10,
) -> SmokeTestReport:
    """
    Run smoke tests on an MCP server.

    Args:
        mcp_url: MCP server URL
        auth_config: Authentication configuration
        test_all_tools: Whether to test all tools
        max_tools_to_test: Maximum number of tools to test

    Returns:
        SmokeTestReport with test results
    """
    client = MCPClient(base_url=mcp_url, auth=auth_config)
    await client.initialize()

    try:
        runner = SmokeTestRunner(client)
        report = await runner.run_smoke_tests(
            test_all_tools=test_all_tools,
            max_tools_to_test=max_tools_to_test,
        )
        return report
    finally:
        await client.close()
