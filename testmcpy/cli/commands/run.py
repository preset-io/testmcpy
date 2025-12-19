"""Test execution commands: research, run, generate, smoke-test."""

import asyncio
import json
from pathlib import Path
from typing import Optional

import typer
import yaml
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.syntax import Syntax
from rich.table import Table

from testmcpy.cli.app import (
    DEFAULT_MCP_URL,
    DEFAULT_MODEL,
    DEFAULT_PROVIDER,
    ModelProvider,
    OutputFormat,
    app,
    console,
)


@app.command()
def research(
    model: str = typer.Option(DEFAULT_MODEL, "--model", "-m", help="Model to test"),
    provider: ModelProvider = typer.Option(
        DEFAULT_PROVIDER, "--provider", "-p", help="Model provider"
    ),
    mcp_url: Optional[str] = typer.Option(
        None, "--mcp-url", help="MCP service URL (overrides profile)"
    ),
    profile: Optional[str] = typer.Option(
        None, "--profile", help="MCP service profile from .mcp_services.yaml"
    ),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output file for results"),
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
    mcp_url: Optional[str] = typer.Option(
        None, "--mcp-url", help="MCP service URL (overrides profile)"
    ),
    profile: Optional[str] = typer.Option(
        None, "--profile", help="MCP service profile from .mcp_services.yaml"
    ),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output report file"),
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
        from testmcpy.server.helpers.mcp_config import load_mcp_yaml
        from testmcpy.server.state import get_or_create_mcp_client
        from testmcpy.src.test_runner import TestCase, TestRunner

        # Get authenticated MCP client
        mcp_client = None
        effective_profile = profile
        if not effective_profile:
            # Use default profile from config
            mcp_config = load_mcp_yaml()
            effective_profile = mcp_config.get("default")

        if effective_profile:
            try:
                mcp_client = await get_or_create_mcp_client(effective_profile)
            except Exception as e:
                console.print(f"[yellow]Warning: Could not load MCP profile: {e}[/yellow]")

        runner = TestRunner(
            model=model,
            provider=provider.value,
            mcp_url=effective_mcp_url,
            mcp_client=mcp_client,
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
            # Use rglob for recursive search in subdirectories
            # Support both .yaml and .yml extensions, plus .json
            for pattern in ["*.yaml", "*.yml", "*.json"]:
                for file in test_path.rglob(pattern):
                    with open(file) as f:
                        if file.suffix == ".json":
                            data = json.load(f)
                        else:
                            data = yaml.safe_load(f)
                        if data is None:
                            continue
                        if "tests" in data:
                            for test_data in data["tests"]:
                                test_cases.append(TestCase.from_dict(test_data))
                        else:
                            # Handle single test case files
                            test_cases.append(TestCase.from_dict(data))

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
def generate(
    profile: Optional[str] = typer.Option(
        None,
        "--profile",
        "-p",
        help="MCP service profile from .mcp_services.yaml",
    ),
    mcp_url: Optional[str] = typer.Option(
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
                console.print("\n[bold]Step 1:[/bold] Connecting to MCP service")
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
                console.print("[bold]Step 3:[/bold] Creating output directory")
                console.print(f"  Path: {output_dir}")

            output_dir.mkdir(parents=True, exist_ok=True)

            if verbose:
                console.print("[green]✓[/green] Output directory ready\n")

            # Step 4: Generate test files
            if verbose:
                console.print("[bold]Step 4:[/bold] Generating test files")
            else:
                console.print("\n[cyan]Generating tests...[/cyan]")

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                task = progress.add_task(
                    f"Generating tests for {tools_discovered} tools...", total=tools_discovered
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
                            output_dir,
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
            console.print("  2. Edit tests as needed to match your requirements")
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
    profile: Optional[str],
    auth_config: Optional[dict],
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
    lines.append("")
    lines.append(f"# Tool: {tool.name}")
    if tool.description:
        lines.append(f"# Description: {tool.description}")
    lines.append("# Generated by: testmcpy generate")
    lines.append("")

    # Add connection info comment
    if profile:
        lines.append(f"# Profile: {profile}")
    lines.append(f"# MCP URL: {mcp_url}")
    if auth_config:
        lines.append(f"# Auth Type: {auth_config.get('type', 'none')}")
    lines.append("")

    lines.append("tests:")

    # Test 1: Basic tool discovery
    lines.append("  # Test 1: Verify tool is available")
    lines.append(f'  - name: "test_{tool.name}_exists"')
    lines.append(f'    prompt: "Use the {tool.name} tool"')
    lines.append("    evaluators:")
    lines.append('      - name: "was_mcp_tool_called"')
    lines.append("        args:")
    lines.append(f'          tool_name: "{tool.name}"')
    lines.append('      - name: "execution_successful"')
    lines.append("")

    # Test 2: Required parameters
    if required_params:
        lines.append("  # Test 2: Verify required parameters are provided")
        lines.append(f'  - name: "test_{tool.name}_required_params"')

        # Build a prompt that mentions the required parameters
        param_mentions = []
        for param in required_params:
            if param["type"] == "integer":
                param_mentions.append(f"{param['name']} 123")
            elif param["type"] == "boolean":
                param_mentions.append(f"{param['name']} true")
            elif param["type"] == "array":
                param_mentions.append(f"{param['name']} list")
            else:
                param_mentions.append(f"{param['name']} 'example'")

        prompt_params = ", ".join(param_mentions)
        lines.append(f'    prompt: "Call {tool.name} with {prompt_params}"')
        lines.append("    evaluators:")
        lines.append('      - name: "was_mcp_tool_called"')
        lines.append("        args:")
        lines.append(f'          tool_name: "{tool.name}"')

        # Check each required parameter was provided
        for param in required_params:
            lines.append('      - name: "tool_called_with_parameter"')
            lines.append("        args:")
            lines.append(f'          tool_name: "{tool.name}"')
            lines.append(f'          parameter_name: "{param["name"]}"')

        lines.append('      - name: "execution_successful"')
        lines.append("")

    # Test 3: Example test cases (if requested)
    if include_examples:
        lines.append(f"  # Test 3: Example usage of {tool.name}")
        lines.append(f'  - name: "test_{tool.name}_example"')
        lines.append(
            f'    prompt: "{_generate_example_prompt(tool, required_params, optional_params)}"'
        )
        lines.append("    evaluators:")
        lines.append('      - name: "was_mcp_tool_called"')
        lines.append("        args:")
        lines.append(f'          tool_name: "{tool.name}"')
        lines.append('      - name: "execution_successful"')
        lines.append('      - name: "within_time_limit"')
        lines.append("        args:")
        lines.append("          max_seconds: 30")
        lines.append("")

    # Add parameter reference comment
    if required_params or optional_params:
        lines.append("# Parameter Reference:")
        if required_params:
            lines.append("# Required Parameters:")
            for param in required_params:
                lines.append(
                    f"#   - {param['name']} ({param['type']}): {param.get('description', 'No description')}"
                )
        if optional_params:
            lines.append("# Optional Parameters:")
            for param in optional_params:
                lines.append(
                    f"#   - {param['name']} ({param['type']}): {param.get('description', 'No description')}"
                )
        lines.append("")

    lines.append("# How to run:")
    if profile:
        lines.append(
            f"#   testmcpy run {output_dir / f'test_{tool.name}.yaml'} --profile {profile}"
        )
    else:
        lines.append(
            f"#   testmcpy run {output_dir / f'test_{tool.name}.yaml'} --mcp-url {mcp_url}"
        )
    lines.append("#")
    lines.append("# Tips:")
    lines.append("#   - Customize prompts to match your specific use cases")
    lines.append("#   - Add more evaluators to validate specific behaviors")
    lines.append("#   - See docs/EVALUATOR_REFERENCE.md for all available evaluators")

    return "\n".join(lines)


def _generate_example_prompt(tool, required_params: list, optional_params: list) -> str:
    """Generate a natural language prompt for example test."""

    if tool.description:
        # Use the tool description to create a natural prompt
        base = tool.description
        if base.endswith("."):
            base = base[:-1]
        return f"{base} using {tool.name}"

    # Fallback: generic prompt with parameters
    if required_params:
        param_names = [p["name"] for p in required_params[:2]]  # Take first 2 params
        if len(required_params) > 2:
            return f"Use {tool.name} with {', '.join(param_names)}, and other required parameters"
        else:
            return f"Use {tool.name} with {' and '.join(param_names)}"

    return f"Execute the {tool.name} tool"


@app.command()
def smoke_test(
    profile: Optional[str] = typer.Option(
        None,
        "--profile",
        "-p",
        help="MCP service profile from .mcp_services.yaml",
    ),
    mcp_url: Optional[str] = typer.Option(
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
    save_report: Optional[str] = typer.Option(
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
            with open(save_report, "w") as f:
                json.dump(report.to_dict(), f, indent=2)
            console.print(f"\n[green]✓[/green] Report saved to: {save_report}")

        # Return exit code based on success
        if report.failed > 0:
            raise typer.Exit(1)

    asyncio.run(run_tests())


def _print_smoke_test_summary(report):
    """Print summary of smoke test results."""
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
