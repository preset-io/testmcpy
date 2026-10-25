"""The three-step gateway smoke lane: protocol/auth, bounded discovery, one read."""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
import uuid
from collections.abc import Callable, Mapping
from dataclasses import replace
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from typing import Any

from testmcpy_oauth_probe.discovery import discover
from testmcpy_oauth_probe.models import (
    AuthFlow,
    CapabilityPolicy,
    ClientAuthMethod,
    Expectations,
    OAuthConfig,
    SecretRef,
    TargetConfig,
    ValueRef,
)
from testmcpy_oauth_probe.models import CheckResult as ProbeCheck
from testmcpy_oauth_probe.models import CheckStatus as ProbeStatus
from testmcpy_oauth_probe.oauth import acquire_token
from testmcpy_oauth_probe.secrets import SecretRegistry, safe_url
from testmcpy_oauth_probe.transport import HttpTransport, HttpxTransport, TransportError

from testmcpy.gateway_smoke.client import McpProtocolError, McpSession, tool_payload
from testmcpy.gateway_smoke.config import Assertion, SmokeConfig, identity_hint
from testmcpy.gateway_smoke.limits import LimitedTransport, LimitExceeded
from testmcpy.gateway_smoke.models import Check, SmokeReport, Status, Step

TransportFactory = Callable[[TargetConfig], HttpTransport]

STEP_IDS = (
    ("protocol_auth", "Protocol and auth"),
    ("tool_discovery", "Bounded tool discovery"),
    ("fixture_read", "Approved fixture read"),
)
_URL_RE = re.compile(r"https?://[^\s\"'<>)\]]+")
_MISSING = object()
_PROBE_STATUS = {
    ProbeStatus.PASS: Status.PASS,
    ProbeStatus.WARN: Status.PASS,
    ProbeStatus.FAIL: Status.FAIL,
    ProbeStatus.ERROR: Status.ERROR,
    ProbeStatus.SKIP: Status.INFO,
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _tool_version() -> str:
    try:
        return version("testmcpy")
    except PackageNotFoundError:
        return "0.0.0+source"


def _ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


def _strip_url_queries(text: str) -> str:
    return _URL_RE.sub(lambda match: safe_url(match.group(0)), text)


def _snippet(value: Any, limit: int = 80) -> str:
    text = json.dumps(value, sort_keys=True, default=str)
    return text if len(text) <= limit else text[: limit - 1] + "…"


class _Run:
    """Mutable state shared by the steps, kept outside the timeout boundary so a
    timed-out run still reports everything gathered so far."""

    def __init__(self) -> None:
        self.steps = [Step(id=step_id, title=title) for step_id, title in STEP_IDS]
        self.current = self.steps[0]
        self.tools: dict[str, dict[str, Any]] | None = None
        self.session: McpSession | None = None

    def step(self, step_id: str) -> Step:
        self.current = next(s for s in self.steps if s.id == step_id)
        return self.current

    def skip_unrun(self, reason: str) -> None:
        for step in self.steps:
            if not step.checks and step.skipped_reason is None:
                step.skipped_reason = reason


def _from_probe(check: ProbeCheck, *, blocked: bool = False, prefix: str = "") -> Check:
    status = _PROBE_STATUS[check.status]
    message = check.message
    if blocked and status in (Status.FAIL, Status.ERROR):
        status = Status.BLOCKED
        message = f"{prefix}{message}"
    return Check(
        id=check.id,
        status=status,
        message=message,
        http_status=check.http_status,
        duration_ms=check.duration_ms,
        evidence=dict(check.evidence),
    )


def build_target(config: SmokeConfig) -> TargetConfig:
    auth = config.auth
    if auth.mode == "bearer":
        oauth = OAuthConfig(
            flow=AuthFlow.BEARER,
            access_token=SecretRef(env=auth.access_token_env or ""),
            error_probe=False,
        )
    else:
        oauth = OAuthConfig(
            flow=AuthFlow.CLIENT_CREDENTIALS,
            client_id=ValueRef(value=auth.client_id, env=auth.client_id_env),
            client_secret=SecretRef(env=auth.client_secret_env or ""),
            client_auth_method=ClientAuthMethod(auth.client_auth_method),
            scopes=auth.scopes,
            resource=auth.resource,
            token_endpoint=auth.token_endpoint,
            error_probe=False,
        )
    needs_as_metadata = auth.mode == "client_credentials" and auth.token_endpoint is None
    prm_policy = (
        CapabilityPolicy.REQUIRED
        if config.require_challenge_metadata
        else CapabilityPolicy.SUPPORTED
    )
    expectations = Expectations(
        issuers=config.expected_issuers,
        resources=config.expected_resources,
        token_issuers=auth.expected_token_issuers,
        audiences=auth.expected_audiences,
        unauthorized_status=config.unauthorized_status,
        capabilities={
            "bearer_challenge": CapabilityPolicy.REQUIRED,
            "protected_resource_metadata": prm_policy,
            "authorization_server_metadata": (
                CapabilityPolicy.REQUIRED if needs_as_metadata else CapabilityPolicy.IGNORE
            ),
            # Optional discovery documents the lane does not need cost calls.
            "oidc_discovery": CapabilityPolicy.IGNORE,
            "dynamic_client_registration": CapabilityPolicy.IGNORE,
        },
    )
    return TargetConfig(
        id="gateway-smoke",
        mcp_url=config.mcp_url,
        spec_profile=config.spec_profile,
        oauth=oauth,
        expectations=expectations,
        # The inner HTTP client gets a little slack so LimitedTransport's hard
        # per-call deadline fires first and reports the limit by name.
        timeout_seconds=config.limits.per_call_timeout_seconds + 1.0,
        max_response_bytes=config.limits.max_response_bytes,
        transient_retries=0,
        allow_http_loopback=config.allow_http_loopback,
        allow_private_network=config.allow_private_network,
    )


def preflight(config: SmokeConfig, environ: Mapping[str, str]) -> dict[str, list[Check]]:
    """Everything that can be decided without the network. Any entry means BLOCKED."""
    blocked: dict[str, list[Check]] = {}

    def block(step_id: str, check_id: str, message: str, **evidence: Any) -> None:
        blocked.setdefault(step_id, []).append(
            Check(id=check_id, status=Status.BLOCKED, message=message, evidence=evidence)
        )

    placeholders = config.placeholders()
    if placeholders:
        block(
            "protocol_auth",
            "preflight.placeholders",
            "config still contains placeholder values; no request was made",
            fields=placeholders,
        )
    missing = [name for name in config.auth.env_names() if not environ.get(name)]
    if missing:
        block(
            "protocol_auth",
            "preflight.credentials",
            "required credential environment variable(s) are unset; no request was made",
            missing_env=missing,
        )
    if config.fixture is None:
        block(
            "fixture_read",
            "preflight.fixture",
            "no approved fixture is configured; no request was made",
        )
    return blocked


def _mcp_check(check_id: str, status: Status, message: str, started: float, **extra: Any) -> Check:
    http_status = extra.pop("http_status", None)
    return Check(
        id=check_id,
        status=status,
        message=message,
        http_status=http_status,
        duration_ms=_ms(started),
        evidence=extra,
    )


def _transport_check(check_id: str, exc: Exception, started: float) -> Check:
    kind = "limit exceeded" if isinstance(exc, LimitExceeded) else "transport failure"
    return _mcp_check(check_id, Status.ERROR, f"{kind}: {exc}", started)


async def _step_protocol_auth(
    config: SmokeConfig,
    target: TargetConfig,
    transport: LimitedTransport,
    registry: SecretRegistry,
    run: _Run,
) -> None:
    step = run.step("protocol_auth")
    began = time.monotonic()
    transport.phase = "discovery"
    discovery = await discover(target, transport)
    step.checks.extend(_from_probe(check) for check in discovery.checks)

    transport.phase = "token"
    token = await acquire_token(
        target, transport, registry, discovery.token_endpoint, discovery.resource
    )
    if token.access_token is None:
        unavailable = (
            transport.phase_unavailable("token")
            or any(c.id == "oauth.token.endpoint" for c in token.checks)
            or any(
                c.id == "oauth.token.acquire" and c.status is ProbeStatus.FAIL for c in token.checks
            )
        )
        step.checks.extend(
            _from_probe(c, blocked=unavailable, prefix="credential unavailable, not testable: ")
            for c in token.checks
        )
        step.duration_ms = _ms(began)
        run.skip_unrun("no access token was obtained, so no authenticated request was made")
        return
    step.checks.extend(_from_probe(c) for c in token.checks)

    transport.phase = "initialize"
    session = McpSession(transport, config.mcp_url, config.protocol_version, token.access_token)
    started = time.monotonic()
    try:
        response, message = await session.request(
            "initialize-1",
            "initialize",
            {
                "protocolVersion": config.protocol_version,
                "capabilities": {},
                "clientInfo": {"name": "testmcpy-gateway-smoke", "version": "1"},
            },
        )
        if message is None:
            step.checks.append(
                _mcp_check(
                    "mcp.initialize.http_status",
                    Status.FAIL,
                    f"authenticated initialize returned HTTP {response.status}; expected 200",
                    started,
                    http_status=response.status,
                )
            )
            step.duration_ms = _ms(began)
            run.skip_unrun("initialize did not succeed")
            return
        step.checks.append(
            _mcp_check(
                "mcp.initialize.http_status",
                Status.PASS,
                "authenticated initialize returned HTTP 200",
                started,
                http_status=response.status,
            )
        )
        result = message.get("result")
        if "error" in message or not isinstance(result, Mapping):
            error = message.get("error")
            rpc_code = error.get("code") if isinstance(error, Mapping) else None
            step.checks.append(
                _mcp_check(
                    "mcp.initialize.contract",
                    Status.FAIL,
                    "initialize returned a JSON-RPC error or no result object",
                    started,
                    rpc_error_code=rpc_code,
                )
            )
            step.duration_ms = _ms(began)
            run.skip_unrun("initialize did not succeed")
            return
        protocol = result.get("protocolVersion")
        server_info = result.get("serverInfo")
        capabilities = result.get("capabilities")
        contract_ok = (
            protocol == config.protocol_version
            and isinstance(server_info, Mapping)
            and isinstance(capabilities, Mapping)
        )
        step.checks.append(
            _mcp_check(
                "mcp.initialize.contract",
                Status.PASS if contract_ok else Status.FAIL,
                "initialize negotiated the requested protocol version"
                if contract_ok
                else "initialize response violates the protocol-version or shape contract",
                started,
                protocol_version=protocol if isinstance(protocol, str) else "invalid",
                requested_protocol_version=config.protocol_version,
                server_info_present=isinstance(server_info, Mapping),
                capabilities_present=isinstance(capabilities, Mapping),
            )
        )
        if not contract_ok or not isinstance(capabilities, Mapping):
            step.duration_ms = _ms(began)
            run.skip_unrun("initialize did not satisfy the protocol contract")
            return
        absent = sorted(set(config.required_capabilities) - set(capabilities))
        step.checks.append(
            _mcp_check(
                "mcp.initialize.capabilities",
                Status.FAIL if absent else Status.PASS,
                f"server does not advertise required capabilities: {', '.join(absent)}"
                if absent
                else "server advertises every required capability",
                started,
                required=list(config.required_capabilities),
                missing=absent,
            )
        )
        session.session_id = response.headers.get("mcp-session-id")
        registry.register(session.session_id)

        started = time.monotonic()
        ack = await session.notify("notifications/initialized")
        accepted = ack.status in (200, 202)
        step.checks.append(
            _mcp_check(
                "mcp.initialized.http_status",
                Status.PASS if accepted else Status.FAIL,
                f"initialized notification returned HTTP {ack.status}; expected 200 or 202",
                started,
                http_status=ack.status,
            )
        )
        step.duration_ms = _ms(began)
        if not accepted or absent:
            run.skip_unrun("session was not established")
            return
        run.session = session
    except McpProtocolError as exc:
        step.checks.append(_mcp_check("mcp.initialize.protocol", Status.ERROR, str(exc), started))
        step.duration_ms = _ms(began)
        run.skip_unrun("initialize response was malformed")
    except TransportError as exc:
        step.checks.append(_transport_check("mcp.initialize.transport", exc, started))
        step.duration_ms = _ms(began)
        run.skip_unrun("transport failed during initialize")


async def _step_discovery(config: SmokeConfig, transport: LimitedTransport, run: _Run) -> None:
    session = run.session
    assert session is not None
    step = run.step("tool_discovery")
    began = time.monotonic()
    transport.phase = "tools_list"
    spec = config.discovery
    tools: dict[str, dict[str, Any]] = {}
    pages = 0
    body_bytes = 0
    cursor: str | None = None
    exhausted = False
    started = time.monotonic()
    try:
        while pages < spec.max_pages:
            started = time.monotonic()
            params: dict[str, Any] = {} if cursor is None else {"cursor": cursor}
            response, message = await session.request(
                f"tools-list-{pages + 1}", "tools/list", params
            )
            if message is None:
                step.checks.append(
                    _mcp_check(
                        "tools_list.http_status",
                        Status.FAIL,
                        f"tools/list returned HTTP {response.status}; expected 200",
                        started,
                        http_status=response.status,
                    )
                )
                step.duration_ms = _ms(began)
                run.skip_unrun("tool catalogue unavailable")
                return
            pages += 1
            body_bytes += len(response.body)
            result = message.get("result")
            if "error" in message or not isinstance(result, Mapping):
                step.checks.append(
                    _mcp_check(
                        "tools_list.contract",
                        Status.FAIL,
                        "tools/list returned a JSON-RPC error",
                        started,
                    )
                )
                step.duration_ms = _ms(began)
                run.skip_unrun("tool catalogue unavailable")
                return
            page_tools = result.get("tools")
            if not isinstance(page_tools, list) or not all(
                isinstance(t, Mapping) for t in page_tools
            ):
                raise McpProtocolError("tools/list tools is not an array of objects")
            for tool in page_tools:
                name = tool.get("name")
                if (
                    not isinstance(name, str)
                    or not name
                    or not isinstance(tool.get("inputSchema"), Mapping)
                ):
                    raise McpProtocolError("tool entries require a name and an inputSchema object")
                if name in tools:
                    raise McpProtocolError("tools/list returned a duplicate tool name")
                tools[name] = dict(tool)
            next_cursor = result.get("nextCursor")
            if next_cursor is None:
                exhausted = True
                break
            if not isinstance(next_cursor, str) or not next_cursor:
                raise McpProtocolError("tools/list nextCursor is invalid")
            cursor = next_cursor
    except McpProtocolError as exc:
        step.checks.append(_mcp_check("tools_list.protocol", Status.ERROR, str(exc), started))
        step.duration_ms = _ms(began)
        run.skip_unrun("tool catalogue was malformed")
        return
    except TransportError as exc:
        step.checks.append(_transport_check("tools_list.transport", exc, started))
        step.duration_ms = _ms(began)
        run.skip_unrun("transport failed during tool discovery")
        return

    run.tools = tools
    step.checks.append(
        _mcp_check(
            "tools_list.catalogue",
            Status.PASS if exhausted else Status.FAIL,
            "tool catalogue enumerated within the page cap"
            if exhausted
            else f"catalogue not exhausted within the {spec.max_pages}-page cap",
            started,
            pages=pages,
            tool_count=len(tools),
        )
    )
    step.checks.append(
        _mcp_check(
            "tools_list.budget.tool_count",
            Status.PASS if len(tools) <= spec.max_tools else Status.FAIL,
            f"{len(tools)} tools advertised; budget is {spec.max_tools}",
            started,
            tool_count=len(tools),
            budget=spec.max_tools,
        )
    )
    step.checks.append(
        _mcp_check(
            "tools_list.budget.bytes",
            Status.PASS if body_bytes <= spec.max_bytes else Status.FAIL,
            f"tools/list bodies total {body_bytes} bytes; budget is {spec.max_bytes}",
            started,
            bytes=body_bytes,
            budget=spec.max_bytes,
        )
    )
    for required in spec.required_tools:
        tool = tools.get(required.name)
        if tool is None:
            step.checks.append(
                _mcp_check(
                    f"tools_list.required.{required.name}",
                    Status.FAIL,
                    f"required tool {required.name!r} is not advertised",
                    started,
                )
            )
            continue
        schema = tool["inputSchema"]
        properties = schema.get("properties")
        properties = properties if isinstance(properties, Mapping) else {}
        required_args = schema.get("required")
        required_args = required_args if isinstance(required_args, list) else []
        missing_props = [p for p in required.properties if p not in properties]
        missing_required = [r for r in required.required if r not in required_args]
        ok = not missing_props and not missing_required
        step.checks.append(
            _mcp_check(
                f"tools_list.required.{required.name}",
                Status.PASS if ok else Status.FAIL,
                f"required tool {required.name!r} is advertised with the expected shape"
                if ok
                else f"required tool {required.name!r} is advertised but its input shape differs",
                started,
                missing_properties=missing_props,
                missing_required_arguments=missing_required,
            )
        )
    step.duration_ms = _ms(began)


def _walk(payload: Any, path: str) -> Any:
    node = payload
    for part in path.split("."):
        if isinstance(node, Mapping) and part in node:
            node = node[part]
        elif isinstance(node, list) and part.isdigit() and int(part) < len(node):
            node = node[int(part)]
        else:
            return _MISSING
    return node


def _json_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    return "object"


def _same(actual: Any, expected: Any) -> bool:
    numeric = (int, float)
    if (
        isinstance(actual, numeric)
        and isinstance(expected, numeric)
        and not isinstance(actual, bool)
        and not isinstance(expected, bool)
    ):
        return bool(actual == expected)
    return json.dumps(actual, sort_keys=True) == json.dumps(expected, sort_keys=True)


def evaluate_assertion(payload: Any, assertion: Assertion) -> tuple[bool, str, dict[str, Any]]:
    actual = _walk(payload, assertion.path)
    present = actual is not _MISSING
    evidence: dict[str, Any] = {"path": assertion.path, "op": assertion.op, "present": present}
    op, expected = assertion.op, assertion.expected
    if op == "exists":
        ok = present == expected
        return ok, f"{assertion.path} exists={present}; expected {expected}", evidence
    if not present:
        return False, f"{assertion.path} is absent", evidence
    evidence["actual_type"] = _json_type(actual)
    if op == "type":
        ok = _json_type(actual) == expected or (
            expected == "number" and _json_type(actual) == "integer"
        )
    elif op == "equals":
        ok = _same(actual, expected)
    elif op == "contains":
        if isinstance(actual, list):
            ok = any(_same(item, expected) for item in actual)
        else:
            ok = isinstance(actual, str) and isinstance(expected, str) and expected in actual
    else:  # min_length
        ok = isinstance(actual, (list, str, dict)) and len(actual) >= int(expected)
    if not ok:
        evidence["actual"] = _snippet(actual)
        evidence["expected"] = _snippet(expected)
    return ok, f"{assertion.path} {op} {'matched' if ok else 'did not match'}", evidence


async def _step_fixture(config: SmokeConfig, transport: LimitedTransport, run: _Run) -> None:
    session, tools, fixture = run.session, run.tools, config.fixture
    assert session is not None and tools is not None and fixture is not None
    step = run.step("fixture_read")
    began = time.monotonic()
    started = time.monotonic()
    advertised = tools.get(fixture.tool)
    if advertised is None:
        step.checks.append(
            _mcp_check(
                "fixture.tool.advertised",
                Status.FAIL,
                f"fixture tool {fixture.tool!r} is not advertised; no call was made",
                started,
            )
        )
        step.duration_ms = _ms(began)
        return
    step.checks.append(
        _mcp_check("fixture.tool.advertised", Status.PASS, "fixture tool is advertised", started)
    )
    annotations = advertised.get("annotations")
    annotations = annotations if isinstance(annotations, Mapping) else {}
    if fixture.inner_tool_argument is None and (
        annotations.get("destructiveHint") is True or annotations.get("readOnlyHint") is False
    ):
        step.checks.append(
            _mcp_check(
                "fixture.read_only.guard",
                Status.BLOCKED,
                "fixture tool advertises itself as not read-only; refusing to call it",
                started,
            )
        )
        step.duration_ms = _ms(began)
        return
    step.checks.append(
        _mcp_check(
            "fixture.workspace.binding",
            Status.PASS if fixture.workspace_argument else Status.INFO,
            f"call is bound to the configured workspace through argument {fixture.workspace_argument!r}"
            if fixture.workspace_argument
            else "no workspace_argument configured; identity is asserted only through fixture.expect",
            started,
            workspace_id=config.workspace_id,
        )
    )
    transport.phase = "fixture_call"
    started = time.monotonic()
    try:
        response, message = await session.request(
            "fixture-1", "tools/call", {"name": fixture.tool, "arguments": fixture.arguments}
        )
        if message is None:
            step.checks.append(
                _mcp_check(
                    "fixture.call.http_status",
                    Status.FAIL,
                    f"fixture tools/call returned HTTP {response.status}; expected 200",
                    started,
                    http_status=response.status,
                )
            )
            step.duration_ms = _ms(began)
            return
        result = message.get("result")
        if "error" in message or not isinstance(result, Mapping):
            error = message.get("error")
            rpc_code = error.get("code") if isinstance(error, Mapping) else None
            step.checks.append(
                _mcp_check(
                    "fixture.call.result",
                    Status.FAIL,
                    "fixture tools/call returned a JSON-RPC error",
                    started,
                    rpc_error_code=rpc_code,
                )
            )
            step.duration_ms = _ms(began)
            return
        if result.get("isError") is True:
            step.checks.append(
                _mcp_check(
                    "fixture.call.result",
                    Status.FAIL,
                    "fixture tool reported isError=true",
                    started,
                    detail=_snippet(result.get("content"), 160),
                )
            )
            step.duration_ms = _ms(began)
            return
        payload = tool_payload(dict(result))
        step.checks.append(
            _mcp_check(
                "fixture.call.result", Status.PASS, "fixture tool returned a JSON result", started
            )
        )
    except McpProtocolError as exc:
        step.checks.append(_mcp_check("fixture.call.protocol", Status.ERROR, str(exc), started))
        step.duration_ms = _ms(began)
        return
    except TransportError as exc:
        step.checks.append(_transport_check("fixture.call.transport", exc, started))
        step.duration_ms = _ms(began)
        return
    for index, assertion in enumerate(fixture.expect):
        ok, message_text, evidence = evaluate_assertion(payload, assertion)
        step.checks.append(
            Check(
                id=f"fixture.expect.{index}",
                status=Status.PASS if ok else Status.FAIL,
                message=message_text,
                evidence=evidence,
            )
        )
    step.duration_ms = _ms(began)


async def _execute(
    config: SmokeConfig,
    target: TargetConfig,
    transport: LimitedTransport,
    registry: SecretRegistry,
    run: _Run,
) -> None:
    await _step_protocol_auth(config, target, transport, registry, run)
    if run.session is None:
        return
    await _step_discovery(config, transport, run)
    if run.tools is None:
        run.skip_unrun("tool catalogue unavailable")
        return
    await _step_fixture(config, transport, run)


def _sanitize(report: SmokeReport, registry: SecretRegistry) -> SmokeReport:
    def text(value: str) -> str:
        return _strip_url_queries(registry.scrub_text(value))

    def scrub(value: Any, key: str | None = None) -> Any:
        scrubbed = registry.scrub(value, key)
        if isinstance(scrubbed, str):
            return _strip_url_queries(scrubbed)
        if isinstance(scrubbed, dict):
            return {k: scrub(v, k) for k, v in scrubbed.items()}
        if isinstance(scrubbed, list):
            return [scrub(item) for item in scrubbed]
        return scrubbed

    steps = [
        replace(
            step,
            checks=[
                replace(check, message=text(check.message), evidence=scrub(check.evidence))
                for check in step.checks
            ],
            skipped_reason=text(step.skipped_reason) if step.skipped_reason else None,
        )
        for step in report.steps
    ]
    sanitized = replace(report, steps=steps)
    registry.assert_clean(json.dumps(sanitized.to_dict(), sort_keys=True))
    return sanitized


async def run_smoke(
    config: SmokeConfig,
    *,
    run_id: str | None = None,
    transport_factory: TransportFactory | None = None,
    environ: Mapping[str, str] | None = None,
) -> SmokeReport:
    env = environ if environ is not None else os.environ
    registry = SecretRegistry(dict(env))
    started_at = _utc_now()
    started = time.monotonic()
    run = _Run()
    target = build_target(config)
    limiter: LimitedTransport | None = None

    blocked = preflight(config, env)
    if blocked:
        # No socket is opened. Steps that were not themselves blocked say why
        # they did not run, so the report cannot be read as a partial pass.
        for step_id, checks in blocked.items():
            run.step(step_id).checks.extend(checks)
        run.skip_unrun("not run: the lane is blocked before any network call")
    else:
        factory = transport_factory or HttpxTransport
        limiter = LimitedTransport(factory(target), config.limits)
        try:
            await asyncio.wait_for(
                _execute(config, target, limiter, registry, run),
                timeout=config.limits.total_timeout_seconds,
            )
        except asyncio.TimeoutError:
            run.current.checks.append(
                Check(
                    id="lane.total_timeout",
                    status=Status.ERROR,
                    message=f"overall timeout of {config.limits.total_timeout_seconds:g}s exceeded",
                )
            )
            run.skip_unrun("overall timeout exceeded")
        except Exception as exc:  # final containment: nothing escapes the reporter
            run.current.checks.append(
                Check(
                    id="lane.unhandled",
                    status=Status.ERROR,
                    message=f"unexpected {type(exc).__name__}: {exc}"
                    if str(exc)
                    else type(exc).__name__,
                )
            )
            run.skip_unrun("lane stopped after an unexpected error")
        finally:
            try:
                await limiter.aclose()
            except Exception:
                pass

    calls = limiter.calls if limiter is not None else []
    report = SmokeReport(
        run_id=run_id or str(uuid.uuid4()),
        tool_version=_tool_version(),
        started_at=started_at,
        duration_ms=_ms(started),
        environment=config.environment,
        workspace_id=config.workspace_id,
        workspace_name=config.workspace_name,
        mcp_url=safe_url(config.mcp_url),
        spec_profile=config.spec_profile,
        steps=run.steps,
        limits={
            "total_timeout_seconds": config.limits.total_timeout_seconds,
            "per_call_timeout_seconds": config.limits.per_call_timeout_seconds,
            "max_calls": config.limits.max_calls,
            "max_response_bytes": config.limits.max_response_bytes,
            "max_total_bytes": config.limits.max_total_bytes,
            "discovery_max_pages": config.discovery.max_pages,
            "discovery_max_tools": config.discovery.max_tools,
            "discovery_max_bytes": config.discovery.max_bytes,
        },
        usage={
            "calls": len(calls),
            "bytes": limiter.total_bytes if limiter is not None else 0,
            "elapsed_ms": _ms(started),
        },
        calls=calls,
    )
    return _sanitize(report, registry)


def blocked_report(config_path: str, reason: str, run_id: str | None = None) -> SmokeReport:
    """A BLOCKED report for a config that could not be used.

    It carries whatever identity could be read from the file so the result still
    says what the run was aiming at. No request is made.
    """
    environment, workspace_id, workspace_name = identity_hint(config_path)
    run = _Run()
    run.steps[0].checks.append(Check(id="preflight.config", status=Status.BLOCKED, message=reason))
    run.skip_unrun("not run: the lane is blocked before any network call")
    report = SmokeReport(
        run_id=run_id or str(uuid.uuid4()),
        tool_version=_tool_version(),
        started_at=_utc_now(),
        duration_ms=0,
        environment=environment,
        workspace_id=workspace_id,
        workspace_name=workspace_name,
        mcp_url=None,
        spec_profile=None,
        steps=run.steps,
        limits={},
        usage={"calls": 0, "bytes": 0, "elapsed_ms": 0},
        calls=[],
    )
    return _sanitize(report, SecretRegistry({}))
