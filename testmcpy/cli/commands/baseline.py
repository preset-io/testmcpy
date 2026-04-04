"""Baseline management commands: save, compare, list."""

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
    app,
    console,
)


@app.command("baseline-save")
def baseline_save(
    name: str = typer.Argument(..., help="Name for the baseline"),
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
    baseline_dir: str = typer.Option(
        ".baselines", "--baseline-dir", help="Directory to store baselines"
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
    hide_tool_output: bool = typer.Option(
        False, "--hide-tool-output", help="Hide detailed tool call output"
    ),
):
    """
    Run tests and save results as a named baseline.

    Example: testmcpy baseline-save v1.0 tests/
    """
    if profile:
        from testmcpy.config import Config

        cfg = Config(profile=profile)
        effective_mcp_url = mcp_url or cfg.get_mcp_url()
    else:
        effective_mcp_url = mcp_url or DEFAULT_MCP_URL

    console.print(
        Panel.fit(
            "[bold cyan]Baseline Save[/bold cyan]\n"
            f"Name: {name} | Model: {model} | Provider: {provider.value}",
            border_style="cyan",
        )
    )

    async def _run():
        from testmcpy.server.helpers.mcp_config import load_mcp_yaml
        from testmcpy.server.state import get_or_create_mcp_client
        from testmcpy.src.baseline import BaselineStore
        from testmcpy.src.test_runner import TestRunner

        # Get MCP client
        mcp_client = None
        effective_profile = profile
        if not effective_profile:
            mcp_config = load_mcp_yaml()
            effective_profile = mcp_config.get("default")
        if effective_profile:
            try:
                mcp_client = await get_or_create_mcp_client(effective_profile)
            except (ConnectionError, ValueError, OSError) as e:
                console.print(f"[yellow]Warning: Could not load MCP profile: {e}[/yellow]")

        # Load test cases
        test_cases = _load_test_cases(test_path)
        console.print(f"\n[bold]Found {len(test_cases)} test case(s)[/bold]")

        # Detect suite-level overrides
        suite_provider, suite_model, suite_provider_config = _detect_suite_overrides(test_path)
        effective_provider = suite_provider or provider.value
        effective_model = suite_model or model

        runner = TestRunner(
            model=effective_model,
            provider=effective_provider,
            mcp_url=effective_mcp_url,
            mcp_client=mcp_client,
            verbose=verbose,
            hide_tool_output=hide_tool_output,
            provider_config=suite_provider_config,
        )

        # Run tests
        results = []
        await runner.initialize()

        for i, test_case in enumerate(test_cases, 1):
            console.print(
                f"\n[cyan]Running test {i}/{len(test_cases)}:[/cyan] [bold]{test_case.name}[/bold]"
            )
            from rich.status import Status

            with Status("[yellow]Executing test...[/yellow]", console=console):
                result = await runner._run_test_with_retry(test_case)
            results.append(result)

            status = "[green]PASSED[/green]" if result.passed else "[red]FAILED[/red]"
            console.print(f"  {status} (score: {result.score:.2f}, time: {result.duration:.2f}s)")

            # Rate limit delay
            if i < len(test_cases):
                if effective_provider in (
                    "claude-sdk",
                    "claude-cli",
                    "claude-code",
                    "codex-cli",
                    "codex",
                ):
                    await asyncio.sleep(1)
                else:
                    console.print("  [dim]Waiting 15s before next test...[/dim]")
                    await asyncio.sleep(15)

        # Save baseline
        store = BaselineStore(baseline_dir=baseline_dir)
        saved_path = store.save_baseline(
            name=name,
            results=results,
            model=effective_model,
            provider=effective_provider,
        )

        passed = sum(1 for r in results if r.passed)
        console.print(f"\n[green]Baseline '{name}' saved to {saved_path}[/green]")
        console.print(f"[bold]Summary:[/bold] {passed}/{len(results)} tests passed")

    asyncio.run(_run())


@app.command("baseline-compare")
def baseline_compare(
    name: str = typer.Argument(..., help="Baseline name to compare against"),
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
    baseline_dir: str = typer.Option(
        ".baselines", "--baseline-dir", help="Directory where baselines are stored"
    ),
    output: Optional[Path] = typer.Option(
        None, "--output", "-o", help="Save regression report to file (.md or .json)"
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
    hide_tool_output: bool = typer.Option(
        False, "--hide-tool-output", help="Hide detailed tool call output"
    ),
):
    """
    Run tests and compare results against a saved baseline.

    Example: testmcpy baseline-compare v1.0 tests/
    """
    if profile:
        from testmcpy.config import Config

        cfg = Config(profile=profile)
        effective_mcp_url = mcp_url or cfg.get_mcp_url()
    else:
        effective_mcp_url = mcp_url or DEFAULT_MCP_URL

    console.print(
        Panel.fit(
            "[bold cyan]Baseline Compare[/bold cyan]\n"
            f"Baseline: {name} | Model: {model} | Provider: {provider.value}",
            border_style="cyan",
        )
    )

    async def _run():
        from testmcpy.server.helpers.mcp_config import load_mcp_yaml
        from testmcpy.server.state import get_or_create_mcp_client
        from testmcpy.src.baseline import BaselineStore
        from testmcpy.src.test_runner import TestRunner

        store = BaselineStore(baseline_dir=baseline_dir)

        # Verify baseline exists before running tests
        try:
            store.load_baseline(name)
        except FileNotFoundError:
            console.print(f"[red]Baseline '{name}' not found in {baseline_dir}/[/red]")
            available = store.list_baselines()
            if available:
                console.print("[yellow]Available baselines:[/yellow]")
                for b in available:
                    console.print(f"  - {b['name']} ({b['model']}, {b['created'][:10]})")
            raise typer.Exit(code=1)

        # Get MCP client
        mcp_client = None
        effective_profile = profile
        if not effective_profile:
            mcp_config = load_mcp_yaml()
            effective_profile = mcp_config.get("default")
        if effective_profile:
            try:
                mcp_client = await get_or_create_mcp_client(effective_profile)
            except (ConnectionError, ValueError, OSError) as e:
                console.print(f"[yellow]Warning: Could not load MCP profile: {e}[/yellow]")

        # Load and run test cases
        test_cases = _load_test_cases(test_path)
        console.print(f"\n[bold]Found {len(test_cases)} test case(s)[/bold]")

        suite_provider, suite_model, suite_provider_config = _detect_suite_overrides(test_path)
        effective_provider = suite_provider or provider.value
        effective_model = suite_model or model

        runner = TestRunner(
            model=effective_model,
            provider=effective_provider,
            mcp_url=effective_mcp_url,
            mcp_client=mcp_client,
            verbose=verbose,
            hide_tool_output=hide_tool_output,
            provider_config=suite_provider_config,
        )

        results = []
        await runner.initialize()

        for i, test_case in enumerate(test_cases, 1):
            console.print(
                f"\n[cyan]Running test {i}/{len(test_cases)}:[/cyan] [bold]{test_case.name}[/bold]"
            )
            from rich.status import Status

            with Status("[yellow]Executing test...[/yellow]", console=console):
                result = await runner._run_test_with_retry(test_case)
            results.append(result)

            status = "[green]PASSED[/green]" if result.passed else "[red]FAILED[/red]"
            console.print(f"  {status} (score: {result.score:.2f}, time: {result.duration:.2f}s)")

            if i < len(test_cases):
                if effective_provider in (
                    "claude-sdk",
                    "claude-cli",
                    "claude-code",
                    "codex-cli",
                    "codex",
                ):
                    await asyncio.sleep(1)
                else:
                    console.print("  [dim]Waiting 15s before next test...[/dim]")
                    await asyncio.sleep(15)

        # Compare against baseline
        console.print(f"\n[bold]Comparing against baseline '{name}'...[/bold]")
        report = store.compare(baseline_name=name, current_results=results)

        # Display summary table
        summary_table = Table(
            title="Regression Summary", show_header=True, header_style="bold cyan"
        )
        summary_table.add_column("Category", style="dim")
        summary_table.add_column("Count")

        summary_table.add_row(
            "[red]New Failures (regressions)[/red]",
            str(len(report.new_failures)),
        )
        summary_table.add_row(
            "[green]Improvements[/green]",
            str(len(report.new_passes)),
        )
        summary_table.add_row(
            "[yellow]Stable Failures[/yellow]",
            str(len(report.stable_failures)),
        )
        summary_table.add_row(
            "Stable Passes",
            str(len(report.stable_passes)),
        )
        summary_table.add_row(
            "Score Changes",
            str(len(report.score_changes)),
        )
        console.print(summary_table)

        # Show regressions in detail
        if report.new_failures:
            console.print("\n[red bold]Regressions:[/red bold]")
            for f in report.new_failures:
                err = f.get("error", "")[:100]
                console.print(
                    f"  [red]REGRESSION[/red] {f['test_name']} "
                    f"(fingerprint: {f.get('fingerprint', 'N/A')})"
                )
                if err:
                    console.print(f"    [dim]{err}[/dim]")

        if report.new_passes:
            console.print("\n[green bold]Improvements:[/green bold]")
            for p in report.new_passes:
                console.print(
                    f"  [green]IMPROVED[/green] {p['test_name']} "
                    f"(score: {p.get('baseline_score', 'N/A')} -> "
                    f"{p['current_score']})"
                )

        # Save report if requested
        if output:
            md_report = store.generate_regression_report(report)
            if output.suffix == ".json":
                from dataclasses import asdict

                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text(json.dumps(asdict(report), indent=2))
            else:
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text(md_report)
            console.print(f"\n[green]Regression report saved to {output}[/green]")

        # Exit with error code if regressions found
        if report.new_failures:
            console.print(
                f"\n[red bold]{len(report.new_failures)} regression(s) detected![/red bold]"
            )
            raise typer.Exit(code=1)

    asyncio.run(_run())


@app.command("baseline-list")
def baseline_list(
    baseline_dir: str = typer.Option(
        ".baselines", "--baseline-dir", help="Directory where baselines are stored"
    ),
):
    """
    List saved baselines.

    Example: testmcpy baseline-list
    """
    from testmcpy.src.baseline import BaselineStore

    store = BaselineStore(baseline_dir=baseline_dir)
    baselines = store.list_baselines()

    if not baselines:
        console.print("[yellow]No baselines found.[/yellow]")
        console.print(f"[dim]Looked in: {store.baseline_dir.resolve()}[/dim]")
        return

    table = Table(title="Saved Baselines", show_header=True, header_style="bold cyan")
    table.add_column("Name", style="bold")
    table.add_column("Model")
    table.add_column("Provider")
    table.add_column("Tests")
    table.add_column("Passed")
    table.add_column("Failed")
    table.add_column("Created")

    for b in baselines:
        table.add_row(
            b["name"],
            b["model"],
            b["provider"],
            str(b["tests"]),
            f"[green]{b['passed']}[/green]",
            f"[red]{b['failed']}[/red]" if b["failed"] > 0 else "0",
            b["created"][:19] if b["created"] else "",
        )

    console.print(table)


def _load_test_cases(test_path: Path) -> list:
    """Load test cases from a file or directory."""
    from testmcpy.src.test_runner import TestCase

    test_cases: list[TestCase] = []

    if test_path.is_file():
        with open(test_path) as f:
            if test_path.suffix == ".json":
                data = json.load(f)
            else:
                data = yaml.safe_load(f)

            if data and "tests" in data:
                for test_data in data["tests"]:
                    test_cases.append(TestCase.from_dict(test_data))
            elif data and "prompt" in data:
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

    return test_cases


def _detect_suite_overrides(
    test_path: Path,
) -> tuple[str | None, str | None, dict]:
    """Detect suite-level provider/model overrides from a test file."""
    if not test_path.is_file():
        return None, None, {}
    try:
        with open(test_path) as f:
            if test_path.suffix == ".json":
                data = json.load(f)
            else:
                data = yaml.safe_load(f)
        if data:
            return (
                data.get("provider"),
                data.get("model"),
                data.get("provider_config", {}),
            )
    except (json.JSONDecodeError, yaml.YAMLError, OSError):
        pass
    return None, None, {}
