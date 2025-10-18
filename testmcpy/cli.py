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

from testmcpy.config import get_config
from testmcpy import __version__

# Suppress MCP notification validation warnings
logging.getLogger().setLevel(logging.ERROR)

# Load environment variables from .env file (for backward compatibility)
load_dotenv(Path(__file__).parent.parent / ".env")

app = typer.Typer(
    name="testmcpy",
    help="MCP Testing Framework - Test LLM tool calling with MCP services",
    add_completion=False,
)

console = Console()


def version_callback(value: bool):
    """Display version and exit."""
    if value:
        console.print(f"[bold cyan]testmcpy[/bold cyan] version [green]{__version__}[/green]")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        None,
        "--version",
        "-v",
        help="Show version and exit",
        callback=version_callback,
        is_eager=True,
    )
):
    """
    testmcpy - MCP Testing Framework

    Test and validate LLM tool calling capabilities with MCP services.
    """
    pass

# Get config instance
config = get_config()
DEFAULT_MODEL = config.default_model or "claude-haiku-4-5"
DEFAULT_PROVIDER = config.default_provider or "anthropic"
DEFAULT_MCP_URL = config.mcp_url


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
        from testmcpy.research.test_ollama_tools import OllamaToolTester, MCPServiceTester, TestResult

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
        from testmcpy.src.test_runner import TestRunner, TestCase

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
    detail: bool = typer.Option(False, "--detail", "-d", help="Show detailed parameter schemas"),
    filter: Optional[str] = typer.Option(None, "--filter", help="Filter tools by name"),
):
    """
    List available MCP tools with beautiful formatting.

    This command connects to the MCP service and displays all available tools
    with their descriptions and parameter schemas in a readable format.
    """
    async def list_tools():
        from testmcpy.src.mcp_client import MCPClient
        from rich.tree import Tree
        from rich.json import JSON
        from rich.markdown import Markdown

        console.print(Panel.fit(
            f"[bold cyan]MCP Tools Explorer[/bold cyan]\n"
            f"Service: {mcp_url}",
            border_style="cyan"
        ))

        try:
            with console.status("[bold green]Connecting to MCP service...[/bold green]"):
                async with MCPClient(mcp_url) as client:
                    all_tools = await client.list_tools()

                    # Apply filter if provided
                    if filter:
                        tools = [t for t in all_tools if filter.lower() in t.name.lower()]
                        if not tools:
                            console.print(f"[yellow]No tools found matching '{filter}'[/yellow]")
                            return
                    else:
                        tools = all_tools

                    if format == OutputFormat.table:
                        if detail:
                            # Detailed view with individual panels for each tool
                            for i, tool in enumerate(tools, 1):
                                # Create a panel for each tool
                                tool_content = []

                                # Description
                                tool_content.append(f"[bold]Description:[/bold]")
                                desc_lines = tool.description.split('\n')
                                for line in desc_lines[:5]:  # First 5 lines
                                    if line.strip():
                                        tool_content.append(f"  {line.strip()}")
                                if len(desc_lines) > 5:
                                    tool_content.append(f"  [dim]... and {len(desc_lines) - 5} more lines[/dim]")

                                tool_content.append("")

                                # Parameters
                                if tool.input_schema:
                                    tool_content.append(f"[bold]Parameters:[/bold]")
                                    props = tool.input_schema.get('properties', {})
                                    required = tool.input_schema.get('required', [])

                                    if props:
                                        for param_name, param_info in props.items():
                                            param_type = param_info.get('type', 'any')
                                            param_desc = param_info.get('description', '')
                                            is_required = '✓' if param_name in required else ' '

                                            tool_content.append(f"  [{is_required}] [cyan]{param_name}[/cyan]: [yellow]{param_type}[/yellow]")
                                            if param_desc:
                                                # Wrap long descriptions
                                                if len(param_desc) > 60:
                                                    param_desc = param_desc[:60] + "..."
                                                tool_content.append(f"      [dim]{param_desc}[/dim]")
                                    else:
                                        tool_content.append("  [dim]No parameters required[/dim]")
                                else:
                                    tool_content.append(f"[dim]No parameter schema[/dim]")

                                panel = Panel(
                                    "\n".join(tool_content),
                                    title=f"[bold green]{i}. {tool.name}[/bold green]",
                                    border_style="green",
                                    expand=False
                                )
                                console.print(panel)
                                console.print()  # Spacing between tools
                        else:
                            # Compact table view
                            table = Table(
                                show_header=True,
                                header_style="bold cyan",
                                border_style="blue",
                                title=f"[bold]Available MCP Tools ({len(tools)})[/bold]",
                                title_style="bold magenta"
                            )
                            table.add_column("#", style="dim", width=4)
                            table.add_column("Tool Name", style="bold green", no_wrap=True)
                            table.add_column("Description", style="white")
                            table.add_column("Params", justify="center", style="cyan")

                            for i, tool in enumerate(tools, 1):
                                # Truncate description intelligently
                                desc = tool.description
                                if len(desc) > 80:
                                    # Try to cut at sentence or word boundary
                                    desc = desc[:80].rsplit('. ', 1)[0] + "..."

                                # Count parameters
                                param_count = len(tool.input_schema.get('properties', {})) if tool.input_schema else 0
                                required_count = len(tool.input_schema.get('required', [])) if tool.input_schema else 0

                                param_str = f"{param_count}"
                                if required_count > 0:
                                    param_str = f"{param_count} ({required_count} req)"

                                table.add_row(
                                    str(i),
                                    tool.name,
                                    desc,
                                    param_str
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
                        console.print(Syntax(json.dumps(output_data, indent=2), "json", theme="monokai"))

                    elif format == OutputFormat.yaml:
                        output_data = [
                            {
                                "name": tool.name,
                                "description": tool.description,
                                "input_schema": tool.input_schema
                            }
                            for tool in tools
                        ]
                        console.print(Syntax(yaml.dump(output_data), "yaml", theme="monokai"))

                    # Summary
                    summary_parts = []
                    summary_parts.append(f"[green]{len(tools)} tool(s) displayed[/green]")
                    if filter:
                        summary_parts.append(f"[yellow]filtered from {len(all_tools)} total[/yellow]")

                    console.print(f"\n[bold]Summary:[/bold] {' | '.join(summary_parts)}")

                    if not detail and format == OutputFormat.table:
                        console.print("[dim]Tip: Use --detail flag to see full parameter schemas[/dim]")

        except Exception as e:
            console.print(Panel(
                f"[red]Error connecting to MCP service:[/red]\n{str(e)}",
                title="[red]Error[/red]",
                border_style="red"
            ))

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

        from testmcpy.src.llm_integration import create_llm_provider
        from testmcpy.src.mcp_client import MCPClient

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
    project_config = {
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
    config_file.write_text(yaml.dump(project_config, default_flow_style=False))
    console.print(f"[green]✓ Created config file: {config_file}[/green]")

    console.print("\n[bold green]Project initialized successfully![/bold green]")
    console.print("\nNext steps:")
    console.print("1. Edit tests/example_tests.yaml to add your test cases")
    console.print("2. Run: testmcpy research  # To test your model")
    console.print("3. Run: testmcpy run tests/  # To run all tests")


@app.command()
def setup(
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite existing config file"),
    location: Optional[str] = typer.Option(None, "--location", "-l", help="Config location: 'user' (~/.testmcpy) or 'project' (.env)"),
):
    """
    Interactive setup wizard for testmcpy configuration.

    Guides you through configuring MCP service, LLM provider, and API keys.
    Creates either ~/.testmcpy (user config) or .env (project config).
    """
    from testmcpy.config import get_config

    console.print(Panel.fit(
        "[bold cyan]testmcpy Interactive Setup[/bold cyan]\n"
        "[dim]Configure MCP service and LLM provider settings[/dim]",
        border_style="cyan"
    ))

    # Load current config to show existing values
    current_config = get_config()

    # Ask for config location if not specified
    if not location:
        console.print("\n[bold]Where would you like to save the configuration?[/bold]")
        console.print("1. [cyan]~/.testmcpy[/cyan] - User config (applies to all projects)")
        console.print("2. [cyan].env[/cyan] - Project config (current directory only)")
        choice = console.input("\nChoice [1]: ").strip() or "1"
        location = "user" if choice == "1" else "project"

    config_path = Path.home() / ".testmcpy" if location == "user" else Path.cwd() / ".env"

    # Check if file exists
    if config_path.exists() and not force:
        console.print(f"\n[yellow]Config file already exists:[/yellow] {config_path}")
        overwrite = console.input("Overwrite? [y/N]: ").strip().lower()
        if overwrite not in ['y', 'yes']:
            console.print("[yellow]Setup cancelled[/yellow]")
            return

    console.print(f"\n[green]Creating config file:[/green] {config_path}\n")

    config_lines = [
        "# testmcpy Configuration",
        "# Generated by interactive setup",
        ""
    ]

    # MCP Service Configuration
    console.print("[bold]MCP Service Configuration[/bold]")

    # Show current MCP URL if set
    current_mcp_url = current_config.mcp_url
    if current_mcp_url and current_mcp_url != "http://localhost:5008/mcp/":
        source = current_config.get_source("MCP_URL")
        console.print(f"[green]✓ MCP Service URL already configured[/green] ({source})")
        console.print(f"[dim]  Current: {current_mcp_url}[/dim]")
        mcp_url = console.input(f"  New URL (or press Enter to keep current): ").strip() or current_mcp_url
    else:
        mcp_url = console.input("MCP Service URL [https://your-workspace.preset.io/mcp]: ").strip()

    if mcp_url:
        config_lines.append(f"MCP_URL={mcp_url}")

    # Ask for authentication method
    console.print("\n[bold]MCP Authentication Method[/bold]")

    # Detect current auth method
    has_dynamic_jwt = all([
        current_config.get("MCP_AUTH_API_URL"),
        current_config.get("MCP_AUTH_API_TOKEN"),
        current_config.get("MCP_AUTH_API_SECRET")
    ])
    has_static_token = current_config.get("MCP_AUTH_TOKEN") or current_config.get("SUPERSET_MCP_TOKEN")

    if has_dynamic_jwt:
        console.print("[dim]Currently configured: Dynamic JWT[/dim]")
    elif has_static_token:
        console.print("[dim]Currently configured: Static Token[/dim]")

    console.print("1. [cyan]Dynamic JWT[/cyan] - Fetch token from Preset API (recommended)")
    console.print("2. [cyan]Static Token[/cyan] - Use a pre-generated bearer token")
    default_auth = "1" if has_dynamic_jwt or not has_static_token else "2"
    auth_method = console.input(f"\nChoice [{default_auth}]: ").strip() or default_auth

    config_lines.append("")
    if auth_method == "1":
        config_lines.append("# Dynamic JWT Authentication")

        # Show current values for dynamic JWT
        current_api_url = current_config.get("MCP_AUTH_API_URL")
        current_api_token = current_config.get("MCP_AUTH_API_TOKEN")
        current_api_secret = current_config.get("MCP_AUTH_API_SECRET")

        if current_api_url:
            source = current_config.get_source("MCP_AUTH_API_URL")
            console.print(f"[green]✓ Auth API URL already configured[/green] ({source})")
            console.print(f"[dim]  Current: {current_api_url}[/dim]")
            api_url = console.input(f"  New URL (or press Enter to keep current): ").strip() or current_api_url
        else:
            api_url = console.input("Auth API URL (e.g., https://api.app.preset.io/v1/auth/): ").strip()

        if current_api_token:
            masked = f"{current_api_token[:8]}...{current_api_token[-4:]}"
            console.print(f"[dim]Current API Token: {masked}[/dim]")
            api_token = console.input(f"API Token [press Enter to keep current]: ").strip() or current_api_token
        else:
            api_token = console.input("API Token: ").strip()

        if current_api_secret:
            masked = f"{current_api_secret[:8]}...{current_api_secret[-4:]}"
            console.print(f"[dim]Current API Secret: {masked}[/dim]")
            api_secret = console.input(f"API Secret [press Enter to keep current]: ").strip() or current_api_secret
        else:
            api_secret = console.input("API Secret: ").strip()

        if api_url:
            config_lines.append(f"MCP_AUTH_API_URL={api_url}")
        if api_token:
            config_lines.append(f"MCP_AUTH_API_TOKEN={api_token}")
        if api_secret:
            config_lines.append(f"MCP_AUTH_API_SECRET={api_secret}")
    else:
        config_lines.append("# Static Bearer Token")

        current_token = current_config.get("MCP_AUTH_TOKEN") or current_config.get("SUPERSET_MCP_TOKEN")
        if current_token:
            masked = f"{current_token[:20]}...{current_token[-8:]}"
            console.print(f"[dim]Current Token: {masked}[/dim]")
            static_token = console.input(f"Bearer Token [press Enter to keep current]: ").strip() or current_token
        else:
            static_token = console.input("Bearer Token: ").strip()

        if static_token:
            config_lines.append(f"MCP_AUTH_TOKEN={static_token}")

    # LLM Provider Configuration
    console.print("\n[bold]LLM Provider Configuration[/bold]")

    # Detect current provider
    current_provider = current_config.default_provider
    if current_provider:
        console.print(f"[dim]Currently configured: {current_provider}[/dim]")

    console.print("1. [cyan]Anthropic[/cyan] - Claude models (requires API key, best tool calling)")
    console.print("2. [cyan]Ollama[/cyan] - Local models (free, requires ollama serve)")
    console.print("3. [cyan]OpenAI[/cyan] - GPT models (requires API key)")

    # Set default based on current provider
    default_provider = "1"
    if current_provider == "ollama":
        default_provider = "2"
    elif current_provider == "openai":
        default_provider = "3"

    provider_choice = console.input(f"\nChoice [{default_provider}]: ").strip() or default_provider

    config_lines.append("")
    config_lines.append("# LLM Provider Settings")

    if provider_choice == "1":
        config_lines.append("DEFAULT_PROVIDER=anthropic")

        console.print("\n[bold]Available Anthropic Models:[/bold]")
        console.print("1. [cyan]claude-sonnet-4-5[/cyan] - Latest Sonnet 4.5 (most capable)")
        console.print("2. [cyan]claude-haiku-4-5[/cyan] - Latest Haiku 4.5 (fast & efficient, recommended)")
        console.print("3. [cyan]claude-opus-4-1[/cyan] - Latest Opus 4.1 (most powerful)")
        console.print("4. [cyan]claude-haiku-4-5[/cyan] - Legacy Haiku 3.5")
        console.print("5. [cyan]Custom model name[/cyan]")

        current_model = current_config.default_model or "claude-haiku-4-5"
        model_choice = console.input(f"\nChoice (or press Enter for current: {current_model}): ").strip()

        if model_choice == "1":
            model = "claude-sonnet-4-5"
        elif model_choice == "2":
            model = "claude-haiku-4-5"
        elif model_choice == "3":
            model = "claude-opus-4-1"
        elif model_choice == "4":
            model = "claude-haiku-4-5"
        elif model_choice == "5":
            model = console.input("Custom model name: ").strip()
        elif model_choice == "":
            model = current_model
        else:
            model = model_choice

        config_lines.append(f"DEFAULT_MODEL={model}")
        config_lines.append(f"ANTHROPIC_MODEL={model}")

        config_lines.append("")

        current_api_key = current_config.get("ANTHROPIC_API_KEY")
        if current_api_key:
            source = current_config.get_source("ANTHROPIC_API_KEY")
            masked = f"{current_api_key[:8]}...{current_api_key[-4:]}"
            console.print(f"[green]✓ Anthropic API Key already configured[/green] ({source})")
            console.print(f"[dim]  Current: {masked}[/dim]")
            api_key = console.input(f"  New key (or press Enter to skip): ").strip() or current_api_key
        else:
            api_key = console.input("Anthropic API Key: ").strip()

        if api_key:
            config_lines.append(f"ANTHROPIC_API_KEY={api_key}")
        else:
            config_lines.append("# ANTHROPIC_API_KEY=sk-ant-...")

    elif provider_choice == "2":
        config_lines.append("DEFAULT_PROVIDER=ollama")

        console.print("\n[bold]Popular Ollama Models:[/bold]")
        console.print("1. [cyan]llama3.1:8b[/cyan] - Meta's Llama 3.1 8B (good balance)")
        console.print("2. [cyan]llama3.1:70b[/cyan] - Meta's Llama 3.1 70B (more capable, slower)")
        console.print("3. [cyan]qwen2.5:14b[/cyan] - Alibaba's Qwen 2.5 14B (strong coding)")
        console.print("4. [cyan]mistral:7b[/cyan] - Mistral 7B (efficient)")
        console.print("5. [cyan]Custom model name[/cyan]")

        current_model = current_config.default_model or "llama3.1:8b"
        model_choice = console.input(f"\nChoice (or press Enter for current: {current_model}): ").strip()

        if model_choice == "1":
            model = "llama3.1:8b"
        elif model_choice == "2":
            model = "llama3.1:70b"
        elif model_choice == "3":
            model = "qwen2.5:14b"
        elif model_choice == "4":
            model = "mistral:7b"
        elif model_choice == "5":
            model = console.input("Custom model name: ").strip()
        elif model_choice == "":
            model = current_model
        else:
            model = model_choice

        config_lines.append(f"DEFAULT_MODEL={model}")

        config_lines.append("")

        current_base_url = current_config.get("OLLAMA_BASE_URL") or "http://localhost:11434"
        base_url = console.input(f"Ollama Base URL [{current_base_url}]: ").strip() or current_base_url
        config_lines.append(f"OLLAMA_BASE_URL={base_url}")

    elif provider_choice == "3":
        config_lines.append("DEFAULT_PROVIDER=openai")

        console.print("\n[bold]Available OpenAI Models:[/bold]")
        console.print("1. [cyan]gpt-4o[/cyan] - GPT-4 Optimized (recommended)")
        console.print("2. [cyan]gpt-4-turbo[/cyan] - GPT-4 Turbo")
        console.print("3. [cyan]gpt-4[/cyan] - GPT-4 (original)")
        console.print("4. [cyan]gpt-3.5-turbo[/cyan] - GPT-3.5 Turbo (faster, cheaper)")
        console.print("5. [cyan]Custom model name[/cyan]")

        current_model = current_config.default_model or "gpt-4o"
        model_choice = console.input(f"\nChoice (or press Enter for current: {current_model}): ").strip()

        if model_choice == "1":
            model = "gpt-4o"
        elif model_choice == "2":
            model = "gpt-4-turbo"
        elif model_choice == "3":
            model = "gpt-4"
        elif model_choice == "4":
            model = "gpt-3.5-turbo"
        elif model_choice == "5":
            model = console.input("Custom model name: ").strip()
        elif model_choice == "":
            model = current_model
        else:
            model = model_choice

        config_lines.append(f"DEFAULT_MODEL={model}")

        config_lines.append("")

        current_api_key = current_config.get("OPENAI_API_KEY")
        if current_api_key:
            source = current_config.get_source("OPENAI_API_KEY")
            masked = f"{current_api_key[:8]}...{current_api_key[-4:]}"
            console.print(f"[green]✓ OpenAI API Key already configured[/green] ({source})")
            console.print(f"[dim]  Current: {masked}[/dim]")
            api_key = console.input(f"  New key (or press Enter to skip): ").strip() or current_api_key
        else:
            api_key = console.input("OpenAI API Key: ").strip()

        if api_key:
            config_lines.append(f"OPENAI_API_KEY={api_key}")
        else:
            config_lines.append("# OPENAI_API_KEY=sk-...")

    # Write config file
    config_lines.append("")
    config_path.write_text("\n".join(config_lines))

    console.print(f"\n[green]✓ Configuration saved to:[/green] {config_path}")
    console.print("\n[bold]Next steps:[/bold]")
    console.print("1. Run: [cyan]testmcpy config-cmd[/cyan]  # Verify configuration")
    console.print("2. Run: [cyan]testmcpy tools[/cyan]  # List available MCP tools")
    console.print("3. Run: [cyan]testmcpy chat[/cyan]  # Start interactive chat")


@app.command()
def serve(
    port: int = typer.Option(8000, "--port", "-p", help="Port to run server on"),
    host: str = typer.Option("127.0.0.1", "--host", help="Host to bind to"),
    dev: bool = typer.Option(False, "--dev", help="Run in development mode (don't build frontend)"),
    no_browser: bool = typer.Option(False, "--no-browser", help="Don't open browser automatically"),
):
    """
    Start web server for testmcpy UI.

    This command starts a FastAPI server that serves a beautiful React-based UI
    for inspecting MCP tools, interactive chat, and test management.
    """
    # Show authentication steps
    console.print("\n[bold cyan]Authentication Setup[/bold cyan]")
    console.print("[dim]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/dim]")

    # Load config
    console.print("  [1/4] Loading configuration...")
    from testmcpy.config import get_config
    cfg = get_config()
    console.print("  [green]✓[/green] Configuration loaded")

    # Check MCP URL
    console.print(f"\n  [2/4] Checking MCP service URL...")
    console.print(f"  [dim]    MCP URL: {cfg.mcp_url}[/dim]")
    console.print(f"  [dim]    Source: {cfg.get_source('MCP_URL')}[/dim]")
    console.print("  [green]✓[/green] MCP URL configured")

    # Check authentication method
    console.print(f"\n  [3/4] Checking authentication method...")
    has_dynamic_jwt = all([
        cfg.get("MCP_AUTH_API_URL"),
        cfg.get("MCP_AUTH_API_TOKEN"),
        cfg.get("MCP_AUTH_API_SECRET")
    ])
    has_static_token = cfg.get("MCP_AUTH_TOKEN") or cfg.get("SUPERSET_MCP_TOKEN")

    if has_dynamic_jwt:
        console.print("  [cyan]→[/cyan] Using dynamic JWT authentication")
        console.print(f"  [dim]    Auth API URL: {cfg.get('MCP_AUTH_API_URL')}[/dim]")
        console.print(f"  [dim]    API Token: {cfg.get('MCP_AUTH_API_TOKEN')[:8]}...{cfg.get('MCP_AUTH_API_TOKEN')[-4:]}[/dim]")
        console.print("  [green]✓[/green] Dynamic JWT configured")

        # Try to fetch token
        console.print(f"\n  [4/4] Fetching JWT token from API...")
        try:
            import requests
            response = requests.post(
                cfg.get("MCP_AUTH_API_URL"),
                headers={"Content-Type": "application/json", "Accept": "application/json"},
                json={"name": cfg.get("MCP_AUTH_API_TOKEN"), "secret": cfg.get("MCP_AUTH_API_SECRET")},
                timeout=10
            )
            if response.status_code == 200:
                console.print("  [green]✓[/green] JWT token fetched successfully")
            else:
                console.print(f"  [yellow]⚠[/yellow] Failed to fetch JWT token (status: {response.status_code})")
                console.print("  [yellow]  Server will attempt to fetch token when needed[/yellow]")
        except Exception as e:
            console.print(f"  [yellow]⚠[/yellow] Failed to fetch JWT token: {str(e)}")
            console.print("  [yellow]  Server will attempt to fetch token when needed[/yellow]")
    elif has_static_token:
        static_token = cfg.get("MCP_AUTH_TOKEN") or cfg.get("SUPERSET_MCP_TOKEN")
        console.print("  [cyan]→[/cyan] Using static bearer token")
        console.print(f"  [dim]    Token: {static_token[:20]}...{static_token[-8:]}[/dim]")
        source = cfg.get_source("MCP_AUTH_TOKEN") or cfg.get_source("SUPERSET_MCP_TOKEN")
        console.print(f"  [dim]    Source: {source}[/dim]")
        console.print("  [green]✓[/green] Static token configured")
        console.print(f"\n  [4/4] Token validation skipped (static token)")
    else:
        console.print("  [yellow]⚠[/yellow] No authentication configured")
        console.print("  [yellow]  MCP service may require authentication[/yellow]")
        console.print(f"\n  [4/4] Authentication setup incomplete")

    console.print("[dim]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/dim]\n")

    console.print(Panel.fit(
        "[bold cyan]testmcpy Web Server[/bold cyan]\n"
        f"Starting server at http://{host}:{port}",
        border_style="cyan"
    ))

    import subprocess
    import sys
    import time
    from pathlib import Path

    # Get paths
    server_dir = Path(__file__).parent / "server"
    ui_dir = Path(__file__).parent / "ui"
    ui_dist = ui_dir / "dist"

    # Check if FastAPI is installed
    try:
        import fastapi
        import uvicorn
    except ImportError:
        console.print("[red]Error: FastAPI and uvicorn are required for the web server[/red]")
        console.print("Install with: pip install 'testmcpy[server]'", markup=False)
        return

    # Build frontend if not in dev mode and dist doesn't exist
    if not dev and not ui_dist.exists():
        console.print("\n[yellow]Frontend not built. Building now...[/yellow]")

        # Check if npm is available
        try:
            subprocess.run(["npm", "--version"], check=True, capture_output=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            console.print("[red]Error: npm is required to build the frontend[/red]")
            console.print("Install Node.js from https://nodejs.org/")
            return

        # Install dependencies
        console.print("Installing npm dependencies...")
        result = subprocess.run(
            ["npm", "install"],
            cwd=ui_dir,
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            console.print(f"[red]Failed to install dependencies:[/red]\n{result.stderr}")
            return

        # Build
        console.print("Building frontend...")
        result = subprocess.run(
            ["npm", "run", "build"],
            cwd=ui_dir,
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            console.print(f"[red]Failed to build frontend:[/red]\n{result.stderr}")
            return

        console.print("[green]Frontend built successfully![/green]\n")

    elif dev:
        console.print("[yellow]Running in dev mode - make sure to start the frontend separately:[/yellow]")
        console.print(f"  cd {ui_dir} && npm run dev\n")

    # Open browser
    if not no_browser:
        import webbrowser
        import threading
        def open_browser():
            time.sleep(1.5)  # Wait for server to start
            webbrowser.open(f"http://{host}:{port}")
        threading.Thread(target=open_browser, daemon=True).start()

    # Start server
    console.print("[green]Server starting...[/green]")
    console.print(f"[dim]API docs available at http://{host}:{port}/docs[/dim]\n")

    try:
        import uvicorn
        from testmcpy.server.api import app as fastapi_app

        uvicorn.run(
            fastapi_app,
            host=host,
            port=port,
            log_level="info"
        )
    except KeyboardInterrupt:
        console.print("\n[yellow]Server stopped[/yellow]")
    except Exception as e:
        console.print(f"[red]Server error:[/red] {e}")


@app.command()
def config_cmd(
    show_all: bool = typer.Option(False, "--all", "-a", help="Show all config values including unset ones"),
):
    """
    Display current testmcpy configuration.

    Shows the configuration values and their sources (environment, config file, etc.).
    """
    console.print(Panel.fit(
        "[bold cyan]testmcpy Configuration[/bold cyan]",
        border_style="cyan"
    ))

    from testmcpy.config import get_config
    cfg = get_config()

    # Get all config values with sources
    all_config = cfg.get_all_with_sources()

    # Create table
    table = Table(
        show_header=True,
        header_style="bold cyan",
        border_style="blue",
        title="[bold]Configuration Values[/bold]",
        title_style="bold magenta"
    )
    table.add_column("Key", style="bold green", no_wrap=True)
    table.add_column("Value", style="white")
    table.add_column("Source", style="yellow")

    # Sort keys for better display
    sorted_keys = sorted(all_config.keys())

    for key in sorted_keys:
        value, source = all_config[key]

        # Mask sensitive values
        if "API_KEY" in key or "TOKEN" in key:
            if value:
                masked_value = f"{value[:8]}{'*' * (len(value) - 8)}" if len(value) > 8 else "***"
            else:
                masked_value = "[dim]not set[/dim]"
        else:
            masked_value = value or "[dim]not set[/dim]"

        table.add_row(key, masked_value, source)

    console.print(table)

    # Show config file locations
    console.print("\n[bold]Configuration Locations (priority order):[/bold]")
    console.print("1. [cyan]Command-line options[/cyan] (highest priority)")
    console.print(f"2. [cyan].env in current directory[/cyan] ({Path.cwd() / '.env'})")
    console.print(f"3. [cyan]~/.testmcpy[/cyan] ({Path.home() / '.testmcpy'})")
    console.print("4. [cyan]Environment variables[/cyan]")
    console.print("5. [cyan]Built-in defaults[/cyan] (lowest priority)")

    # Check which config files exist
    console.print("\n[bold]Config Files:[/bold]")
    cwd_env = Path.cwd() / ".env"
    user_config = Path.home() / ".testmcpy"

    if cwd_env.exists():
        console.print(f"[green]✓[/green] {cwd_env} (exists)")
    else:
        console.print(f"[dim]✗ {cwd_env} (not found)[/dim]")

    if user_config.exists():
        console.print(f"[green]✓[/green] {user_config} (exists)")
    else:
        console.print(f"[dim]✗ {user_config} (not found)[/dim]")
        console.print(f"\n[dim]Tip: Create {user_config} to set user defaults[/dim]")


@app.command()
def config_mcp(
    target: str = typer.Argument(..., help="Target application: claude-desktop, claude-code, or chatgpt-desktop"),
    server_name: Optional[str] = typer.Option(None, "--name", "-n", help="Server name in config (default: preset-superset)"),
    mcp_url: Optional[str] = typer.Option(None, "--mcp-url", help="MCP service URL (uses config default if not provided)"),
    auth_token: Optional[str] = typer.Option(None, "--token", help="Bearer token (uses dynamic JWT if not provided)"),
):
    """
    Configure MCP server for Claude Desktop, Claude Code, or ChatGPT Desktop.

    This command automatically adds your MCP service configuration to the appropriate
    application config file. It supports:

    - claude-desktop: ~/Library/Application Support/Claude/claude_desktop_config.json
    - claude-code: ~/.claude.json or .mcp.json
    - chatgpt-desktop: Similar to claude-desktop format

    The command will use your current testmcpy configuration (MCP URL and auth)
    and format it appropriately for the target application.
    """
    import platform
    from pathlib import Path

    console.print(Panel.fit(
        f"[bold cyan]Configure MCP for {target}[/bold cyan]",
        border_style="cyan"
    ))

    # Determine target config file path
    system = platform.system()
    target = target.lower()

    if target == "claude-desktop":
        if system == "Darwin":  # macOS
            config_path = Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
        elif system == "Windows":
            config_path = Path(os.getenv("APPDATA")) / "Claude" / "claude_desktop_config.json"
        else:  # Linux
            config_path = Path.home() / ".config" / "Claude" / "claude_desktop_config.json"

    elif target == "claude-code":
        # Prefer ~/.claude.json for reliability
        config_path = Path.home() / ".claude.json"
        console.print("[dim]Note: Using ~/.claude.json (recommended). You can also use .mcp.json in project directory.[/dim]\n")

    elif target == "chatgpt-desktop":
        # ChatGPT Desktop uses similar format to Claude Desktop
        if system == "Darwin":  # macOS
            config_path = Path.home() / "Library" / "Application Support" / "ChatGPT" / "config.json"
        else:
            console.print("[yellow]ChatGPT Desktop config location not well-documented for this OS.[/yellow]")
            console.print("[yellow]Please check ChatGPT Desktop documentation for config file location.[/yellow]")
            return

    else:
        console.print(f"[red]Error: Unknown target '{target}'[/red]")
        console.print("Supported targets: claude-desktop, claude-code, chatgpt-desktop")
        return

    # Get MCP configuration
    cfg = get_config()
    mcp_url = mcp_url or cfg.mcp_url
    server_name = server_name or "preset-superset"

    if not mcp_url:
        console.print("[red]Error: MCP URL not configured[/red]")
        console.print("Run: testmcpy setup")
        return

    # Get auth token
    if not auth_token:
        # ALWAYS fetch fresh token from dynamic JWT if configured
        if cfg.get("MCP_AUTH_API_URL") and cfg.get("MCP_AUTH_API_TOKEN") and cfg.get("MCP_AUTH_API_SECRET"):
            console.print("[yellow]Fetching bearer token using dynamic JWT...[/yellow]")
            try:
                import requests
                auth_url = cfg.get("MCP_AUTH_API_URL")
                api_token = cfg.get("MCP_AUTH_API_TOKEN")
                api_secret = cfg.get("MCP_AUTH_API_SECRET")

                console.print(f"[dim]Auth URL: {auth_url}[/dim]")
                console.print(f"[dim]API Token: {api_token[:8]}...{api_token[-4:]}[/dim]")

                response = requests.post(
                    auth_url,
                    headers={
                        "Content-Type": "application/json",
                        "Accept": "application/json"
                    },
                    json={"name": api_token, "secret": api_secret},
                    timeout=10
                )

                console.print(f"[dim]Response status: {response.status_code}[/dim]")

                if response.status_code != 200:
                    console.print(f"[red]Error: API returned {response.status_code}[/red]")
                    console.print(f"[red]Response: {response.text}[/red]")
                    console.print("[yellow]Please provide --token with a long-lived bearer token[/yellow]")
                    return

                auth_data = response.json()
                # Try both 'access_token' and 'payload.access_token' keys
                auth_token = auth_data.get("access_token")
                if not auth_token and "payload" in auth_data:
                    payload = auth_data["payload"]
                    if isinstance(payload, dict):
                        auth_token = payload.get("access_token")
                    else:
                        auth_token = payload

                if auth_token:
                    console.print(f"[green]✓ Successfully fetched bearer token (length: {len(auth_token)})[/green]")
                else:
                    console.print(f"[red]Error: No access_token or payload in response[/red]")
                    console.print(f"[red]Response keys: {list(auth_data.keys())}[/red]")
                    console.print(f"[red]Full response: {auth_data}[/red]")
                    return
            except Exception as e:
                console.print(f"[red]Error fetching token: {e}[/red]")
                import traceback
                console.print(f"[red]{traceback.format_exc()}[/red]")
                console.print("[yellow]Please provide --token with a long-lived bearer token[/yellow]")
                return
        else:
            console.print("[red]Error: No authentication token available[/red]")
            console.print("Provide --token or configure dynamic JWT (MCP_AUTH_API_*)")
            return

    # Create MCP server configuration
    mcp_server_config = {
        "command": "npx",
        "args": [
            "-y",
            "mcp-remote@latest",
            mcp_url,
            "--header",
            f"Authorization: Bearer {auth_token}"
        ],
        "env": {
            "NODE_OPTIONS": "--no-warnings"
        }
    }

    # Read existing config if it exists
    existing_config = {}
    if config_path.exists():
        try:
            with open(config_path) as f:
                existing_config = json.load(f)
            console.print(f"[green]✓ Found existing config at {config_path}[/green]")
        except Exception as e:
            console.print(f"[yellow]Warning: Could not read existing config: {e}[/yellow]")

    # Update config
    if "mcpServers" not in existing_config:
        existing_config["mcpServers"] = {}

    existing_config["mcpServers"][server_name] = mcp_server_config

    # Ensure parent directory exists
    config_path.parent.mkdir(parents=True, exist_ok=True)

    # Write config
    try:
        with open(config_path, 'w') as f:
            json.dump(existing_config, f, indent=2)

        console.print(f"\n[green]✓ MCP server configured successfully![/green]")
        console.print(f"[green]✓ Config file: {config_path}[/green]")
        console.print(f"[green]✓ Server name: {server_name}[/green]")
        console.print(f"[green]✓ MCP URL: {mcp_url}[/green]")

        # Show the config that was added
        console.print("\n[bold]Added configuration:[/bold]")
        config_display = {
            server_name: {
                "command": "npx",
                "args": [
                    "-y",
                    "mcp-remote@latest",
                    mcp_url,
                    "--header",
                    f"Authorization: Bearer {auth_token[:20]}...{auth_token[-8:]}"
                ],
                "env": {
                    "NODE_OPTIONS": "--no-warnings"
                }
            }
        }
        console.print(Syntax(json.dumps(config_display, indent=2), "json", theme="monokai"))

        # Next steps
        console.print("\n[bold]Next steps:[/bold]")
        if target == "claude-desktop":
            console.print("1. Restart Claude Desktop")
            console.print("2. The MCP server should appear in Claude's tool list")
        elif target == "claude-code":
            console.print("1. Restart Claude Code (or reload window)")
            console.print("2. The MCP server should be available")
            console.print("3. Use --mcp-debug flag if you encounter issues")
        elif target == "chatgpt-desktop":
            console.print("1. Restart ChatGPT Desktop")
            console.print("2. The MCP server should be available")

    except Exception as e:
        console.print(f"[red]Error writing config file:[/red] {e}")
        return


@app.command()
def doctor():
    """
    Run health checks to diagnose installation issues.

    This command checks Python version, dependencies, configuration,
    and MCP connectivity to help identify and resolve issues.
    """
    console.print(Panel.fit(
        "[bold cyan]testmcpy Health Check[/bold cyan]\n"
        "[dim]Diagnosing installation and configuration...[/dim]",
        border_style="cyan"
    ))

    issues_found = []
    warnings_found = []

    # 1. Check Python version
    console.print("\n[bold]1. Python Version[/bold]")
    import sys
    python_version = sys.version_info
    version_str = f"{python_version.major}.{python_version.minor}.{python_version.micro}"

    if python_version >= (3, 9) and python_version < (3, 13):
        console.print(f"[green]✓[/green] Python {version_str} (compatible)")
    elif python_version < (3, 9):
        console.print(f"[red]✗[/red] Python {version_str} (too old, requires 3.9+)")
        issues_found.append(f"Python version {version_str} is too old. Requires Python 3.9 or higher.")
    else:
        console.print(f"[yellow]⚠[/yellow] Python {version_str} (not tested, may not work)")
        warnings_found.append(f"Python {version_str} is newer than 3.12 and has not been tested with testmcpy.")

    # 2. Check core dependencies
    console.print("\n[bold]2. Core Dependencies[/bold]")
    core_deps = [
        ("typer", "typer"),
        ("rich", "rich"),
        ("yaml", "pyyaml"),
        ("httpx", "httpx"),
        ("anthropic", "anthropic"),
        ("fastmcp", "fastmcp"),
        ("dotenv", "python-dotenv"),
    ]

    all_core_deps_ok = True
    for import_name, package_name in core_deps:
        try:
            __import__(import_name)
            console.print(f"[green]✓[/green] {package_name}")
        except ImportError:
            console.print(f"[red]✗[/red] {package_name} - not installed")
            issues_found.append(f"Missing required dependency: {package_name}")
            all_core_deps_ok = False

    # 3. Check optional dependencies
    console.print("\n[bold]3. Optional Dependencies[/bold]")

    # Server dependencies
    console.print("[dim]Server (Web UI):[/dim]")
    try:
        import fastapi
        import uvicorn
        console.print(f"[green]✓[/green] fastapi, uvicorn - Web UI available")
    except ImportError:
        console.print("[dim]✗[/dim] fastapi, uvicorn - Install with: pip install 'testmcpy[server]'", markup=False)

    # SDK dependency
    console.print("[dim]Claude Agent SDK:[/dim]")
    try:
        import claude_agent_sdk
        console.print(f"[green]✓[/green] claude-agent-sdk - SDK provider available")
    except ImportError:
        console.print("[dim]✗[/dim] claude-agent-sdk - Install with: pip install 'testmcpy[sdk]'", markup=False)

    # 4. Check configuration
    console.print("\n[bold]4. Configuration[/bold]")

    cfg = get_config()

    # Check MCP URL
    mcp_url = cfg.mcp_url
    if mcp_url and mcp_url != "http://localhost:5008/mcp/":
        console.print(f"[green]✓[/green] MCP URL configured: {mcp_url}")
    else:
        console.print(f"[yellow]⚠[/yellow] MCP URL not configured (using default)")
        warnings_found.append("MCP URL not configured. Run: testmcpy setup")

    # Check authentication
    has_dynamic_jwt = all([
        cfg.get("MCP_AUTH_API_URL"),
        cfg.get("MCP_AUTH_API_TOKEN"),
        cfg.get("MCP_AUTH_API_SECRET")
    ])
    has_static_token = cfg.get("MCP_AUTH_TOKEN") or cfg.get("SUPERSET_MCP_TOKEN")

    if has_dynamic_jwt:
        console.print(f"[green]✓[/green] MCP Authentication: Dynamic JWT configured")
    elif has_static_token:
        console.print(f"[green]✓[/green] MCP Authentication: Static token configured")
    else:
        console.print(f"[yellow]⚠[/yellow] MCP Authentication: Not configured")
        warnings_found.append("MCP authentication not configured. Run: testmcpy setup")

    # Check LLM provider
    provider = cfg.default_provider
    model = cfg.default_model
    if provider:
        console.print(f"[green]✓[/green] LLM Provider: {provider}")
        console.print(f"[dim]  Model: {model}[/dim]")

        # Check provider-specific API keys
        if provider == "anthropic":
            api_key = cfg.get("ANTHROPIC_API_KEY")
            if api_key:
                console.print(f"[green]✓[/green] Anthropic API key configured")
            else:
                console.print(f"[red]✗[/red] Anthropic API key missing")
                issues_found.append("Anthropic API key not configured. Set ANTHROPIC_API_KEY in ~/.testmcpy")
        elif provider == "openai":
            api_key = cfg.get("OPENAI_API_KEY")
            if api_key:
                console.print(f"[green]✓[/green] OpenAI API key configured")
            else:
                console.print(f"[red]✗[/red] OpenAI API key missing")
                issues_found.append("OpenAI API key not configured. Set OPENAI_API_KEY in ~/.testmcpy")
        elif provider == "ollama":
            base_url = cfg.get("OLLAMA_BASE_URL") or "http://localhost:11434"
            console.print(f"[dim]  Ollama URL: {base_url}[/dim]")
    else:
        console.print(f"[yellow]⚠[/yellow] LLM Provider: Not configured")
        warnings_found.append("LLM provider not configured. Run: testmcpy setup")

    # 5. Check MCP connectivity (if configured)
    if mcp_url and mcp_url != "http://localhost:5008/mcp/" and all_core_deps_ok:
        console.print("\n[bold]5. MCP Connectivity[/bold]")

        async def check_mcp():
            try:
                from testmcpy.src.mcp_client import MCPClient
                with console.status("[dim]Connecting to MCP service...[/dim]"):
                    client = MCPClient(mcp_url)
                    await client.initialize()
                    tools = await client.list_tools()
                    await client.close()

                console.print(f"[green]✓[/green] MCP service reachable")
                console.print(f"[dim]  Found {len(tools)} tools[/dim]")
                return True
            except Exception as e:
                console.print(f"[red]✗[/red] MCP service unreachable: {str(e)}")
                issues_found.append(f"Cannot connect to MCP service: {str(e)}")
                return False

        try:
            asyncio.run(check_mcp())
        except Exception as e:
            console.print(f"[red]✗[/red] MCP connectivity test failed: {str(e)}")
            issues_found.append(f"MCP connectivity test error: {str(e)}")
    else:
        console.print("\n[bold]5. MCP Connectivity[/bold]")
        console.print("[dim]Skipped (MCP not configured or missing dependencies)[/dim]")

    # 6. Check virtual environment
    console.print("\n[bold]6. Environment[/bold]")
    if hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix):
        console.print(f"[green]✓[/green] Running in virtual environment")
        console.print(f"[dim]  Location: {sys.prefix}[/dim]")
    else:
        console.print(f"[yellow]⚠[/yellow] Not running in virtual environment")
        warnings_found.append("Not using a virtual environment. Consider using: python3 -m venv venv")

    # 7. Check config files
    console.print("\n[bold]7. Configuration Files[/bold]")
    cwd_env = Path.cwd() / ".env"
    user_config = Path.home() / ".testmcpy"

    config_files_exist = False
    if cwd_env.exists():
        console.print(f"[green]✓[/green] {cwd_env}")
        config_files_exist = True
    else:
        console.print(f"[dim]✗ {cwd_env} (not found)[/dim]")

    if user_config.exists():
        console.print(f"[green]✓[/green] {user_config}")
        config_files_exist = True
    else:
        console.print(f"[dim]✗ {user_config} (not found)[/dim]")

    if not config_files_exist:
        warnings_found.append("No configuration files found. Run: testmcpy setup")

    # Summary
    console.print("\n" + "="*50)
    if not issues_found and not warnings_found:
        console.print("\n[bold green]✓ All checks passed![/bold green]")
        console.print("[dim]Your testmcpy installation is healthy.[/dim]")
    else:
        if issues_found:
            console.print(f"\n[bold red]Found {len(issues_found)} issue(s):[/bold red]")
            for i, issue in enumerate(issues_found, 1):
                console.print(f"  {i}. {issue}")

        if warnings_found:
            console.print(f"\n[bold yellow]Found {len(warnings_found)} warning(s):[/bold yellow]")
            for i, warning in enumerate(warnings_found, 1):
                console.print(f"  {i}. {warning}")

        console.print("\n[bold]Recommended Actions:[/bold]")
        if any("Python version" in issue for issue in issues_found):
            console.print("• Upgrade Python to 3.9 or higher: https://www.python.org/downloads/")
        if any("Missing required dependency" in issue for issue in issues_found):
            console.print("• Reinstall testmcpy: pip install --upgrade testmcpy")
        if any("API key" in issue for issue in issues_found):
            console.print("• Configure API keys: testmcpy setup")
        if any("MCP" in str(warnings_found) or "MCP" in str(issues_found)):
            console.print("• Configure MCP service: testmcpy setup")
        if any("virtual environment" in warning for warning in warnings_found):
            console.print("• Create virtual environment: python3 -m venv venv && source venv/bin/activate")

    console.print()


if __name__ == "__main__":
    app()