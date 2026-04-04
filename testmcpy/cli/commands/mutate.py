"""Prompt mutation commands: generate and test prompt variations."""

import asyncio
import json
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
    OutputFormat,
    app,
    console,
)


@app.command()
def mutate(
    test_path: Path = typer.Argument(..., help="Path to test YAML file"),
    strategies: Optional[str] = typer.Option(
        None,
        "--strategies",
        "-s",
        help="Comma-separated mutation strategies (typo,casual,verbose,minimal,rephrase,negation)",
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
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output report file"),
    format: OutputFormat = typer.Option(OutputFormat.table, "--format", "-f", help="Output format"),
    seed: Optional[int] = typer.Option(
        None, "--seed", help="Random seed for reproducible mutations"
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show mutations without running tests"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
):
    """
    Generate and test prompt mutations for robustness testing.

    Mutates prompts in a test YAML file using various strategies (typo, casual,
    verbose, etc.) and optionally runs them to check that the same tools are
    called regardless of phrasing.

    Examples:

        testmcpy mutate tests/my_test.yaml --strategies typo,casual,verbose

        testmcpy mutate tests/my_test.yaml --dry-run

        testmcpy mutate tests/my_test.yaml --seed 42 --format json
    """
    from testmcpy.src.prompt_mutation import PromptMutator
    from testmcpy.src.test_runner import TestCase

    if not test_path.exists():
        console.print(f"[red]Error: Test file not found: {test_path}[/red]")
        raise typer.Exit(code=1)

    # Parse strategies
    strategy_list = None
    if strategies:
        strategy_list = [s.strip() for s in strategies.split(",")]
        valid = {"typo", "casual", "verbose", "minimal", "rephrase", "negation"}
        invalid = set(strategy_list) - valid
        if invalid:
            console.print(f"[red]Error: Unknown strategies: {', '.join(invalid)}[/red]")
            console.print(f"[dim]Valid strategies: {', '.join(sorted(valid))}[/dim]")
            raise typer.Exit(code=1)

    # Load test cases
    content = test_path.read_text()
    data = yaml.safe_load(content)
    test_cases = [TestCase.from_dict(t) for t in data.get("tests", [])]

    if not test_cases:
        console.print("[red]Error: No test cases found in file[/red]")
        raise typer.Exit(code=1)

    mutator = PromptMutator(seed=seed)

    console.print(
        Panel.fit(
            "[bold cyan]MCP Testing Framework - Prompt Mutation[/bold cyan]\n"
            f"File: {test_path} | Tests: {len(test_cases)}",
            border_style="cyan",
        )
    )

    if dry_run:
        _show_mutations_dry_run(test_cases, mutator, strategy_list, format, output)
        return

    # Run mutation tests
    _run_mutation_tests(
        test_cases=test_cases,
        mutator=mutator,
        strategy_list=strategy_list,
        model=model,
        provider=provider,
        mcp_url=mcp_url,
        profile=profile,
        format=format,
        output=output,
        verbose=verbose,
    )


def _show_mutations_dry_run(
    test_cases,
    mutator,
    strategy_list,
    format,
    output,
):
    """Display generated mutations without running tests."""
    all_mutations = []

    for tc in test_cases:
        mutations = mutator.mutate(tc.prompt, strategies=strategy_list)
        entry = {
            "test_name": tc.name,
            "original_prompt": tc.prompt,
            "mutations": mutations,
        }
        all_mutations.append(entry)

        if format == OutputFormat.table:
            console.print(f"\n[bold]{tc.name}[/bold]")
            console.print(f"  Original: [dim]{tc.prompt}[/dim]\n")

            table = Table(show_header=True, header_style="bold cyan")
            table.add_column("Strategy", style="dim", width=12)
            table.add_column("Mutated Prompt")

            for m in mutations:
                table.add_row(m["strategy"], m["prompt"])

            console.print(table)

    if format == OutputFormat.json:
        console.print(json.dumps(all_mutations, indent=2))
    elif format == OutputFormat.yaml:
        console.print(yaml.dump(all_mutations, default_flow_style=False))

    if output:
        output_data = json.dumps(all_mutations, indent=2)
        output.write_text(output_data)
        console.print(f"\n[green]Mutations saved to {output}[/green]")

    console.print(
        f"\n[dim]Generated {sum(len(e['mutations']) for e in all_mutations)} "
        f"mutations across {len(test_cases)} test(s)[/dim]"
    )


def _run_mutation_tests(
    test_cases,
    mutator,
    strategy_list,
    model,
    provider,
    mcp_url,
    profile,
    format,
    output,
    verbose,
):
    """Run mutation tests with the actual LLM test runner."""

    async def _run():
        from testmcpy.server.helpers.mcp_config import load_mcp_yaml
        from testmcpy.server.state import get_or_create_mcp_client
        from testmcpy.src.prompt_mutation import MutationTestRunner
        from testmcpy.src.test_runner import TestRunner

        # Resolve MCP URL
        effective_mcp_url = mcp_url
        effective_profile = profile
        if not effective_profile:
            mcp_config = load_mcp_yaml()
            effective_profile = mcp_config.get("default")

        if not effective_mcp_url and effective_profile:
            mcp_client = await get_or_create_mcp_client(effective_profile)
        else:
            mcp_client = None

        runner = TestRunner(
            model=model,
            provider=provider.value,
            mcp_url=effective_mcp_url or DEFAULT_MCP_URL,
            mcp_client=mcp_client,
            verbose=verbose,
        )

        mutation_runner = MutationTestRunner(test_runner=runner, mutator=mutator)

        reports = []
        for tc in test_cases:
            console.print(f"\n[bold]Testing mutations for: {tc.name}[/bold]")
            report = await mutation_runner.run_mutation_test(tc, strategies=strategy_list)
            reports.append(report)

            if format == OutputFormat.table:
                _print_mutation_report_table(report)

        if format == OutputFormat.json:
            console.print(json.dumps([r.to_dict() for r in reports], indent=2))
        elif format == OutputFormat.yaml:
            console.print(yaml.dump([r.to_dict() for r in reports], default_flow_style=False))

        if output:
            output_data = json.dumps([r.to_dict() for r in reports], indent=2)
            output.write_text(output_data)
            console.print(f"\n[green]Results saved to {output}[/green]")

        # Print summary
        _print_summary(reports)

    asyncio.run(_run())


def _print_mutation_report_table(report):
    """Print a single mutation test report as a rich table."""
    console.print(f"  Original prompt: [dim]{report.original_prompt}[/dim]")
    console.print(
        f"  Original tools called: [dim]{', '.join(report.original_tool_calls) or 'none'}[/dim]"
    )

    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Strategy", style="dim", width=12)
    table.add_column("Mutated Prompt", max_width=50)
    table.add_column("Matched", justify="center", width=8)
    table.add_column("Score", justify="right", width=8)
    table.add_column("Error", style="red", max_width=30)

    for mr in report.mutation_results:
        matched_str = "[green]yes[/green]" if mr.matched_original else "[red]no[/red]"
        error_str = (mr.error or "")[:30] if mr.error else ""
        table.add_row(
            mr.strategy,
            mr.prompt[:50],
            matched_str,
            f"{mr.score:.2f}",
            error_str,
        )

    console.print(table)
    pct = report.consistency_score * 100
    color = "green" if pct >= 80 else "yellow" if pct >= 50 else "red"
    console.print(
        f"  Consistency: [{color}]{pct:.0f}%[/{color}] "
        f"({report.matched_mutations}/{report.total_mutations} matched)"
    )


def _print_summary(reports):
    """Print overall summary across all test cases."""
    if not reports:
        return

    total_mutations = sum(r.total_mutations for r in reports)
    total_matched = sum(r.matched_mutations for r in reports)
    avg_consistency = (total_matched / total_mutations * 100) if total_mutations > 0 else 0

    console.print("\n")
    console.print(
        Panel.fit(
            f"[bold]Mutation Test Summary[/bold]\n"
            f"Tests: {len(reports)} | "
            f"Total mutations: {total_mutations} | "
            f"Matched: {total_matched} | "
            f"Consistency: {avg_consistency:.0f}%",
            border_style="cyan",
        )
    )
