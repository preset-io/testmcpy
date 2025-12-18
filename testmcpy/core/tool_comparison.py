"""
Tool Comparison and Benchmarking Module.

This module provides functionality to compare the same MCP tool across:
- Two different MCP servers
- Two different profiles
- Same server with different parameters

Captures execution time, success rates, and response differences.
"""

import json
import statistics
import time
from dataclasses import dataclass
from typing import Any

from testmcpy.mcp_profiles import load_profile
from testmcpy.src.mcp_client import MCPClient, MCPToolCall


@dataclass
class ToolExecutionMetrics:
    """Metrics from a single tool execution."""

    success: bool
    execution_time: float  # in seconds
    response_content: Any
    error_message: str | None = None


@dataclass
class ToolComparisonConfig:
    """Configuration for tool comparison."""

    tool_name: str
    tool_params: dict[str, Any]
    iterations: int = 1

    # Source 1
    profile1: str | None = None
    mcp_url1: str | None = None
    mcp_name1: str | None = None  # Specific MCP server name within profile
    auth1: dict[str, Any] | None = None

    # Source 2
    profile2: str | None = None
    mcp_url2: str | None = None
    mcp_name2: str | None = None  # Specific MCP server name within profile
    auth2: dict[str, Any] | None = None

    # Output
    output_file: str | None = None
    timeout: float = 30.0

    def validate(self) -> tuple[bool, str | None]:
        """Validate configuration.

        Returns:
            Tuple of (is_valid, error_message)
        """
        # Must have at least one source specified
        if not (self.profile1 or self.mcp_url1):
            return False, "Must specify either --profile1 or --mcp-url1"

        if not (self.profile2 or self.mcp_url2):
            return False, "Must specify either --profile2 or --mcp-url2"

        # If both profile and url specified for same source, that's fine - url takes precedence

        if self.iterations < 1:
            return False, "Iterations must be at least 1"

        return True, None


@dataclass
class ToolComparisonStats:
    """Statistical comparison of tool executions."""

    min_time: float
    max_time: float
    avg_time: float
    median_time: float
    success_rate: float  # 0.0 to 1.0
    total_executions: int
    successful_executions: int
    failed_executions: int


@dataclass
class ToolComparisonResult:
    """Result from comparing a tool across two sources."""

    tool_name: str
    tool_params: dict[str, Any]
    iterations: int

    # Source 1 results
    source1_name: str
    source1_stats: ToolComparisonStats
    source1_executions: list[ToolExecutionMetrics]

    # Source 2 results
    source2_name: str
    source2_stats: ToolComparisonStats
    source2_executions: list[ToolExecutionMetrics]

    # Comparison
    responses_match: bool = False
    response_diff: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "tool_name": self.tool_name,
            "tool_params": self.tool_params,
            "iterations": self.iterations,
            "source1": {
                "name": self.source1_name,
                "stats": {
                    "min_time": self.source1_stats.min_time,
                    "max_time": self.source1_stats.max_time,
                    "avg_time": self.source1_stats.avg_time,
                    "median_time": self.source1_stats.median_time,
                    "success_rate": self.source1_stats.success_rate,
                    "total_executions": self.source1_stats.total_executions,
                    "successful_executions": self.source1_stats.successful_executions,
                    "failed_executions": self.source1_stats.failed_executions,
                },
                "executions": [
                    {
                        "success": e.success,
                        "execution_time": e.execution_time,
                        "response_content": e.response_content,
                        "error_message": e.error_message,
                    }
                    for e in self.source1_executions
                ],
            },
            "source2": {
                "name": self.source2_name,
                "stats": {
                    "min_time": self.source2_stats.min_time,
                    "max_time": self.source2_stats.max_time,
                    "avg_time": self.source2_stats.avg_time,
                    "median_time": self.source2_stats.median_time,
                    "success_rate": self.source2_stats.success_rate,
                    "total_executions": self.source2_stats.total_executions,
                    "successful_executions": self.source2_stats.successful_executions,
                    "failed_executions": self.source2_stats.failed_executions,
                },
                "executions": [
                    {
                        "success": e.success,
                        "execution_time": e.execution_time,
                        "response_content": e.response_content,
                        "error_message": e.error_message,
                    }
                    for e in self.source2_executions
                ],
            },
            "comparison": {
                "responses_match": self.responses_match,
                "response_diff": self.response_diff,
            },
        }


class ToolComparator:
    """Compare tool execution across different MCP sources."""

    def __init__(self, config: ToolComparisonConfig):
        """Initialize tool comparator.

        Args:
            config: Comparison configuration
        """
        self.config = config
        self.client1: MCPClient | None = None
        self.client2: MCPClient | None = None

    async def _initialize_clients(self) -> tuple[str, str]:
        """Initialize MCP clients for both sources.

        Returns:
            Tuple of (source1_name, source2_name)

        Raises:
            ValueError: If configuration is invalid
            Exception: If client initialization fails
        """
        # Validate config
        is_valid, error = self.config.validate()
        if not is_valid:
            raise ValueError(f"Invalid configuration: {error}")

        # Initialize source 1
        source1_name = ""
        if self.config.mcp_url1:
            # Direct URL provided
            base_url1 = self.config.mcp_url1
            auth1 = self.config.auth1
            source1_name = f"URL: {base_url1}"
        elif self.config.profile1:
            # Load from profile
            profile1 = load_profile(self.config.profile1)
            if not profile1:
                raise ValueError(f"Profile not found: {self.config.profile1}")

            # Find the MCP server
            if self.config.mcp_name1:
                # Specific MCP server requested
                mcp1 = next((m for m in profile1.mcps if m.name == self.config.mcp_name1), None)
                if not mcp1:
                    raise ValueError(
                        f"MCP server '{self.config.mcp_name1}' not found in "
                        f"profile '{self.config.profile1}'"
                    )
            else:
                # Use default or first MCP
                mcp1 = next((m for m in profile1.mcps if m.default), None)
                if not mcp1 and len(profile1.mcps) > 0:
                    mcp1 = profile1.mcps[0]
                if not mcp1:
                    raise ValueError(f"No MCP servers found in profile '{self.config.profile1}'")

            base_url1 = mcp1.mcp_url
            auth1 = mcp1.auth.to_dict()
            source1_name = f"Profile: {self.config.profile1} / MCP: {mcp1.name}"
        else:
            raise ValueError("Must specify either profile1 or mcp_url1")

        # Initialize source 2
        source2_name = ""
        if self.config.mcp_url2:
            # Direct URL provided
            base_url2 = self.config.mcp_url2
            auth2 = self.config.auth2
            source2_name = f"URL: {base_url2}"
        elif self.config.profile2:
            # Load from profile
            profile2 = load_profile(self.config.profile2)
            if not profile2:
                raise ValueError(f"Profile not found: {self.config.profile2}")

            # Find the MCP server
            if self.config.mcp_name2:
                # Specific MCP server requested
                mcp2 = next((m for m in profile2.mcps if m.name == self.config.mcp_name2), None)
                if not mcp2:
                    raise ValueError(
                        f"MCP server '{self.config.mcp_name2}' not found in "
                        f"profile '{self.config.profile2}'"
                    )
            else:
                # Use default or first MCP
                mcp2 = next((m for m in profile2.mcps if m.default), None)
                if not mcp2 and len(profile2.mcps) > 0:
                    mcp2 = profile2.mcps[0]
                if not mcp2:
                    raise ValueError(f"No MCP servers found in profile '{self.config.profile2}'")

            base_url2 = mcp2.mcp_url
            auth2 = mcp2.auth.to_dict()
            source2_name = f"Profile: {self.config.profile2} / MCP: {mcp2.name}"
        else:
            raise ValueError("Must specify either profile2 or mcp_url2")

        # Create clients
        self.client1 = MCPClient(base_url=base_url1, auth=auth1)
        self.client2 = MCPClient(base_url=base_url2, auth=auth2)

        # Initialize connections
        await self.client1.initialize(timeout=self.config.timeout)
        await self.client2.initialize(timeout=self.config.timeout)

        return source1_name, source2_name

    async def _execute_tool_once(
        self, client: MCPClient, tool_name: str, params: dict[str, Any]
    ) -> ToolExecutionMetrics:
        """Execute a tool once and measure metrics.

        Args:
            client: MCP client to use
            tool_name: Name of tool to call
            params: Tool parameters

        Returns:
            Execution metrics
        """
        start_time = time.time()

        tool_call = MCPToolCall(name=tool_name, arguments=params, id=f"compare-{time.time()}")

        result = await client.call_tool(tool_call, timeout=self.config.timeout)

        end_time = time.time()
        execution_time = end_time - start_time

        return ToolExecutionMetrics(
            success=not result.is_error,
            execution_time=execution_time,
            response_content=result.content if not result.is_error else None,
            error_message=result.error_message if result.is_error else None,
        )

    def _calculate_stats(self, executions: list[ToolExecutionMetrics]) -> ToolComparisonStats:
        """Calculate statistics from execution metrics.

        Args:
            executions: List of execution metrics

        Returns:
            Comparison statistics
        """
        successful = [e for e in executions if e.success]
        failed = [e for e in executions if not e.success]

        times = [e.execution_time for e in executions]

        return ToolComparisonStats(
            min_time=min(times) if times else 0.0,
            max_time=max(times) if times else 0.0,
            avg_time=statistics.mean(times) if times else 0.0,
            median_time=statistics.median(times) if times else 0.0,
            success_rate=len(successful) / len(executions) if executions else 0.0,
            total_executions=len(executions),
            successful_executions=len(successful),
            failed_executions=len(failed),
        )

    def _compare_responses(
        self, executions1: list[ToolExecutionMetrics], executions2: list[ToolExecutionMetrics]
    ) -> tuple[bool, str | None]:
        """Compare responses from both sources.

        Args:
            executions1: Executions from source 1
            executions2: Executions from source 2

        Returns:
            Tuple of (responses_match, diff_description)
        """
        # Get first successful response from each
        success1 = next((e for e in executions1 if e.success), None)
        success2 = next((e for e in executions2 if e.success), None)

        if not success1 or not success2:
            return False, "One or both sources had no successful executions"

        # Compare content
        content1 = success1.response_content
        content2 = success2.response_content

        # Try to compare as JSON if possible
        try:
            if isinstance(content1, str):
                content1 = json.loads(content1)
            if isinstance(content2, str):
                content2 = json.loads(content2)
        except (json.JSONDecodeError, TypeError):
            pass  # Keep as strings

        if content1 == content2:
            return True, None

        # Generate diff description
        diff = (
            f"Response 1 type: {type(content1).__name__}, "
            f"Response 2 type: {type(content2).__name__}"
        )
        return False, diff

    async def compare(self) -> ToolComparisonResult:
        """Run tool comparison.

        Returns:
            Comparison result

        Raises:
            Exception: If comparison fails
        """
        try:
            # Initialize clients
            source1_name, source2_name = await self._initialize_clients()

            # Verify tool exists on both sources
            tools1 = await self.client1.list_tools(timeout=self.config.timeout)
            tools2 = await self.client2.list_tools(timeout=self.config.timeout)

            tool1 = next((t for t in tools1 if t.name == self.config.tool_name), None)
            tool2 = next((t for t in tools2 if t.name == self.config.tool_name), None)

            if not tool1:
                raise ValueError(f"Tool '{self.config.tool_name}' not found in source 1")
            if not tool2:
                raise ValueError(f"Tool '{self.config.tool_name}' not found in source 2")

            # Execute iterations
            executions1 = []
            executions2 = []

            for _ in range(self.config.iterations):
                # Execute on both sources
                result1 = await self._execute_tool_once(
                    self.client1, self.config.tool_name, self.config.tool_params
                )
                result2 = await self._execute_tool_once(
                    self.client2, self.config.tool_name, self.config.tool_params
                )

                executions1.append(result1)
                executions2.append(result2)

            # Calculate stats
            stats1 = self._calculate_stats(executions1)
            stats2 = self._calculate_stats(executions2)

            # Compare responses
            responses_match, diff = self._compare_responses(executions1, executions2)

            return ToolComparisonResult(
                tool_name=self.config.tool_name,
                tool_params=self.config.tool_params,
                iterations=self.config.iterations,
                source1_name=source1_name,
                source1_stats=stats1,
                source1_executions=executions1,
                source2_name=source2_name,
                source2_stats=stats2,
                source2_executions=executions2,
                responses_match=responses_match,
                response_diff=diff,
            )

        finally:
            # Clean up clients
            if self.client1:
                await self.client1.close()
            if self.client2:
                await self.client2.close()
