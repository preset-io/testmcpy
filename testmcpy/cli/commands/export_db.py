"""Export test results to an external database for BI/dashboard tools like Superset."""

import json
import os
from typing import Optional

import typer
from rich.panel import Panel
from rich.table import Table

from testmcpy.cli.app import app, console


def _check_pandas():
    """Check if pandas is installed, raise helpful error if not."""
    try:
        import pandas  # noqa: F401

        return True
    except ImportError:
        console.print(
            Panel(
                "[red]pandas is required for database export.[/red]\n\n"
                "Install it with:\n"
                "  [cyan]pip install testmcpy\\[export\\][/cyan]\n"
                "  or\n"
                "  [cyan]pip install pandas[/cyan]",
                title="Missing Dependency",
            )
        )
        raise typer.Exit(1)


def _build_runs_df(storage, since: str | None = None):
    """Build a denormalized DataFrame of test runs."""
    import pandas as pd

    runs = storage.list_runs(limit=10000)
    if not runs:
        return pd.DataFrame()

    rows = []
    for run_meta in runs:
        if since and run_meta.get("started_at", "") < since:
            continue

        full_run = storage.get_run(run_meta["run_id"])
        if not full_run:
            continue

        summary = full_run.get("summary", {})
        rows.append(
            {
                "run_id": full_run["run_id"],
                "suite_id": full_run["test_id"],
                "model": full_run["model"],
                "provider": full_run["provider"],
                "mcp_profile_id": full_run.get("metadata", {}).get("mcp_profile"),
                "status": "completed" if full_run.get("completed_at") else "running",
                "total_questions": summary.get("total", 0),
                "passed": summary.get("passed", 0),
                "failed": summary.get("failed", 0),
                "pass_rate": summary.get("pass_rate", 0.0),
                "total_tokens": summary.get("total_tokens", 0),
                "total_duration_ms": summary.get("total_duration_ms", 0),
                "started_at": full_run.get("started_at"),
                "completed_at": full_run.get("completed_at"),
            }
        )

    return pd.DataFrame(rows)


def _build_question_results_df(storage, since: str | None = None):
    """Build a denormalized DataFrame of question results with run context."""
    import pandas as pd

    runs = storage.list_runs(limit=10000)
    if not runs:
        return pd.DataFrame()

    rows = []
    for run_meta in runs:
        if since and run_meta.get("started_at", "") < since:
            continue

        full_run = storage.get_run(run_meta["run_id"])
        if not full_run:
            continue

        for qr in full_run.get("question_results", []):
            tool_uses = qr.get("tool_uses", [])
            rows.append(
                {
                    "run_id": full_run["run_id"],
                    "suite_id": full_run["test_id"],
                    "model": full_run["model"],
                    "provider": full_run["provider"],
                    "question_id": qr["question_id"],
                    "passed": qr["passed"],
                    "score": qr["score"],
                    "tokens_input": qr["tokens_input"],
                    "tokens_output": qr["tokens_output"],
                    "tokens_total": qr["tokens_input"] + qr["tokens_output"],
                    "duration_ms": qr["duration_ms"],
                    "error": qr.get("error"),
                    "num_tool_calls": len(tool_uses) if isinstance(tool_uses, list) else 0,
                    "evaluations_json": json.dumps(qr.get("evaluations", []), default=str),
                    "started_at": full_run.get("started_at"),
                }
            )

    return pd.DataFrame(rows)


def _build_smoke_reports_df(storage, since: str | None = None):
    """Build a denormalized DataFrame of smoke report results."""
    import pandas as pd

    reports = storage.list_smoke_reports(limit=10000)
    if not reports:
        return pd.DataFrame()

    rows = []
    for report_meta in reports:
        if since and report_meta.get("timestamp", "") < since:
            continue

        full_report = storage.get_smoke_report(report_meta["report_id"])
        if not full_report:
            continue

        for result in full_report.get("results", []):
            rows.append(
                {
                    "report_id": full_report["report_id"],
                    "profile_id": full_report.get("profile_id"),
                    "profile_name": full_report.get("profile_name"),
                    "server_url": full_report.get("server_url"),
                    "tool_name": result.get("test_name", result.get("tool_name", "unknown")),
                    "success": result.get("success", False),
                    "duration_ms": result.get("duration_ms", 0),
                    "error_message": result.get("error_message"),
                    "report_total_tests": full_report.get("total_tests", 0),
                    "report_passed": full_report.get("passed", 0),
                    "report_success_rate": full_report.get("success_rate", 0.0),
                    "created_at": full_report.get("timestamp"),
                }
            )

    return pd.DataFrame(rows)


def _build_generation_logs_df(storage, since: str | None = None):
    """Build a denormalized DataFrame of generation logs."""
    import pandas as pd

    logs = storage.list_generation_logs(limit=10000)
    if not logs:
        return pd.DataFrame()

    rows = []
    for log_meta in logs:
        if since and log_meta.get("timestamp", "") < since:
            continue

        full_log = storage.get_generation_log(log_meta["log_id"])
        if not full_log:
            continue

        metadata = full_log.get("metadata", {})
        rows.append(
            {
                "log_id": metadata.get("log_id"),
                "tool_name": metadata.get("tool_name"),
                "coverage_level": metadata.get("coverage_level"),
                "provider": metadata.get("provider"),
                "model": metadata.get("model"),
                "success": metadata.get("success", False),
                "test_count": metadata.get("test_count", 0),
                "total_cost": metadata.get("total_cost", 0.0),
                "num_llm_calls": len(full_log.get("llm_calls", [])),
                "error": metadata.get("error"),
                "created_at": metadata.get("timestamp"),
            }
        )

    return pd.DataFrame(rows)


TABLE_BUILDERS = {
    "runs": ("testmcpy_runs", _build_runs_df),
    "questions": ("testmcpy_question_results", _build_question_results_df),
    "smoke": ("testmcpy_smoke_reports", _build_smoke_reports_df),
    "generation": ("testmcpy_generation_logs", _build_generation_logs_df),
}


@app.command("export-db")
def export_db(
    target: Optional[str] = typer.Option(
        None,
        "--target",
        "-t",
        help="SQLAlchemy connection URL (e.g. postgresql://user:pass@host/db)",
    ),
    tables: str = typer.Option(
        "all",
        "--tables",
        help="Comma-separated tables to export: runs,questions,smoke,generation (or 'all')",
    ),
    since: Optional[str] = typer.Option(
        None,
        "--since",
        help="Only export data after this ISO date (e.g. 2026-01-01)",
    ),
    replace: bool = typer.Option(
        False,
        "--replace",
        help="Replace existing tables instead of appending",
    ),
    schema: Optional[str] = typer.Option(
        None,
        "--schema",
        help="Database schema to write tables into",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Show what would be exported without writing",
    ),
):
    """Export test results to an external database for dashboarding (e.g. Superset).

    Reads from the local testmcpy database and pushes denormalized,
    dashboard-friendly tables to any SQLAlchemy-supported database.

    Set TESTMCPY_TARGET_SQLALCHEMY_URL as an env var or use --target.
    """
    _check_pandas()
    from sqlalchemy import create_engine

    # Resolve target URL
    target_url = target or os.environ.get("TESTMCPY_TARGET_SQLALCHEMY_URL")
    if not target_url:
        console.print(
            Panel(
                "[red]No target database specified.[/red]\n\n"
                "Provide a SQLAlchemy connection URL via:\n"
                "  [cyan]--target postgresql://user:pass@host/db[/cyan]\n"
                "  or\n"
                "  [cyan]export TESTMCPY_TARGET_SQLALCHEMY_URL=postgresql://...[/cyan]",
                title="Missing Target",
            )
        )
        raise typer.Exit(1)

    # Determine which tables to export
    if tables == "all":
        selected = list(TABLE_BUILDERS.keys())
    else:
        selected = [t.strip() for t in tables.split(",") if t.strip()]
        invalid = [t for t in selected if t not in TABLE_BUILDERS]
        if invalid:
            console.print(
                f"[red]Unknown table(s): {', '.join(invalid)}[/red]\n"
                f"Valid options: {', '.join(TABLE_BUILDERS.keys())}"
            )
            raise typer.Exit(1)

    # Load data from local storage
    from testmcpy.storage import get_storage

    storage = get_storage()
    if_exists = "replace" if replace else "append"

    console.print(
        Panel(
            f"[cyan]Target:[/cyan] {_mask_url(target_url)}\n"
            f"[cyan]Tables:[/cyan] {', '.join(selected)}\n"
            f"[cyan]Mode:[/cyan] {'replace' if replace else 'append'}\n"
            f"[cyan]Since:[/cyan] {since or 'all time'}\n"
            f"[cyan]Dry run:[/cyan] {dry_run}",
            title="Export Configuration",
        )
    )

    # Build DataFrames
    results_table = Table(title="Export Results")
    results_table.add_column("Table", style="cyan")
    results_table.add_column("Rows", justify="right")
    results_table.add_column("Status", style="green")

    total_rows = 0

    for table_key in selected:
        table_name, builder = TABLE_BUILDERS[table_key]
        df = builder(storage, since=since)
        row_count = len(df)
        total_rows += row_count

        if dry_run:
            results_table.add_row(table_name, str(row_count), "[yellow]dry run[/yellow]")
            if row_count > 0:
                console.print(f"\n[dim]Preview: {table_name}[/dim]")
                console.print(df.head().to_string())
            continue

        if row_count == 0:
            results_table.add_row(table_name, "0", "[dim]skipped (empty)[/dim]")
            continue

        # Push to target database
        try:
            engine = create_engine(target_url)
            df.to_sql(
                name=table_name,
                con=engine,
                schema=schema,
                if_exists=if_exists,
                index=False,
            )
            engine.dispose()
            results_table.add_row(table_name, str(row_count), "[green]pushed[/green]")
        except Exception as e:
            results_table.add_row(table_name, str(row_count), f"[red]error: {e}[/red]")

    console.print()
    console.print(results_table)
    console.print(f"\n[bold]Total rows: {total_rows}[/bold]")

    if dry_run:
        console.print("[yellow]Dry run — no data was written.[/yellow]")


def _mask_url(url: str) -> str:
    """Mask password in connection URL for display."""
    if "://" not in url:
        return url
    try:
        from urllib.parse import urlparse

        parsed = urlparse(url)
        if parsed.password:
            masked = url.replace(f":{parsed.password}@", ":***@")
            return masked
    except ValueError:
        pass
    return url
