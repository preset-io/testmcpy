"""Headless CLI: ``python -m testmcpy.gateway_smoke`` / ``testmcpy gateway-smoke``.

There is deliberately no flag that accepts a token, secret or password. Secrets
are read only from the environment variables the config names.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Sequence
from pathlib import Path

from testmcpy.gateway_smoke.config import ConfigError, SmokeConfig, load_config
from testmcpy.gateway_smoke.models import EXIT_CODES, Status
from testmcpy.gateway_smoke.reporters import to_human, to_json, to_junit
from testmcpy.gateway_smoke.runner import blocked_report, run_smoke

EXIT_CODE_HELP = "exit codes: 0 PASS, 1 FAIL, 2 ERROR, 3 BLOCKED"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="testmcpy-gateway-smoke",
        description="Compact, read-only, deterministic MCP gateway smoke lane. "
        "No LLM calls, no writes. " + EXIT_CODE_HELP,
    )
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate", help="Validate a config offline (no network, no secrets)")
    validate.add_argument("--config", required=True, metavar="PATH")
    run = sub.add_parser("run", help="Run the lane. " + EXIT_CODE_HELP)
    run.add_argument("--config", required=True, metavar="PATH")
    run.add_argument("--format", choices=("human", "json"), default="human")
    run.add_argument(
        "--output", default="-", metavar="PATH", help="Report destination ('-' = stdout)"
    )
    run.add_argument("--junit", metavar="PATH", help="Also write JUnit XML here")
    run.add_argument("--run-id")
    run.add_argument(
        "--expect-environment",
        metavar="NAME",
        help="Refuse to run (BLOCKED) unless the config's environment equals NAME",
    )
    run.add_argument(
        "--expect-workspace-id",
        metavar="ID",
        help="Refuse to run (BLOCKED) unless the config's workspace.id equals ID",
    )
    return parser


def _write(path: str, content: str) -> None:
    if path == "-":
        sys.stdout.write(content)
    else:
        Path(path).write_text(content, encoding="utf-8")


def _identity_mismatch(config: SmokeConfig, args: argparse.Namespace) -> str | None:
    if args.expect_environment and config.environment != args.expect_environment:
        return (
            f"config environment {config.environment!r} does not match "
            f"--expect-environment {args.expect_environment!r}"
        )
    if args.expect_workspace_id and config.workspace_id != args.expect_workspace_id:
        return "config workspace.id does not match --expect-workspace-id"
    return None


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "validate":
        try:
            config = load_config(args.config)
        except ConfigError as exc:
            print(f"configuration error: {exc}", file=sys.stderr)
            return EXIT_CODES[Status.BLOCKED]
        placeholders = config.placeholders()
        note = (
            f"; placeholders in {', '.join(placeholders)} (a run would be BLOCKED)"
            if placeholders
            else ""
        )
        print(
            f"valid {config.environment} / {config.workspace_name} config: "
            f"{len(config.fixture.expect) if config.fixture else 0} fixture assertion(s){note}"
        )
        return 0

    try:
        config = load_config(args.config)
        mismatch = _identity_mismatch(config, args)
        if mismatch:
            raise ConfigError(mismatch)
    except ConfigError as exc:
        report = blocked_report(args.config, f"config unusable: {exc}", args.run_id)
    else:
        try:
            report = asyncio.run(run_smoke(config, run_id=args.run_id))
        except KeyboardInterrupt:
            print("interrupted", file=sys.stderr)
            return EXIT_CODES[Status.ERROR]
        except RuntimeError as exc:  # SecretRegistry.assert_clean refused to emit
            print(f"error: {exc}", file=sys.stderr)
            return EXIT_CODES[Status.ERROR]
    try:
        _write(args.output, to_json(report) if args.format == "json" else to_human(report))
        if args.junit:
            _write(args.junit, to_junit(report))
    except OSError as exc:
        # The run happened but its result could not be recorded. That is not a
        # gateway FAIL (exit 1); report it as ERROR so nothing reads it as one.
        print(f"error: cannot write report: {exc.strerror or type(exc).__name__}", file=sys.stderr)
        return EXIT_CODES[Status.ERROR]
    return report.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
