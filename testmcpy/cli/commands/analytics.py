"""CLI commands for test-performance analytics.

`testmcpy matrix | leaderboard | flaky` — per-test × per-config
analysis backed by the same testmcpy.analytics functions as the
/api/analytics endpoints. Reads the results DB directly; no server
needed.
"""

import csv
import io
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import typer
from rich.markup import escape
from rich.table import Table

from testmcpy.cli.app import app, console


def _parse_since(since: Optional[str]) -> Optional[str]:
    """Accept '30d'/'12h' shorthand or a literal ISO date string."""
    if not since:
        return None
    if since.endswith("d") and since[:-1].isdigit():
        delta = timedelta(days=int(since[:-1]))
    elif since.endswith("h") and since[:-1].isdigit():
        delta = timedelta(hours=int(since[:-1]))
    else:
        return since  # assume ISO date / datetime prefix
    return (datetime.now(timezone.utc) - delta).strftime("%Y-%m-%dT%H:%M:%S")


def _get_session(db_path: Optional[str]):
    from testmcpy.storage import TestStorage, get_storage

    storage = TestStorage(db_path=db_path) if db_path else get_storage()
    return storage.session()


def _pct(rate: float) -> str:
    return f"{rate * 100:.0f}%"


def _emit_csv(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return ""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()


@app.command()
def matrix(
    suite: Optional[str] = typer.Option(None, "--suite", help="Filter to one test suite/file"),
    since: Optional[str] = typer.Option(
        None, "--since", help="Window: '30d', '12h', or an ISO date"
    ),
    min_runs: int = typer.Option(1, "--min-runs", help="Hide cells with fewer runs"),
    no_profile: bool = typer.Option(
        False, "--no-profile", help="Group by model+provider only (ignore MCP profile)"
    ),
    output_format: str = typer.Option("table", "--format", help="table, json, or csv"),
    db_path: Optional[str] = typer.Option(None, "--db-path", help="Results DB path override"),
    fail_below: Optional[float] = typer.Option(
        None,
        "--fail-below",
        help="Exit 1 if any config's overall pass rate is below this (0-1)",
    ),
):
    """Per-test × per-config performance matrix."""
    from testmcpy import analytics

    with _get_session(db_path) as session:
        data = analytics.test_matrix(
            session,
            suite_id=suite,
            date_from=_parse_since(since),
            min_runs=min_runs,
            include_profile=not no_profile,
        )

    if output_format == "json":
        console.print_json(json.dumps(data))
    elif output_format == "csv":
        flat = [
            {
                "question_id": row["question_id"],
                "config": key,
                **{k: v for k, v in cell.items() if k != "trend"},
            }
            for row in data["rows"]
            for key, cell in row["cells"].items()
        ]
        print(_emit_csv(flat), end="")
    else:
        configs = [c["key"] for c in data["configs"]]
        if not configs:
            console.print(
                "[yellow]No completed runs found.[/yellow] "
                "Generate data with: [cyan]testmcpy bench tests/ --repeat 3[/cyan]"
            )
            raise typer.Exit(0)

        table = Table(show_header=True, header_style="bold cyan", title="Test × Config Matrix")
        table.add_column("Test", style="dim", overflow="fold")
        for key in configs:
            table.add_column(key, justify="center")
        for row in data["rows"]:
            cells = []
            for key in configs:
                cell = row["cells"].get(key)
                if cell is None:
                    cells.append("[dim]—[/dim]")
                    continue
                color = (
                    "green"
                    if cell["pass_rate"] == 1.0
                    else "red"
                    if cell["pass_rate"] == 0.0
                    else "yellow"
                )
                label = f"[{color}]{_pct(cell['pass_rate'])}[/{color}] · n={cell['n']}"
                if cell["flaky"]:
                    label += " [yellow]⚡[/yellow]"
                cells.append(label)
            table.add_row(row["question_id"], *cells)

        footer = ["[bold]All tests[/bold]"]
        for config in data["configs"]:
            footer.append(f"[bold]{_pct(config['pass_rate'])}[/bold] · runs={config['n_runs']}")
        table.add_row(*footer)
        console.print(table)
        for warning in data["warnings"]:
            console.print(f"[yellow]⚠ {warning}[/yellow]")

    if fail_below is not None:
        failing = [c for c in data["configs"] if c["pass_rate"] < fail_below]
        if failing:
            console.print(
                f"[red]{len(failing)} config(s) below {_pct(fail_below)}: "
                + ", ".join(c["key"] for c in failing)
                + "[/red]"
            )
            raise typer.Exit(1)


@app.command()
def leaderboard(
    suite: Optional[str] = typer.Option(None, "--suite", help="Filter to one test suite/file"),
    since: Optional[str] = typer.Option(
        None, "--since", help="Window: '30d', '12h', or an ISO date"
    ),
    no_profile: bool = typer.Option(
        False, "--no-profile", help="Group by model+provider only (ignore MCP profile)"
    ),
    by_effort: bool = typer.Option(
        False, "--by-effort", help="Split configs by reasoning-effort level"
    ),
    by_suite: bool = typer.Option(False, "--by-suite", help="Split configs by test suite"),
    output_format: str = typer.Option("table", "--format", help="table, json, or csv"),
    db_path: Optional[str] = typer.Option(None, "--db-path", help="Results DB path override"),
):
    """Configs ranked by pass rate, with cost-per-pass and latency."""
    from testmcpy import analytics

    with _get_session(db_path) as session:
        ranked = analytics.leaderboard(
            session,
            suite_id=suite,
            date_from=_parse_since(since),
            include_profile=not no_profile,
            include_effort=by_effort,
            include_suite=by_suite,
        )

    if output_format == "json":
        console.print_json(json.dumps({"configs": ranked}))
        return
    if output_format == "csv":
        print(_emit_csv(ranked), end="")
        return

    if not ranked:
        console.print(
            "[yellow]No completed runs found.[/yellow] "
            "Generate data with: [cyan]testmcpy bench tests/ --repeat 3[/cyan]"
        )
        return

    table = Table(show_header=True, header_style="bold cyan", title="Config Leaderboard")
    table.add_column("#", style="dim")
    table.add_column("Config")
    table.add_column("Pass rate", justify="right")
    table.add_column("Runs", justify="right")
    table.add_column("Flaky cells", justify="right")
    table.add_column("Cost/pass", justify="right")
    table.add_column("Avg latency", justify="right")
    for i, config in enumerate(ranked, 1):
        cost = f"${config['cost_per_pass']:.4f}" if config["cost_per_pass"] else "—"
        table.add_row(
            str(i),
            # escape(): keys can contain "[high]", which Rich would parse as
            # style markup and swallow.
            escape(config["key"]),
            _pct(config["pass_rate"]),
            str(config["n_runs"]),
            str(config["flaky_cells"]),
            cost,
            f"{config['avg_duration_ms'] / 1000:.1f}s",
        )
    console.print(table)


@app.command()
def flaky(
    suite: Optional[str] = typer.Option(None, "--suite", help="Filter to one test suite/file"),
    since: Optional[str] = typer.Option(
        None, "--since", help="Window: '30d', '12h', or an ISO date"
    ),
    min_runs: int = typer.Option(3, "--min-runs", help="Minimum runs to call a cell flaky"),
    output_format: str = typer.Option("table", "--format", help="table, json, or csv"),
    db_path: Optional[str] = typer.Option(None, "--db-path", help="Results DB path override"),
    fail_on_flaky: bool = typer.Option(
        False, "--fail-on-flaky", help="Exit 1 if any flaky test is found (CI)"
    ),
):
    """Flaky tests (intermittent within one config), flakiest first."""
    from testmcpy import analytics

    with _get_session(db_path) as session:
        rows = analytics.flaky_tests(
            session,
            suite_id=suite,
            date_from=_parse_since(since),
            min_runs=min_runs,
        )

    if output_format == "json":
        console.print_json(json.dumps({"flaky": rows}))
    elif output_format == "csv":
        print(_emit_csv(rows), end="")
    elif not rows:
        console.print("[green]No flaky tests found.[/green]")
    else:
        table = Table(show_header=True, header_style="bold cyan", title="Flaky Tests")
        table.add_column("Test", style="dim")
        table.add_column("Config")
        table.add_column("Pass rate", justify="right")
        table.add_column("Runs", justify="right")
        table.add_column("Last run")
        for row in rows:
            table.add_row(
                row["question_id"],
                row["config"],
                _pct(row["pass_rate"]),
                str(row["n"]),
                row["last_run_at"] or "—",
            )
        console.print(table)

    if fail_on_flaky and rows:
        raise typer.Exit(1)
