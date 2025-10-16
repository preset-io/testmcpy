#!/usr/bin/env python3
"""
MCP Testing Framework CLI - Test and validate LLM+MCP interactions.

This CLI provides commands for testing LLM tool calling capabilities with MCP services,
running evaluation suites, and generating reports.
"""

import asyncio
import json
import os
import logging
from pathlib import Path
from typing import Optional, List
from enum import Enum

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.syntax import Syntax
from rich import print as rprint
import yaml
from dotenv import load_dotenv

# Suppress MCP notification validation warnings
logging.getLogger().setLevel(logging.ERROR)

# Load environment variables from .env file
load_dotenv(Path(__file__).parent / ".env")

app = typer.Typer(
    name="mcp-test",
    help="MCP Testing Framework - Test LLM tool calling with MCP services",
    add_completion=False,
)

console = Console()

# Config defaults from environment variables
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "llama3.1:8b")
DEFAULT_PROVIDER = os.getenv("DEFAULT_PROVIDER", "ollama")
DEFAULT_MCP_URL = os.getenv("MCP_URL", "http://localhost:5008/mcp/")


class OutputFormat(str, Enum):
    """Output format options."""
    yaml = "yaml"
    json = "json"
    table = "table"


class ModelProvider(str, Enum):
    """Supported model providers."""
    ollama = "ollama"
    openai = "openai"
    local = "local"
    anthropic = "anthropic"
    claude_sdk = "claude-sdk"
    claude_cli = "claude-cli"


@app.command()
def research(
    model: str = typer.Option(DEFAULT_MODEL, "--model", "-m", help="Model to test"),
    provider: ModelProvider = typer.Option(DEFAULT_PROVIDER, "--provider", "-p", help="Model provider"),
    mcp_url: str = typer.Option(DEFAULT_MCP_URL, "--mcp-url", help="MCP service URL"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output file for results"),
    format: OutputFormat = typer.Option(OutputFormat.table, "--format", "-f", help="Output format"),
):
    """
    Research and test LLM tool calling capabilities.

    This command tests whether a given LLM model can successfully call MCP tools.
    """
    console.print(Panel.fit(
        "[bold cyan]MCP Testing Framework - Research Mode[/bold cyan]\n"
        f"Testing {model} via {provider.value}",
        border_style="cyan"
    ))

    async def run_research():
        # Import here to avoid circular dependencies
        from research.test_ollama_tools import OllamaToolTester, MCPServiceTester, TestResult

        # Test MCP connection
        console.print("\n[bold]Testing MCP Service[/bold]")
        mcp_tester = MCPServiceTester(mcp_url)

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Connecting to MCP service...", total=None)

            connected = await mcp_tester.test_connection()
            progress.update(task, completed=True)

            if connected:
                console.print("[green]✓ MCP service is reachable[/green]")
                tools = await mcp_tester.list_tools()
                if tools:
                    console.print(f"[green]✓ Found {len(tools)} MCP tools[/green]")
            else:
                console.print("[red]✗ MCP service not reachable[/red]")

        # Test model
        console.print(f"\n[bold]Testing Model: {model}[/bold]")

        if provider == ModelProvider.ollama:
            tester = OllamaToolTester()

            # Define test tools
            test_tools = [{
                "type": "function",
                "function": {
                    "name": "get_chart_data",
                    "description": "Get data for a specific chart",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "chart_id": {"type": "integer", "description": "Chart ID"}
                        },
                        "required": ["chart_id"]
                    }
                }
            }]

            # Test prompt
            test_prompt = "Get the data for chart ID 42"

            # Run test
            result = await tester.test_tool_calling(model, test_prompt, test_tools)

            # Display results
            if format == OutputFormat.table:
                table = Table(show_header=True, header_style="bold cyan")
                table.add_column("Property", style="dim")
                table.add_column("Value")

                table.add_row("Model", model)
                table.add_row("Success", "✓" if result.success else "✗")
                table.add_row("Tool Called", "✓" if result.tool_called else "✗")
                table.add_row("Tool Name", result.tool_name or "-")
                table.add_row("Response Time", f"{result.response_time:.2f}s")

                if result.error:
                    table.add_row("Error", f"[red]{result.error}[/red]")

                console.print(table)

            elif format == OutputFormat.json:
                output_data = {
                    "model": result.model,
                    "success": result.success,
                    "tool_called": result.tool_called,
                    "tool_name": result.tool_name,
                    "response_time": result.response_time,
                    "error": result.error,
                }
                console.print(Syntax(json.dumps(output_data, indent=2), "json"))

            elif format == OutputFormat.yaml:
                output_data = {
                    "model": result.model,
                    "success": result.success,
                    "tool_called": result.tool_called,
                    "tool_name": result.tool_name,
                    "response_time": result.response_time,
                    "error": result.error,
                }
                console.print(Syntax(yaml.dump(output_data), "yaml"))

            # Save to file if requested
            if output:
                output_data = {
                    "model": result.model,
                    "provider": provider.value,
                    "success": result.success,
                    "tool_called": result.tool_called,
                    "tool_name": result.tool_name,
                    "response_time": result.response_time,
                    "error": result.error,
                    "raw_response": result.raw_response,
                }

                if format == OutputFormat.json:
                    output.write_text(json.dumps(output_data, indent=2))
                else:
                    output.write_text(yaml.dump(output_data))

                console.print(f"\n[green]Results saved to {output}[/green]")

            await tester.close()

        await mcp_tester.close()

    asyncio.run(run_research())


@app.command()
def run(
    test_path: Path = typer.Argument(..., help="Path to test file or directory"),
    model: str = typer.Option(DEFAULT_MODEL, "--model", "-m", help="Model to use"),
    provider: ModelProvider = typer.Option(DEFAULT_PROVIDER, "--provider", "-p", help="Model provider"),
    mcp_url: str = typer.Option(DEFAULT_MCP_URL, "--mcp-url", help="MCP service URL"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output report file"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Don't actually run tests"),
    hide_tool_output: bool = typer.Option(False, "--hide-tool-output", help="Hide detailed tool call output in verbose mode"),
):
    """
    Run test cases against MCP service.

    This command executes test cases defined in YAML/JSON files.
    """
    console.print(Panel.fit(
        "[bold cyan]MCP Testing Framework - Run Tests[/bold cyan]\n"
        f"Model: {model} | Provider: {provider.value}",
        border_style="cyan"
    ))

    async def run_tests():
        # Import test runner
        from src.test_runner import TestRunner, TestCase

        runner = TestRunner(
            model=model,
            provider=provider.value,
            mcp_url=mcp_url,
            verbose=verbose,
            hide_tool_output=hide_tool_output
        )

        # Load test cases
        test_cases = []
        if test_path.is_file():
            with open(test_path) as f:
                if test_path.suffix == ".json":
                    data = json.load(f)
                else:
                    data = yaml.safe_load(f)

                if "tests" in data:
                    for test_data in data["tests"]:
                        test_cases.append(TestCase.from_dict(test_data))
                else:
                    test_cases.append(TestCase.from_dict(data))

        elif test_path.is_dir():
            for file in test_path.glob("*.yaml"):
                with open(file) as f:
                    data = yaml.safe_load(f)
                    if "tests" in data:
                        for test_data in data["tests"]:
                            test_cases.append(TestCase.from_dict(test_data))

        console.print(f"\n[bold]Found {len(test_cases)} test case(s)[/bold]")

        if dry_run:
            console.print("[yellow]DRY RUN - Not executing tests[/yellow]")
            for i, test in enumerate(test_cases, 1):
                console.print(f"{i}. {test.name}: {test.prompt[:50]}...")
            return

        # Run tests
        results = await runner.run_tests(test_cases)

        # Display results
        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("Test", style="dim")
        table.add_column("Status")
        table.add_column("Score")
        table.add_column("Time")
        table.add_column("Details")

        total_passed = 0
        total_cost = 0.0
        total_tokens = 0
        for result in results:
            status = "[green]PASS[/green]" if result.passed else "[red]FAIL[/red]"
            if result.passed:
                total_passed += 1

            # Aggregate cost and tokens from TestResult
            total_cost += result.cost
            if result.token_usage and 'total' in result.token_usage:
                total_tokens += result.token_usage['total']

            table.add_row(
                result.test_name,
                status,
                f"{result.score:.2f}",
                f"{result.duration:.2f}s",
                result.reason or "-"
            )

        console.print(table)

        # Summary with cost and tokens
        summary_parts = [f"{total_passed}/{len(results)} tests passed"]
        if total_tokens > 0:
            summary_parts.append(f"{total_tokens:,} tokens")
        if total_cost > 0:
            summary_parts.append(f"${total_cost:.4f}")

        console.print(f"\n[bold]Summary:[/bold] {' | '.join(summary_parts)}")

        # Save report if requested
        if output:
            report_data = {
                "model": model,
                "provider": provider.value,
                "summary": {
                    "total": len(results),
                    "passed": total_passed,
                    "failed": len(results) - total_passed,
                },
                "results": [r.to_dict() for r in results]
            }

            if output.suffix == ".json":
                output.write_text(json.dumps(report_data, indent=2))
            else:
                output.write_text(yaml.dump(report_data))

            console.print(f"\n[green]Report saved to {output}[/green]")

    asyncio.run(run_tests())


@app.command()
def tools(
    mcp_url: str = typer.Option(DEFAULT_MCP_URL, "--mcp-url", help="MCP service URL"),
    format: OutputFormat = typer.Option(OutputFormat.table, "--format", "-f", help="Output format"),
):
    """
    List available MCP tools.

    This command connects to the MCP service and lists all available tools.
    """
    async def list_tools():
        from src.mcp_client import MCPClient

        console.print("[bold]Connecting to MCP service...[/bold]")

        try:
            async with MCPClient(mcp_url) as client:
                tools = await client.list_tools()

                if format == OutputFormat.table:
                    table = Table(show_header=True, header_style="bold cyan")
                    table.add_column("Name", style="dim")
                    table.add_column("Description")
                    table.add_column("Parameters")

                    for tool in tools:
                        params = json.dumps(tool.input_schema, indent=2) if tool.input_schema else "{}"
                        table.add_row(
                            tool.name,
                            tool.description[:50] + "..." if len(tool.description) > 50 else tool.description,
                            params[:100] + "..." if len(params) > 100 else params
                        )

                    console.print(table)

                elif format == OutputFormat.json:
                    output_data = [
                        {
                            "name": tool.name,
                            "description": tool.description,
                            "input_schema": tool.input_schema
                        }
                        for tool in tools
                    ]
                    console.print(Syntax(json.dumps(output_data, indent=2), "json"))

                elif format == OutputFormat.yaml:
                    output_data = [
                        {
                            "name": tool.name,
                            "description": tool.description,
                            "input_schema": tool.input_schema
                        }
                        for tool in tools
                    ]
                    console.print(Syntax(yaml.dump(output_data), "yaml"))

                console.print(f"\n[green]Found {len(tools)} tools[/green]")

        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")

    asyncio.run(list_tools())


@app.command()
def report(
    report_files: List[Path] = typer.Argument(..., help="Report files to compare"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output comparison file"),
):
    """
    Compare test reports from different models.

    This command takes multiple report files and generates a comparison.
    """
    console.print(Panel.fit(
        "[bold cyan]MCP Testing Framework - Report Comparison[/bold cyan]",
        border_style="cyan"
    ))

    reports = []
    for file in report_files:
        with open(file) as f:
            if file.suffix == ".json":
                reports.append(json.load(f))
            else:
                reports.append(yaml.safe_load(f))

    # Create comparison table
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Model", style="dim")
    table.add_column("Provider")
    table.add_column("Total Tests")
    table.add_column("Passed")
    table.add_column("Failed")
    table.add_column("Success Rate")

    for report in reports:
        summary = report["summary"]
        success_rate = (summary["passed"] / summary["total"] * 100) if summary["total"] > 0 else 0

        table.add_row(
            report["model"],
            report.get("provider", "unknown"),
            str(summary["total"]),
            f"[green]{summary['passed']}[/green]",
            f"[red]{summary['failed']}[/red]",
            f"{success_rate:.1f}%"
        )

    console.print(table)

    # Find tests that failed in one model but not another
    if len(reports) == 2:
        console.print("\n[bold]Differential Analysis[/bold]")

        r1, r2 = reports[0], reports[1]
        r1_results = {r["test_name"]: r["passed"] for r in r1["results"]}
        r2_results = {r["test_name"]: r["passed"] for r in r2["results"]}

        # Tests that failed in r1 but passed in r2
        failed_in_1 = [name for name, passed in r1_results.items() if not passed and r2_results.get(name, False)]
        # Tests that failed in r2 but passed in r1
        failed_in_2 = [name for name, passed in r2_results.items() if not passed and r1_results.get(name, False)]

        if failed_in_1:
            console.print(f"\n[yellow]Tests that failed in {r1['model']} but passed in {r2['model']}:[/yellow]")
            for test in failed_in_1:
                console.print(f"  - {test}")

        if failed_in_2:
            console.print(f"\n[yellow]Tests that failed in {r2['model']} but passed in {r1['model']}:[/yellow]")
            for test in failed_in_2:
                console.print(f"  - {test}")

    # Save comparison if requested
    if output:
        comparison = {
            "reports": reports,
            "comparison": {
                "models": [r["model"] for r in reports],
                "summary": [r["summary"] for r in reports]
            }
        }

        if output.suffix == ".json":
            output.write_text(json.dumps(comparison, indent=2))
        else:
            output.write_text(yaml.dump(comparison))

        console.print(f"\n[green]Comparison saved to {output}[/green]")


@app.command()
def chat(
    model: str = typer.Option(DEFAULT_MODEL, "--model", "-m", help="Model to use"),
    provider: ModelProvider = typer.Option(DEFAULT_PROVIDER, "--provider", "-p", help="Model provider"),
    mcp_url: str = typer.Option(DEFAULT_MCP_URL, "--mcp-url", help="MCP service URL"),
    no_mcp: bool = typer.Option(False, "--no-mcp", help="Chat without MCP tools"),
):
    """
    Interactive chat with LLM that has access to MCP tools.

    Start a chat session where you can directly talk to the LLM and it can use
    MCP tools from your service. Type 'exit' or 'quit' to end the session.

    Use --no-mcp flag to chat without MCP tools.
    """
    if no_mcp:
        console.print(Panel.fit(
            f"[bold cyan]Interactive Chat with {model}[/bold cyan]\n"
            f"Provider: {provider.value}\nMode: Standalone (no MCP tools)\n\n"
            "[dim]Type your message and press Enter. Type 'exit' or 'quit' to end session.[/dim]",
            border_style="cyan"
        ))
    else:
        console.print(Panel.fit(
            f"[bold cyan]Interactive Chat with {model}[/bold cyan]\n"
            f"Provider: {provider.value}\nMCP Service: {mcp_url}\n\n"
            "[dim]Type your message and press Enter. Type 'exit' or 'quit' to end session.[/dim]",
            border_style="cyan"
        ))

    async def chat_session():
        import sys
        import os
        sys.path.append(os.path.dirname(os.path.abspath(__file__)))

        from src.llm_integration import create_llm_provider
        from src.mcp_client import MCPClient

        # Initialize LLM
        llm = create_llm_provider(provider.value, model)
        await llm.initialize()

        tools = []
        mcp_client = None

        if not no_mcp:
            try:
                # Initialize MCP client
                mcp_client = MCPClient(mcp_url)
                await mcp_client.initialize()

                # Get available tools
                tools = await mcp_client.list_tools()
                console.print(f"[green]Connected to MCP service with {len(tools)} tools available[/green]\n")
            except Exception as e:
                console.print(f"[yellow]MCP connection failed: {e}[/yellow]")
                console.print("[yellow]Continuing without MCP tools...[/yellow]\n")

        if not tools:
            console.print("[dim]Chat mode: Standalone (no tools available)[/dim]\n")

        # Chat loop
        while True:
            try:
                # Get user input
                user_input = console.input("[bold blue]You:[/bold blue] ")

                if user_input.lower() in ['exit', 'quit', 'bye']:
                    console.print("[yellow]Goodbye![/yellow]")
                    break

                if not user_input.strip():
                    continue

                # Show thinking indicator
                with console.status("[dim]Thinking...[/dim]"):
                    # Convert MCPTool objects to dictionaries for LLM
                    tools_dict = []
                    for tool in tools:
                        tools_dict.append({
                            "name": tool.name,
                            "description": tool.description,
                            "inputSchema": tool.input_schema
                        })

                    # Generate response with available tools
                    response = await llm.generate_with_tools(user_input, tools_dict)

                # Display response
                console.print(f"[bold green]{model}:[/bold green] {response.response}")

                # Show tool calls if any
                if response.tool_calls:
                    console.print(f"[dim]Used {len(response.tool_calls)} tool call(s)[/dim]")
                    for tool_call in response.tool_calls:
                        console.print(f"[dim]→ {tool_call['name']}({tool_call['arguments']})[/dim]")

                console.print()  # Empty line for spacing

            except KeyboardInterrupt:
                console.print("\n[yellow]Chat interrupted. Goodbye![/yellow]")
                break
            except Exception as e:
                console.print(f"[red]Error: {e}[/red]")

        # Cleanup
        if mcp_client:
            await mcp_client.close()
        await llm.close()

    asyncio.run(chat_session())


@app.command()
def init(
    path: Path = typer.Argument(Path("."), help="Directory to initialize"),
):
    """
    Initialize a new MCP test project.

    This command creates the standard directory structure and example files.
    """
    console.print(Panel.fit(
        "[bold cyan]MCP Testing Framework - Initialize Project[/bold cyan]",
        border_style="cyan"
    ))

    # Create directories
    dirs = ["tests", "evals", "reports"]
    for dir_name in dirs:
        dir_path = path / dir_name
        dir_path.mkdir(parents=True, exist_ok=True)
        console.print(f"[green]✓ Created {dir_path}[/green]")

    # Create example test file
    example_test = {
        "version": "1.0",
        "tests": [
            {
                "name": "test_get_chart_data",
                "prompt": "Get the data for chart with ID 123",
                "evaluators": [
                    {"name": "was_mcp_tool_called", "args": {"tool_name": "get_chart"}},
                    {"name": "execution_successful"},
                    {"name": "final_answer_contains", "args": {"expected_content": "chart"}}
                ]
            },
            {
                "name": "test_create_dashboard",
                "prompt": "Create a new dashboard called 'Sales Overview' with a bar chart",
                "evaluators": [
                    {"name": "was_superset_chart_created"},
                    {"name": "execution_successful"},
                    {"name": "within_time_limit", "args": {"max_seconds": 30}}
                ]
            }
        ]
    }

    test_file = path / "tests" / "example_tests.yaml"
    test_file.write_text(yaml.dump(example_test, default_flow_style=False))
    console.print(f"[green]✓ Created example test file: {test_file}[/green]")

    # Create config file
    config = {
        "mcp_url": DEFAULT_MCP_URL,
        "default_model": DEFAULT_MODEL,
        "default_provider": DEFAULT_PROVIDER,
        "evaluators": {
            "timeout": 30,
            "max_tokens": 2000,
            "max_cost": 0.10
        }
    }

    config_file = path / "mcp_test_config.yaml"
    config_file.write_text(yaml.dump(config, default_flow_style=False))
    console.print(f"[green]✓ Created config file: {config_file}[/green]")

    console.print("\n[bold green]Project initialized successfully![/bold green]")
    console.print("\nNext steps:")
    console.print("1. Edit tests/example_tests.yaml to add your test cases")
    console.print("2. Run: mcp-test research  # To test your model")
    console.print("3. Run: mcp-test run tests/  # To run all tests")


if __name__ == "__main__":
    app()