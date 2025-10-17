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

# Get config instance
config = get_config()
DEFAULT_MODEL = config.default_model or "claude-3-5-haiku-20241022"
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
        console.print(f"[dim]Current: {current_mcp_url} (from {source})[/dim]")
        mcp_url = console.input(f"MCP Service URL [{current_mcp_url}]: ").strip() or current_mcp_url
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
        current_api_url = current_config.get("MCP_AUTH_API_URL") or "https://api.app.preset.io/v1/auth/"
        current_api_token = current_config.get("MCP_AUTH_API_TOKEN")
        current_api_secret = current_config.get("MCP_AUTH_API_SECRET")

        if current_api_url != "https://api.app.preset.io/v1/auth/":
            api_url = console.input(f"Auth API URL [{current_api_url}]: ").strip() or current_api_url
        else:
            api_url = console.input("Auth API URL [https://api.app.preset.io/v1/auth/]: ").strip()

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

        current_model = current_config.default_model or "claude-3-5-haiku-20241022"
        model = console.input(f"Model [{current_model}]: ").strip() or current_model
        config_lines.append(f"DEFAULT_MODEL={model}")
        config_lines.append(f"ANTHROPIC_MODEL={model}")

        config_lines.append("")

        current_api_key = current_config.get("ANTHROPIC_API_KEY")
        if current_api_key:
            masked = f"{current_api_key[:8]}...{current_api_key[-4:]}"
            console.print(f"[dim]Current API Key: {masked}[/dim]")
            api_key = console.input(f"Anthropic API Key [press Enter to keep current]: ").strip() or current_api_key
        else:
            api_key = console.input("Anthropic API Key: ").strip()

        if api_key:
            config_lines.append(f"ANTHROPIC_API_KEY={api_key}")
        else:
            config_lines.append("# ANTHROPIC_API_KEY=sk-ant-...")

    elif provider_choice == "2":
        config_lines.append("DEFAULT_PROVIDER=ollama")

        current_model = current_config.default_model or "llama3.1:8b"
        model = console.input(f"Model [{current_model}]: ").strip() or current_model
        config_lines.append(f"DEFAULT_MODEL={model}")

        config_lines.append("")

        current_base_url = current_config.get("OLLAMA_BASE_URL") or "http://localhost:11434"
        base_url = console.input(f"Ollama Base URL [{current_base_url}]: ").strip() or current_base_url
        config_lines.append(f"OLLAMA_BASE_URL={base_url}")

    elif provider_choice == "3":
        config_lines.append("DEFAULT_PROVIDER=openai")

        current_model = current_config.default_model or "gpt-4-turbo"
        model = console.input(f"Model [{current_model}]: ").strip() or current_model
        config_lines.append(f"DEFAULT_MODEL={model}")

        config_lines.append("")

        current_api_key = current_config.get("OPENAI_API_KEY")
        if current_api_key:
            masked = f"{current_api_key[:8]}...{current_api_key[-4:]}"
            console.print(f"[dim]Current API Key: {masked}[/dim]")
            api_key = console.input(f"OpenAI API Key [press Enter to keep current]: ").strip() or current_api_key
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


if __name__ == "__main__":
    app()