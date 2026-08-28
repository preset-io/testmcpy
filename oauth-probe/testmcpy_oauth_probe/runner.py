"""Headless orchestration and adapter/library API."""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import Callable, Sequence
from dataclasses import replace
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version

from testmcpy_oauth_probe.discovery import discover
from testmcpy_oauth_probe.mcp import probe_mcp
from testmcpy_oauth_probe.models import (
    REPORT_SCHEMA,
    CheckResult,
    CheckStatus,
    Correlation,
    Manifest,
    ProbeReport,
    RunReport,
    TargetConfig,
)
from testmcpy_oauth_probe.oauth import acquire_token
from testmcpy_oauth_probe.secrets import SecretRegistry
from testmcpy_oauth_probe.transport import (
    HttpTransport,
    HttpxTransport,
    TransportError,
    validate_url_syntax,
)

TransportFactory = Callable[[TargetConfig], HttpTransport]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _tool_version() -> str:
    for package in ("testmcpy-oauth-probe", "testmcpy"):
        try:
            return version(package)
        except PackageNotFoundError:
            continue
    return "0.0.0+source"


def _merge_correlation(base: Correlation, override: Correlation | None) -> Correlation:
    if override is None:
        return base
    return Correlation(
        service=override.service or base.service,
        region=override.region or base.region,
        revision=override.revision or base.revision,
        deployment_id=override.deployment_id or base.deployment_id,
    )


def _sanitize_check(check: CheckResult, registry: SecretRegistry) -> CheckResult:
    return replace(
        check,
        message=registry.scrub_text(check.message),
        evidence=registry.scrub(check.evidence),
    )


class ProbeRunner:
    """Typed runner shared by the CLI and application adapters."""

    def __init__(
        self,
        *,
        transport_factory: TransportFactory | None = None,
        environ: dict[str, str] | None = None,
    ) -> None:
        self._transport_factory = transport_factory or HttpxTransport
        self._environ = environ

    async def run_target(
        self,
        target: TargetConfig,
        *,
        correlation_override: Correlation | None = None,
    ) -> ProbeReport:
        started_at = _utc_now()
        started = time.monotonic()
        checks: list[CheckResult] = []
        registry = SecretRegistry(self._environ)
        transport = self._transport_factory(target)
        try:
            try:
                validate_url_syntax(target.mcp_url, target)
                checks.append(
                    CheckResult(
                        id="target.url.policy",
                        stage="target",
                        status=CheckStatus.PASS,
                        message="target URL satisfies syntax and transport policy",
                        reference="RFC 9700 §4.17",
                    )
                )
            except TransportError as exc:
                checks.append(
                    CheckResult(
                        id="target.url.policy",
                        stage="target",
                        status=CheckStatus.ERROR,
                        message=str(exc),
                        reference="RFC 9700 §4.17",
                    )
                )
                return self._report(
                    target, correlation_override, started_at, started, checks, registry
                )

            discovery = await discover(target, transport)
            checks.extend(discovery.checks)
            token = await acquire_token(
                target,
                transport,
                registry,
                discovery.token_endpoint,
            )
            checks.extend(token.checks)
            if token.access_token:
                mcp_result = await probe_mcp(target, transport, registry, token.access_token)
                checks.extend(mcp_result.checks)
            else:
                checks.append(
                    CheckResult(
                        id="mcp.authenticated.roundtrip",
                        stage="mcp_initialize",
                        status=CheckStatus.SKIP,
                        applicable=False,
                        message="authenticated MCP round trip skipped because no access token is available",
                    )
                )
        except (
            Exception
        ) as exc:  # final containment: no transport/client exception escapes reporters
            checks.append(
                CheckResult(
                    id="runner.unhandled",
                    stage="runner",
                    status=CheckStatus.ERROR,
                    message=registry.scrub_text(str(exc) or type(exc).__name__),
                )
            )
        finally:
            try:
                await transport.aclose()
            except Exception:
                # Closing must never turn an already-sanitized result into an
                # escaping transport exception. No response data is emitted here.
                pass
        return self._report(target, correlation_override, started_at, started, checks, registry)

    def _report(
        self,
        target: TargetConfig,
        correlation_override: Correlation | None,
        started_at: str,
        started: float,
        checks: list[CheckResult],
        registry: SecretRegistry,
    ) -> ProbeReport:
        report = ProbeReport(
            target_id=target.id,
            spec_profile=target.spec_profile,
            started_at=started_at,
            duration_ms=int((time.monotonic() - started) * 1000),
            correlation=_merge_correlation(target.correlation, correlation_override),
            checks=tuple(_sanitize_check(check, registry) for check in checks),
        )
        rendered = json.dumps(report.to_dict(), sort_keys=True)
        registry.assert_clean(rendered)
        return report

    async def run_manifest(
        self,
        manifest: Manifest,
        *,
        target_ids: Sequence[str] | None = None,
        profile: str | None = None,
        run_id: str | None = None,
        correlation_override: Correlation | None = None,
    ) -> RunReport:
        if target_ids and profile:
            raise ValueError("target_ids and profile are mutually exclusive")
        if profile is not None:
            if profile not in manifest.profiles:
                raise ValueError(f"unknown profile {profile!r}")
            selected = manifest.profiles[profile].targets
        elif target_ids:
            selected = tuple(target_ids)
        else:
            selected = tuple(manifest.targets)
        unknown = sorted(set(selected) - set(manifest.targets))
        if unknown:
            raise ValueError(f"unknown target(s): {', '.join(unknown)}")
        started_at = _utc_now()
        started = time.monotonic()
        reports = []
        for target_id in selected:
            reports.append(
                await self.run_target(
                    manifest.targets[target_id],
                    correlation_override=correlation_override,
                )
            )
        return RunReport(
            schema=REPORT_SCHEMA,
            run_id=run_id or str(uuid.uuid4()),
            tool_version=_tool_version(),
            started_at=started_at,
            duration_ms=int((time.monotonic() - started) * 1000),
            reports=tuple(reports),
        )


async def run_manifest(
    manifest: Manifest,
    *,
    target_ids: Sequence[str] | None = None,
    profile: str | None = None,
    run_id: str | None = None,
    correlation_override: Correlation | None = None,
    transport_factory: TransportFactory | None = None,
    environ: dict[str, str] | None = None,
) -> RunReport:
    return await ProbeRunner(
        transport_factory=transport_factory,
        environ=environ,
    ).run_manifest(
        manifest,
        target_ids=target_ids,
        profile=profile,
        run_id=run_id,
        correlation_override=correlation_override,
    )
