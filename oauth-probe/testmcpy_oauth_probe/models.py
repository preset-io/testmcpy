"""Versioned, dependency-free configuration and result models."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

CONFIG_SCHEMA = "testmcpy.io/oauth-smoke/v1"
REPORT_SCHEMA = "testmcpy.io/oauth-smoke-report/v1"
SUPPORTED_SPEC_PROFILES = (
    "mcp-2025-03-26",
    "mcp-2025-06-18",
    "mcp-2025-11-25",
)


class CapabilityPolicy(str, Enum):
    """How an optional or deployment-specific capability is evaluated."""

    REQUIRED = "required"
    SUPPORTED = "supported"
    FORBIDDEN = "forbidden"
    IGNORE = "ignore"


class CheckStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    SKIP = "skip"
    WARN = "warn"
    ERROR = "error"


class AuthFlow(str, Enum):
    NONE = "none"
    BEARER = "bearer"
    REFRESH_TOKEN = "refresh_token"
    CLIENT_CREDENTIALS = "client_credentials"
    AUTHORIZATION_CODE = "authorization_code"


class ClientAuthMethod(str, Enum):
    NONE = "none"
    CLIENT_SECRET_BASIC = "client_secret_basic"
    CLIENT_SECRET_POST = "client_secret_post"
    CLIENT_SECRET_JWT = "client_secret_jwt"


@dataclass(frozen=True)
class SecretRef:
    """Reference to a secret. Secret values are never represented in config."""

    env: str


@dataclass(frozen=True)
class ValueRef:
    value: str | None = None
    env: str | None = None


@dataclass(frozen=True)
class Correlation:
    service: str | None = None
    region: str | None = None
    revision: str | None = None
    deployment_id: str | None = None


@dataclass(frozen=True)
class OAuthConfig:
    flow: AuthFlow = AuthFlow.NONE
    access_token: SecretRef | None = None
    refresh_token: SecretRef | None = None
    authorization_code: SecretRef | None = None
    pkce_verifier: SecretRef | None = None
    client_id: ValueRef | None = None
    client_secret: SecretRef | None = None
    client_auth_method: ClientAuthMethod = ClientAuthMethod.NONE
    scopes: tuple[str, ...] = ()
    resource: str | None = None
    audience: str | None = None
    token_endpoint: str | None = None
    redirect_uri: str | None = None
    error_probe: bool = True


@dataclass(frozen=True)
class Expectations:
    issuers: tuple[str, ...] = ()
    token_issuers: tuple[str, ...] = ()
    resources: tuple[str, ...] = ()
    audiences: tuple[str, ...] = ()
    scopes: tuple[str, ...] = ()
    grants: dict[str, CapabilityPolicy] = field(default_factory=dict)
    auth_methods: dict[str, CapabilityPolicy] = field(default_factory=dict)
    endpoints: dict[str, CapabilityPolicy] = field(default_factory=dict)
    capabilities: dict[str, CapabilityPolicy] = field(default_factory=dict)
    unauthorized_status: int = 401
    initialize_status: int = 200
    initialized_statuses: tuple[int, ...] = (200, 202)
    tools_list_status: int = 200
    min_tools: int = 0

    def policy(self, capability: str, default: CapabilityPolicy) -> CapabilityPolicy:
        return self.capabilities.get(capability, default)


@dataclass(frozen=True)
class TargetConfig:
    id: str
    mcp_url: str
    spec_profile: str = "mcp-2025-06-18"
    correlation: Correlation = field(default_factory=Correlation)
    oauth: OAuthConfig = field(default_factory=OAuthConfig)
    expectations: Expectations = field(default_factory=Expectations)
    timeout_seconds: float = 20.0
    max_response_bytes: int = 1_048_576
    transient_retries: int = 1
    allow_http_loopback: bool = True
    allow_private_network: bool = False


@dataclass(frozen=True)
class RunProfile:
    targets: tuple[str, ...]


@dataclass(frozen=True)
class Manifest:
    schema: str
    targets: dict[str, TargetConfig]
    profiles: dict[str, RunProfile] = field(default_factory=dict)


@dataclass(frozen=True)
class CheckResult:
    id: str
    stage: str
    status: CheckStatus
    message: str
    duration_ms: int = 0
    applicable: bool = True
    reference: str | None = None
    http_status: int | None = None
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "id": self.id,
            "stage": self.stage,
            "status": self.status.value,
            "applicable": self.applicable,
            "message": self.message,
            "duration_ms": self.duration_ms,
            "evidence": self.evidence,
        }
        if self.reference is not None:
            result["reference"] = self.reference
        if self.http_status is not None:
            result["http_status"] = self.http_status
        return result


@dataclass(frozen=True)
class ProbeReport:
    target_id: str
    spec_profile: str
    started_at: str
    duration_ms: int
    correlation: Correlation
    checks: tuple[CheckResult, ...]

    @property
    def summary(self) -> dict[str, int]:
        return {
            status.value: sum(check.status is status for check in self.checks)
            for status in CheckStatus
        }

    @property
    def exit_code(self) -> int:
        if any(check.status is CheckStatus.ERROR for check in self.checks):
            return 2
        if any(check.status is CheckStatus.FAIL for check in self.checks):
            return 1
        return 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": {
                "id": self.target_id,
                "service": self.correlation.service,
                "region": self.correlation.region,
                "revision": self.correlation.revision,
                "deployment_id": self.correlation.deployment_id,
            },
            "spec_profile": self.spec_profile,
            "started_at": self.started_at,
            "duration_ms": self.duration_ms,
            "summary": self.summary,
            "checks": [check.to_dict() for check in self.checks],
        }


@dataclass(frozen=True)
class RunReport:
    schema: str
    run_id: str
    tool_version: str
    started_at: str
    duration_ms: int
    reports: tuple[ProbeReport, ...]

    @property
    def exit_code(self) -> int:
        return max((report.exit_code for report in self.reports), default=0)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "run": {
                "id": self.run_id,
                "tool_version": self.tool_version,
                "started_at": self.started_at,
                "duration_ms": self.duration_ms,
            },
            "targets": [report.to_dict() for report in self.reports],
        }
