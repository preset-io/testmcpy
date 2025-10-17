#!/usr/bin/env python3
"""
Phase 0 Research: Test Ollama's tool calling capabilities with MCP protocol.

This script validates that we can:
1. Connect to Ollama
2. Use a model with tool calling capabilities
3. Parse tool calls from the model's response
4. Connect to the MCP service at localhost:5008/mcp/
"""

import json
import asyncio
import time
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
import httpx
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

console = Console()


@dataclass
class ToolCall:
    """Represents a tool call from the LLM."""
    name: str
    arguments: Dict[str, Any]

    def to_dict(self):
        return asdict(self)


@dataclass
class TestResult:
    """Results from a test run."""
    model: str
    success: bool
    tool_called: bool
    tool_name: Optional[str]
    response_time: float
    error: Optional[str]
    raw_response: Optional[str]


class OllamaToolTester:
    """Test Ollama models for tool calling capabilities."""

    def __init__(self, base_url: str = "http://localhost:11434"):
        self.base_url = base_url
        self.client = httpx.AsyncClient(timeout=30.0)

    async def test_model_availability(self, model: str) -> bool:
        """Check if a model is available in Ollama."""
        try:
            response = await self.client.get(f"{self.base_url}/api/tags")
            if response.status_code == 200:
                models = response.json().get("models", [])
                return any(m["name"] == model for m in models)
            return False
        except Exception as e:
            console.print(f"[red]Error checking model availability: {e}[/red]")
            return False

    async def pull_model(self, model: str):
        """Pull a model if not available."""
        console.print(f"[yellow]Pulling model {model}...[/yellow]")
        try:
            response = await self.client.post(
                f"{self.base_url}/api/pull",
                json={"name": model},
                timeout=300.0  # 5 minutes for model download
            )
            if response.status_code == 200:
                console.print(f"[green]Model {model} pulled successfully[/green]")
                return True
            return False
        except Exception as e:
            console.print(f"[red]Error pulling model: {e}[/red]")
            return False

    async def test_tool_calling(self, model: str, prompt: str, tools: List[Dict]) -> TestResult:
        """Test a model's tool calling capability."""
        start_time = time.time()

        try:
            # Prepare the request with tools
            request_data = {
                "model": model,
                "prompt": prompt,
                "tools": tools,
                "format": "json",
                "stream": False,
                "options": {
                    "temperature": 0.1,  # Low temperature for consistent tool calling
                    "num_predict": 512
                }
            }

            # Make the request
            response = await self.client.post(
                f"{self.base_url}/api/generate",
                json=request_data
            )

            response_time = time.time() - start_time

            if response.status_code != 200:
                return TestResult(
                    model=model,
                    success=False,
                    tool_called=False,
                    tool_name=None,
                    response_time=response_time,
                    error=f"HTTP {response.status_code}: {response.text}",
                    raw_response=None
                )

            result = response.json()
            response_text = result.get("response", "")

            # Try to parse tool call from response
            tool_call = self._parse_tool_call(response_text)

            return TestResult(
                model=model,
                success=True,
                tool_called=tool_call is not None,
                tool_name=tool_call.name if tool_call else None,
                response_time=response_time,
                error=None,
                raw_response=response_text
            )

        except Exception as e:
            return TestResult(
                model=model,
                success=False,
                tool_called=False,
                tool_name=None,
                response_time=time.time() - start_time,
                error=str(e),
                raw_response=None
            )

    def _parse_tool_call(self, response: str) -> Optional[ToolCall]:
        """Parse tool call from model response."""
        try:
            # Try to parse as JSON
            data = json.loads(response)

            # Check for common tool call patterns
            if "tool" in data and "arguments" in data:
                return ToolCall(name=data["tool"], arguments=data["arguments"])
            elif "function" in data and "arguments" in data:
                return ToolCall(name=data["function"], arguments=data["arguments"])
            elif "tool_call" in data:
                tc = data["tool_call"]
                if isinstance(tc, dict) and "name" in tc:
                    return ToolCall(
                        name=tc["name"],
                        arguments=tc.get("arguments", {})
                    )

            # Check if the entire response is a tool call
            if "name" in data and ("arguments" in data or "parameters" in data):
                return ToolCall(
                    name=data["name"],
                    arguments=data.get("arguments", data.get("parameters", {}))
                )

        except json.JSONDecodeError:
            # Try to find JSON in the response
            import re
            json_pattern = r'\{[^{}]*\}'
            matches = re.findall(json_pattern, response)
            for match in matches:
                try:
                    data = json.loads(match)
                    if "tool" in data or "function" in data or "name" in data:
                        return self._parse_tool_call(match)
                except:
                    continue

        return None

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()


class MCPServiceTester:
    """Test connectivity to MCP service."""

    def __init__(self, base_url: str = "http://localhost:5008/mcp/"):
        self.base_url = base_url
        self.client = httpx.AsyncClient(timeout=10.0)

    async def test_connection(self) -> bool:
        """Test if MCP service is reachable."""
        try:
            response = await self.client.get(f"{self.base_url}/")
            return response.status_code in [200, 404]  # 404 is OK, means service is running
        except Exception as e:
            console.print(f"[red]MCP service not reachable: {e}[/red]")
            return False

    async def list_tools(self) -> Optional[List[Dict]]:
        """List available MCP tools."""
        try:
            response = await self.client.post(
                self.base_url,
                json={
                    "jsonrpc": "2.0",
                    "method": "tools/list",
                    "params": {},
                    "id": 1
                }
            )
            if response.status_code == 200:
                result = response.json()
                if "result" in result:
                    return result["result"].get("tools", [])
            return None
        except Exception as e:
            console.print(f"[red]Error listing MCP tools: {e}[/red]")
            return None

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()


async def main():
    """Main test runner."""
    console.print(Panel.fit(
        "[bold cyan]MCP Testing Framework - Phase 0 Research[/bold cyan]\n"
        "Testing Ollama models for tool calling capabilities",
        border_style="cyan"
    ))

    # Test models
    models_to_test = [
        "llama3.1:8b",
        "mistral-nemo:latest",
        "qwen2.5:7b",
    ]

    # Sample tool definition
    test_tools = [{
        "type": "function",
        "function": {
            "name": "get_chart_data",
            "description": "Get data for a specific chart from Superset",
            "parameters": {
                "type": "object",
                "properties": {
                    "chart_id": {
                        "type": "integer",
                        "description": "The ID of the chart"
                    }
                },
                "required": ["chart_id"]
            }
        }
    }]

    # Test prompt that should trigger tool use
    test_prompt = "Get the data for chart ID 42"

    # Initialize testers
    ollama_tester = OllamaToolTester()
    mcp_tester = MCPServiceTester()

    # Test MCP service connection
    console.print("\n[bold]Testing MCP Service Connection[/bold]")
    mcp_connected = await mcp_tester.test_connection()
    if mcp_connected:
        console.print("[green]✓ MCP service is reachable[/green]")

        # List available tools
        tools = await mcp_tester.list_tools()
        if tools:
            console.print(f"[green]✓ Found {len(tools)} MCP tools[/green]")
            for tool in tools[:3]:  # Show first 3 tools
                console.print(f"  - {tool.get('name', 'unnamed')}")
            if len(tools) > 3:
                console.print(f"  ... and {len(tools) - 3} more")
    else:
        console.print("[yellow]⚠ MCP service not reachable - continuing with Ollama tests[/yellow]")

    # Test Ollama models
    console.print("\n[bold]Testing Ollama Models[/bold]")

    results = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:

        for model in models_to_test:
            task = progress.add_task(f"Testing {model}...", total=None)

            # Check if model is available
            available = await ollama_tester.test_model_availability(model)
            if not available:
                console.print(f"[yellow]Model {model} not found, attempting to pull...[/yellow]")
                success = await ollama_tester.pull_model(model)
                if not success:
                    console.print(f"[red]Failed to pull {model}, skipping[/red]")
                    progress.remove_task(task)
                    continue

            # Test tool calling
            result = await ollama_tester.test_tool_calling(model, test_prompt, test_tools)
            results.append(result)

            progress.remove_task(task)

            # Display result
            if result.success:
                if result.tool_called:
                    console.print(f"[green]✓ {model}: Tool calling successful ({result.tool_name})[/green]")
                else:
                    console.print(f"[yellow]⚠ {model}: Response received but no tool call detected[/yellow]")
            else:
                console.print(f"[red]✗ {model}: Failed - {result.error}[/red]")

    # Display results table
    console.print("\n[bold]Test Results Summary[/bold]")

    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Model", style="dim")
    table.add_column("Success", justify="center")
    table.add_column("Tool Called", justify="center")
    table.add_column("Response Time", justify="right")
    table.add_column("Tool Name")

    for result in results:
        table.add_row(
            result.model,
            "✓" if result.success else "✗",
            "✓" if result.tool_called else "✗",
            f"{result.response_time:.2f}s",
            result.tool_name or "-"
        )

    console.print(table)

    # Recommendation
    console.print("\n[bold]Recommendation[/bold]")
    successful_models = [r for r in results if r.success and r.tool_called]
    if successful_models:
        best_model = min(successful_models, key=lambda x: x.response_time)
        console.print(
            f"[green]Best model for tool calling: {best_model.model} "
            f"(response time: {best_model.response_time:.2f}s)[/green]"
        )
    else:
        console.print("[yellow]No models successfully demonstrated tool calling.[/yellow]")
        console.print("Consider testing with different models or prompts.")

    # Cleanup
    await ollama_tester.close()
    await mcp_tester.close()


if __name__ == "__main__":
    asyncio.run(main())