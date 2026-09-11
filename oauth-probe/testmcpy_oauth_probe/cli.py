"""Minimal argparse CLI, independent of testmcpy's UI/LLM dependencies."""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Sequence
from pathlib import Path

from testmcpy_oauth_probe.config import (
    ConfigError,
    dump_manifest_schema,
    dump_report_schema,
    load_manifest,
    loads_manifest,
)
from testmcpy_oauth_probe.models import CONFIG_SCHEMA, Correlation
from testmcpy_oauth_probe.reporters import to_human, to_json, to_jsonl, to_junit
from testmcpy_oauth_probe.runner import ProbeRunner


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="testmcpy-oauth",
        description="Vendor-neutral OAuth/MCP interoperability probe (not formal certification)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate = subparsers.add_parser("validate", help="Validate a manifest without network access")
    validate.add_argument("--config", required=True)
    schema = subparsers.add_parser("schema", help="Print a versioned JSON Schema")
    schema.add_argument("--kind", choices=("manifest", "report"), default="manifest")
    schema.set_defaults(command="schema")
    check = subparsers.add_parser("check", help="Run configured targets headlessly")
    check.add_argument("--config", required=True)
    check.add_argument("--target", action="append", dest="targets")
    check.add_argument("--profile")
    check.add_argument("--format", choices=("human", "json", "jsonl"), default="human")
    check.add_argument("--output", default="-")
    check.add_argument("--junit")
    check.add_argument("--run-id")
    check.add_argument("--service")
    check.add_argument("--region")
    check.add_argument("--revision")
    check.add_argument("--deployment-id")
    discover = subparsers.add_parser("discover", help="Run discovery without credentials")
    discover.add_argument("--url", required=True)
    discover.add_argument("--format", choices=("human", "json", "jsonl"), default="human")
    return parser


def _write(path: str, content: str) -> None:
    if path == "-":
        sys.stdout.write(content)
    else:
        Path(path).write_text(content, encoding="utf-8")


def _render(report_format: str, report: object) -> str:
    from testmcpy_oauth_probe.models import RunReport

    assert isinstance(report, RunReport)
    if report_format == "json":
        return to_json(report)
    if report_format == "jsonl":
        return to_jsonl(report)
    return to_human(report)


async def _run(args: argparse.Namespace) -> int:
    if args.command == "discover":
        manifest = loads_manifest(
            f"""schema: {CONFIG_SCHEMA}
targets:
  discovery:
    mcp_url: {args.url!r}
    oauth:
      flow: none
"""
        )
        report = await ProbeRunner().run_manifest(manifest)
        _write("-", _render(args.format, report))
        return report.exit_code
    manifest = load_manifest(args.config)
    report = await ProbeRunner().run_manifest(
        manifest,
        target_ids=args.targets,
        profile=args.profile,
        run_id=args.run_id,
        correlation_override=Correlation(
            service=args.service,
            region=args.region,
            revision=args.revision,
            deployment_id=args.deployment_id,
        ),
    )
    _write(args.output, _render(args.format, report))
    if args.junit:
        _write(args.junit, to_junit(report))
    return report.exit_code


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "schema":
            print(dump_report_schema() if args.kind == "report" else dump_manifest_schema())
            return 0
        if args.command == "validate":
            manifest = load_manifest(args.config)
            print(
                f"valid {manifest.schema} manifest: {len(manifest.targets)} target(s), "
                f"{len(manifest.profiles)} profile(s)"
            )
            return 0
        return asyncio.run(_run(args))
    except (ConfigError, ValueError) as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
