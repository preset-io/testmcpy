"""Typer adapter for the read-only MCP gateway smoke lane.

The lane itself lives in ``testmcpy.gateway_smoke`` and is also runnable
headlessly as ``python -m testmcpy.gateway_smoke``. There is no flag for a token
or secret: credentials come only from the environment variables the config names.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from testmcpy.cli.app import app
from testmcpy.gateway_smoke.cli import EXIT_CODE_HELP
from testmcpy.gateway_smoke.cli import main as smoke_main

gateway_smoke_app = typer.Typer(
    name="gateway-smoke",
    help="Compact, read-only, deterministic MCP gateway smoke lane (no LLM calls). "
    + EXIT_CODE_HELP,
    no_args_is_help=True,
)
app.add_typer(gateway_smoke_app, name="gateway-smoke")


@gateway_smoke_app.command("validate")
def validate(
    config: Path = typer.Option(..., "--config", exists=True, dir_okay=False),
) -> None:
    """Validate a lane config offline: no network, no secrets resolved."""
    raise typer.Exit(smoke_main(["validate", "--config", str(config)]))


@gateway_smoke_app.command("run")
def run(
    config: Path = typer.Option(..., "--config", dir_okay=False),
    output_format: str = typer.Option("human", "--format", help="human or json"),
    output: str = typer.Option("-", "--output", help="Report destination ('-' = stdout)"),
    junit: Optional[Path] = typer.Option(None, "--junit", dir_okay=False),
    run_id: Optional[str] = typer.Option(None, "--run-id"),
    expect_environment: Optional[str] = typer.Option(
        None, "--expect-environment", help="BLOCKED unless the config's environment equals this"
    ),
    expect_workspace_id: Optional[str] = typer.Option(
        None, "--expect-workspace-id", help="BLOCKED unless the config's workspace.id equals this"
    ),
) -> None:
    """Run the three-step lane. Exit: 0 PASS, 1 FAIL, 2 ERROR, 3 BLOCKED."""
    if output_format not in {"human", "json"}:
        typer.echo("--format must be human or json", err=True)
        raise typer.Exit(2)
    argv = ["run", "--config", str(config), "--format", output_format, "--output", output]
    for flag, value in (
        ("--junit", junit),
        ("--run-id", run_id),
        ("--expect-environment", expect_environment),
        ("--expect-workspace-id", expect_workspace_id),
    ):
        if value is not None:
            argv += [flag, str(value)]
    raise typer.Exit(smoke_main(argv))
