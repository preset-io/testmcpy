"""Push local test results to a remote testmcpy server."""

import os
from typing import Optional

import requests
import typer
from rich.panel import Panel
from rich.table import Table

from testmcpy.cli.app import app, console


@app.command("push")
def push(
    server: Optional[str] = typer.Option(
        None,
        "--server",
        "-s",
        help="Remote testmcpy server URL (e.g. https://testmcpy.sandbox.preset.io)",
    ),
    api_key: Optional[str] = typer.Option(
        None,
        "--api-key",
        "-k",
        help="API key for authentication",
    ),
    run_id: Optional[str] = typer.Option(
        None,
        "--run-id",
        help="Push a specific run by ID",
    ),
    latest: int = typer.Option(
        1,
        "--latest",
        "-n",
        help="Push the N most recent runs",
    ),
    include_smoke: bool = typer.Option(
        False,
        "--include-smoke",
        help="Also push smoke reports",
    ),
    include_generation: bool = typer.Option(
        False,
        "--include-generation",
        help="Also push generation logs",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Show what would be pushed without sending",
    ),
):
    """Push local test results to a remote testmcpy server.

    Reads from the local database and POSTs results to the remote server's
    /api/results/save endpoint.

    Set TESTMCPY_SERVER_URL and TESTMCPY_API_KEY as env vars or use --server and --api-key.
    """
    # Resolve server URL
    server_url = server or os.environ.get("TESTMCPY_SERVER_URL")
    if not server_url:
        console.print(
            Panel(
                "[red]No server URL specified.[/red]\n\n"
                "Provide the remote testmcpy server URL via:\n"
                "  [cyan]--server https://testmcpy.sandbox.preset.io[/cyan]\n"
                "  or\n"
                "  [cyan]export TESTMCPY_SERVER_URL=https://...[/cyan]",
                title="Missing Server",
            )
        )
        raise typer.Exit(1)

    # Resolve API key
    auth_key = api_key or os.environ.get("TESTMCPY_API_KEY")

    # Strip trailing slash
    server_url = server_url.rstrip("/")

    from testmcpy.storage import get_storage

    storage = get_storage()

    console.print(
        Panel(
            f"[cyan]Server:[/cyan] {server_url}\n"
            f"[cyan]Auth:[/cyan] {'API key set' if auth_key else 'none'}\n"
            f"[cyan]Dry run:[/cyan] {dry_run}",
            title="Push Configuration",
        )
    )

    results_table = Table(title="Push Results")
    results_table.add_column("Type", style="cyan")
    results_table.add_column("ID")
    results_table.add_column("Status", style="green")

    # Determine which runs to push
    if run_id:
        run_ids = [run_id]
    else:
        runs = storage.list_runs(limit=latest)
        run_ids = [r["run_id"] for r in runs]

    if not run_ids:
        console.print("[yellow]No test runs found in local database.[/yellow]")
        raise typer.Exit(0)

    # Push test runs
    headers = {"Content-Type": "application/json"}
    if auth_key:
        headers["Authorization"] = f"Bearer {auth_key}"

    for rid in run_ids:
        full_run = storage.get_run(rid)
        if not full_run:
            results_table.add_row("run", rid, "[red]not found locally[/red]")
            continue

        if dry_run:
            qcount = len(full_run.get("question_results", []))
            results_table.add_row("run", rid, f"[yellow]dry run ({qcount} questions)[/yellow]")
            continue

        # Transform to the format expected by /api/results/save
        payload = _run_to_save_payload(full_run)

        try:
            resp = requests.post(
                f"{server_url}/api/results/save",
                headers=headers,
                json=payload,
                timeout=30,
            )
            if resp.status_code == 200:
                remote_id = resp.json().get("run_id", "?")
                results_table.add_row("run", rid, f"[green]pushed → {remote_id}[/green]")
            else:
                results_table.add_row(
                    "run", rid, f"[red]{resp.status_code}: {resp.text[:80]}[/red]"
                )
        except requests.ConnectionError:
            results_table.add_row("run", rid, f"[red]connection failed to {server_url}[/red]")
        except requests.Timeout:
            results_table.add_row("run", rid, "[red]timeout[/red]")

    # Push smoke reports
    if include_smoke:
        reports = storage.list_smoke_reports(limit=latest)
        for report_meta in reports:
            report = storage.get_smoke_report(report_meta["report_id"])
            if not report:
                continue

            if dry_run:
                results_table.add_row(
                    "smoke",
                    report_meta["report_id"],
                    "[yellow]dry run[/yellow]",
                )
                continue

            try:
                resp = requests.post(
                    f"{server_url}/api/smoke-reports/save",
                    headers=headers,
                    json=report,
                    timeout=30,
                )
                if resp.status_code == 200:
                    results_table.add_row(
                        "smoke",
                        report_meta["report_id"],
                        "[green]pushed[/green]",
                    )
                else:
                    results_table.add_row(
                        "smoke",
                        report_meta["report_id"],
                        f"[red]{resp.status_code}[/red]",
                    )
            except (requests.ConnectionError, requests.Timeout) as e:
                results_table.add_row(
                    "smoke",
                    report_meta["report_id"],
                    f"[red]{type(e).__name__}[/red]",
                )

    # Push generation logs
    if include_generation:
        logs = storage.list_generation_logs(limit=latest)
        for log_meta in logs:
            log = storage.get_generation_log(log_meta["log_id"])
            if not log:
                continue

            if dry_run:
                results_table.add_row(
                    "generation",
                    log_meta["log_id"],
                    "[yellow]dry run[/yellow]",
                )
                continue

            try:
                resp = requests.post(
                    f"{server_url}/api/generation-logs/save",
                    headers=headers,
                    json=log,
                    timeout=30,
                )
                if resp.status_code == 200:
                    results_table.add_row(
                        "generation",
                        log_meta["log_id"],
                        "[green]pushed[/green]",
                    )
                else:
                    results_table.add_row(
                        "generation",
                        log_meta["log_id"],
                        f"[red]{resp.status_code}[/red]",
                    )
            except (requests.ConnectionError, requests.Timeout) as e:
                results_table.add_row(
                    "generation",
                    log_meta["log_id"],
                    f"[red]{type(e).__name__}[/red]",
                )

    console.print()
    console.print(results_table)

    if dry_run:
        console.print("\n[yellow]Dry run — no data was sent.[/yellow]")


def _run_to_save_payload(run: dict) -> dict:
    """Transform a storage get_run() result into the /api/results/save payload format."""
    results = []
    for qr in run.get("question_results", []):
        results.append(
            {
                "test_name": qr["question_id"],
                "passed": qr["passed"],
                "score": qr["score"],
                "duration": qr["duration_ms"] / 1000.0,
                "cost": 0.0,
                "response": qr.get("answer"),
                "tool_calls": qr.get("tool_uses"),
                "tool_results": qr.get("tool_results"),
                "token_usage": {
                    "input": qr.get("tokens_input", 0),
                    "output": qr.get("tokens_output", 0),
                    "total": qr.get("tokens_input", 0) + qr.get("tokens_output", 0),
                },
                "evaluations": qr.get("evaluations"),
                "error": qr.get("error"),
            }
        )

    summary = run.get("summary", {})

    return {
        "test_file": run.get("test_id", "unknown"),
        "test_file_path": "",
        "provider": run.get("provider", "unknown"),
        "model": run.get("model", "unknown"),
        "mcp_profile": run.get("metadata", {}).get("mcp_profile"),
        "results": results,
        "summary": {
            "total": summary.get("total", 0),
            "passed": summary.get("passed", 0),
            "failed": summary.get("failed", 0),
        },
    }
