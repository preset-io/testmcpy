"""Metamorphic relation testing CLI command."""

import asyncio
from pathlib import Path
from typing import Optional

import typer
import yaml
from rich.panel import Panel
from rich.table import Table

from testmcpy.cli.app import (
    DEFAULT_MCP_URL,
    DEFAULT_MODEL,
    DEFAULT_PROVIDER,
    ModelProvider,
    app,
    console,
)


@app.command()
def metamorphic(
    test_path: Path = typer.Argument(..., help="Path to test YAML file"),
    relations: Optional[str] = typer.Option(
        None,
        "--relations",
        "-r",
        help="Comma-separated relation names (default: all). "
        "Available: idempotency, tool_selection_stability, parameter_preservation",
    ),
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
    output: Optional[Path] = typer.Option(
        None, "--output", "-o", help="Output markdown report file"
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
):
    """
    Run metamorphic relation tests on MCP test cases.

    Metamorphic testing checks invariant properties across related inputs.
    For example, rephrasing a prompt should still call the same tools.

    Available relations:
      - idempotency: same query twice -> same tools
      - tool_selection_stability: rephrased prompt -> same tools
      - parameter_preservation: minor variation -> same tool parameters
    """
    if not test_path.exists():
        console.print(f"[red]Error: Test file not found: {test_path}[/red]")
        raise typer.Exit(code=1)

    # Parse relation names
    relation_names = None
    if relations:
        relation_names = [r.strip() for r in relations.split(",")]

    console.print(
        Panel.fit(
            "[bold cyan]MCP Testing Framework - Metamorphic Testing[/bold cyan]\n"
            f"Model: {model} | Provider: {provider.value}",
            border_style="cyan",
        )
    )

    async def run_metamorphic():
        from testmcpy.server.helpers.mcp_config import load_mcp_yaml
        from testmcpy.server.state import get_or_create_mcp_client
        from testmcpy.src.metamorphic import (
            BUILTIN_RELATIONS,
            MetamorphicTester,
        )
        from testmcpy.src.test_runner import TestCase, TestRunner

        # Validate relation names early
        if relation_names:
            unknown = [r for r in relation_names if r not in BUILTIN_RELATIONS]
            if unknown:
                console.print(f"[red]Error: Unknown relation(s): {', '.join(unknown)}[/red]")
                console.print(f"[dim]Available: {', '.join(BUILTIN_RELATIONS.keys())}[/dim]")
                raise typer.Exit(code=1)

        # Get authenticated MCP client
        mcp_client = None
        effective_profile = profile
        if not effective_profile:
            mcp_config = load_mcp_yaml()
            effective_profile = mcp_config.get("default")

        if effective_profile:
            try:
                mcp_client = await get_or_create_mcp_client(effective_profile)
            except Exception as e:
                console.print(f"[yellow]Warning: Could not load MCP profile: {e}[/yellow]")

        # Load test cases from YAML
        with open(test_path) as f:
            data = yaml.safe_load(f)

        suite_provider = data.get("provider", provider.value)
        suite_model = data.get("model", model)
        suite_provider_config = data.get("provider_config", {})
        effective_mcp_url = mcp_url or DEFAULT_MCP_URL

        test_cases: list[TestCase] = []
        if "tests" in data:
            for test_data in data["tests"]:
                test_cases.append(TestCase.from_dict(test_data))
        elif "prompt" in data:
            test_cases.append(TestCase.from_dict(data))

        if not test_cases:
            console.print("[red]Error: No test cases found in file.[/red]")
            raise typer.Exit(code=1)

        console.print(f"[dim]Loaded {len(test_cases)} test case(s) from {test_path}[/dim]")

        tested_relations = relation_names or list(BUILTIN_RELATIONS.keys())
        console.print(f"[dim]Relations to test: {', '.join(tested_relations)}[/dim]")
        console.print()

        # Create runner
        runner = TestRunner(
            model=suite_model,
            provider=suite_provider,
            mcp_url=effective_mcp_url,
            mcp_client=mcp_client,
            verbose=verbose,
            provider_config=suite_provider_config,
        )
        await runner.initialize()

        tester = MetamorphicTester(runner)
        all_results = []

        try:
            for tc in test_cases:
                console.print(f"[bold]Testing: {tc.name}[/bold]")
                results = await tester.test_all_relations(tc, relation_names)
                all_results.extend(results)

                # Show results as we go
                for r in results:
                    status = "[green]PASS[/green]" if r.passed else "[red]FAIL[/red]"
                    console.print(
                        f"  {status} {r.relation}: "
                        f"source=[{', '.join(r.source_tools) or 'none'}] "
                        f"followup=[{', '.join(r.followup_tools) or 'none'}]"
                    )
                    if r.error:
                        console.print(f"    [red]Error: {r.error}[/red]")
                console.print()
        finally:
            await runner.cleanup()

        # Summary table
        table = Table(title="Metamorphic Test Summary")
        table.add_column("Test Case", style="cyan")
        table.add_column("Relation", style="magenta")
        table.add_column("Status", justify="center")
        table.add_column("Duration", justify="right")

        for r in all_results:
            status = "[green]PASS[/green]" if r.passed else "[red]FAIL[/red]"
            table.add_row(
                r.source_test_name,
                r.relation,
                status,
                f"{r.duration_ms:.0f}ms",
            )

        console.print(table)

        # Overall summary
        total = len(all_results)
        passed = sum(1 for r in all_results if r.passed)
        console.print(
            f"\n[bold]Results: {passed}/{total} passed ({passed / total:.0%})[/bold]"
            if total > 0
            else ""
        )

        # Generate report if requested
        if output:
            report_md = tester.generate_report(all_results)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(report_md)
            console.print(f"\n[dim]Report written to {output}[/dim]")

        return all_results

    asyncio.run(run_metamorphic())
