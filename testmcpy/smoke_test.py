"""
Smoke testing for MCP servers.

This module provides functionality to run basic health checks and smoke tests
on MCP servers to verify they're working correctly.
"""

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from testmcpy.src.mcp_client import MCPClient, MCPToolCall


@dataclass
class SmokeTestResult:
    """Result from a single smoke test."""

    test_name: str
    success: bool
    duration_ms: float
    error_message: str | None = None
    details: dict[str, Any] | None = None


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
                }
                for r in self.results
            ],
        }


class SmokeTestRunner:
    """Runs smoke tests against an MCP server."""

    def __init__(self, mcp_client: MCPClient):
        self.client = mcp_client
        self.results: list[SmokeTestResult] = []

    async def _run_test(self, test_name: str, test_func) -> SmokeTestResult:
        """Run a single test and capture results."""
        start = asyncio.get_event_loop().time()
        try:
            details = await test_func()
            duration_ms = (asyncio.get_event_loop().time() - start) * 1000
            return SmokeTestResult(
                test_name=test_name,
                success=True,
                duration_ms=duration_ms,
                details=details,
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

    async def test_tool_with_reasonable_params(self, tool_name: str, tool_schema: dict) -> dict:
        """Test a tool with reasonable default parameters."""
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
            raise Exception(result.error_message or "Tool call failed")

        return {
            "tool": tool_name,
            "parameters": params,
            "result_type": type(result.content).__name__,
        }

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
        tools_to_test = tools[:max_tools_to_test]  # Limit number of tools tested

        for tool in tools_to_test:
            tool_schema = {
                "inputSchema": tool.inputSchema if hasattr(tool, "inputSchema") else {}
            }

            result = await self._run_test(
                f"Tool: {tool.name}",
                lambda t=tool, s=tool_schema: self.test_tool_with_reasonable_params(
                    t.name, s
                ),
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
            timestamp=datetime.utcnow().isoformat() + "Z",
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
