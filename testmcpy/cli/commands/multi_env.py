"""Multi-environment orchestration command."""

import asyncio
import json
from pathlib import Path
from typing import Optional

import typer
import yaml
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from testmcpy.cli.app import (
    DEFAULT_MODEL,
    DEFAULT_PROVIDER,
    ModelProvider,
    app,
    console,
)


@app.command(name="multi-env")
def multi_env(
    test_path: Path = typer.Argument(..., help="Path to test file or directory"),
    envs: str = typer.Option(
        ...,
        "--envs",
        help="Comma-separated 'name:profile_id' pairs (e.g. 'staging:localhost,sandbox:sandbox-profile')",
    ),
    model: str = typer.Option(DEFAULT_MODEL, "--model", "-m", help="LLM model to use"),
    provider: ModelProvider = typer.Option(
        DEFAULT_PROVIDER, "--provider", "-p", help="LLM provider"
    ),
    output: Optional[Path] = typer.Option(
        None, "--output", "-o", help="Output file for results (JSON)"
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
):
    """
    Run eval suite across multiple environments and compare results.

    Runs the same test cases against different MCP profiles (environments)
    using a single LLM model, then produces a comparison matrix highlighting
    environment-specific failures.

    Example:
        testmcpy multi-env tests/ --envs "staging:localhost,sandbox:sandbox-profile" --model claude-sonnet-4 --provider anthropic
    """
    from testmcpy.src.multi_env import EnvironmentConfig, MultiEnvironmentRunner

    # Parse environment specs
    env_specs = [s.strip() for s in envs.split(",") if s.strip()]
    if len(env_specs) < 2:
        console.print(
            "[red]Error: --envs requires at least 2 comma-separated name:profile_id pairs[/red]"
        )
        raise typer.Exit(code=1)

    try:
        env_configs = [EnvironmentConfig.from_string(spec) for spec in env_specs]
    except ValueError as e:
        console.print(f"[red]Error parsing --envs: {e}[/red]")
        raise typer.Exit(code=1)

    console.print(
        Panel.fit(
            "[bold cyan]MCP Testing Framework - Multi-Environment Comparison[/bold cyan]\n"
            f"Model: {model} | Provider: {provider.value}\n"
            f"Environments: {len(env_configs)}",
            border_style="cyan",
        )
    )

    for ec in env_configs:
        console.print(f"  [dim]* {ec.name} (profile: {ec.profile_id})[/dim]")

    async def run_multi_env():
        from testmcpy.src.test_runner import TestCase

        # Load test cases
        test_cases: list[TestCase] = []

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
            for pattern in ["*.yaml", "*.yml", "*.json"]:
                for file in test_path.rglob(pattern):
                    if any(part.startswith(".") for part in file.relative_to(test_path).parts):
                        continue
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
                        elif "prompt" in data:
                            test_cases.append(TestCase.from_dict(data))

        if not test_cases:
            console.print("[red]No test cases found.[/red]")
            raise typer.Exit(code=1)

        console.print(f"\n[bold]Found {len(test_cases)} test case(s)[/bold]")

        # Run multi-environment comparison
        runner = MultiEnvironmentRunner(
            environments=env_configs,
            model=model,
            provider=provider.value,
            verbose=verbose,
        )

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            for ec in env_configs:
                progress.add_task(
                    f"Running tests against {ec.name} ({ec.profile_id})...",
                    total=None,
                )

            results = await runner.run(test_cases)

        # Display comparison matrix
        report_md = runner.generate_comparison_report(results)
        console.print()
        console.print(report_md)

        # Per-environment summary
        console.print("\n[bold]Per-Environment Summary:[/bold]")
        for er in results:
            status_color = "green" if er.passed == er.total_tests else "yellow"
            console.print(
                f"  [{status_color}]{er.environment.name}[/{status_color}]: "
                f"{er.passed}/{er.total_tests} passed, "
                f"score {er.score * 100:.0f}%, "
                f"{er.total_duration:.0f}s"
            )

        # Show environment-specific issues
        issues = runner.find_env_specific_issues(results)
        if issues:
            console.print(f"\n[yellow]Found {len(issues)} environment-specific issue(s)[/yellow]")

        # Save output if requested
        if output:
            output_data = runner.to_dict()
            with open(output, "w") as f:
                json.dump(output_data, f, indent=2, default=str)
            console.print(f"\n[green]Results saved to {output}[/green]")

    asyncio.run(run_multi_env())
