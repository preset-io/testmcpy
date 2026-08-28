"""Deterministic black-box OAuth/MCP fixture matrix for the headless probe."""

from __future__ import annotations

import base64
import json
from collections.abc import Mapping
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from testmcpy_oauth_probe.config import (
    ConfigError,
    load_manifest,
    loads_manifest,
    manifest_json_schema,
    report_json_schema,
)
from testmcpy_oauth_probe.discovery import (
    authorization_metadata_urls,
    parse_bearer_challenge,
    protected_resource_metadata_urls,
)
from testmcpy_oauth_probe.models import CheckStatus
from testmcpy_oauth_probe.reporters import to_human, to_json, to_jsonl, to_junit
from testmcpy_oauth_probe.runner import ProbeRunner
from testmcpy_oauth_probe.secrets import safe_url
from testmcpy_oauth_probe.transport import HttpResponse

ACCESS_SECRET = "access-token-secret-canary-123456789"
REFRESH_SECRET = "refresh-token-secret-canary-123456789"
CLIENT_SECRET = "client-secret-canary-123456789"
SESSION_SECRET = "session-secret-canary-123456789"
AUTH_ISSUER = "https://auth.example.test/tenant"
MCP_URL = "https://healthy.example.test/mcp"


def _jwt(*, issuer: str = AUTH_ISSUER, audience: str = "mcp-api") -> str:
    def encode(value: dict[str, Any]) -> str:
        return base64.urlsafe_b64encode(json.dumps(value).encode()).rstrip(b"=").decode()

    return f"{encode({'alg': 'HS256'})}.{encode({'iss': issuer, 'aud': audience})}.signature"


def _manifest(*, flow: str = "refresh_token", capabilities: str = "supported") -> str:
    oauth: dict[str, Any] = {"flow": flow}
    if flow != "none":
        oauth.update(
            {
                "refresh_token": {"env": "TEST_REFRESH_TOKEN"},
                "client_id": {"env": "TEST_CLIENT_ID"},
                "client_secret": {"env": "TEST_CLIENT_SECRET"},
                "client_auth_method": "client_secret_basic",
                "scopes": ["mcp.read"],
                "resource": MCP_URL,
                "audience": "mcp-api",
            }
        )
    return json.dumps(
        {
            "schema": "testmcpy.io/oauth-smoke/v1",
            "targets": {
                "healthy": {
                    "mcp_url": MCP_URL,
                    "correlation": {
                        "service": "example-mcp",
                        "region": "test-region",
                        "revision": "example-revision",
                    },
                    "oauth": oauth,
                    "expectations": {
                        "issuers": [AUTH_ISSUER],
                        "token_issuers": [AUTH_ISSUER],
                        "resources": [MCP_URL],
                        "audiences": ["mcp-api"],
                        "scopes": ["mcp.read"],
                        "min_tools": 1,
                        "grants": {"refresh_token": "required"},
                        "auth_methods": {"client_secret_basic": "required"},
                        "endpoints": {"token_endpoint": "required"},
                        "capabilities": {
                            "oidc_discovery": capabilities,
                            "dynamic_client_registration": "supported",
                        },
                    },
                }
            },
            "profiles": {"canary": {"targets": ["healthy"]}},
        }
    )


class FixtureTransport:
    """Programmable example.test AS + protected resource fixture."""

    def __init__(
        self,
        _target: object,
        *,
        scenario: str = "healthy",
    ) -> None:
        self.scenario = scenario
        self.requests: list[tuple[str, str, Mapping[str, str], Mapping[str, str] | None]] = []
        self.closed = False

    def response(
        self,
        url: str,
        status: int,
        *,
        payload: Any | None = None,
        body: bytes | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> HttpResponse:
        response_headers = {key.lower(): value for key, value in (headers or {}).items()}
        if payload is not None:
            body = json.dumps(payload).encode()
            response_headers.setdefault("content-type", "application/json")
        return HttpResponse(
            status=status,
            headers=response_headers,
            body=body or b"",
            latency_ms=1,
            url=url,
        )

    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        json_body: Mapping[str, Any] | None = None,
        form_body: Mapping[str, str] | None = None,
        retry_safe: bool = False,
    ) -> HttpResponse:
        del retry_safe
        headers = headers or {}
        self.requests.append((method, url, headers, form_body))
        if url == MCP_URL and method == "POST":
            rpc_method = json_body.get("method") if json_body else None
            bearer = headers.get("authorization")
            if bearer is None:
                challenge = (
                    "Basic realm=legacy, "
                    'Bearer realm="mcp", scope="mcp.read", '
                    'resource_metadata="https://healthy.example.test/meta"'
                )
                if self.scenario == "malformed_challenge":
                    challenge = "Basic realm=legacy"
                return self.response(
                    url,
                    401,
                    headers={"www-authenticate": challenge, "content-type": "application/json"},
                    payload={"error": "unauthorized"},
                )
            if rpc_method == "initialize":
                if self.scenario == "authenticated_500":
                    return self.response(url, 500, payload={"error": "server failure"})
                response_id = (
                    "wrong-correlation"
                    if self.scenario == "protocol_correlation"
                    else json_body.get("id")
                )
                payload = {
                    "jsonrpc": "2.0",
                    "id": response_id,
                    "result": {
                        "protocolVersion": "2025-06-18",
                        "serverInfo": {"name": "fixture", "version": "1"},
                        "capabilities": {"tools": {}},
                    },
                }
                if self.scenario == "sse":
                    return self.response(
                        url,
                        200,
                        body=f"event: message\ndata: {json.dumps(payload)}\n\n".encode(),
                        headers={
                            "content-type": "text/event-stream",
                            "mcp-session-id": SESSION_SECRET,
                        },
                    )
                return self.response(
                    url,
                    200,
                    payload=payload,
                    headers={"mcp-session-id": SESSION_SECRET},
                )
            if rpc_method == "notifications/initialized":
                assert headers.get("mcp-session-id") == SESSION_SECRET
                return self.response(url, 202)
            if rpc_method == "tools/list":
                tools = (
                    [{"name": "missing-schema"}]
                    if self.scenario == "malformed_tool"
                    else [{"name": "safe-tool", "inputSchema": {"type": "object"}}]
                )
                return self.response(
                    url,
                    200,
                    payload={
                        "jsonrpc": "2.0",
                        "id": json_body.get("id"),
                        "result": {"tools": tools},
                    },
                )
        if url == "https://healthy.example.test/meta":
            if self.scenario == "metadata_redirect":
                return self.response(
                    url, 302, headers={"location": "https://other.example.test/meta"}
                )
            if self.scenario == "malformed_metadata":
                return self.response(
                    url,
                    200,
                    body=b"not-json",
                    headers={"content-type": "application/json"},
                )
            resource = (
                "https://wrong-region.example.test/mcp"
                if self.scenario == "wrong_resource"
                else MCP_URL
            )
            return self.response(
                url,
                200,
                payload={
                    "resource": resource,
                    "authorization_servers": [AUTH_ISSUER],
                    "scopes_supported": ["mcp.read"],
                },
            )
        if url == "https://auth.example.test/.well-known/oauth-authorization-server/tenant":
            issuer = (
                "https://wrong-region.example.test"
                if self.scenario == "wrong_issuer"
                else AUTH_ISSUER
            )
            return self.response(
                url,
                200,
                payload={
                    "issuer": issuer,
                    "authorization_endpoint": "https://auth.example.test/authorize",
                    "token_endpoint": "https://auth.example.test/token",
                    "registration_endpoint": "https://auth.example.test/register",
                    "response_types_supported": ["code"],
                    "grant_types_supported": [
                        "authorization_code",
                        "refresh_token",
                        "client_credentials",
                    ],
                    "code_challenge_methods_supported": ["S256"],
                    "token_endpoint_auth_methods_supported": [
                        "none",
                        "client_secret_basic",
                        "client_secret_post",
                        "client_secret_jwt",
                    ],
                    "scopes_supported": ["mcp.read"],
                    "protected_resources": [MCP_URL],
                },
            )
        if url in {
            "https://auth.example.test/tenant/.well-known/openid-configuration",
            "https://auth.example.test/.well-known/openid-configuration/tenant",
        }:
            return self.response(
                url,
                200,
                payload={
                    "issuer": AUTH_ISSUER,
                    "authorization_endpoint": "https://auth.example.test/authorize",
                    "token_endpoint": "https://auth.example.test/token",
                    "jwks_uri": "https://auth.example.test/jwks",
                },
            )
        if url == "https://auth.example.test/token":
            if form_body and form_body.get("grant_type") == "urn:testmcpy:unsupported-grant":
                return self.response(
                    url,
                    400,
                    payload={"error": "unsupported_grant_type"},
                    headers={"cache-control": "no-store", "pragma": "no-cache"},
                )
            if self.scenario == "malformed_token":
                return self.response(
                    url,
                    200,
                    body=f"token={ACCESS_SECRET}".encode(),
                    headers={"content-type": "text/plain"},
                )
            audience = "wrong-region-api" if self.scenario == "wrong_audience" else "mcp-api"
            access_token = (
                "opaque-access-token-123456789"
                if self.scenario == "opaque_token"
                else _jwt(audience=audience)
            )
            return self.response(
                url,
                200,
                payload={
                    "access_token": access_token,
                    "refresh_token": "rotated-refresh-secret-987654321",
                    "token_type": "Bearer",
                    "expires_in": 300,
                    "scope": "mcp.read",
                },
                headers={"cache-control": "no-store", "pragma": "no-cache"},
            )
        if "/.well-known/" in url:
            return self.response(url, 404, payload={"error": "not_found"})
        raise AssertionError(f"unexpected request: {method} {url}")

    async def aclose(self) -> None:
        self.closed = True


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario", ["healthy", "sse"])
async def test_healthy_json_and_sse_roundtrips_are_stage_visible_and_redacted(
    scenario: str,
) -> None:
    transports: list[FixtureTransport] = []

    def factory(target: object) -> FixtureTransport:
        transport = FixtureTransport(target, scenario=scenario)
        transports.append(transport)
        return transport

    report = await ProbeRunner(
        transport_factory=factory,
        environ={
            "TEST_REFRESH_TOKEN": REFRESH_SECRET,
            "TEST_CLIENT_ID": "example-client",
            "TEST_CLIENT_SECRET": CLIENT_SECRET,
        },
    ).run_manifest(loads_manifest(_manifest()), profile="canary", run_id="fixture-run")

    assert report.exit_code == 0
    assert all(transport.closed for transport in transports)
    ids = {check.id for check in report.reports[0].checks}
    assert {
        "rfc9728.resource.identity",
        "rfc8414.issuer.identity",
        "oauth.token.error_contract",
        "oauth.refresh.rotation",
        "oauth.token.claims.policy",
        "mcp.initialize.protocol_contract",
        "mcp.initialized.http_status",
        "mcp.tools_list.protocol_contract",
    } <= ids
    rendered = "".join((to_json(report), to_jsonl(report), to_human(report), to_junit(report)))
    for secret in (ACCESS_SECRET, REFRESH_SECRET, CLIENT_SECRET, SESSION_SECRET, _jwt()):
        assert secret not in rendered
    Draft202012Validator(report_json_schema()).validate(report.to_dict())
    assert "example-revision" in rendered
    assert "test-region" in rendered
    assert "service=example-mcp" in to_human(report)
    assert 'name="service" value="example-mcp"' in to_junit(report)
    assert any(
        request[3] and request[3].get("refresh_token") == REFRESH_SECRET
        for request in transports[0].requests
    )


@pytest.mark.asyncio
async def test_opaque_token_is_valid_when_only_metadata_issuer_is_constrained() -> None:
    document = json.loads(_manifest())
    expectations = document["targets"]["healthy"]["expectations"]
    expectations.pop("token_issuers")
    expectations.pop("audiences")

    report = await ProbeRunner(
        transport_factory=lambda target: FixtureTransport(target, scenario="opaque_token"),
        environ={
            "TEST_REFRESH_TOKEN": REFRESH_SECRET,
            "TEST_CLIENT_ID": "example-client",
            "TEST_CLIENT_SECRET": CLIENT_SECRET,
        },
    ).run_manifest(loads_manifest(json.dumps(document)))

    checks = {check.id: check for check in report.reports[0].checks}
    assert checks["rfc8414.issuer.identity"].status is CheckStatus.PASS
    assert checks["oauth.token.claims.policy"].status is CheckStatus.SKIP
    assert checks["mcp.initialize.protocol_contract"].status is CheckStatus.PASS
    assert report.exit_code == 0


@pytest.mark.asyncio
async def test_bearer_claim_policy_runs_without_optional_metadata_fetches() -> None:
    document = json.loads(_manifest())
    target = document["targets"]["healthy"]
    target["oauth"] = {"flow": "bearer", "access_token": {"env": "TEST_ACCESS_TOKEN"}}
    target["expectations"]["capabilities"].update(
        {
            "protected_resource_metadata": "ignore",
            "authorization_server_metadata": "ignore",
            "oidc_discovery": "ignore",
        }
    )
    transport: FixtureTransport | None = None

    def factory(target_config: object) -> FixtureTransport:
        nonlocal transport
        transport = FixtureTransport(target_config)
        return transport

    report = await ProbeRunner(
        transport_factory=factory,
        environ={"TEST_ACCESS_TOKEN": _jwt()},
    ).run_manifest(loads_manifest(json.dumps(document)))

    assert report.exit_code == 0
    assert transport is not None
    assert not [request for request in transport.requests if request[0] == "GET"]
    checks = {check.id: check for check in report.reports[0].checks}
    assert checks["oauth.token.claims.policy"].status is CheckStatus.PASS
    assert checks["rfc9728.metadata.available"].status is CheckStatus.SKIP
    assert checks["rfc8414.metadata.available"].status is CheckStatus.SKIP


@pytest.mark.asyncio
async def test_basic_client_credentials_are_form_encoded_before_base64() -> None:
    transport: FixtureTransport | None = None

    def factory(target_config: object) -> FixtureTransport:
        nonlocal transport
        transport = FixtureTransport(target_config)
        return transport

    report = await ProbeRunner(
        transport_factory=factory,
        environ={
            "TEST_REFRESH_TOKEN": REFRESH_SECRET,
            "TEST_CLIENT_ID": "client:name",
            "TEST_CLIENT_SECRET": "secret/value",
        },
    ).run_manifest(loads_manifest(_manifest()))

    assert report.exit_code == 0
    assert transport is not None
    token_request = next(
        request
        for request in transport.requests
        if request[1] == "https://auth.example.test/token"
        and request[3]
        and request[3].get("grant_type") == "refresh_token"
    )
    authorization = token_request[2]["authorization"]
    assert base64.b64decode(authorization.removeprefix("Basic ")).decode() == (
        "client%3Aname:secret%2Fvalue"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("flow", "auth_method"),
    [
        ("client_credentials", "client_secret_jwt"),
        ("authorization_code", "none"),
    ],
)
async def test_confidential_client_and_preobtained_pkce_paths(flow: str, auth_method: str) -> None:
    document = json.loads(_manifest())
    oauth: dict[str, Any] = {
        "flow": flow,
        "client_id": {"env": "TEST_CLIENT_ID"},
        "client_auth_method": auth_method,
        "scopes": ["mcp.read"],
        "resource": MCP_URL,
        "audience": "mcp-api",
    }
    if auth_method != "none":
        oauth["client_secret"] = {"env": "TEST_CLIENT_SECRET"}
    if flow == "authorization_code":
        oauth.update(
            {
                "authorization_code": {"env": "TEST_AUTH_CODE"},
                "pkce_verifier": {"env": "TEST_PKCE_VERIFIER"},
                "redirect_uri": "http://127.0.0.1:9876/callback",
            }
        )
    document["targets"]["healthy"]["oauth"] = oauth
    document["targets"]["healthy"]["expectations"]["grants"] = {flow: "required"}
    document["targets"]["healthy"]["expectations"]["auth_methods"] = (
        {auth_method: "required"} if auth_method != "none" else {}
    )
    transport: FixtureTransport | None = None

    def factory(target: object) -> FixtureTransport:
        nonlocal transport
        transport = FixtureTransport(target)
        return transport

    report = await ProbeRunner(
        transport_factory=factory,
        environ={
            "TEST_CLIENT_ID": "example-client",
            "TEST_CLIENT_SECRET": CLIENT_SECRET,
            "TEST_AUTH_CODE": "authorization-code-canary-123456789",
            "TEST_PKCE_VERIFIER": "pkce-verifier-canary-123456789012345678901234567890",
        },
    ).run_manifest(loads_manifest(json.dumps(document)))
    assert report.exit_code == 0
    assert transport is not None
    token_requests = [
        request
        for request in transport.requests
        if request[1] == "https://auth.example.test/token"
        and request[3]
        and request[3].get("grant_type") == flow
    ]
    assert len(token_requests) == 1
    form = token_requests[0][3]
    assert form is not None
    if flow == "client_credentials":
        assert form.get("client_assertion_type")
        assert form.get("client_assertion")
    else:
        assert form.get("code_verifier")
        assert form.get("redirect_uri") == "http://127.0.0.1:9876/callback"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("scenario", "failed_check"),
    [
        ("wrong_resource", "rfc9728.resource.identity"),
        ("wrong_issuer", "rfc8414.issuer.identity"),
        ("wrong_audience", "oauth.token.claims.policy"),
        ("authenticated_500", "mcp.initialize.http_status"),
        ("malformed_challenge", "mcp.auth.challenge.bearer"),
        ("protocol_correlation", "mcp.initialize.protocol_contract"),
        ("malformed_tool", "mcp.tools_list.protocol_contract"),
    ],
)
async def test_incident_and_malformed_protocol_scenarios_fail_deterministically(
    scenario: str, failed_check: str
) -> None:
    transport: FixtureTransport | None = None

    def factory(target: object) -> FixtureTransport:
        nonlocal transport
        transport = FixtureTransport(target, scenario=scenario)
        return transport

    report = await ProbeRunner(
        transport_factory=factory,
        environ={
            "TEST_REFRESH_TOKEN": REFRESH_SECRET,
            "TEST_CLIENT_ID": "example-client",
            "TEST_CLIENT_SECRET": CLIENT_SECRET,
        },
    ).run_manifest(loads_manifest(_manifest()))
    checks = {check.id: check for check in report.reports[0].checks}
    assert checks[failed_check].status in {CheckStatus.FAIL, CheckStatus.ERROR}
    assert report.exit_code in {1, 2}
    if scenario == "authenticated_500":
        assert transport is not None
        authenticated_initialize = [
            request
            for request in transport.requests
            if request[0] == "POST" and request[1] == MCP_URL and request[2].get("authorization")
        ]
        assert len(authenticated_initialize) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario", ["malformed_metadata", "metadata_redirect", "malformed_token"])
async def test_malformed_metadata_redirect_and_token_never_leak_bodies(scenario: str) -> None:
    report = await ProbeRunner(
        transport_factory=lambda target: FixtureTransport(target, scenario=scenario),
        environ={
            "TEST_REFRESH_TOKEN": REFRESH_SECRET,
            "TEST_CLIENT_ID": "example-client",
            "TEST_CLIENT_SECRET": CLIENT_SECRET,
        },
    ).run_manifest(loads_manifest(_manifest()))
    rendered = to_json(report)
    assert ACCESS_SECRET not in rendered
    assert REFRESH_SECRET not in rendered
    assert CLIENT_SECRET not in rendered
    assert report.exit_code == 2


def test_optional_oidc_and_dcr_are_skipped_not_made_universally_mandatory() -> None:
    manifest = loads_manifest(_manifest(flow="none", capabilities="ignore"))
    expectations = manifest.targets["healthy"].expectations
    assert expectations.capabilities["oidc_discovery"].value == "ignore"


def test_config_is_strict_versioned_and_credentials_are_references() -> None:
    manifest = loads_manifest(_manifest())
    assert manifest.schema == "testmcpy.io/oauth-smoke/v1"
    assert manifest.targets["healthy"].oauth.client_secret is not None
    assert manifest.targets["healthy"].oauth.client_secret.env == "TEST_CLIENT_SECRET"
    direct_secret = json.loads(_manifest())
    direct_secret["targets"]["healthy"]["oauth"]["client_secret"] = CLIENT_SECRET
    with pytest.raises(ConfigError, match="must be an object"):
        loads_manifest(json.dumps(direct_secret))
    unknown_field = json.loads(_manifest())
    unknown_field["targets"]["healthy"]["typo"] = True
    with pytest.raises(ConfigError, match="unknown field"):
        loads_manifest(json.dumps(unknown_field))
    with pytest.raises(ConfigError, match="unsupported schema"):
        loads_manifest(_manifest().replace("oauth-smoke/v1", "oauth-smoke/v2"))
    invalid_status = json.loads(_manifest())
    invalid_status["targets"]["healthy"]["expectations"]["initialize_status"] = 42
    with pytest.raises(ConfigError, match="HTTP status"):
        loads_manifest(json.dumps(invalid_status))
    empty_profile = json.loads(_manifest())
    empty_profile["profiles"]["canary"]["targets"] = []
    with pytest.raises(ConfigError, match="must not be empty"):
        loads_manifest(json.dumps(empty_profile))
    public_client_credentials = json.loads(_manifest())
    public_client_credentials["targets"]["healthy"]["oauth"].update(
        {"flow": "client_credentials", "client_auth_method": "none"}
    )
    with pytest.raises(ConfigError, match="confidential client"):
        loads_manifest(json.dumps(public_client_credentials))


def test_packaged_schema_and_documented_example_stay_loadable() -> None:
    schema = manifest_json_schema()
    assert schema["$id"] == "testmcpy.io/oauth-smoke/v1"
    manifest = load_manifest("examples/oauth-smoke/auth-smoke.example.yaml")
    assert tuple(manifest.targets) == ("example-us",)
    report_schema = report_json_schema()
    assert report_schema["$id"] == "testmcpy.io/oauth-smoke-report/v1"
    Draft202012Validator.check_schema(schema)
    Draft202012Validator.check_schema(report_schema)


def test_discovery_builders_and_multi_challenge_parser_cover_path_issuers() -> None:
    assert protected_resource_metadata_urls(
        "https://mcp.example.test/tenant/mcp",
        "https://mcp.example.test/custom-meta",
    ) == (
        "https://mcp.example.test/custom-meta",
        "https://mcp.example.test/.well-known/oauth-protected-resource/tenant/mcp",
        "https://mcp.example.test/.well-known/oauth-protected-resource",
    )
    assert authorization_metadata_urls("https://auth.example.test/tenant") == (
        "https://auth.example.test/.well-known/oauth-authorization-server/tenant",
        "https://auth.example.test/.well-known/openid-configuration/tenant",
        "https://auth.example.test/tenant/.well-known/openid-configuration",
    )
    assert parse_bearer_challenge(
        'Basic realm="old", Bearer realm="mcp", scope="read write", resource_metadata="https://mcp.example.test/meta"'
    ) == {
        "realm": "mcp",
        "scope": "read write",
        "resource_metadata": "https://mcp.example.test/meta",
    }
    assert safe_url("https://[::1]:8443/path?secret=value") == "https://[::1]:8443/path"
    assert safe_url("https://example.test:invalid/path") == "[INVALID URL]"
