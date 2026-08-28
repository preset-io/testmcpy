"""Typer adapter for the shared headless OAuth/MCP probe."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

import typer
from testmcpy_oauth_probe.config import ConfigError, dump_manifest_schema, load_manifest
from testmcpy_oauth_probe.models import Correlation
from testmcpy_oauth_probe.reporters import to_human, to_json, to_jsonl, to_junit
from testmcpy_oauth_probe.runner import ProbeRunner

from testmcpy.cli.app import app, console

auth_app = typer.Typer(
    name="auth",
    help="Headless OAuth/MCP interoperability checks (not formal certification)",
    no_args_is_help=True,
)
app.add_typer(auth_app, name="auth")


@auth_app.command("validate")
def validate(config: Path = typer.Option(..., "--config", exists=True, dir_okay=False)) -> None:
    """Validate the versioned manifest without resolving secrets or using the network."""
    try:
        manifest = load_manifest(config)
    except ConfigError as exc:
        console.print(f"[red]Configuration error:[/red] {exc}")
        raise typer.Exit(2)
    console.print(
        f"[green]Valid[/green] {manifest.schema}: {len(manifest.targets)} target(s), "
        f"{len(manifest.profiles)} profile(s)"
    )


@auth_app.command("schema")
def schema() -> None:
    """Print the current manifest JSON Schema."""
    console.print(dump_manifest_schema(), markup=False)


@auth_app.command("check")
def check(
    config: Path = typer.Option(..., "--config", exists=True, dir_okay=False),
    target: Optional[list[str]] = typer.Option(None, "--target"),
    profile: Optional[str] = typer.Option(None, "--profile"),
    output_format: str = typer.Option("human", "--format", help="human, json, or jsonl"),
    output: str = typer.Option("-", "--output"),
    junit: Optional[Path] = typer.Option(None, "--junit", dir_okay=False),
    run_id: Optional[str] = typer.Option(None, "--run-id"),
    service: Optional[str] = typer.Option(None, "--service"),
    region: Optional[str] = typer.Option(None, "--region"),
    revision: Optional[str] = typer.Option(None, "--revision"),
    deployment_id: Optional[str] = typer.Option(None, "--deployment-id"),
) -> None:
    """Run one or more safe, noninteractive target probes."""
    if output_format not in {"human", "json", "jsonl"}:
        console.print("[red]--format must be human, json, or jsonl[/red]")
        raise typer.Exit(2)
    try:
        manifest = load_manifest(config)
        report = asyncio.run(
            ProbeRunner().run_manifest(
                manifest,
                target_ids=target,
                profile=profile,
                run_id=run_id,
                correlation_override=Correlation(
                    service=service,
                    region=region,
                    revision=revision,
                    deployment_id=deployment_id,
                ),
            )
        )
    except (ConfigError, ValueError) as exc:
        console.print(f"[red]Configuration error:[/red] {exc}")
        raise typer.Exit(2)
    rendered = (
        to_json(report)
        if output_format == "json"
        else to_jsonl(report)
        if output_format == "jsonl"
        else to_human(report)
    )
    if output == "-":
        console.print(rendered, markup=False, end="")
    else:
        Path(output).write_text(rendered, encoding="utf-8")
    if junit is not None:
        junit.write_text(to_junit(report), encoding="utf-8")
    raise typer.Exit(report.exit_code)
