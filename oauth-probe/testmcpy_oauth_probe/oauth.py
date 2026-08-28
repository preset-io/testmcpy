"""Noninteractive OAuth token paths and safe token-endpoint probes."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from testmcpy_oauth_probe.models import (
    AuthFlow,
    CheckResult,
    CheckStatus,
    ClientAuthMethod,
    TargetConfig,
)
from testmcpy_oauth_probe.secrets import SecretRegistry, safe_url
from testmcpy_oauth_probe.transport import HttpResponse, HttpTransport, TransportError

_ASSERTION_TYPE = "urn:ietf:params:oauth:client-assertion-type:jwt-bearer"


@dataclass(frozen=True)
class TokenResult:
    access_token: str | None
    checks: tuple[CheckResult, ...]


def _check(
    check_id: str,
    status: CheckStatus,
    message: str,
    *,
    started: float,
    http_status: int | None = None,
    evidence: dict[str, Any] | None = None,
    reference: str | None = None,
    applicable: bool = True,
) -> CheckResult:
    return CheckResult(
        id=check_id,
        stage="oauth_token",
        status=status,
        message=message,
        duration_ms=int((time.monotonic() - started) * 1000),
        applicable=applicable,
        reference=reference,
        http_status=http_status,
        evidence=evidence or {},
    )


def _json_object(response: HttpResponse) -> dict[str, Any]:
    content_type = response.headers.get("content-type", "").lower()
    if "application/json" not in content_type and "+json" not in content_type:
        raise ValueError("token endpoint response is not JSON")
    try:
        value = json.loads(response.body)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("token endpoint returned malformed JSON") from exc
    if not isinstance(value, dict):
        raise ValueError("token endpoint JSON top level must be an object")
    return value


def _b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _client_secret_assertion(client_id: str, secret: str, audience: str) -> str:
    now = int(time.time())
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "iss": client_id,
        "sub": client_id,
        "aud": audience,
        "iat": now,
        "exp": now + 300,
        "jti": secrets.token_urlsafe(24),
    }
    encoded = f"{_b64url(json.dumps(header, separators=(',', ':')).encode())}.{_b64url(json.dumps(payload, separators=(',', ':')).encode())}"
    signature = hmac.new(secret.encode(), encoded.encode(), hashlib.sha256).digest()
    return f"{encoded}.{_b64url(signature)}"


def _decode_claims(token: str) -> dict[str, Any] | None:
    parts = token.split(".")
    if len(parts) != 3:
        return None
    try:
        payload = parts[1] + "=" * (-len(parts[1]) % 4)
        value = json.loads(base64.urlsafe_b64decode(payload))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


async def _safe_error_probe(
    token_endpoint: str,
    transport: HttpTransport,
) -> CheckResult:
    started = time.monotonic()
    try:
        response = await transport.request(
            "POST",
            token_endpoint,
            headers={
                "accept": "application/json",
                "content-type": "application/x-www-form-urlencoded",
            },
            form_body={"grant_type": "urn:testmcpy:unsupported-grant"},
        )
        payload = _json_object(response)
        error = payload.get("error")
        valid_error = isinstance(error, str) and bool(error)
        valid_status = response.status in {400, 401}
        return _check(
            "oauth.token.error_contract",
            CheckStatus.PASS if valid_error and valid_status else CheckStatus.FAIL,
            "token endpoint returned a structured OAuth error"
            if valid_error and valid_status
            else "token endpoint did not return the expected OAuth error contract",
            started=started,
            http_status=response.status,
            evidence={"error": error if isinstance(error, str) else "missing"},
            reference="RFC 6749 §5.2",
        )
    except (TransportError, ValueError) as exc:
        return _check(
            "oauth.token.error_contract",
            CheckStatus.ERROR,
            str(exc),
            started=started,
            reference="RFC 6749 §5.2",
        )


def _apply_client_auth(
    target: TargetConfig,
    registry: SecretRegistry,
    token_endpoint: str,
    form: dict[str, str],
    headers: dict[str, str],
) -> None:
    oauth = target.oauth
    client_id = registry.resolve_value(oauth.client_id)
    client_secret = registry.resolve(oauth.client_secret)
    method = oauth.client_auth_method
    if method is ClientAuthMethod.NONE:
        if client_id:
            form["client_id"] = client_id
        return
    if not client_id or not client_secret:
        raise ValueError(f"client credentials required for {method.value}")
    if method is ClientAuthMethod.CLIENT_SECRET_BASIC:
        encoded = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
        registry.register(encoded)
        headers["authorization"] = f"Basic {encoded}"
    elif method is ClientAuthMethod.CLIENT_SECRET_POST:
        form["client_id"] = client_id
        form["client_secret"] = client_secret
    elif method is ClientAuthMethod.CLIENT_SECRET_JWT:
        assertion = _client_secret_assertion(client_id, client_secret, token_endpoint)
        registry.register(assertion)
        form.update(
            {
                "client_id": client_id,
                "client_assertion_type": _ASSERTION_TYPE,
                "client_assertion": assertion,
            }
        )


async def acquire_token(
    target: TargetConfig,
    transport: HttpTransport,
    registry: SecretRegistry,
    token_endpoint: str | None,
) -> TokenResult:
    checks: list[CheckResult] = []
    oauth = target.oauth
    if oauth.flow is AuthFlow.BEARER:
        started = time.monotonic()
        try:
            token = registry.resolve(oauth.access_token)
        except ValueError as exc:
            checks.append(
                _check("oauth.credential.resolve", CheckStatus.ERROR, str(exc), started=started)
            )
            return TokenResult(None, tuple(checks))
        checks.append(
            _check(
                "oauth.bearer.supplied",
                CheckStatus.PASS,
                "bearer credential resolved from its environment reference",
                started=started,
            )
        )
        return TokenResult(token, tuple(checks))
    if oauth.flow is AuthFlow.NONE:
        checks.append(
            _check(
                "oauth.token.acquire",
                CheckStatus.SKIP,
                "no token flow configured",
                started=time.monotonic(),
                applicable=False,
            )
        )
        return TokenResult(None, tuple(checks))
    if token_endpoint is None:
        checks.append(
            _check(
                "oauth.token.endpoint",
                CheckStatus.ERROR,
                "token endpoint is required by the configured flow but was not discovered",
                started=time.monotonic(),
            )
        )
        return TokenResult(None, tuple(checks))

    parsed = urlsplit(token_endpoint)
    if parsed.query or parsed.fragment or parsed.username or parsed.password:
        checks.append(
            _check(
                "oauth.token.endpoint",
                CheckStatus.ERROR,
                "token endpoint URL contains forbidden query, fragment, or userinfo",
                started=time.monotonic(),
                evidence={"endpoint": safe_url(token_endpoint)},
            )
        )
        return TokenResult(None, tuple(checks))

    if oauth.error_probe:
        checks.append(await _safe_error_probe(token_endpoint, transport))

    form: dict[str, str] = {"grant_type": oauth.flow.value}
    headers = {
        "accept": "application/json",
        "content-type": "application/x-www-form-urlencoded",
    }
    started = time.monotonic()
    try:
        if oauth.flow is AuthFlow.REFRESH_TOKEN:
            refresh_token = registry.resolve(oauth.refresh_token)
            assert refresh_token is not None
            form["refresh_token"] = refresh_token
        elif oauth.flow is AuthFlow.AUTHORIZATION_CODE:
            code = registry.resolve(oauth.authorization_code)
            verifier = registry.resolve(oauth.pkce_verifier)
            assert code is not None and verifier is not None and oauth.redirect_uri is not None
            form.update(
                {
                    "code": code,
                    "code_verifier": verifier,
                    "redirect_uri": oauth.redirect_uri,
                }
            )
        if oauth.scopes:
            form["scope"] = " ".join(oauth.scopes)
        if oauth.resource:
            form["resource"] = oauth.resource
        if oauth.audience:
            form["audience"] = oauth.audience
        _apply_client_auth(target, registry, token_endpoint, form, headers)
        response = await transport.request(
            "POST",
            token_endpoint,
            headers=headers,
            form_body=form,
        )
        if response.status != 200:
            payload = _json_object(response)
            error = payload.get("error")
            checks.append(
                _check(
                    "oauth.token.acquire",
                    CheckStatus.FAIL,
                    "token endpoint rejected the configured grant",
                    started=started,
                    http_status=response.status,
                    evidence={"error": error if isinstance(error, str) else "missing"},
                    reference="RFC 6749 §5.2",
                )
            )
            return TokenResult(None, tuple(checks))
        payload = _json_object(response)
        access_token = payload.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise ValueError("successful token response is missing access_token")
        registry.register(access_token)
        refresh = payload.get("refresh_token")
        registry.register(refresh if isinstance(refresh, str) else None)
        token_type = payload.get("token_type")
        if not isinstance(token_type, str) or token_type.lower() != "bearer":
            raise ValueError("successful token response token_type is not Bearer")
        expires_in = payload.get("expires_in")
        if expires_in is not None and (
            isinstance(expires_in, bool)
            or not isinstance(expires_in, (int, float))
            or expires_in <= 0
        ):
            raise ValueError("successful token response expires_in is invalid")
        checks.append(
            _check(
                "oauth.token.acquire",
                CheckStatus.PASS,
                f"{oauth.flow.value} grant returned a Bearer token",
                started=started,
                http_status=response.status,
                reference="RFC 6749 §5.1",
                evidence={
                    "expires_in_present": expires_in is not None,
                    "refresh_token_issued": isinstance(refresh, str) and bool(refresh),
                },
            )
        )
        cache_control = response.headers.get("cache-control", "").lower()
        pragma = response.headers.get("pragma", "").lower()
        cache_ok = "no-store" in cache_control and "no-cache" in pragma
        checks.append(
            _check(
                "oauth.token.cache_headers",
                CheckStatus.PASS if cache_ok else CheckStatus.FAIL,
                "token response disables caching"
                if cache_ok
                else "token response is missing no-store/no-cache headers",
                started=started,
                reference="RFC 6749 §5.1",
            )
        )
        granted_scope = payload.get("scope")
        granted = (
            set(granted_scope.split()) if isinstance(granted_scope, str) else set(oauth.scopes)
        )
        required = set(target.expectations.scopes)
        missing = sorted(required - granted)
        checks.append(
            _check(
                "oauth.token.scope.policy",
                CheckStatus.FAIL if missing else CheckStatus.PASS,
                "token scope policy is satisfied"
                if not missing
                else "token response is missing required scopes",
                started=started,
                evidence={"missing_scopes": missing, "granted_scope_count": len(granted)},
            )
        )
        claims = _decode_claims(access_token)
        if target.expectations.issuers or target.expectations.audiences:
            if claims is None:
                checks.append(
                    _check(
                        "oauth.token.claims.policy",
                        CheckStatus.FAIL,
                        "claim policy requires a JWT-shaped token but the token is opaque",
                        started=started,
                    )
                )
            else:
                issuer = claims.get("iss")
                audience_value = claims.get("aud")
                audiences = (
                    {audience_value}
                    if isinstance(audience_value, str)
                    else set(audience_value)
                    if isinstance(audience_value, list)
                    and all(isinstance(item, str) for item in audience_value)
                    else set()
                )
                issuer_ok = not target.expectations.issuers or issuer in target.expectations.issuers
                audience_ok = not target.expectations.audiences or bool(
                    audiences.intersection(target.expectations.audiences)
                )
                checks.append(
                    _check(
                        "oauth.token.claims.policy",
                        CheckStatus.PASS if issuer_ok and audience_ok else CheckStatus.FAIL,
                        "unverified routing claims match deployment policy"
                        if issuer_ok and audience_ok
                        else "unverified routing claims violate issuer/audience policy",
                        started=started,
                        evidence={
                            "issuer_matches": issuer_ok,
                            "audience_matches": audience_ok,
                            "note": "diagnostic claim decoding; MCP resource acceptance is authoritative",
                        },
                    )
                )
        else:
            checks.append(
                _check(
                    "oauth.token.claims.policy",
                    CheckStatus.SKIP,
                    "no JWT claim policy configured; opaque tokens remain valid",
                    started=started,
                    applicable=False,
                )
            )
        return TokenResult(access_token, tuple(checks))
    except (TransportError, ValueError) as exc:
        checks.append(
            _check(
                "oauth.token.acquire",
                CheckStatus.ERROR,
                str(exc),
                started=started,
                evidence={"endpoint": safe_url(token_endpoint)},
            )
        )
        return TokenResult(None, tuple(checks))
