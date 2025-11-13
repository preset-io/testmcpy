#!/usr/bin/env python3
"""
MCP Testing Framework CLI - Test and validate LLM+MCP interactions.

This CLI provides commands for testing LLM tool calling capabilities with MCP services,
running evaluation suites, and generating reports.
"""

import asyncio
import json
import logging
import os
from enum import Enum
from pathlib import Path

import typer
import yaml
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.syntax import Syntax
from rich.table import Table

from testmcpy import __version__
from testmcpy.config import get_config

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


def print_logo():
    """Print testmcpy ASCII logo."""
    logo = """
  [bold cyan]▀█▀ █▀▀ █▀ ▀█▀ █▀▄▀█ █▀▀ █▀█ █▄█[/bold cyan]
  [bold cyan] █  ██▄ ▄█  █  █ ▀ █ █▄▄ █▀▀  █ [/bold cyan]

  [dim]🧪 Test  •  📊 Benchmark  •  ✓ Validate[/dim]
  [dim]MCP Testing Framework[/dim]
"""
    console.print(logo)


def version_callback(value: bool):
    """Display version and exit."""
    if value:
        print_logo()
        console.print(f"\n  Version: [green]{__version__}[/green]")
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
    ),
):
    """
    testmcpy - MCP Testing Framework

    Test and validate LLM tool calling capabilities with MCP services.
    """
    pass


# Get config instance
config = get_config()

# Get defaults from LLM profile if available
_default_llm = config.get_default_llm_provider()
DEFAULT_MODEL = _default_llm.model if _default_llm else "claude-sonnet-4-5"
DEFAULT_PROVIDER = _default_llm.provider if _default_llm else "anthropic"

# Get default MCP URL from profile if available
_default_mcp_url = config.get_mcp_url()
DEFAULT_MCP_URL = _default_mcp_url if _default_mcp_url else None


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
    provider: ModelProvider = typer.Option(
        DEFAULT_PROVIDER, "--provider", "-p", help="Model provider"
    ),
    mcp_url: str | None = typer.Option(
        None, "--mcp-url", help="MCP service URL (overrides profile)"
    ),
    profile: str | None = typer.Option(
        None, "--profile", help="MCP service profile from .mcp_services.yaml"
    ),
    output: Path | None = typer.Option(None, "--output", "-o", help="Output file for results"),
    format: OutputFormat = typer.Option(OutputFormat.table, "--format", "-f", help="Output format"),
):
    """
    Research and test LLM tool calling capabilities.

    This command tests whether a given LLM model can successfully call MCP tools.
    """
    # Load config with profile if specified
    if profile:
        from testmcpy.config import Config

        cfg = Config(profile=profile)
        effective_mcp_url = mcp_url or cfg.get_mcp_url()
    else:
        effective_mcp_url = mcp_url or DEFAULT_MCP_URL

    console.print(
        Panel.fit(
            "[bold cyan]MCP Testing Framework - Research Mode[/bold cyan]\n"
            f"Testing {model} via {provider.value}",
            border_style="cyan",
        )
    )

    async def run_research():
        # Import here to avoid circular dependencies
        from testmcpy.research.test_ollama_tools import (
            MCPServiceTester,
            OllamaToolTester,
        )

        # Test MCP connection
        console.print("\n[bold]Testing MCP Service[/bold]")
        mcp_tester = MCPServiceTester(effective_mcp_url)

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
            test_tools = [
                {
                    "type": "function",
                    "function": {
                        "name": "get_chart_data",
                        "description": "Get data for a specific chart",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "chart_id": {"type": "integer", "description": "Chart ID"}
                            },
                            "required": ["chart_id"],
                        },
                    },
                }
            ]

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
    provider: ModelProvider = typer.Option(
        DEFAULT_PROVIDER, "--provider", "-p", help="Model provider"
    ),
    mcp_url: str | None = typer.Option(
        None, "--mcp-url", help="MCP service URL (overrides profile)"
    ),
    profile: str | None = typer.Option(
        None, "--profile", help="MCP service profile from .mcp_services.yaml"
    ),
    output: Path | None = typer.Option(None, "--output", "-o", help="Output report file"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Don't actually run tests"),
    hide_tool_output: bool = typer.Option(
        False, "--hide-tool-output", help="Hide detailed tool call output in verbose mode"
    ),
):
    """
    Run test cases against MCP service.

    This command executes test cases defined in YAML/JSON files.
    """
    # Load config with profile if specified
    if profile:
        from testmcpy.config import Config

        cfg = Config(profile=profile)
        effective_mcp_url = mcp_url or cfg.get_mcp_url()
    else:
        effective_mcp_url = mcp_url or DEFAULT_MCP_URL

    console.print(
        Panel.fit(
            "[bold cyan]MCP Testing Framework - Run Tests[/bold cyan]\n"
            f"Model: {model} | Provider: {provider.value}",
            border_style="cyan",
        )
    )

    async def run_tests():
        # Import test runner
        from testmcpy.src.test_runner import TestCase, TestRunner

        runner = TestRunner(
            model=model,
            provider=provider.value,
            mcp_url=effective_mcp_url,
            verbose=verbose,
            hide_tool_output=hide_tool_output,
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
            if result.token_usage and "total" in result.token_usage:
                total_tokens += result.token_usage["total"]

            table.add_row(
                result.test_name,
                status,
                f"{result.score:.2f}",
                f"{result.duration:.2f}s",
                result.reason or "-",
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
                "results": [r.to_dict() for r in results],
            }

            if output.suffix == ".json":
                output.write_text(json.dumps(report_data, indent=2))
            else:
                output.write_text(yaml.dump(report_data))

            console.print(f"\n[green]Report saved to {output}[/green]")

    asyncio.run(run_tests())


@app.command()
def tools(
    mcp_url: str | None = typer.Option(
        None, "--mcp-url", help="MCP service URL (overrides profile)"
    ),
    profile: str | None = typer.Option(
        None, "--profile", help="MCP service profile from .mcp_services.yaml"
    ),
    format: OutputFormat = typer.Option(OutputFormat.table, "--format", "-f", help="Output format"),
    detail: bool = typer.Option(False, "--detail", "-d", help="Show detailed parameter schemas"),
    filter: str | None = typer.Option(None, "--filter", help="Filter tools by name"),
):
    """
    List available MCP tools with beautiful formatting.

    This command connects to the MCP service and displays all available tools
    with their descriptions and parameter schemas in a readable format.
    """
    # Load config with profile if specified
    if profile:
        from testmcpy.config import Config

        cfg = Config(profile=profile)
        effective_mcp_url = mcp_url or cfg.get_mcp_url()
    else:
        effective_mcp_url = mcp_url or DEFAULT_MCP_URL

    async def list_tools():
        from testmcpy.src.mcp_client import MCPClient

        console.print(
            Panel.fit(
                f"[bold cyan]MCP Tools Explorer[/bold cyan]\nService: {effective_mcp_url}",
                border_style="cyan",
            )
        )

        try:
            with console.status("[bold green]Connecting to MCP service...[/bold green]"):
                async with MCPClient(effective_mcp_url) as client:
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
                                tool_content.append("[bold]Description:[/bold]")
                                desc_lines = tool.description.split("\n")
                                for line in desc_lines[:5]:  # First 5 lines
                                    if line.strip():
                                        tool_content.append(f"  {line.strip()}")
                                if len(desc_lines) > 5:
                                    tool_content.append(
                                        f"  [dim]... and {len(desc_lines) - 5} more lines[/dim]"
                                    )

                                tool_content.append("")

                                # Parameters
                                if tool.input_schema:
                                    tool_content.append("[bold]Parameters:[/bold]")
                                    props = tool.input_schema.get("properties", {})
                                    required = tool.input_schema.get("required", [])

                                    if props:
                                        for param_name, param_info in props.items():
                                            param_type = param_info.get("type", "any")
                                            param_desc = param_info.get("description", "")
                                            is_required = "✓" if param_name in required else " "

                                            tool_content.append(
                                                f"  [{is_required}] [cyan]{param_name}[/cyan]: [yellow]{param_type}[/yellow]"
                                            )
                                            if param_desc:
                                                # Wrap long descriptions
                                                if len(param_desc) > 60:
                                                    param_desc = param_desc[:60] + "..."
                                                tool_content.append(
                                                    f"      [dim]{param_desc}[/dim]"
                                                )
                                    else:
                                        tool_content.append("  [dim]No parameters required[/dim]")
                                else:
                                    tool_content.append("[dim]No parameter schema[/dim]")

                                panel = Panel(
                                    "\n".join(tool_content),
                                    title=f"[bold green]{i}. {tool.name}[/bold green]",
                                    border_style="green",
                                    expand=False,
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
                                title_style="bold magenta",
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
                                    desc = desc[:80].rsplit(". ", 1)[0] + "..."

                                # Count parameters
                                param_count = (
                                    len(tool.input_schema.get("properties", {}))
                                    if tool.input_schema
                                    else 0
                                )
                                required_count = (
                                    len(tool.input_schema.get("required", []))
                                    if tool.input_schema
                                    else 0
                                )

                                param_str = f"{param_count}"
                                if required_count > 0:
                                    param_str = f"{param_count} ({required_count} req)"

                                table.add_row(str(i), tool.name, desc, param_str)

                            console.print(table)

                    elif format == OutputFormat.json:
                        output_data = [
                            {
                                "name": tool.name,
                                "description": tool.description,
                                "input_schema": tool.input_schema,
                            }
                            for tool in tools
                        ]
                        console.print(
                            Syntax(json.dumps(output_data, indent=2), "json", theme="monokai")
                        )

                    elif format == OutputFormat.yaml:
                        output_data = [
                            {
                                "name": tool.name,
                                "description": tool.description,
                                "input_schema": tool.input_schema,
                            }
                            for tool in tools
                        ]
                        console.print(Syntax(yaml.dump(output_data), "yaml", theme="monokai"))

                    # Summary
                    summary_parts = []
                    summary_parts.append(f"[green]{len(tools)} tool(s) displayed[/green]")
                    if filter:
                        summary_parts.append(
                            f"[yellow]filtered from {len(all_tools)} total[/yellow]"
                        )

                    console.print(f"\n[bold]Summary:[/bold] {' | '.join(summary_parts)}")

                    if not detail and format == OutputFormat.table:
                        console.print(
                            "[dim]Tip: Use --detail flag to see full parameter schemas[/dim]"
                        )

        except Exception as e:
            console.print(
                Panel(
                    f"[red]Error connecting to MCP service:[/red]\n{str(e)}",
                    title="[red]Error[/red]",
                    border_style="red",
                )
            )

    asyncio.run(list_tools())


@app.command()
def report(
    report_files: list[Path] = typer.Argument(..., help="Report files to compare"),
    output: Path | None = typer.Option(None, "--output", "-o", help="Output comparison file"),
):
    """
    Compare test reports from different models.

    This command takes multiple report files and generates a comparison.
    """
    console.print(
        Panel.fit(
            "[bold cyan]MCP Testing Framework - Report Comparison[/bold cyan]", border_style="cyan"
        )
    )

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
            f"{success_rate:.1f}%",
        )

    console.print(table)

    # Find tests that failed in one model but not another
    if len(reports) == 2:
        console.print("\n[bold]Differential Analysis[/bold]")

        r1, r2 = reports[0], reports[1]
        r1_results = {r["test_name"]: r["passed"] for r in r1["results"]}
        r2_results = {r["test_name"]: r["passed"] for r in r2["results"]}

        # Tests that failed in r1 but passed in r2
        failed_in_1 = [
            name
            for name, passed in r1_results.items()
            if not passed and r2_results.get(name, False)
        ]
        # Tests that failed in r2 but passed in r1
        failed_in_2 = [
            name
            for name, passed in r2_results.items()
            if not passed and r1_results.get(name, False)
        ]

        if failed_in_1:
            console.print(
                f"\n[yellow]Tests that failed in {r1['model']} but passed in {r2['model']}:[/yellow]"
            )
            for test in failed_in_1:
                console.print(f"  - {test}")

        if failed_in_2:
            console.print(
                f"\n[yellow]Tests that failed in {r2['model']} but passed in {r1['model']}:[/yellow]"
            )
            for test in failed_in_2:
                console.print(f"  - {test}")

    # Save comparison if requested
    if output:
        comparison = {
            "reports": reports,
            "comparison": {
                "models": [r["model"] for r in reports],
                "summary": [r["summary"] for r in reports],
            },
        }

        if output.suffix == ".json":
            output.write_text(json.dumps(comparison, indent=2))
        else:
            output.write_text(yaml.dump(comparison))

        console.print(f"\n[green]Comparison saved to {output}[/green]")


@app.command()
def interact(
    model: str = typer.Option(DEFAULT_MODEL, "--model", "-m", help="Model to use"),
    provider: ModelProvider = typer.Option(
        DEFAULT_PROVIDER, "--provider", "-p", help="Model provider"
    ),
    mcp_url: str | None = typer.Option(
        None, "--mcp-url", help="MCP service URL (overrides profile)"
    ),
    profile: str | None = typer.Option(
        None, "--profile", help="MCP service profile from .mcp_services.yaml"
    ),
    no_mcp: bool = typer.Option(False, "--no-mcp", help="Interact without MCP tools"),
):
    """
    Interactive conversation with LLM that has access to MCP tools.

    Start an interactive session where you can directly talk to the LLM and it can use
    MCP tools from your service. Type 'exit' or 'quit' to end the session.

    Use --no-mcp flag to interact without MCP tools.
    """
    # Load config with profile if specified
    if profile:
        from testmcpy.config import Config

        cfg = Config(profile=profile)
        effective_mcp_url = mcp_url or cfg.get_mcp_url()
    else:
        effective_mcp_url = mcp_url or DEFAULT_MCP_URL

    if no_mcp:
        console.print(
            Panel.fit(
                f"[bold cyan]Interactive Session with {model}[/bold cyan]\n"
                f"Provider: {provider.value}\nMode: Standalone (no MCP tools)\n\n"
                "[dim]Type your message and press Enter. Type 'exit' or 'quit' to end session.[/dim]",
                border_style="cyan",
            )
        )
    else:
        console.print(
            Panel.fit(
                f"[bold cyan]Interactive Session with {model}[/bold cyan]\n"
                f"Provider: {provider.value}\nMCP Service: {effective_mcp_url}\n\n"
                "[dim]Type your message and press Enter. Type 'exit' or 'quit' to end session.[/dim]",
                border_style="cyan",
            )
        )

    async def interact_session():
        import os
        import sys

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
                mcp_client = MCPClient(effective_mcp_url)
                await mcp_client.initialize()

                # Get available tools
                tools = await mcp_client.list_tools()
                console.print(
                    f"[green]Connected to MCP service with {len(tools)} tools available[/green]\n"
                )
            except Exception as e:
                console.print(f"[yellow]MCP connection failed: {e}[/yellow]")
                console.print("[yellow]Continuing without MCP tools...[/yellow]\n")

        if not tools:
            console.print("[dim]Interactive mode: Standalone (no tools available)[/dim]\n")

        # Interactive loop
        while True:
            try:
                # Get user input
                user_input = console.input("[bold blue]You:[/bold blue] ")

                if user_input.lower() in ["exit", "quit", "bye"]:
                    console.print("[yellow]Goodbye![/yellow]")
                    break

                if not user_input.strip():
                    continue

                # Show thinking indicator
                with console.status("[dim]Thinking...[/dim]"):
                    # Convert MCPTool objects to dictionaries for LLM
                    tools_dict = []
                    for tool in tools:
                        tools_dict.append(
                            {
                                "name": tool.name,
                                "description": tool.description,
                                "inputSchema": tool.input_schema,
                            }
                        )

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
                console.print("\n[yellow]Session interrupted. Goodbye![/yellow]")
                break
            except Exception as e:
                console.print(f"[red]Error: {e}[/red]")

        # Cleanup
        if mcp_client:
            await mcp_client.close()
        await llm.close()

    asyncio.run(interact_session())


@app.command()
def init(
    path: Path = typer.Argument(Path("."), help="Directory to initialize"),
):
    """
    Initialize a new MCP test project.

    This command creates the standard directory structure and example files.
    """
    console.print(
        Panel.fit(
            "[bold cyan]MCP Testing Framework - Initialize Project[/bold cyan]", border_style="cyan"
        )
    )

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
                    {"name": "final_answer_contains", "args": {"expected_content": "chart"}},
                ],
            },
            {
                "name": "test_create_dashboard",
                "prompt": "Create a new dashboard called 'Sales Overview' with a bar chart",
                "evaluators": [
                    {"name": "was_superset_chart_created"},
                    {"name": "execution_successful"},
                    {"name": "within_time_limit", "args": {"max_seconds": 30}},
                ],
            },
        ],
    }

    test_file = path / "tests" / "example_tests.yaml"
    test_file.write_text(yaml.dump(example_test, default_flow_style=False))
    console.print(f"[green]✓ Created example test file: {test_file}[/green]")

    # Create config file
    project_config = {
        "mcp_url": DEFAULT_MCP_URL,
        "default_model": DEFAULT_MODEL,
        "default_provider": DEFAULT_PROVIDER,
        "evaluators": {"timeout": 30, "max_tokens": 2000, "max_cost": 0.10},
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
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite existing config files"),
):
    """
    Interactive setup wizard for testmcpy configuration.

    Guides you through configuring MCP service profiles and LLM providers.
    Creates .llm_providers.yaml and .mcp_services.yaml in current directory.
    """
    from testmcpy.config import get_config

    console.print(
        Panel.fit(
            "[bold cyan]testmcpy Interactive Setup[/bold cyan]\n"
            "[dim]Configure MCP service profiles and LLM providers[/dim]",
            border_style="cyan",
        )
    )

    # Load current config to show existing values and detect env vars
    current_config = get_config()

    # Check for existing files
    llm_yaml_path = Path.cwd() / ".llm_providers.yaml"
    mcp_yaml_path = Path.cwd() / ".mcp_services.yaml"

    if (llm_yaml_path.exists() or mcp_yaml_path.exists()) and not force:
        console.print("\n[yellow]Configuration files already exist:[/yellow]")
        if llm_yaml_path.exists():
            console.print(f"  • {llm_yaml_path}")
        if mcp_yaml_path.exists():
            console.print(f"  • {mcp_yaml_path}")
        overwrite = console.input("\nOverwrite? [y/N]: ").strip().lower()
        if overwrite not in ["y", "yes"]:
            console.print("[yellow]Setup cancelled[/yellow]")
            return

    # ============================================================
    # LLM Provider Configuration
    # ============================================================
    console.print("\n[bold cyan]━━━ LLM Provider Configuration ━━━[/bold cyan]\n")

    # Detect API keys from environment
    env_anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    env_openai_key = os.environ.get("OPENAI_API_KEY")

    # Show detected environment variables
    if env_anthropic_key or env_openai_key:
        console.print("[green]✓ Detected API keys in environment:[/green]")
        if env_anthropic_key:
            console.print(f"  • ANTHROPIC_API_KEY: {env_anthropic_key[:8]}...{env_anthropic_key[-4:]}")
        if env_openai_key:
            console.print(f"  • OPENAI_API_KEY: {env_openai_key[:8]}...{env_openai_key[-4:]}")
        console.print()

    # Ask which provider to use
    console.print("[bold]Select LLM Provider:[/bold]")
    console.print("1. [cyan]Anthropic[/cyan] - Claude models (best tool calling)")
    console.print("2. [cyan]OpenAI[/cyan] - GPT models")
    console.print("3. [cyan]Ollama[/cyan] - Local models (free, requires ollama serve)")

    provider_choice = console.input("\nChoice [1]: ").strip() or "1"

    llm_config = {"default": "prod", "profiles": {}}

    if provider_choice == "1":
        # Anthropic
        console.print("\n[bold]Anthropic Configuration:[/bold]")
        console.print("1. [cyan]claude-sonnet-4-5[/cyan] - Latest Sonnet 4.5 (most capable)")
        console.print("2. [cyan]claude-haiku-4-5[/cyan] - Latest Haiku 4.5 (fast & efficient)")
        console.print("3. [cyan]claude-opus-4-1[/cyan] - Latest Opus 4.1 (most powerful)")

        model_choice = console.input("\nChoice [1]: ").strip() or "1"
        model = "claude-sonnet-4-5"
        if model_choice == "2":
            model = "claude-haiku-4-5"
        elif model_choice == "3":
            model = "claude-opus-4-1"

        # API Key
        if env_anthropic_key:
            console.print(f"\n[green]Using Anthropic API key from environment:[/green] {env_anthropic_key[:8]}...{env_anthropic_key[-4:]}")
            use_env = console.input("Save this key to .llm_providers.yaml? [Y/n]: ").strip().lower()
            if use_env in ["", "y", "yes"]:
                api_key = env_anthropic_key
            else:
                api_key = console.input("Enter different API key: ").strip()
        else:
            api_key = console.input("\nAnthropic API Key: ").strip()

        llm_config["profiles"]["prod"] = {
            "name": "Production",
            "description": "High-quality models for production use",
            "providers": [
                {
                    "name": f"Claude {model}",
                    "provider": "anthropic",
                    "model": model,
                    "api_key": api_key,
                    "timeout": 60,
                    "default": True,
                }
            ],
        }

    elif provider_choice == "2":
        # OpenAI
        console.print("\n[bold]OpenAI Configuration:[/bold]")
        console.print("1. [cyan]gpt-4o[/cyan] - GPT-4 Optimized (recommended)")
        console.print("2. [cyan]gpt-4-turbo[/cyan] - GPT-4 Turbo")
        console.print("3. [cyan]gpt-3.5-turbo[/cyan] - GPT-3.5 Turbo (faster, cheaper)")

        model_choice = console.input("\nChoice [1]: ").strip() or "1"
        model = "gpt-4o"
        if model_choice == "2":
            model = "gpt-4-turbo"
        elif model_choice == "3":
            model = "gpt-3.5-turbo"

        # API Key
        if env_openai_key:
            console.print(f"\n[green]Using OpenAI API key from environment:[/green] {env_openai_key[:8]}...{env_openai_key[-4:]}")
            use_env = console.input("Save this key to .llm_providers.yaml? [Y/n]: ").strip().lower()
            if use_env in ["", "y", "yes"]:
                api_key = env_openai_key
            else:
                api_key = console.input("Enter different API key: ").strip()
        else:
            api_key = console.input("\nOpenAI API Key: ").strip()

        llm_config["profiles"]["prod"] = {
            "name": "Production",
            "description": "High-quality models for production use",
            "providers": [
                {
                    "name": f"OpenAI {model}",
                    "provider": "openai",
                    "model": model,
                    "api_key": api_key,
                    "timeout": 60,
                    "default": True,
                }
            ],
        }

    else:
        # Ollama
        console.print("\n[bold]Ollama Configuration:[/bold]")
        console.print("1. [cyan]llama3.1:8b[/cyan] - Meta's Llama 3.1 8B (good balance)")
        console.print("2. [cyan]qwen2.5:14b[/cyan] - Alibaba's Qwen 2.5 14B (strong coding)")
        console.print("3. [cyan]mistral:7b[/cyan] - Mistral 7B (efficient)")

        model_choice = console.input("\nChoice [1]: ").strip() or "1"
        model = "llama3.1:8b"
        if model_choice == "2":
            model = "qwen2.5:14b"
        elif model_choice == "3":
            model = "mistral:7b"

        base_url = console.input("\nOllama Base URL [http://localhost:11434]: ").strip() or "http://localhost:11434"

        llm_config["profiles"]["prod"] = {
            "name": "Production",
            "description": "Local Ollama models",
            "providers": [
                {
                    "name": f"Ollama {model}",
                    "provider": "ollama",
                    "model": model,
                    "base_url": base_url,
                    "timeout": 120,
                    "default": True,
                }
            ],
        }

    # Save LLM config
    llm_yaml_path.write_text(yaml.dump(llm_config, default_flow_style=False, sort_keys=False))
    console.print(f"\n[green]✓ LLM configuration saved to:[/green] {llm_yaml_path}")

    # ============================================================
    # MCP Service Configuration
    # ============================================================
    console.print("\n[bold cyan]━━━ MCP Service Configuration ━━━[/bold cyan]\n")

    # Show current MCP URL if set
    current_mcp_url = current_config.get_mcp_url()
    if current_mcp_url and current_mcp_url != "http://localhost:5008/mcp/":
        source = current_config.get_source("MCP_URL")
        console.print(f"[green]✓ MCP Service URL detected[/green] ({source})")
        console.print(f"[dim]  Current: {current_mcp_url}[/dim]")
        mcp_url = console.input("  New URL (or press Enter to keep current): ").strip() or current_mcp_url
    else:
        mcp_url = console.input("MCP Service URL [https://your-workspace.preset.io/mcp]: ").strip()

    if not mcp_url:
        console.print("[yellow]Skipping MCP configuration[/yellow]")
        console.print(f"[dim]You can configure MCP later by editing {mcp_yaml_path}[/dim]")
    else:
        # Ask for authentication method
        console.print("\n[bold]MCP Authentication Method:[/bold]")

        # Detect current auth method
        has_dynamic_jwt = all([
            current_config.get("MCP_AUTH_API_URL"),
            current_config.get("MCP_AUTH_API_TOKEN"),
            current_config.get("MCP_AUTH_API_SECRET"),
        ])
        has_static_token = current_config.get("MCP_AUTH_TOKEN") or current_config.get("SUPERSET_MCP_TOKEN")

        if has_dynamic_jwt:
            console.print("[dim]Currently configured: Dynamic JWT[/dim]")
        elif has_static_token:
            console.print("[dim]Currently configured: Static Token[/dim]")

        console.print("1. [cyan]Dynamic JWT[/cyan] - Fetch token from Preset API (recommended)")
        console.print("2. [cyan]Static Token[/cyan] - Use a pre-generated bearer token")
        console.print("3. [cyan]None[/cyan] - No authentication required")

        default_auth = "1" if has_dynamic_jwt or not has_static_token else "2"
        auth_method = console.input(f"\nChoice [{default_auth}]: ").strip() or default_auth

        auth_config = {}

        if auth_method == "1":
            # Dynamic JWT
            current_api_url = current_config.get("MCP_AUTH_API_URL")
            if current_api_url:
                console.print(f"[dim]Current Auth API URL: {current_api_url}[/dim]")
                api_url = console.input("  New URL (or press Enter to keep current): ").strip() or current_api_url
            else:
                api_url = console.input("Auth API URL (e.g., https://api.app.preset.io/v1/auth/): ").strip()

            current_api_token = current_config.get("MCP_AUTH_API_TOKEN")
            if current_api_token:
                masked = f"{current_api_token[:8]}...{current_api_token[-4:]}"
                console.print(f"[dim]Current API Token: {masked}[/dim]")
                api_token = console.input("  New token (or press Enter to keep current): ").strip() or current_api_token
            else:
                api_token = console.input("API Token: ").strip()

            current_api_secret = current_config.get("MCP_AUTH_API_SECRET")
            if current_api_secret:
                masked = f"{current_api_secret[:8]}...{current_api_secret[-4:]}"
                console.print(f"[dim]Current API Secret: {masked}[/dim]")
                api_secret = console.input("  New secret (or press Enter to keep current): ").strip() or current_api_secret
            else:
                api_secret = console.input("API Secret: ").strip()

            auth_config = {
                "auth_type": "jwt",
                "api_url": api_url,
                "api_token": api_token,
                "api_secret": api_secret,
            }

        elif auth_method == "2":
            # Static token
            current_token = current_config.get("MCP_AUTH_TOKEN") or current_config.get("SUPERSET_MCP_TOKEN")
            if current_token:
                masked = f"{current_token[:20]}...{current_token[-8:]}"
                console.print(f"[dim]Current Token: {masked}[/dim]")
                static_token = console.input("  New token (or press Enter to keep current): ").strip() or current_token
            else:
                static_token = console.input("Bearer Token: ").strip()

            auth_config = {
                "auth_type": "bearer",
                "token": static_token,
            }
        else:
            # No auth
            auth_config = {"auth_type": "none"}

        # Create MCP config
        mcp_config = {
            "default": "prod",
            "profiles": {
                "prod": {
                    "name": "Production",
                    "description": "Production MCP service",
                    "mcps": [
                        {
                            "name": "Preset Superset",
                            "mcp_url": mcp_url,
                            "auth": auth_config,
                            "timeout": 30,
                            "rate_limit_rpm": 60,
                            "default": True,
                        }
                    ],
                }
            },
        }

        # Save MCP config
        mcp_yaml_path.write_text(yaml.dump(mcp_config, default_flow_style=False, sort_keys=False))
        console.print(f"\n[green]✓ MCP configuration saved to:[/green] {mcp_yaml_path}")

    # Final summary
    console.print("\n[bold green]✓ Setup Complete![/bold green]")
    console.print("\n[bold]Configuration files created:[/bold]")
    console.print(f"  • {llm_yaml_path}")
    if mcp_yaml_path.exists():
        console.print(f"  • {mcp_yaml_path}")

    console.print("\n[bold]Next steps:[/bold]")
    console.print("1. Run: [cyan]testmcpy config-cmd[/cyan]  # Verify configuration")
    if mcp_yaml_path.exists():
        console.print("2. Run: [cyan]testmcpy tools[/cyan]  # List available MCP tools")
        console.print("3. Run: [cyan]testmcpy interact[/cyan]  # Start interactive session")
    console.print("\n[dim]Note: You can edit these files manually or run setup again with --force[/dim]")


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
    # Show logo
    print_logo()

    # Show authentication steps
    console.print("\n[bold cyan]Authentication Setup[/bold cyan]")
    console.print("[dim]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/dim]")

    # Load config
    console.print("  [1/4] Loading configuration...")
    from testmcpy.config import get_config

    cfg = get_config()
    console.print("  [green]✓[/green] Configuration loaded")

    # Check MCP URL
    console.print("\n  [2/4] Checking MCP service URL...")
    console.print(f"  [dim]    MCP URL: {cfg.get_mcp_url()}[/dim]")
    console.print(f"  [dim]    Source: {cfg.get_source('MCP_URL')}[/dim]")
    console.print("  [green]✓[/green] MCP URL configured")

    # Check authentication method
    console.print("\n  [3/4] Checking authentication method...")
    has_dynamic_jwt = all(
        [cfg.get("MCP_AUTH_API_URL"), cfg.get("MCP_AUTH_API_TOKEN"), cfg.get("MCP_AUTH_API_SECRET")]
    )
    has_static_token = cfg.get("MCP_AUTH_TOKEN") or cfg.get("SUPERSET_MCP_TOKEN")

    if has_dynamic_jwt:
        console.print("  [cyan]→[/cyan] Using dynamic JWT authentication")
        console.print(f"  [dim]    Auth API URL: {cfg.get('MCP_AUTH_API_URL')}[/dim]")
        console.print(
            f"  [dim]    API Token: {cfg.get('MCP_AUTH_API_TOKEN')[:8]}...{cfg.get('MCP_AUTH_API_TOKEN')[-4:]}[/dim]"
        )
        console.print("  [green]✓[/green] Dynamic JWT configured")

        # Try to fetch token
        console.print("\n  [4/4] Fetching JWT token from API...")
        try:
            import requests

            response = requests.post(
                cfg.get("MCP_AUTH_API_URL"),
                headers={"Content-Type": "application/json", "Accept": "application/json"},
                json={
                    "name": cfg.get("MCP_AUTH_API_TOKEN"),
                    "secret": cfg.get("MCP_AUTH_API_SECRET"),
                },
                timeout=10,
            )
            if response.status_code == 200:
                console.print("  [green]✓[/green] JWT token fetched successfully")
            else:
                console.print(
                    f"  [yellow]⚠[/yellow] Failed to fetch JWT token (status: {response.status_code})"
                )
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
        console.print("\n  [4/4] Token validation skipped (static token)")
    else:
        console.print("  [yellow]⚠[/yellow] No authentication configured")
        console.print("  [yellow]  MCP service may require authentication[/yellow]")
        console.print("\n  [4/4] Authentication setup incomplete")

    console.print("[dim]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/dim]\n")

    console.print(
        Panel.fit(
            f"[bold cyan]testmcpy Web Server[/bold cyan]\nStarting server at http://{host}:{port}",
            border_style="cyan",
        )
    )

    import subprocess
    import time
    from pathlib import Path

    # Get paths
    Path(__file__).parent / "server"
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
        result = subprocess.run(["npm", "install"], cwd=ui_dir, capture_output=True, text=True)
        if result.returncode != 0:
            console.print(f"[red]Failed to install dependencies:[/red]\n{result.stderr}")
            return

        # Build
        console.print("Building frontend...")
        result = subprocess.run(["npm", "run", "build"], cwd=ui_dir, capture_output=True, text=True)
        if result.returncode != 0:
            console.print(f"[red]Failed to build frontend:[/red]\n{result.stderr}")
            return

        console.print("[green]Frontend built successfully![/green]\n")

    elif dev:
        console.print(
            "[yellow]Running in dev mode - make sure to start the frontend separately:[/yellow]"
        )
        console.print(f"  cd {ui_dir} && npm run dev\n")

    # Open browser
    if not no_browser:
        import threading
        import webbrowser
        import requests

        def open_browser():
            # Wait for server to be ready by checking health endpoint
            url = f"http://{host}:{port}/"
            max_attempts = 30
            for i in range(max_attempts):
                try:
                    response = requests.get(url, timeout=1)
                    if response.status_code == 200:
                        # Server is ready
                        webbrowser.open(url)
                        return
                except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
                    pass
                time.sleep(0.2)  # Wait 200ms between attempts

            # If server didn't start after max attempts, open anyway
            webbrowser.open(url)

        threading.Thread(target=open_browser, daemon=True).start()

    # Start server
    console.print("[green]Server starting...[/green]")
    console.print(f"[dim]API docs available at http://{host}:{port}/docs[/dim]\n")

    try:
        import uvicorn

        from testmcpy.server.api import app as fastapi_app

        uvicorn.run(fastapi_app, host=host, port=port, log_level="info")
    except KeyboardInterrupt:
        console.print("\n[yellow]Server stopped[/yellow]")
    except Exception as e:
        console.print(f"[red]Server error:[/red] {e}")


@app.command()
def config_cmd(
    show_all: bool = typer.Option(
        False, "--all", "-a", help="Show all config values including unset ones"
    ),
):
    """
    Display current testmcpy configuration.

    Shows the configuration values and their sources (environment, config file, etc.).
    """
    console.print(Panel.fit("[bold cyan]testmcpy Configuration[/bold cyan]", border_style="cyan"))

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
        title_style="bold magenta",
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
    target: str = typer.Argument(
        ..., help="Target application: claude-desktop, claude-code, or chatgpt-desktop"
    ),
    server_name: str | None = typer.Option(
        None, "--name", "-n", help="Server name in config (default: preset-superset)"
    ),
    mcp_url: str | None = typer.Option(
        None, "--mcp-url", help="MCP service URL (uses config default if not provided)"
    ),
    auth_token: str | None = typer.Option(
        None, "--token", help="Bearer token (uses dynamic JWT if not provided)"
    ),
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

    console.print(
        Panel.fit(f"[bold cyan]Configure MCP for {target}[/bold cyan]", border_style="cyan")
    )

    # Determine target config file path
    system = platform.system()
    target = target.lower()

    if target == "claude-desktop":
        if system == "Darwin":  # macOS
            config_path = (
                Path.home()
                / "Library"
                / "Application Support"
                / "Claude"
                / "claude_desktop_config.json"
            )
        elif system == "Windows":
            config_path = Path(os.getenv("APPDATA")) / "Claude" / "claude_desktop_config.json"
        else:  # Linux
            config_path = Path.home() / ".config" / "Claude" / "claude_desktop_config.json"

    elif target == "claude-code":
        # Prefer ~/.claude.json for reliability
        config_path = Path.home() / ".claude.json"
        console.print(
            "[dim]Note: Using ~/.claude.json (recommended). You can also use .mcp.json in project directory.[/dim]\n"
        )

    elif target == "chatgpt-desktop":
        # ChatGPT Desktop uses similar format to Claude Desktop
        if system == "Darwin":  # macOS
            config_path = (
                Path.home() / "Library" / "Application Support" / "ChatGPT" / "config.json"
            )
        else:
            console.print(
                "[yellow]ChatGPT Desktop config location not well-documented for this OS.[/yellow]"
            )
            console.print(
                "[yellow]Please check ChatGPT Desktop documentation for config file location.[/yellow]"
            )
            return

    else:
        console.print(f"[red]Error: Unknown target '{target}'[/red]")
        console.print("Supported targets: claude-desktop, claude-code, chatgpt-desktop")
        return

    # Get MCP configuration
    cfg = get_config()
    mcp_url = mcp_url or cfg.get_mcp_url()
    server_name = server_name or "preset-superset"

    if not mcp_url:
        console.print("[red]Error: MCP URL not configured[/red]")
        console.print("Run: testmcpy setup")
        return

    # Get auth token
    if not auth_token:
        # Try to get auth from MCP profile first
        mcp_server = cfg.get_default_mcp_server()
        if mcp_server and mcp_server.auth:
            auth = mcp_server.auth

            if auth.auth_type == "bearer" and auth.token:
                # Static bearer token
                console.print("[green]✓ Using bearer token from MCP profile[/green]")
                auth_token = auth.token

            elif auth.auth_type == "jwt" and auth.api_url and auth.api_token and auth.api_secret:
                # Dynamic JWT - fetch token
                console.print("[yellow]Fetching bearer token using JWT from MCP profile...[/yellow]")
                try:
                    import requests

                    console.print(f"[dim]Auth URL: {auth.api_url}[/dim]")
                    console.print(f"[dim]API Token: {auth.api_token[:8]}...{auth.api_token[-4:]}[/dim]")

                    response = requests.post(
                        auth.api_url,
                        headers={"Content-Type": "application/json", "Accept": "application/json"},
                        json={"name": auth.api_token, "secret": auth.api_secret},
                        timeout=10,
                    )

                    console.print(f"[dim]Response status: {response.status_code}[/dim]")

                    if response.status_code != 200:
                        console.print(f"[red]Error: API returned {response.status_code}[/red]")
                        console.print(f"[red]Response: {response.text}[/red]")
                        console.print(
                            "[yellow]Please provide --token with a long-lived bearer token[/yellow]"
                        )
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
                        console.print(
                            f"[green]✓ Successfully fetched bearer token (length: {len(auth_token)})[/green]"
                        )
                    else:
                        console.print("[red]Error: No access_token or payload in response[/red]")
                        console.print(f"[red]Response keys: {list(auth_data.keys())}[/red]")
                        console.print(f"[red]Full response: {auth_data}[/red]")
                        return
                except Exception as e:
                    console.print(f"[red]Error fetching token: {e}[/red]")
                    import traceback

                    console.print(f"[red]{traceback.format_exc()}[/red]")
                    console.print(
                        "[yellow]Please provide --token with a long-lived bearer token[/yellow]"
                    )
                    return
            elif auth.auth_type == "none":
                # No auth required
                console.print("[yellow]Note: MCP profile has auth_type: none[/yellow]")
                console.print("[yellow]Skipping authentication (you may need to add --token manually)[/yellow]")
                auth_token = ""  # Empty token for no-auth
            else:
                console.print(f"[yellow]Warning: Unknown or incomplete auth type in MCP profile: {auth.auth_type}[/yellow]")

        # Fallback to old env-var approach if no MCP profile auth
        if not auth_token:
            if (
                cfg.get("MCP_AUTH_API_URL")
                and cfg.get("MCP_AUTH_API_TOKEN")
                and cfg.get("MCP_AUTH_API_SECRET")
            ):
                console.print("[yellow]Fetching bearer token using legacy env vars (MCP_AUTH_API_*)...[/yellow]")
                try:
                    import requests

                    auth_url = cfg.get("MCP_AUTH_API_URL")
                    api_token = cfg.get("MCP_AUTH_API_TOKEN")
                    api_secret = cfg.get("MCP_AUTH_API_SECRET")

                    console.print(f"[dim]Auth URL: {auth_url}[/dim]")
                    console.print(f"[dim]API Token: {api_token[:8]}...{api_token[-4:]}[/dim]")

                    response = requests.post(
                        auth_url,
                        headers={"Content-Type": "application/json", "Accept": "application/json"},
                        json={"name": api_token, "secret": api_secret},
                        timeout=10,
                    )

                    console.print(f"[dim]Response status: {response.status_code}[/dim]")

                    if response.status_code != 200:
                        console.print(f"[red]Error: API returned {response.status_code}[/red]")
                        console.print(f"[red]Response: {response.text}[/red]")
                        console.print(
                            "[yellow]Please provide --token with a long-lived bearer token[/yellow]"
                        )
                        return

                    auth_data = response.json()
                    auth_token = auth_data.get("access_token")
                    if not auth_token and "payload" in auth_data:
                        payload = auth_data["payload"]
                        if isinstance(payload, dict):
                            auth_token = payload.get("access_token")
                        else:
                            auth_token = payload

                    if auth_token:
                        console.print(
                            f"[green]✓ Successfully fetched bearer token (length: {len(auth_token)})[/green]"
                        )
                    else:
                        console.print("[red]Error: No access_token or payload in response[/red]")
                        return
                except Exception as e:
                    console.print(f"[red]Error fetching token: {e}[/red]")
                    return
            else:
                console.print("[red]Error: No authentication token available[/red]")
                console.print("Options:")
                console.print("  1. Configure MCP profile in .mcp_services.yaml (recommended)")
                console.print("  2. Provide --token with a bearer token")
                console.print("  3. Configure legacy env vars (MCP_AUTH_API_*)")
                return

    # Create MCP server configuration
    mcp_args = ["-y", "mcp-remote@latest", mcp_url]

    # Only add Authorization header if we have a token (not empty for no-auth)
    if auth_token:
        mcp_args.extend(["--header", f"Authorization: Bearer {auth_token}"])

    mcp_server_config = {
        "command": "npx",
        "args": mcp_args,
        "env": {"NODE_OPTIONS": "--no-warnings"},
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
        with open(config_path, "w") as f:
            json.dump(existing_config, f, indent=2)

        console.print("\n[green]✓ MCP server configured successfully![/green]")
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
                    f"Authorization: Bearer {auth_token[:20]}...{auth_token[-8:]}",
                ],
                "env": {"NODE_OPTIONS": "--no-warnings"},
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
def export(
    tool_name: str | None = typer.Argument(None, help="Tool name to export (or use --all)"),
    format: str = typer.Option("typescript", "--format", "-f", help="Export format"),
    output: Path | None = typer.Option(None, "--output", "-o", help="Output file"),
    all: bool = typer.Option(False, "--all", help="Export all tools"),
    profile: str | None = typer.Option(None, "--profile", help="MCP profile"),
    mcp_url: str | None = typer.Option(None, "--mcp-url", help="MCP service URL"),
):
    """
    Export MCP tool schemas in various formats.

    Supported formats: typescript, python, protobuf, thrift, graphql, curl, json, yaml

    Examples:
        # Export as TypeScript
        testmcpy export get_chart_data --format typescript

        # Export all tools as Python to file
        testmcpy export --all --format python -o schemas.py

        # Generate cURL command
        testmcpy export list_datasets --format curl

        # Use specific profile
        testmcpy export search --format protobuf --profile production
    """
    from testmcpy.formatters import FORMATS

    # Load config with profile if specified
    if profile:
        from testmcpy.config import Config

        cfg = Config(profile=profile)
        effective_mcp_url = mcp_url or cfg.get_mcp_url()
    else:
        effective_mcp_url = mcp_url or DEFAULT_MCP_URL

    # Validate format
    if format not in FORMATS:
        console.print(f"[red]Error: Unknown format '{format}'[/red]")
        console.print(f"[yellow]Supported formats: {', '.join(FORMATS.keys())}[/yellow]")
        raise typer.Exit(1)

    # Validate that either tool_name or --all is provided
    if not tool_name and not all:
        console.print("[red]Error: Either specify a tool name or use --all flag[/red]")
        console.print("[yellow]Example: testmcpy export my_tool --format typescript[/yellow]")
        raise typer.Exit(1)

    async def export_schemas():
        from testmcpy.src.mcp_client import MCPClient

        console.print(
            Panel.fit(
                f"[bold cyan]Export MCP Tool Schemas[/bold cyan]\n"
                f"Format: {FORMATS[format]['label']} | Service: {effective_mcp_url}",
                border_style="cyan",
            )
        )

        try:
            with console.status("[bold green]Connecting to MCP service...[/bold green]"):
                async with MCPClient(effective_mcp_url) as client:
                    tools = await client.list_tools()

                    if not tools:
                        console.print("[yellow]No tools found in MCP service[/yellow]")
                        return

                    # Filter tools if specific tool requested
                    if not all:
                        tools = [t for t in tools if t.name == tool_name]
                        if not tools:
                            console.print(f"[red]Error: Tool '{tool_name}' not found[/red]")
                            console.print(
                                f"[yellow]Available tools: {', '.join([t.name for t in await client.list_tools()])}[/yellow]"
                            )
                            return

                    console.print(
                        f"[green]✓ Found {len(tools)} tool(s) to export[/green]\n"
                    )

                    # Get the conversion function
                    convert_func = FORMATS[format]["convert"]
                    language = FORMATS[format]["language"]

                    # Generate output
                    output_lines = []

                    for i, tool in enumerate(tools):
                        # Add separator between tools when exporting all
                        if all and i > 0:
                            if format in ["typescript", "python"]:
                                output_lines.append("\n\n")
                            elif format in ["protobuf", "thrift", "graphql"]:
                                output_lines.append("\n")
                            elif format == "curl":
                                output_lines.append("\n" + "=" * 80 + "\n\n")
                            else:
                                output_lines.append("\n---\n\n")

                        # Add tool name comment for clarity when exporting all
                        if all:
                            if format in ["typescript", "python", "protobuf", "thrift", "graphql"]:
                                output_lines.append(f"// Tool: {tool.name}\n")
                            elif format == "yaml":
                                output_lines.append(f"# Tool: {tool.name}\n")

                        # Convert schema
                        if format == "curl":
                            converted = convert_func(tool.input_schema, tool.name)
                        elif format in ["json", "yaml"]:
                            # For JSON/YAML, include tool metadata
                            schema_with_metadata = {
                                "name": tool.name,
                                "description": tool.description,
                                "input_schema": tool.input_schema,
                            }
                            converted = convert_func(schema_with_metadata)
                        else:
                            # For code formats, use a nice name
                            name = "".join(
                                word.capitalize() for word in tool.name.replace("-", "_").split("_")
                            )
                            if format == "typescript":
                                name = f"{name}Params"
                            elif format == "python":
                                name = f"{name}Params"
                            elif format == "protobuf":
                                name = f"{name}Request"
                            elif format == "thrift":
                                name = f"{name}Request"
                            elif format == "graphql":
                                name = f"{name}Input"

                            converted = convert_func(tool.input_schema, name)

                        output_lines.append(converted)

                    output_text = "".join(output_lines)

                    # Display or save output
                    if output:
                        output.write_text(output_text)
                        console.print(f"[green]✓ Exported to {output}[/green]")
                    else:
                        # Display with syntax highlighting
                        console.print(Syntax(output_text, language, theme="monokai"))

        except Exception as e:
            console.print(
                Panel(
                    f"[red]Error exporting schemas:[/red]\n{str(e)}",
                    title="[red]Error[/red]",
                    border_style="red",
                )
            )

    asyncio.run(export_schemas())


@app.command()
def dash(
    profile: str = typer.Option(None, "--profile", "-p", help="MCP profile to use"),
    auto_refresh: bool = typer.Option(False, "--auto-refresh", help="Auto-refresh status"),
):
    """
    Launch interactive TUI dashboard.

    Beautiful terminal-based dashboard for MCP testing and exploration.
    Navigate with keyboard shortcuts, manage profiles, explore tools, and more.

    Features:
    - Browse MCP tools and resources
    - Manage profiles
    - View connection status
    - Quick actions and shortcuts

    Press '?' for help once inside the dashboard.
    """
    try:
        from testmcpy.tui.app import run_tui
    except ImportError:
        console.print("[red]Error: Textual is required for the TUI dashboard[/red]")
        console.print("Install with: pip install 'testmcpy[tui]' or pip install textual")
        console.print("Or upgrade: pip install --upgrade testmcpy")
        return

    # Launch the TUI
    try:
        run_tui(profile=profile, enable_auto_refresh=auto_refresh)
    except Exception as e:
        console.print(f"[red]Error launching dashboard:[/red] {e}")
        import traceback
        console.print(f"[dim]{traceback.format_exc()}[/dim]")


@app.command()
def explore(
    profile: str | None = typer.Option(
        None, "--profile", "-p", help="MCP service profile from .mcp_services.yaml"
    ),
):
    """
    Launch interactive MCP explorer TUI.

    This command starts an interactive terminal interface for browsing and
    exploring MCP tools, resources, and prompts. Features include:

    - Browse tools organized by categories
    - View detailed tool documentation and schemas
    - Search and filter tools
    - Generate test files from tools
    - AI-powered documentation optimization

    Navigation:
    - Arrow keys / hjkl: Navigate tree
    - Enter: Expand/collapse or show details
    - /: Search tools
    - t: Generate test for selected tool
    - o: Optimize docs for selected tool
    - h / Esc: Return to home
    - q: Quit
    """
    console.print(
        Panel.fit(
            "[bold cyan]MCP Explorer - Interactive TUI[/bold cyan]\n"
            f"Profile: {profile or 'default'}",
            border_style="cyan",
        )
    )

    try:
        # Import here to avoid dependency issues if textual not installed
        from testmcpy.tui.simple_app import run_tui

        run_tui(profile=profile)
    except ImportError:
        console.print(
            "[red]Error: Textual is required for the TUI explorer[/red]\n"
            "Install with: pip install 'testmcpy[tui]' or pip install textual",
            markup=False,
        )
    except Exception as e:
        console.print(f"[red]Error launching explorer:[/red] {e}")


@app.command()
def profiles(
    show_details: bool = typer.Option(
        False,
        "--details",
        "-d",
        help="Show detailed profile information",
    ),
    set_default: str = typer.Option(
        None,
        "--set-default",
        help="Set the default profile (writes to .mcp_services.yaml)",
    ),
    get_default: bool = typer.Option(
        False,
        "--get-default",
        help="Show the current default profile",
    ),
):
    """
    List and manage MCP profiles.

    View all configured MCP profiles, get/set the default profile.
    For interactive profile management, use: testmcpy dash

    Examples:
        testmcpy profiles                    # List all profiles
        testmcpy profiles --details          # Show detailed info
        testmcpy profiles --get-default      # Show default profile
        testmcpy profiles --set-default prod # Set 'prod' as default
    """
    from testmcpy.mcp_profiles import get_profile_config, load_profile
    from pathlib import Path
    import yaml

    profile_config = get_profile_config()

    # Handle --get-default
    if get_default:
        default = profile_config.default_profile
        if default:
            console.print(f"\n[bold cyan]Default MCP Profile:[/bold cyan] {default}\n")
        else:
            console.print("\n[yellow]No default profile set[/yellow]\n")
        return

    # Handle --set-default
    if set_default:
        # Verify profile exists
        if set_default not in profile_config.list_profiles():
            console.print(f"\n[red]Error: Profile '{set_default}' not found[/red]")
            console.print("\nAvailable profiles:")
            for p in profile_config.list_profiles():
                console.print(f"  • {p}")
            return

        # Read current YAML file
        config_path = profile_config.config_path
        if not config_path or not config_path.exists():
            console.print(f"\n[red]Error: Config file not found at {config_path}[/red]")
            console.print("Run: [cyan]testmcpy setup[/cyan]")
            return

        try:
            with open(config_path, 'r') as f:
                config_data = yaml.safe_load(f) or {}

            # Update default
            config_data['default'] = set_default

            # Write back
            with open(config_path, 'w') as f:
                yaml.dump(config_data, f, default_flow_style=False, sort_keys=False)

            console.print(f"\n[green]✓ Default profile set to:[/green] {set_default}")
            console.print(f"[dim]Updated: {config_path}[/dim]\n")

        except Exception as e:
            console.print(f"\n[red]Error updating config: {e}[/red]\n")
        return

    # List profiles
    console.print("\n[bold cyan]MCP Profiles[/bold cyan]\n")

    profile_ids = profile_config.list_profiles()

    if not profile_ids:
        console.print("[dim]No profiles configured.[/dim]")
        console.print("\nTo configure profiles, create [cyan].mcp_services.yaml[/cyan]")
        console.print("See: [blue]https://github.com/preset-io/testmcpy/blob/main/docs/MCP_PROFILES.md[/blue]")
        return

    # Get default profile
    default_profile_id = profile_config.default_profile

    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("", style="dim", width=3)  # Default indicator
    table.add_column("Profile ID", style="cyan")
    table.add_column("Name", style="white")
    table.add_column("MCPs", justify="right")
    if show_details:
        table.add_column("First MCP URL")
        table.add_column("Auth Type")

    for profile_id in profile_ids:
        profile = load_profile(profile_id)
        if not profile:
            continue

        is_default = profile_id == default_profile_id
        status_icon = "●" if is_default else "○"
        mcp_count = len(profile.mcps) if profile.mcps else 0

        row = [
            status_icon,
            profile_id,
            profile.name or "-",
            str(mcp_count),
        ]

        if show_details and profile.mcps:
            first_mcp = profile.mcps[0]
            row.extend([
                first_mcp.mcp_url,
                first_mcp.auth.auth_type if first_mcp.auth else "none",
            ])

        table.add_row(*row)

    console.print(table)
    console.print(f"\n[dim]Total: {len(profile_ids)} profile(s)[/dim]")
    if default_profile_id:
        console.print(f"[dim]Default: {default_profile_id}[/dim]")

    console.print("\n[bold]Commands:[/bold]")
    console.print("  [cyan]testmcpy profiles --get-default[/cyan]        # Show default profile")
    console.print("  [cyan]testmcpy profiles --set-default <name>[/cyan] # Set default profile")
    console.print("  [cyan]testmcpy dash[/cyan]                         # Interactive management")


@app.command()
def status(
    profile: str = typer.Option(
        None,
        "--profile",
        "-p",
        help="MCP profile to check",
    ),
):
    """
    Show MCP connection status (CLI parity command).

    Quick command to check MCP service connectivity without launching the TUI.
    For real-time status monitoring, use: testmcpy dash --auto-refresh
    """
    from testmcpy.mcp_profiles import get_profile_config, list_available_profiles

    console.print("\n[bold cyan]MCP Connection Status[/bold cyan]\n")

    # Get profile configuration
    profile_config = get_profile_config()

    if not profile_config.has_profiles():
        console.print("[red]No MCP profiles configured.[/red]")
        console.print("\nRun: [cyan]testmcpy setup[/cyan]")
        return

    # Determine which profiles to check
    if profile:
        profiles_to_check = [profile_config.get_profile(profile)]
        if not profiles_to_check[0]:
            console.print(f"[red]Profile '{profile}' not found.[/red]")
            return
    else:
        profiles_to_check = list_available_profiles()

    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Profile", style="cyan")
    table.add_column("MCP Service")
    table.add_column("Status", justify="center")
    table.add_column("Tools", justify="right")

    async def check_profile_status(prof):
        """Check status of a single profile."""
        if not prof.mcps:
            return [(prof.profile_id, "N/A", "[red]No MCPs configured[/red]", "0")]

        results = []
        for mcp in prof.mcps:
            try:
                from testmcpy.src.mcp_client import MCPClient

                client = MCPClient(mcp.mcp_url)
                await client.initialize()
                tools = await client.list_tools()
                await client.close()

                status = "[green]🟢 Connected[/green]"
                tool_count = str(len(tools))
            except Exception as e:
                status = f"[red]🔴 Error[/red]"
                tool_count = "0"

            results.append((
                prof.profile_id,
                mcp.name,
                status,
                tool_count,
            ))

        return results

    # Check all profiles
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("[cyan]Checking connections...", total=len(profiles_to_check))

        for prof in profiles_to_check:
            try:
                results = asyncio.run(check_profile_status(prof))
                for row in results:
                    table.add_row(*row)
            except Exception as e:
                table.add_row(
                    prof.profile_id,
                    "Error",
                    f"[red]Failed: {str(e)[:30]}[/red]",
                    "0",
                )
            progress.advance(task)

    console.print(table)
    console.print("\nFor live monitoring: [cyan]testmcpy dash --auto-refresh[/cyan]")


@app.command(name="explore-cli")
def explore_cli(
    profile: str = typer.Option(
        None,
        "--profile",
        "-p",
        help="MCP profile to use",
    ),
    output: OutputFormat = typer.Option(
        OutputFormat.table,
        "--output",
        "-o",
        help="Output format",
    ),
):
    """
    List available MCP tools (CLI parity command).

    Quick command to browse MCP tools without launching the TUI.
    For interactive exploration, use: testmcpy explorer (or testmcpy dash)
    """
    from testmcpy.mcp_profiles import get_profile_config

    console.print("\n[bold cyan]MCP Tools Explorer[/bold cyan]\n")

    # Get profile configuration
    profile_config = get_profile_config()

    if not profile_config.has_profiles():
        console.print("[red]No MCP profiles configured.[/red]")
        console.print("\nRun: [cyan]testmcpy setup[/cyan]")
        return

    # Get profile
    prof = profile_config.get_profile(profile)
    if not prof:
        console.print(f"[red]Profile '{profile}' not found.[/red]")
        return

    if not prof.mcps:
        console.print("[red]No MCP services configured in profile.[/red]")
        return

    async def fetch_tools():
        """Fetch tools from MCP service."""
        mcp = prof.mcps[0]
        try:
            from testmcpy.src.mcp_client import MCPClient

            with console.status(f"[dim]Connecting to {mcp.name}...[/dim]"):
                client = MCPClient(mcp.mcp_url)
                await client.initialize()
                tools = await client.list_tools()
                await client.close()

            return tools
        except Exception as e:
            console.print(f"[red]Error connecting to MCP:[/red] {e}")
            return []

    tools = asyncio.run(fetch_tools())

    if not tools:
        console.print("[yellow]No tools found.[/yellow]")
        return

    # Output based on format
    if output == OutputFormat.table:
        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("#", style="dim", width=4)
        table.add_column("Tool Name", style="cyan")
        table.add_column("Description")

        for i, tool in enumerate(tools, 1):
            table.add_row(
                str(i),
                tool.get("name", "unknown"),
                tool.get("description", "")[:80] + ("..." if len(tool.get("description", "")) > 80 else ""),
            )

        console.print(table)
        console.print(f"\n[dim]Total: {len(tools)} tool(s)[/dim]")

    elif output == OutputFormat.json:
        import json

        console.print(json.dumps(tools, indent=2))

    elif output == OutputFormat.yaml:
        import yaml

        console.print(yaml.dump(tools, default_flow_style=False))

    console.print("\nFor interactive exploration: [cyan]testmcpy explorer[/cyan]")


@app.command()
def chat(
    profile: str | None = typer.Option(None, "--profile", "-p", help="MCP profile to use"),
    provider: str | None = typer.Option(None, "--provider", help="LLM provider (anthropic, openai, ollama, etc.)"),
    model: str | None = typer.Option(None, "--model", "-m", help="Model name"),
    mcp_url: str | None = typer.Option(None, "--mcp-url", help="MCP service URL"),
):
    """
    Launch interactive chat interface with tool calling visualization.

    This opens a beautiful terminal UI for chatting with an LLM that has
    access to MCP tools. All tool calls are visualized in real-time, and
    you can save conversations as tests or evaluate them with evaluators.

    Key bindings:
    - Enter: Send message
    - Ctrl+E: Evaluate conversation
    - Ctrl+S: Save as test
    - Ctrl+C: Cancel/Exit

    Examples:
        testmcpy chat                          # Use default config
        testmcpy chat --profile prod           # Use specific MCP profile
        testmcpy chat --model claude-opus-4    # Use specific model
    """
    try:
        # Check if textual is installed
        try:
            from testmcpy.tui.app import launch_chat
        except ImportError:
            console.print(
                Panel(
                    "[red]Error:[/red] Textual not installed\n\n"
                    "The chat interface requires Textual. Install it with:\n"
                    "[cyan]pip install textual textual-dev[/cyan]",
                    title="[red]Missing Dependency[/red]",
                    border_style="red",
                )
            )
            raise typer.Exit(1)

        # Launch the chat interface
        launch_chat(
            profile=profile,
            provider=provider,
            model=model,
            mcp_url=mcp_url,
        )

    except KeyboardInterrupt:
        console.print("\n[dim]Chat session ended.[/dim]")
    except Exception as e:
        console.print(
            Panel(
                f"[red]Error launching chat:[/red]\n{str(e)}",
                title="[red]Error[/red]",
                border_style="red",
            )
        )
        raise typer.Exit(1)


@app.command()
def generate(
    profile: str | None = typer.Option(
        None,
        "--profile",
        "-p",
        help="MCP service profile from .mcp_services.yaml",
    ),
    mcp_url: str | None = typer.Option(
        None,
        "--mcp-url",
        help="MCP service URL (overrides profile)",
    ),
    output_dir: Path = typer.Option(
        Path("tests/generated"),
        "--output",
        "-o",
        help="Output directory for generated tests",
    ),
    test_prefix: str = typer.Option(
        "test_",
        "--prefix",
        help="Prefix for generated test files",
    ),
    include_examples: bool = typer.Option(
        True,
        "--examples/--no-examples",
        help="Include example test cases for each tool",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Show detailed progress",
    ),
):
    """
    Generate test suite for an MCP service.

    This command connects to an MCP service, discovers all available tools,
    and generates comprehensive test YAML files for each tool.

    Examples:
        testmcpy generate --profile my-profile
        testmcpy generate --mcp-url http://localhost:5008/mcp
        testmcpy generate --profile prod --output tests/prod-tests
    """
    console.print(
        Panel.fit(
            "[bold cyan]Test Suite Generator[/bold cyan]\n"
            "[dim]Discovering MCP tools and generating tests...[/dim]",
            border_style="cyan",
        )
    )

    # Load config with profile if specified
    if profile:
        from testmcpy.config import Config
        cfg = Config(profile=profile)
        effective_mcp_url = mcp_url or cfg.get_mcp_url()
        mcp_server = cfg.get_default_mcp_server()
        auth_config = mcp_server.auth.to_dict() if mcp_server else None
    else:
        effective_mcp_url = mcp_url or DEFAULT_MCP_URL
        auth_config = None

    if not effective_mcp_url:
        console.print("[red]Error:[/red] No MCP URL provided. Use --mcp-url or --profile")
        console.print("\nExamples:")
        console.print("  testmcpy generate --mcp-url http://localhost:5008/mcp")
        console.print("  testmcpy generate --profile my-profile")
        raise typer.Exit(1)

    async def run_generation():
        from testmcpy.src.mcp_client import MCPClient

        tools_discovered = 0
        tests_generated = 0
        errors = []

        try:
            # Step 1: Connect to MCP service
            if verbose:
                console.print(f"\n[bold]Step 1:[/bold] Connecting to MCP service")
                console.print(f"  URL: {effective_mcp_url}")
                if auth_config:
                    console.print(f"  Auth: {auth_config.get('type', 'none')}")

            with console.status("[cyan]Connecting to MCP service...[/cyan]"):
                client = MCPClient(base_url=effective_mcp_url, auth=auth_config)
                await client.initialize()

            if verbose:
                console.print("[green]✓[/green] Connected successfully\n")
            else:
                console.print("[green]✓[/green] Connected to MCP service")

            # Step 2: Discover tools
            if verbose:
                console.print("[bold]Step 2:[/bold] Discovering available tools")

            with console.status("[cyan]Listing tools...[/cyan]"):
                tools = await client.list_tools()

            tools_discovered = len(tools)

            if tools_discovered == 0:
                console.print("[yellow]⚠[/yellow] No tools found in MCP service")
                await client.close()
                return

            if verbose:
                console.print(f"[green]✓[/green] Found {tools_discovered} tools\n")
                for tool in tools:
                    console.print(f"  • {tool.name}")
                console.print()
            else:
                console.print(f"[green]✓[/green] Found {tools_discovered} tools")

            # Step 3: Create output directory
            if verbose:
                console.print(f"[bold]Step 3:[/bold] Creating output directory")
                console.print(f"  Path: {output_dir}")

            output_dir.mkdir(parents=True, exist_ok=True)

            if verbose:
                console.print(f"[green]✓[/green] Output directory ready\n")

            # Step 4: Generate test files
            if verbose:
                console.print(f"[bold]Step 4:[/bold] Generating test files")
            else:
                console.print("\n[cyan]Generating tests...[/cyan]")

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                task = progress.add_task(
                    f"Generating tests for {tools_discovered} tools...",
                    total=tools_discovered
                )

                for tool in tools:
                    try:
                        # Generate test YAML for this tool
                        test_content = _generate_tool_test(
                            tool,
                            effective_mcp_url,
                            profile,
                            auth_config,
                            include_examples,
                            output_dir
                        )

                        # Write to file
                        safe_name = tool.name.replace("/", "_").replace(":", "_")
                        test_file = output_dir / f"{test_prefix}{safe_name}.yaml"
                        test_file.write_text(test_content)

                        tests_generated += 1

                        if verbose:
                            console.print(f"  [green]✓[/green] {test_file.name}")

                    except Exception as e:
                        error_msg = f"Failed to generate test for {tool.name}: {str(e)}"
                        errors.append(error_msg)
                        if verbose:
                            console.print(f"  [red]✗[/red] {tool.name}: {str(e)}")

                    progress.update(task, advance=1)

            # Close MCP connection
            await client.close()

            # Step 5: Summary
            console.print("\n" + "=" * 50)
            console.print("[bold green]Test Generation Complete![/bold green]\n")

            table = Table(show_header=False, box=None)
            table.add_column("Label", style="dim")
            table.add_column("Value", style="bold")

            table.add_row("Tools discovered:", str(tools_discovered))
            table.add_row("Tests generated:", f"[green]{tests_generated}[/green]")
            if errors:
                table.add_row("Errors:", f"[red]{len(errors)}[/red]")
            table.add_row("Output directory:", str(output_dir))

            console.print(table)

            if errors:
                console.print("\n[bold red]Errors:[/bold red]")
                for error in errors:
                    console.print(f"  • {error}")

            console.print("\n[bold]Next steps:[/bold]")
            console.print(f"  1. Review generated tests: [cyan]ls {output_dir}[/cyan]")
            console.print(f"  2. Edit tests as needed to match your requirements")
            console.print(f"  3. Run tests: [cyan]testmcpy run {output_dir}[/cyan]")
            console.print()

        except Exception as e:
            console.print(f"\n[red]Error:[/red] {str(e)}")
            if verbose:
                import traceback
                console.print("\n[dim]Traceback:[/dim]")
                console.print(traceback.format_exc())
            raise typer.Exit(1)

    asyncio.run(run_generation())


def _generate_tool_test(
    tool,
    mcp_url: str,
    profile: str | None,
    auth_config: dict | None,
    include_examples: bool,
    output_dir: Path = Path("tests/generated"),
) -> str:
    """Generate a test YAML file for a single tool."""

    # Extract required parameters from schema
    required_params = []
    optional_params = []

    schema = tool.input_schema
    if schema and "properties" in schema:
        required_list = schema.get("required", [])
        for param_name, param_info in schema["properties"].items():
            param_type = param_info.get("type", "string")
            param_desc = param_info.get("description", "")

            param_dict = {
                "name": param_name,
                "type": param_type,
                "description": param_desc,
            }

            if param_name in required_list:
                required_params.append(param_dict)
            else:
                optional_params.append(param_dict)

    # Start building the YAML content
    lines = []
    lines.append('version: "1.0"')
    lines.append(f'name: "Test Suite for {tool.name}"')
    lines.append(f'description: "Auto-generated tests for the {tool.name} MCP tool"')
    lines.append('')
    lines.append(f'# Tool: {tool.name}')
    if tool.description:
        lines.append(f'# Description: {tool.description}')
    lines.append(f'# Generated by: testmcpy generate')
    lines.append('')

    # Add connection info comment
    if profile:
        lines.append(f'# Profile: {profile}')
    lines.append(f'# MCP URL: {mcp_url}')
    if auth_config:
        lines.append(f'# Auth Type: {auth_config.get("type", "none")}')
    lines.append('')

    lines.append('tests:')

    # Test 1: Basic tool discovery
    lines.append('  # Test 1: Verify tool is available')
    lines.append(f'  - name: "test_{tool.name}_exists"')
    lines.append(f'    prompt: "Use the {tool.name} tool"')
    lines.append('    evaluators:')
    lines.append('      - name: "was_mcp_tool_called"')
    lines.append('        args:')
    lines.append(f'          tool_name: "{tool.name}"')
    lines.append('      - name: "execution_successful"')
    lines.append('')

    # Test 2: Required parameters
    if required_params:
        lines.append('  # Test 2: Verify required parameters are provided')
        lines.append(f'  - name: "test_{tool.name}_required_params"')

        # Build a prompt that mentions the required parameters
        param_mentions = []
        for param in required_params:
            if param['type'] == 'integer':
                param_mentions.append(f"{param['name']} 123")
            elif param['type'] == 'boolean':
                param_mentions.append(f"{param['name']} true")
            elif param['type'] == 'array':
                param_mentions.append(f"{param['name']} list")
            else:
                param_mentions.append(f"{param['name']} 'example'")

        prompt_params = ", ".join(param_mentions)
        lines.append(f'    prompt: "Call {tool.name} with {prompt_params}"')
        lines.append('    evaluators:')
        lines.append('      - name: "was_mcp_tool_called"')
        lines.append('        args:')
        lines.append(f'          tool_name: "{tool.name}"')

        # Check each required parameter was provided
        for param in required_params:
            lines.append('      - name: "tool_called_with_parameter"')
            lines.append('        args:')
            lines.append(f'          tool_name: "{tool.name}"')
            lines.append(f'          parameter_name: "{param["name"]}"')

        lines.append('      - name: "execution_successful"')
        lines.append('')

    # Test 3: Example test cases (if requested)
    if include_examples:
        lines.append(f'  # Test 3: Example usage of {tool.name}')
        lines.append(f'  - name: "test_{tool.name}_example"')
        lines.append(f'    prompt: "{_generate_example_prompt(tool, required_params, optional_params)}"')
        lines.append('    evaluators:')
        lines.append('      - name: "was_mcp_tool_called"')
        lines.append('        args:')
        lines.append(f'          tool_name: "{tool.name}"')
        lines.append('      - name: "execution_successful"')
        lines.append('      - name: "within_time_limit"')
        lines.append('        args:')
        lines.append('          max_seconds: 30')
        lines.append('')

    # Add parameter reference comment
    if required_params or optional_params:
        lines.append('# Parameter Reference:')
        if required_params:
            lines.append('# Required Parameters:')
            for param in required_params:
                lines.append(f'#   - {param["name"]} ({param["type"]}): {param.get("description", "No description")}')
        if optional_params:
            lines.append('# Optional Parameters:')
            for param in optional_params:
                lines.append(f'#   - {param["name"]} ({param["type"]}): {param.get("description", "No description")}')
        lines.append('')

    lines.append('# How to run:')
    if profile:
        lines.append(f'#   testmcpy run {output_dir / f"test_{tool.name}.yaml"} --profile {profile}')
    else:
        lines.append(f'#   testmcpy run {output_dir / f"test_{tool.name}.yaml"} --mcp-url {mcp_url}')
    lines.append('#')
    lines.append('# Tips:')
    lines.append('#   - Customize prompts to match your specific use cases')
    lines.append('#   - Add more evaluators to validate specific behaviors')
    lines.append('#   - See docs/EVALUATOR_REFERENCE.md for all available evaluators')

    return '\n'.join(lines)


def _generate_example_prompt(tool, required_params: list, optional_params: list) -> str:
    """Generate a natural language prompt for example test."""

    if tool.description:
        # Use the tool description to create a natural prompt
        base = tool.description
        if base.endswith('.'):
            base = base[:-1]
        return f"{base} using {tool.name}"

    # Fallback: generic prompt with parameters
    if required_params:
        param_names = [p['name'] for p in required_params[:2]]  # Take first 2 params
        if len(required_params) > 2:
            return f"Use {tool.name} with {', '.join(param_names)}, and other required parameters"
        else:
            return f"Use {tool.name} with {' and '.join(param_names)}"

    return f"Execute the {tool.name} tool"


@app.command()
def doctor():
    """
    Run health checks to diagnose installation issues.

    This command checks Python version, dependencies, configuration,
    and MCP connectivity to help identify and resolve issues.
    """
    console.print(
        Panel.fit(
            "[bold cyan]testmcpy Health Check[/bold cyan]\n"
            "[dim]Diagnosing installation and configuration...[/dim]",
            border_style="cyan",
        )
    )

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
        issues_found.append(
            f"Python version {version_str} is too old. Requires Python 3.9 or higher."
        )
    else:
        console.print(f"[yellow]⚠[/yellow] Python {version_str} (not tested, may not work)")
        warnings_found.append(
            f"Python {version_str} is newer than 3.12 and has not been tested with testmcpy."
        )

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

        console.print("[green]✓[/green] fastapi, uvicorn - Web UI available")
    except ImportError:
        console.print(
            "[dim]✗[/dim] fastapi, uvicorn - Install with: pip install 'testmcpy[server]'",
            markup=False,
        )

    # SDK dependency
    console.print("[dim]Claude Agent SDK:[/dim]")
    try:
        import claude_agent_sdk

        console.print("[green]✓[/green] claude-agent-sdk - SDK provider available")
    except ImportError:
        console.print(
            "[dim]✗[/dim] claude-agent-sdk - Install with: pip install 'testmcpy[sdk]'",
            markup=False,
        )

    # 4. Check configuration
    console.print("\n[bold]4. Configuration[/bold]")

    cfg = get_config()

    # Check MCP URL
    mcp_url = cfg.get_mcp_url()
    if mcp_url and mcp_url != "http://localhost:5008/mcp/":
        console.print(f"[green]✓[/green] MCP URL configured: {mcp_url}")
    else:
        console.print("[yellow]⚠[/yellow] MCP URL not configured (using default)")
        warnings_found.append("MCP URL not configured. Run: testmcpy setup")

    # Check authentication
    has_dynamic_jwt = all(
        [cfg.get("MCP_AUTH_API_URL"), cfg.get("MCP_AUTH_API_TOKEN"), cfg.get("MCP_AUTH_API_SECRET")]
    )
    has_static_token = cfg.get("MCP_AUTH_TOKEN") or cfg.get("SUPERSET_MCP_TOKEN")

    if has_dynamic_jwt:
        console.print("[green]✓[/green] MCP Authentication: Dynamic JWT configured")
    elif has_static_token:
        console.print("[green]✓[/green] MCP Authentication: Static token configured")
    else:
        console.print("[yellow]⚠[/yellow] MCP Authentication: Not configured")
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
                console.print("[green]✓[/green] Anthropic API key configured")
            else:
                console.print("[red]✗[/red] Anthropic API key missing")
                issues_found.append(
                    "Anthropic API key not configured. Set ANTHROPIC_API_KEY in ~/.testmcpy"
                )
        elif provider == "openai":
            api_key = cfg.get("OPENAI_API_KEY")
            if api_key:
                console.print("[green]✓[/green] OpenAI API key configured")
            else:
                console.print("[red]✗[/red] OpenAI API key missing")
                issues_found.append(
                    "OpenAI API key not configured. Set OPENAI_API_KEY in ~/.testmcpy"
                )
        elif provider == "ollama":
            base_url = cfg.get("OLLAMA_BASE_URL") or "http://localhost:11434"
            console.print(f"[dim]  Ollama URL: {base_url}[/dim]")
    else:
        console.print("[yellow]⚠[/yellow] LLM Provider: Not configured")
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

                console.print("[green]✓[/green] MCP service reachable")
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
    if hasattr(sys, "real_prefix") or (
        hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix
    ):
        console.print("[green]✓[/green] Running in virtual environment")
        console.print(f"[dim]  Location: {sys.prefix}[/dim]")
    else:
        console.print("[yellow]⚠[/yellow] Not running in virtual environment")
        warnings_found.append(
            "Not using a virtual environment. Consider using: python3 -m venv venv"
        )

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
    console.print("\n" + "=" * 50)
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
            console.print(
                "• Create virtual environment: python3 -m venv venv && source venv/bin/activate"
            )

    console.print()


@app.command()
def smoke_test(
    profile: str | None = typer.Option(
        None,
        "--profile",
        "-p",
        help="MCP service profile from .mcp_services.yaml",
    ),
    mcp_url: str | None = typer.Option(
        None,
        "--mcp-url",
        help="MCP service URL (overrides profile)",
    ),
    test_all_tools: bool = typer.Option(
        True,
        "--test-all/--basic-only",
        help="Test all tools or just basic operations",
    ),
    max_tools: int = typer.Option(
        10,
        "--max-tools",
        help="Maximum number of tools to test",
    ),
    output_format: str = typer.Option(
        "table",
        "--format",
        "-f",
        help="Output format: table, json, or summary",
    ),
    save_report: str | None = typer.Option(
        None,
        "--save",
        "-s",
        help="Save detailed report to file (JSON format)",
    ),
):
    """
    Run smoke tests on an MCP server.

    Performs basic health checks and tests all available tools with reasonable
    parameters to verify the MCP server is working correctly.

    Tests include:
    - Connection check
    - List tools
    - Call each tool with reasonable default parameters

    Examples:
        testmcpy smoke-test --profile prod
        testmcpy smoke-test --mcp-url http://localhost:5008/mcp
        testmcpy smoke-test --profile sandbox --basic-only
        testmcpy smoke-test --profile prod --save smoke-test-report.json
    """
    console.print(
        Panel.fit(
            "[bold cyan]MCP Server Smoke Test[/bold cyan]\n"
            "[dim]Running health checks and testing tools...[/dim]",
            border_style="cyan",
        )
    )

    # Load config with profile if specified
    if profile:
        from testmcpy.config import Config
        cfg = Config(profile=profile)
        effective_mcp_url = mcp_url or cfg.get_mcp_url()
        mcp_server = cfg.get_default_mcp_server()
        auth_config = mcp_server.auth.to_dict() if mcp_server and mcp_server.auth else None
    else:
        effective_mcp_url = mcp_url or DEFAULT_MCP_URL
        auth_config = None

    if not effective_mcp_url:
        console.print("[red]Error:[/red] No MCP URL provided. Use --mcp-url or --profile")
        console.print("\nExamples:")
        console.print("  testmcpy smoke-test --mcp-url http://localhost:5008/mcp")
        console.print("  testmcpy smoke-test --profile my-profile")
        raise typer.Exit(1)

    async def run_tests():
        from testmcpy.smoke_test import run_smoke_test

        console.print(f"\n[bold]Server:[/bold] {effective_mcp_url}")
        if auth_config:
            console.print(f"[bold]Auth:[/bold] {auth_config.get('type', 'none')}")
        console.print()

        with console.status("[cyan]Running smoke tests...[/cyan]"):
            report = await run_smoke_test(
                mcp_url=effective_mcp_url,
                auth_config=auth_config,
                test_all_tools=test_all_tools,
                max_tools_to_test=max_tools,
            )

        # Display results based on format
        if output_format == "json":
            console.print(json.dumps(report.to_dict(), indent=2))
        elif output_format == "summary":
            _print_smoke_test_summary(report)
        else:  # table
            _print_smoke_test_table(report)

        # Save report if requested
        if save_report:
            with open(save_report, 'w') as f:
                json.dump(report.to_dict(), f, indent=2)
            console.print(f"\n[green]✓[/green] Report saved to: {save_report}")

        # Return exit code based on success
        if report.failed > 0:
            raise typer.Exit(1)

    asyncio.run(run_tests())


def _print_smoke_test_summary(report):
    """Print summary of smoke test results."""
    from rich.table import Table

    # Overall status
    status_color = "green" if report.failed == 0 else "red" if report.passed == 0 else "yellow"
    status_icon = "✓" if report.failed == 0 else "✗" if report.passed == 0 else "⚠"

    console.print(f"\n[bold {status_color}]{status_icon} Smoke Test Results[/bold {status_color}]")
    console.print(f"[dim]Server: {report.server_url}[/dim]")
    console.print(f"[dim]Completed: {report.timestamp}[/dim]")
    console.print()

    # Stats
    console.print(f"[bold]Total Tests:[/bold] {report.total_tests}")
    console.print(f"[bold green]Passed:[/bold green] {report.passed}")
    console.print(f"[bold red]Failed:[/bold red] {report.failed}")
    console.print(f"[bold]Success Rate:[/bold] {report.success_rate:.1f}%")
    console.print(f"[bold]Duration:[/bold] {report.duration_ms:.0f}ms")

    # Failed tests
    if report.failed > 0:
        console.print("\n[bold red]Failed Tests:[/bold red]")
        for result in report.results:
            if not result.success:
                console.print(f"  • {result.test_name}")
                if result.error_message:
                    console.print(f"    [dim]{result.error_message}[/dim]")


def _print_smoke_test_table(report):
    """Print detailed table of smoke test results."""
    from rich.table import Table

    # Overall status panel
    status_color = "green" if report.failed == 0 else "red" if report.passed == 0 else "yellow"
    status_icon = "✓" if report.failed == 0 else "✗" if report.passed == 0 else "⚠"

    console.print(
        Panel.fit(
            f"[bold {status_color}]{status_icon} Smoke Test Results[/bold {status_color}]\n"
            f"[dim]Server: {report.server_url}[/dim]\n"
            f"Tests: {report.passed}/{report.total_tests} passed | "
            f"Success Rate: {report.success_rate:.1f}% | "
            f"Duration: {report.duration_ms:.0f}ms",
            border_style=status_color,
        )
    )

    # Results table
    table = Table(show_header=True, header_style="bold cyan", show_lines=True)
    table.add_column("Status", style="bold", width=8)
    table.add_column("Test Name", style="cyan")
    table.add_column("Duration", justify="right")
    table.add_column("Details")

    for result in report.results:
        status = "[green]✓ PASS[/green]" if result.success else "[red]✗ FAIL[/red]"
        duration = f"{result.duration_ms:.0f}ms"

        # Details column
        if result.success and result.details:
            if "tool_count" in result.details:
                details = f"{result.details['tool_count']} tools available"
            elif "tool" in result.details:
                details = f"Called with {len(result.details.get('parameters', {}))} params"
            else:
                details = "Success"
        elif not result.success:
            details = result.error_message or "Failed"
        else:
            details = "Success"

        table.add_row(status, result.test_name, duration, details)

    console.print()
    console.print(table)


if __name__ == "__main__":
    app()
