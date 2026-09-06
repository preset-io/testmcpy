"""RFC 6750/8414/9728 and optional OIDC discovery checks."""

from __future__ import annotations

import json
import re
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from testmcpy_oauth_probe.models import (
    AuthFlow,
    CapabilityPolicy,
    CheckResult,
    CheckStatus,
    TargetConfig,
)
from testmcpy_oauth_probe.secrets import safe_url
from testmcpy_oauth_probe.transport import (
    HttpResponse,
    HttpTransport,
    TransportError,
    validate_url_syntax,
)

_JSON_MEDIA_TYPES = ("application/json", "+json")
_AUTH_PARAM_RE = re.compile(
    r"([!#$%&'*+.^_`|~0-9A-Za-z-]+)\s*=\s*(?:\"((?:[^\"\\]|\\.)*)\"|([^,\s]+))"
)


@dataclass(frozen=True)
class DiscoveryResult:
    checks: tuple[CheckResult, ...]
    challenge: dict[str, str]
    protected_resource_metadata: dict[str, Any] | None
    authorization_metadata: dict[str, Any] | None
    oidc_metadata: dict[str, Any] | None
    token_endpoint: str | None
    resource: str | None


def _origin(url: str) -> str:
    parsed = urlsplit(url)
    netloc = parsed.hostname or ""
    if ":" in netloc:
        netloc = f"[{netloc}]"
    if parsed.port is not None:
        netloc = f"{netloc}:{parsed.port}"
    return urlunsplit((parsed.scheme, netloc, "", "", ""))


def protected_resource_metadata_urls(
    resource_url: str, challenge_url: str | None
) -> tuple[str, ...]:
    parsed = urlsplit(resource_url)
    base = _origin(resource_url)
    candidates: list[str] = []
    if challenge_url:
        candidates.append(challenge_url)
    if parsed.path and parsed.path != "/":
        candidates.append(f"{base}/.well-known/oauth-protected-resource{parsed.path}")
    candidates.append(f"{base}/.well-known/oauth-protected-resource")
    return tuple(dict.fromkeys(candidates))


def authorization_metadata_urls(issuer: str) -> tuple[str, ...]:
    parsed = urlsplit(issuer)
    base = _origin(issuer)
    path = parsed.path.rstrip("/")
    if path:
        return (
            f"{base}/.well-known/oauth-authorization-server{path}",
            f"{base}/.well-known/openid-configuration{path}",
            f"{base}{path}/.well-known/openid-configuration",
        )
    return (
        f"{base}/.well-known/oauth-authorization-server",
        f"{base}/.well-known/openid-configuration",
    )


def oidc_metadata_urls(issuer: str) -> tuple[str, ...]:
    parsed = urlsplit(issuer)
    base = _origin(issuer)
    path = parsed.path.rstrip("/")
    values = [f"{base}{path}/.well-known/openid-configuration"]
    if path:
        values.append(f"{base}/.well-known/openid-configuration{path}")
    return tuple(dict.fromkeys(values))


def parse_bearer_challenge(header: str) -> dict[str, str]:
    """Parse Bearer auth-params without retaining unrelated challenges."""
    if not header:
        return {}
    bearer = re.search(r"(?i)(?:^|,)\s*Bearer(?:\s+|$)", header)
    if bearer is None:
        return {}
    # A following auth-scheme is a comma-delimited token not followed by '='.
    tail = header[bearer.end() :]
    next_scheme = re.search(r",\s*[!#$%&'*+.^_`|~0-9A-Za-z-]+\s+(?![^,]*=)", tail)
    if next_scheme is not None:
        tail = tail[: next_scheme.start()]
    result: dict[str, str] = {}
    for match in _AUTH_PARAM_RE.finditer(tail):
        raw = match.group(2) if match.group(2) is not None else match.group(3)
        result[match.group(1).lower()] = re.sub(r"\\(.)", r"\1", raw or "")
    return result


def _json_object(response: HttpResponse, stage: str) -> dict[str, Any]:
    content_type = response.headers.get("content-type", "").lower()
    if not any(media_type in content_type for media_type in _JSON_MEDIA_TYPES):
        raise ValueError(f"{stage} response is not JSON")
    try:
        value = json.loads(response.body)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError(f"{stage} returned malformed JSON") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{stage} JSON top level must be an object")
    return value


def _check(
    check_id: str,
    stage: str,
    status: CheckStatus,
    message: str,
    *,
    started: float,
    reference: str | None = None,
    http_status: int | None = None,
    evidence: dict[str, Any] | None = None,
    applicable: bool = True,
) -> CheckResult:
    return CheckResult(
        id=check_id,
        stage=stage,
        status=status,
        message=message,
        duration_ms=int((time.monotonic() - started) * 1000),
        applicable=applicable,
        reference=reference,
        http_status=http_status,
        evidence=evidence or {},
    )


def _policy_result(
    *,
    check_id: str,
    stage: str,
    name: str,
    present: bool,
    policy: CapabilityPolicy,
    started: float,
    reference: str | None = None,
) -> CheckResult:
    if policy is CapabilityPolicy.IGNORE:
        return _check(
            check_id,
            stage,
            CheckStatus.SKIP,
            f"{name} ignored by policy",
            started=started,
            reference=reference,
            applicable=False,
        )
    if policy is CapabilityPolicy.FORBIDDEN:
        status = CheckStatus.FAIL if present else CheckStatus.PASS
        message = f"forbidden {name} is advertised" if present else f"{name} is not advertised"
        return _check(check_id, stage, status, message, started=started, reference=reference)
    if not present:
        if policy is CapabilityPolicy.REQUIRED:
            return _check(
                check_id,
                stage,
                CheckStatus.FAIL,
                f"required {name} is absent",
                started=started,
                reference=reference,
            )
        return _check(
            check_id,
            stage,
            CheckStatus.SKIP,
            f"optional {name} is not advertised",
            started=started,
            reference=reference,
            applicable=False,
        )
    return _check(
        check_id,
        stage,
        CheckStatus.PASS,
        f"{name} is advertised",
        started=started,
        reference=reference,
    )


async def _first_json(
    transport: HttpTransport,
    candidates: tuple[str, ...],
    stage: str,
) -> tuple[str, HttpResponse, dict[str, Any]] | None:
    for candidate in candidates:
        response = await transport.request("GET", candidate, retry_safe=True)
        if response.status == 404:
            continue
        if response.status != 200:
            raise ValueError(f"{stage} returned unexpected HTTP status {response.status}")
        return candidate, response, _json_object(response, stage)
    return None


def _string_list(metadata: Mapping[str, Any], field: str) -> tuple[str, ...] | None:
    value = metadata.get(field)
    if value is None:
        return None
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise ValueError(f"metadata field {field} must be an array of strings")
    return tuple(value)


def _absolute_url(metadata: Mapping[str, Any], field: str) -> str | None:
    value = metadata.get(field)
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ValueError(f"metadata field {field} must be a non-empty URL string")
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError(f"metadata field {field} must be an absolute HTTP(S) URL")
    return value


async def discover(target: TargetConfig, transport: HttpTransport) -> DiscoveryResult:
    checks: list[CheckResult] = []
    challenge: dict[str, str] = {}
    prm: dict[str, Any] | None = None
    auth_metadata: dict[str, Any] | None = None
    oidc_metadata: dict[str, Any] | None = None
    token_endpoint: str | None = target.oauth.token_endpoint
    initialize = {
        "jsonrpc": "2.0",
        "id": "challenge",
        "method": "initialize",
        "params": {
            "protocolVersion": target.spec_profile.removeprefix("mcp-"),
            "capabilities": {},
            "clientInfo": {"name": "testmcpy-oauth-probe", "version": "1"},
        },
    }
    started = time.monotonic()
    try:
        response = await transport.request(
            "POST",
            target.mcp_url,
            headers={
                "accept": "application/json, text/event-stream",
                "content-type": "application/json",
                "mcp-protocol-version": target.spec_profile.removeprefix("mcp-"),
            },
            json_body=initialize,
        )
        expected = target.expectations.unauthorized_status
        status = CheckStatus.PASS if response.status == expected else CheckStatus.FAIL
        checks.append(
            _check(
                "mcp.auth.unauthorized.status",
                "mcp_unauthorized",
                status,
                f"unauthenticated initialize returned HTTP {response.status}; expected {expected}",
                started=started,
                reference="MCP Authorization / RFC 6750 §3",
                http_status=response.status,
            )
        )
        challenge = parse_bearer_challenge(response.headers.get("www-authenticate", ""))
        challenge_policy = target.expectations.policy("bearer_challenge", CapabilityPolicy.REQUIRED)
        checks.append(
            _policy_result(
                check_id="mcp.auth.challenge.bearer",
                stage="mcp_unauthorized",
                name="Bearer challenge",
                present=bool(challenge),
                policy=challenge_policy,
                started=started,
                reference="RFC 6750 §3",
            )
        )
    except (TransportError, ValueError) as exc:
        checks.append(
            _check(
                "mcp.auth.unauthorized.status",
                "mcp_unauthorized",
                CheckStatus.ERROR,
                str(exc),
                started=started,
                reference="MCP Authorization / RFC 6750 §3",
            )
        )

    prm_default = (
        CapabilityPolicy.SUPPORTED
        if target.spec_profile == "mcp-2025-03-26"
        else CapabilityPolicy.REQUIRED
    )
    prm_policy = target.expectations.policy("protected_resource_metadata", prm_default)
    started = time.monotonic()
    try:
        prm_result = (
            None
            if prm_policy is CapabilityPolicy.IGNORE
            else await _first_json(
                transport,
                protected_resource_metadata_urls(
                    target.mcp_url, challenge.get("resource_metadata")
                ),
                "protected-resource metadata",
            )
        )
        prm = prm_result[2] if prm_result else None
        checks.append(
            _policy_result(
                check_id="rfc9728.metadata.available",
                stage="protected_resource_metadata",
                name="protected-resource metadata",
                present=prm is not None,
                policy=prm_policy,
                started=started,
                reference="RFC 9728 §3",
            )
        )
        if prm_result is not None and prm is not None:
            prm_url, response, prm = prm_result
            resource = prm.get("resource")
            if not isinstance(resource, str) or not resource:
                raise ValueError("protected-resource metadata resource must be a URL string")
            # RFC 9728 binds metadata to the protected resource used for
            # discovery. Deployment expectations may tighten policy but may
            # never replace this trust binding.
            expected_resources = (target.mcp_url,)
            checks.append(
                _check(
                    "rfc9728.resource.identity",
                    "protected_resource_metadata",
                    CheckStatus.PASS if resource in expected_resources else CheckStatus.FAIL,
                    "protected-resource identity matches exactly"
                    if resource in expected_resources
                    else "protected-resource identity does not match any expected resource",
                    started=started,
                    reference="RFC 9728 §3.3",
                    http_status=response.status,
                    evidence={"metadata_url": safe_url(prm_url), "resource": safe_url(resource)},
                )
            )
            servers = _string_list(prm, "authorization_servers") or ()
            if target.spec_profile != "mcp-2025-03-26" and not servers:
                checks.append(
                    _check(
                        "rfc9728.authorization_servers.required",
                        "protected_resource_metadata",
                        CheckStatus.FAIL,
                        "protected-resource metadata must advertise an authorization server",
                        started=started,
                        reference="MCP Authorization 2025-06-18 / RFC 9728 §2",
                    )
                )
            scopes = _string_list(prm, "scopes_supported") or ()
            missing_scopes = sorted(set(target.expectations.scopes) - set(scopes))
            checks.append(
                _check(
                    "rfc9728.scopes.policy",
                    "protected_resource_metadata",
                    CheckStatus.FAIL if missing_scopes else CheckStatus.PASS,
                    "required scopes are advertised"
                    if not missing_scopes
                    else "required scopes are missing",
                    started=started,
                    reference="RFC 9728 §2",
                    evidence={
                        "missing_scopes": missing_scopes,
                        "advertised_scope_count": len(scopes),
                    },
                )
            )
        else:
            servers = ()
    except (TransportError, ValueError) as exc:
        checks.append(
            _check(
                "rfc9728.metadata.contract",
                "protected_resource_metadata",
                CheckStatus.ERROR,
                str(exc),
                started=started,
                reference="RFC 9728",
            )
        )
        servers = ()

    expected_issuers = target.expectations.issuers
    selected_issuer: str | None = None
    if servers:
        matching = [
            issuer for issuer in servers if not expected_issuers or issuer in expected_issuers
        ]
        if len(matching) == 1:
            selected_issuer = matching[0]
        elif len(servers) == 1 and not expected_issuers:
            selected_issuer = servers[0]
        else:
            checks.append(
                _check(
                    "oauth.issuer.selection",
                    "authorization_server_metadata",
                    CheckStatus.FAIL,
                    "authorization server selection is ambiguous or violates issuer policy",
                    started=time.monotonic(),
                    evidence={"advertised_count": len(servers)},
                )
            )
    elif target.spec_profile != "mcp-2025-03-26":
        selected_issuer = None
    elif expected_issuers:
        selected_issuer = expected_issuers[0] if len(expected_issuers) == 1 else None
    else:
        selected_issuer = _origin(target.mcp_url)

    auth_policy = target.expectations.policy(
        "authorization_server_metadata", CapabilityPolicy.REQUIRED
    )
    started = time.monotonic()
    try:
        auth_result = (
            await _first_json(
                transport,
                authorization_metadata_urls(selected_issuer),
                "authorization-server metadata",
            )
            if selected_issuer and auth_policy is not CapabilityPolicy.IGNORE
            else None
        )
        auth_metadata = auth_result[2] if auth_result else None
        checks.append(
            _policy_result(
                check_id="rfc8414.metadata.available",
                stage="authorization_server_metadata",
                name="authorization-server metadata",
                present=auth_metadata is not None,
                policy=auth_policy,
                started=started,
                reference="RFC 8414 §3",
            )
        )
        if auth_result is not None and auth_metadata is not None:
            metadata_url, response, auth_metadata = auth_result
            issuer = auth_metadata.get("issuer")
            if not isinstance(issuer, str) or not issuer:
                raise ValueError("authorization metadata issuer must be a URL string")
            issuer_ok = issuer == selected_issuer and (
                not expected_issuers or issuer in expected_issuers
            )
            checks.append(
                _check(
                    "rfc8414.issuer.identity",
                    "authorization_server_metadata",
                    CheckStatus.PASS if issuer_ok else CheckStatus.FAIL,
                    "issuer matches exactly"
                    if issuer_ok
                    else "issuer does not match selection policy",
                    started=started,
                    reference="RFC 8414 §3.3",
                    http_status=response.status,
                    evidence={"issuer": safe_url(issuer), "metadata_url": safe_url(metadata_url)},
                )
            )
            token_endpoint = target.oauth.token_endpoint or _absolute_url(
                auth_metadata, "token_endpoint"
            )
            response_types = _string_list(auth_metadata, "response_types_supported")
            if response_types is None:
                raise ValueError("metadata field response_types_supported is required")
            endpoint_values = {
                field: _absolute_url(auth_metadata, field)
                for field in (
                    "authorization_endpoint",
                    "token_endpoint",
                    "registration_endpoint",
                    "revocation_endpoint",
                    "introspection_endpoint",
                    "jwks_uri",
                )
            }
            for endpoint in endpoint_values.values():
                if endpoint is not None:
                    validate_url_syntax(endpoint, target)
            for endpoint_name, policy in target.expectations.endpoints.items():
                endpoint = endpoint_values.get(endpoint_name) or _absolute_url(
                    auth_metadata, endpoint_name
                )
                if endpoint is not None:
                    validate_url_syntax(endpoint, target)
                checks.append(
                    _policy_result(
                        check_id=f"oauth.endpoint.{endpoint_name}",
                        stage="authorization_server_metadata",
                        name=endpoint_name,
                        present=endpoint is not None,
                        policy=policy,
                        started=started,
                        reference="RFC 8414 §2",
                    )
                )
            grants = _string_list(auth_metadata, "grant_types_supported")
            advertised_grants = set(grants or ("authorization_code", "implicit"))
            for grant, policy in target.expectations.grants.items():
                checks.append(
                    _policy_result(
                        check_id=f"oauth.grant.{grant}",
                        stage="authorization_server_metadata",
                        name=f"grant {grant}",
                        present=grant in advertised_grants,
                        policy=policy,
                        started=started,
                        reference="RFC 8414 §2",
                    )
                )
            selected_grant = {
                AuthFlow.REFRESH_TOKEN: "refresh_token",
                AuthFlow.CLIENT_CREDENTIALS: "client_credentials",
                AuthFlow.AUTHORIZATION_CODE: "authorization_code",
            }.get(target.oauth.flow)
            if selected_grant is not None:
                checks.append(
                    _policy_result(
                        check_id="oauth.grant.selected",
                        stage="authorization_server_metadata",
                        name=f"configured grant {selected_grant}",
                        present=selected_grant in advertised_grants,
                        policy=CapabilityPolicy.REQUIRED,
                        started=started,
                        reference="RFC 8414 §2",
                    )
                )
            methods = _string_list(auth_metadata, "token_endpoint_auth_methods_supported")
            advertised_methods = set(methods or ("client_secret_basic",))
            for method, policy in target.expectations.auth_methods.items():
                checks.append(
                    _policy_result(
                        check_id=f"oauth.client_auth.{method}",
                        stage="authorization_server_metadata",
                        name=f"client auth method {method}",
                        present=method in advertised_methods,
                        policy=policy,
                        started=started,
                        reference="RFC 8414 §2",
                    )
                )
            if target.oauth.flow in {
                AuthFlow.REFRESH_TOKEN,
                AuthFlow.CLIENT_CREDENTIALS,
                AuthFlow.AUTHORIZATION_CODE,
            }:
                selected_method = target.oauth.client_auth_method.value
                checks.append(
                    _policy_result(
                        check_id="oauth.client_auth.selected",
                        stage="authorization_server_metadata",
                        name=f"configured client auth method {selected_method}",
                        present=selected_method in advertised_methods,
                        policy=CapabilityPolicy.REQUIRED,
                        started=started,
                        reference="RFC 8414 §2",
                    )
                )
            advertised_scopes = set(_string_list(auth_metadata, "scopes_supported") or ())
            missing_scopes = sorted(set(target.expectations.scopes) - advertised_scopes)
            checks.append(
                _check(
                    "rfc8414.scopes.policy",
                    "authorization_server_metadata",
                    CheckStatus.FAIL if missing_scopes else CheckStatus.PASS,
                    "authorization metadata advertises required scopes"
                    if not missing_scopes
                    else "authorization metadata is missing required scopes",
                    started=started,
                    reference="RFC 8414 §2",
                    evidence={"missing_scopes": missing_scopes},
                )
            )
            if target.oauth.flow is AuthFlow.AUTHORIZATION_CODE:
                pkce_methods = set(
                    _string_list(auth_metadata, "code_challenge_methods_supported") or ()
                )
                auth_code_contract = (
                    "code" in response_types
                    and "S256" in pkce_methods
                    and endpoint_values["authorization_endpoint"] is not None
                )
                checks.append(
                    _check(
                        "oauth.authorization_code.pkce_policy",
                        "authorization_server_metadata",
                        CheckStatus.PASS if auth_code_contract else CheckStatus.FAIL,
                        "authorization-code metadata advertises code and PKCE S256"
                        if auth_code_contract
                        else "authorization-code metadata is missing code, endpoint, or PKCE S256",
                        started=started,
                        reference="RFC 7636 §4.2 / MCP Authorization",
                    )
                )
            protected_resources = _string_list(auth_metadata, "protected_resources")
            if protected_resources is not None:
                expected_resource = target.oauth.resource or target.mcp_url
                checks.append(
                    _check(
                        "rfc8414.protected_resources.crosscheck",
                        "authorization_server_metadata",
                        CheckStatus.PASS
                        if expected_resource in protected_resources
                        else CheckStatus.FAIL,
                        "authorization server covers the protected resource"
                        if expected_resource in protected_resources
                        else "authorization server does not cover the expected resource",
                        started=started,
                        evidence={"advertised_count": len(protected_resources)},
                    )
                )
            dcr_policy = target.expectations.policy(
                "dynamic_client_registration", CapabilityPolicy.SUPPORTED
            )
            checks.append(
                _policy_result(
                    check_id="rfc7591.registration.available",
                    stage="authorization_server_metadata",
                    name="dynamic client registration",
                    present=_absolute_url(auth_metadata, "registration_endpoint") is not None,
                    policy=dcr_policy,
                    started=started,
                    reference="RFC 7591",
                )
            )
    except (TransportError, ValueError) as exc:
        checks.append(
            _check(
                "rfc8414.metadata.contract",
                "authorization_server_metadata",
                CheckStatus.ERROR,
                str(exc),
                started=started,
                reference="RFC 8414",
            )
        )

    oidc_default = (
        CapabilityPolicy.REQUIRED
        if target.spec_profile == "mcp-2025-11-25"
        else CapabilityPolicy.SUPPORTED
    )
    oidc_policy = target.expectations.policy("oidc_discovery", oidc_default)
    started = time.monotonic()
    try:
        oidc_result = (
            await _first_json(transport, oidc_metadata_urls(selected_issuer), "OIDC discovery")
            if selected_issuer and oidc_policy is not CapabilityPolicy.IGNORE
            else None
        )
        oidc_metadata = oidc_result[2] if oidc_result else None
        checks.append(
            _policy_result(
                check_id="oidc.discovery.available",
                stage="oidc_discovery",
                name="OIDC discovery",
                present=oidc_metadata is not None,
                policy=oidc_policy,
                started=started,
                reference="OpenID Connect Discovery 1.0 §4",
            )
        )
        if oidc_metadata is not None:
            issuer = oidc_metadata.get("issuer")
            ok = isinstance(issuer, str) and issuer == selected_issuer
            checks.append(
                _check(
                    "oidc.issuer.identity",
                    "oidc_discovery",
                    CheckStatus.PASS if ok else CheckStatus.FAIL,
                    "OIDC issuer matches exactly" if ok else "OIDC issuer does not match",
                    started=started,
                    reference="OpenID Connect Discovery 1.0 §4.3",
                    evidence={"issuer": safe_url(issuer) if isinstance(issuer, str) else "invalid"},
                )
            )
    except (TransportError, ValueError) as exc:
        checks.append(
            _check(
                "oidc.discovery.contract",
                "oidc_discovery",
                CheckStatus.ERROR,
                str(exc),
                started=started,
                reference="OpenID Connect Discovery 1.0",
            )
        )

    return DiscoveryResult(
        checks=tuple(checks),
        challenge=challenge,
        protected_resource_metadata=prm,
        authorization_metadata=auth_metadata,
        oidc_metadata=oidc_metadata,
        token_endpoint=token_endpoint,
        resource=(
            prm.get("resource")
            if isinstance(prm, dict) and prm.get("resource") == target.mcp_url
            else None
        ),
    )
