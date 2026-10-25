"""Strict, versioned configuration for the gateway smoke lane.

Everything the lane may touch is named here: one environment, one workspace,
one read-only fixture call. Secrets are referenced by environment variable
*name* only and are never part of the document.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import yaml
from testmcpy_oauth_probe.models import SUPPORTED_SPEC_PROFILES

CONFIG_SCHEMA = "testmcpy.io/gateway-smoke/v1"
REPORT_SCHEMA = "testmcpy.io/gateway-smoke-report/v1"

AUTH_MODES = ("client_credentials", "bearer")
CLIENT_AUTH_METHODS = ("client_secret_basic", "client_secret_post")
ASSERTION_OPS = ("equals", "exists", "type", "contains", "min_length")
JSON_TYPES = ("string", "number", "integer", "boolean", "object", "array", "null")

# A value containing this marker, or a host in a reserved documentation domain,
# means the checked-in example was run unedited. The lane refuses (BLOCKED) and
# never opens a socket to such a target.
PLACEHOLDER_MARKER = "REPLACE_ME"
_RESERVED_SUFFIXES = (
    ".example",
    ".example.com",
    ".example.net",
    ".example.org",
    ".test",
    ".invalid",
)

# Tool-name tokens that indicate a write or side effect. This is a config-time
# guard against an approved fixture being pointed at a mutating tool; it is a
# denylist, so it narrows mistakes rather than proving read-only behaviour. The
# single configured call is still the only call the lane ever makes.
WRITE_VERBS = frozenset(
    {
        "add", "cancel", "create", "delete", "drop", "duplicate", "execute", "export",
        "generate", "grant", "import", "insert", "kill", "move", "patch", "post",
        "publish", "put", "remove", "rename", "reset", "restore", "revoke", "run",
        "save", "send", "set", "share", "truncate", "update", "upsert", "write",
    }
)  # fmt: skip

_ENV_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


class ConfigError(ValueError):
    """The configuration is unusable. The lane reports this as BLOCKED."""


@dataclass(frozen=True)
class Limits:
    total_timeout_seconds: float = 60.0
    per_call_timeout_seconds: float = 15.0
    max_calls: int = 16
    max_response_bytes: int = 262_144
    max_total_bytes: int = 1_048_576


@dataclass(frozen=True)
class AuthConfig:
    mode: str = "client_credentials"
    client_id: str | None = None
    client_id_env: str | None = None
    client_secret_env: str | None = None
    client_auth_method: str = "client_secret_basic"
    access_token_env: str | None = None
    scopes: tuple[str, ...] = ()
    resource: str | None = None
    token_endpoint: str | None = None
    expected_token_issuers: tuple[str, ...] = ()
    expected_audiences: tuple[str, ...] = ()

    def env_names(self) -> tuple[str, ...]:
        """Environment variables that must be set for this mode, in order."""
        names: tuple[str | None, ...]
        if self.mode == "bearer":
            names = (self.access_token_env,)
        else:
            names = (self.client_id_env, self.client_secret_env)
        return tuple(name for name in names if name)


@dataclass(frozen=True)
class RequiredTool:
    name: str
    properties: tuple[str, ...] = ()
    required: tuple[str, ...] = ()


@dataclass(frozen=True)
class DiscoveryConfig:
    max_pages: int = 3
    max_tools: int = 50
    max_bytes: int = 65_536
    required_tools: tuple[RequiredTool, ...] = ()


@dataclass(frozen=True)
class Assertion:
    path: str
    op: str
    expected: Any = None


@dataclass(frozen=True)
class FixtureConfig:
    tool: str
    arguments: dict[str, Any]
    expect: tuple[Assertion, ...]
    workspace_argument: str | None = None
    inner_tool_argument: str | None = None


@dataclass(frozen=True)
class SmokeConfig:
    environment: str
    mcp_url: str
    workspace_id: str
    workspace_name: str
    spec_profile: str = "mcp-2025-06-18"
    auth: AuthConfig = field(default_factory=AuthConfig)
    unauthorized_status: int = 401
    require_challenge_metadata: bool = True
    expected_resources: tuple[str, ...] = ()
    expected_issuers: tuple[str, ...] = ()
    required_capabilities: tuple[str, ...] = ("tools",)
    limits: Limits = field(default_factory=Limits)
    discovery: DiscoveryConfig = field(default_factory=DiscoveryConfig)
    fixture: FixtureConfig | None = None
    allow_http_loopback: bool = False
    allow_private_network: bool = False

    @property
    def protocol_version(self) -> str:
        return self.spec_profile.removeprefix("mcp-")

    def placeholders(self) -> list[str]:
        """Names of fields still holding checked-in placeholder values."""
        found: list[str] = []
        values = {
            "environment": self.environment,
            "mcp_url": self.mcp_url,
            "workspace.id": self.workspace_id,
            "workspace.name": self.workspace_name,
        }
        if self.fixture is not None:
            values["fixture.arguments"] = repr(self.fixture.arguments)
        for name, value in values.items():
            if PLACEHOLDER_MARKER in value:
                found.append(name)
        host = (urlsplit(self.mcp_url).hostname or "").lower()
        if host.endswith(_RESERVED_SUFFIXES) and "mcp_url" not in found:
            if not (self.allow_http_loopback and host == "localhost"):
                found.append("mcp_url")
        return found


def _mapping(value: Any, path: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ConfigError(f"{path} must be an object")
    return {str(key): item for key, item in value.items()}


def _only(data: Mapping[str, Any], allowed: set[str], path: str) -> None:
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise ConfigError(f"{path} contains unknown field(s): {', '.join(unknown)}")


def _string(value: Any, path: str, *, required: bool = False) -> str | None:
    if value is None and not required:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{path} must be a non-empty string")
    return value


def _strings(value: Any, path: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(i, str) and i for i in value):
        raise ConfigError(f"{path} must be an array of non-empty strings")
    if len(set(value)) != len(value):
        raise ConfigError(f"{path} must not contain duplicates")
    return tuple(value)


def _int(value: Any, path: str, *, minimum: int, maximum: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not minimum <= value <= maximum:
        raise ConfigError(f"{path} must be an integer between {minimum} and {maximum}")
    return value


def _seconds(value: Any, path: str, *, maximum: float) -> float:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(value)
        or not 0 < value <= maximum
    ):
        raise ConfigError(f"{path} must be a number greater than 0 and at most {maximum:g}")
    return float(value)


def _bool(value: Any, path: str) -> bool:
    if not isinstance(value, bool):
        raise ConfigError(f"{path} must be a boolean")
    return value


def _env_ref(value: Any, path: str) -> str | None:
    """A secret reference: `{env: NAME}`. A literal secret is rejected."""
    if value is None:
        return None
    data = _mapping(value, path)
    _only(data, {"env"}, path)
    name = _string(data.get("env"), f"{path}.env", required=True)
    assert name is not None
    if not _ENV_NAME.fullmatch(name):
        raise ConfigError(f"{path}.env must be an environment variable name")
    return name


def _auth(value: Any) -> AuthConfig:
    data = _mapping(value, "auth")
    _only(
        data,
        {
            "mode", "client_id", "client_secret", "client_auth_method", "access_token",
            "scopes", "resource", "token_endpoint", "expected_token_issuers",
            "expected_audiences",
        },
        "auth",
    )  # fmt: skip
    mode = data.get("mode", "client_credentials")
    if mode not in AUTH_MODES:
        raise ConfigError(f"auth.mode must be one of: {', '.join(AUTH_MODES)}")
    method = data.get("client_auth_method", "client_secret_basic")
    if method not in CLIENT_AUTH_METHODS:
        raise ConfigError(
            f"auth.client_auth_method must be one of: {', '.join(CLIENT_AUTH_METHODS)}"
        )
    client_id_raw = data.get("client_id")
    client_id: str | None = None
    client_id_env: str | None = None
    if isinstance(client_id_raw, str):
        client_id = _string(client_id_raw, "auth.client_id")
    elif client_id_raw is not None:
        client_id_env = _env_ref(client_id_raw, "auth.client_id")
    config = AuthConfig(
        mode=mode,
        client_id=client_id,
        client_id_env=client_id_env,
        client_secret_env=_env_ref(data.get("client_secret"), "auth.client_secret"),
        client_auth_method=method,
        access_token_env=_env_ref(data.get("access_token"), "auth.access_token"),
        scopes=_strings(data.get("scopes"), "auth.scopes"),
        resource=_string(data.get("resource"), "auth.resource"),
        token_endpoint=_string(data.get("token_endpoint"), "auth.token_endpoint"),
        expected_token_issuers=_strings(
            data.get("expected_token_issuers"), "auth.expected_token_issuers"
        ),
        expected_audiences=_strings(data.get("expected_audiences"), "auth.expected_audiences"),
    )
    if mode == "bearer":
        if config.access_token_env is None:
            raise ConfigError("auth.mode bearer requires auth.access_token: {env: NAME}")
        if config.client_secret_env or config.client_id or config.client_id_env:
            raise ConfigError("auth.mode bearer does not accept client credentials")
    else:
        if config.client_secret_env is None or not (config.client_id or config.client_id_env):
            raise ConfigError(
                "auth.mode client_credentials requires auth.client_id and "
                "auth.client_secret: {env: NAME}"
            )
        if config.access_token_env:
            raise ConfigError("auth.mode client_credentials does not accept auth.access_token")
    return config


def _limits(value: Any) -> Limits:
    data = _mapping(value, "limits")
    _only(
        data,
        {
            "total_timeout_seconds", "per_call_timeout_seconds", "max_calls",
            "max_response_bytes", "max_total_bytes",
        },
        "limits",
    )  # fmt: skip
    base = Limits()
    limits = Limits(
        total_timeout_seconds=_seconds(
            data.get("total_timeout_seconds", base.total_timeout_seconds),
            "limits.total_timeout_seconds",
            maximum=600,
        ),
        per_call_timeout_seconds=_seconds(
            data.get("per_call_timeout_seconds", base.per_call_timeout_seconds),
            "limits.per_call_timeout_seconds",
            maximum=120,
        ),
        max_calls=_int(
            data.get("max_calls", base.max_calls), "limits.max_calls", minimum=3, maximum=40
        ),
        max_response_bytes=_int(
            data.get("max_response_bytes", base.max_response_bytes),
            "limits.max_response_bytes",
            minimum=1024,
            maximum=8_388_608,
        ),
        max_total_bytes=_int(
            data.get("max_total_bytes", base.max_total_bytes),
            "limits.max_total_bytes",
            minimum=1024,
            maximum=33_554_432,
        ),
    )
    if limits.per_call_timeout_seconds > limits.total_timeout_seconds:
        raise ConfigError("limits.per_call_timeout_seconds must not exceed total_timeout_seconds")
    return limits


def _discovery(value: Any) -> DiscoveryConfig:
    data = _mapping(value, "discovery")
    _only(data, {"max_pages", "max_tools", "max_bytes", "required_tools"}, "discovery")
    base = DiscoveryConfig()
    raw_tools = data.get("required_tools", [])
    if not isinstance(raw_tools, list):
        raise ConfigError("discovery.required_tools must be an array")
    tools: list[RequiredTool] = []
    for index, item in enumerate(raw_tools):
        path = f"discovery.required_tools[{index}]"
        if isinstance(item, str):
            tools.append(RequiredTool(name=_string(item, path, required=True) or ""))
            continue
        entry = _mapping(item, path)
        _only(entry, {"name", "properties", "required"}, path)
        tools.append(
            RequiredTool(
                name=_string(entry.get("name"), f"{path}.name", required=True) or "",
                properties=_strings(entry.get("properties"), f"{path}.properties"),
                required=_strings(entry.get("required"), f"{path}.required"),
            )
        )
    names = [tool.name for tool in tools]
    if len(set(names)) != len(names):
        raise ConfigError("discovery.required_tools must not repeat a tool name")
    return DiscoveryConfig(
        max_pages=_int(
            data.get("max_pages", base.max_pages), "discovery.max_pages", minimum=1, maximum=10
        ),
        max_tools=_int(
            data.get("max_tools", base.max_tools), "discovery.max_tools", minimum=1, maximum=500
        ),
        max_bytes=_int(
            data.get("max_bytes", base.max_bytes),
            "discovery.max_bytes",
            minimum=1024,
            maximum=8_388_608,
        ),
        required_tools=tuple(tools),
    )


def tool_is_write_like(name: str) -> bool:
    tokens = re.split(r"[^a-z0-9]+", re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name).lower())
    return any(token in WRITE_VERBS for token in tokens)


def _assertion(value: Any, path: str) -> Assertion:
    data = _mapping(value, path)
    _only(data, {"path", *ASSERTION_OPS}, path)
    field_path = _string(data.get("path"), f"{path}.path", required=True)
    assert field_path is not None
    ops = [op for op in ASSERTION_OPS if op in data]
    if len(ops) != 1:
        raise ConfigError(f"{path} needs exactly one of: {', '.join(ASSERTION_OPS)}")
    op = ops[0]
    expected = data[op]
    if op == "exists" and not isinstance(expected, bool):
        raise ConfigError(f"{path}.exists must be a boolean")
    if op == "type" and expected not in JSON_TYPES:
        raise ConfigError(f"{path}.type must be one of: {', '.join(JSON_TYPES)}")
    if op == "min_length":
        _int(expected, f"{path}.min_length", minimum=0, maximum=1_000_000)
    return Assertion(path=field_path, op=op, expected=expected)


def _fixture(value: Any) -> FixtureConfig | None:
    if value is None:
        return None
    data = _mapping(value, "fixture")
    _only(
        data,
        {"tool", "arguments", "read_only", "workspace_argument", "inner_tool_argument", "expect"},
        "fixture",
    )
    tool = _string(data.get("tool"), "fixture.tool", required=True)
    assert tool is not None
    # The operator must say so explicitly: an approved fixture is a read.
    if data.get("read_only") is not True:
        raise ConfigError("fixture.read_only must be true: the lane only performs approved reads")
    arguments = data.get("arguments", {})
    if not isinstance(arguments, Mapping):
        raise ConfigError("fixture.arguments must be an object")
    arguments = dict(arguments)
    inner_arg = _string(data.get("inner_tool_argument"), "fixture.inner_tool_argument")
    workspace_arg = _string(data.get("workspace_argument"), "fixture.workspace_argument")
    if tool_is_write_like(tool):
        raise ConfigError(f"fixture.tool {tool!r} looks like a write; refusing")
    if inner_arg is not None:
        inner = arguments.get(inner_arg)
        if not isinstance(inner, str) or not inner:
            raise ConfigError(f"fixture.arguments.{inner_arg} must name the dispatched tool")
        if tool_is_write_like(inner):
            raise ConfigError(f"dispatched tool {inner!r} looks like a write; refusing")
    raw_expect = data.get("expect")
    if not isinstance(raw_expect, list) or not raw_expect:
        raise ConfigError("fixture.expect must list at least one deterministic assertion")
    return FixtureConfig(
        tool=tool,
        arguments=arguments,
        expect=tuple(_assertion(item, f"fixture.expect[{i}]") for i, item in enumerate(raw_expect)),
        workspace_argument=workspace_arg,
        inner_tool_argument=inner_arg,
    )


def _parse(document: Any) -> SmokeConfig:
    root = _mapping(document, "config")
    _only(
        root,
        {
            "schema", "environment", "mcp_url", "spec_profile", "workspace", "auth", "challenge",
            "protocol", "limits", "discovery", "fixture", "allow_http_loopback",
            "allow_private_network",
        },
        "config",
    )  # fmt: skip
    if root.get("schema") != CONFIG_SCHEMA:
        raise ConfigError(f"unsupported schema {root.get('schema')!r}; expected {CONFIG_SCHEMA!r}")
    environment = _string(root.get("environment"), "environment", required=True)
    mcp_url = _string(root.get("mcp_url"), "mcp_url", required=True)
    assert environment is not None and mcp_url is not None
    spec_profile = root.get("spec_profile", "mcp-2025-06-18")
    if spec_profile not in SUPPORTED_SPEC_PROFILES:
        raise ConfigError(f"spec_profile must be one of: {', '.join(SUPPORTED_SPEC_PROFILES)}")
    workspace = _mapping(root.get("workspace"), "workspace")
    _only(workspace, {"id", "name"}, "workspace")
    workspace_id = _string(workspace.get("id"), "workspace.id", required=True)
    workspace_name = _string(workspace.get("name"), "workspace.name", required=True)
    assert workspace_id is not None and workspace_name is not None
    challenge = _mapping(root.get("challenge"), "challenge")
    _only(
        challenge, {"unauthorized_status", "require_metadata", "resources", "issuers"}, "challenge"
    )
    unauthorized = _int(
        challenge.get("unauthorized_status", 401),
        "challenge.unauthorized_status",
        minimum=100,
        maximum=599,
    )
    require_metadata = _bool(challenge.get("require_metadata", True), "challenge.require_metadata")
    protocol = _mapping(root.get("protocol"), "protocol")
    _only(protocol, {"required_capabilities"}, "protocol")
    capabilities = protocol.get("required_capabilities", ["tools"])
    capabilities = _strings(capabilities, "protocol.required_capabilities")
    fixture = _fixture(root.get("fixture"))
    if fixture is not None and fixture.workspace_argument is not None:
        if fixture.arguments.get(fixture.workspace_argument) != workspace_id:
            raise ConfigError(
                f"fixture.arguments.{fixture.workspace_argument} must equal workspace.id "
                "so the call cannot target a different workspace"
            )
    return SmokeConfig(
        environment=environment,
        mcp_url=mcp_url,
        workspace_id=workspace_id,
        workspace_name=workspace_name,
        spec_profile=spec_profile,
        auth=_auth(root.get("auth")),
        unauthorized_status=unauthorized,
        require_challenge_metadata=require_metadata,
        expected_resources=_strings(challenge.get("resources"), "challenge.resources"),
        expected_issuers=_strings(challenge.get("issuers"), "challenge.issuers"),
        required_capabilities=capabilities,
        limits=_limits(root.get("limits")),
        discovery=_discovery(root.get("discovery")),
        fixture=fixture,
        allow_http_loopback=_bool(root.get("allow_http_loopback", False), "allow_http_loopback"),
        allow_private_network=_bool(
            root.get("allow_private_network", False), "allow_private_network"
        ),
    )


def loads_config(content: str, *, source: str = "<string>") -> SmokeConfig:
    try:
        document = yaml.safe_load(content)
    except yaml.YAMLError as exc:
        raise ConfigError(f"invalid YAML/JSON in {source}") from exc
    return _parse(document)


def load_config(path: str | Path) -> SmokeConfig:
    source = Path(path)
    try:
        content = source.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"cannot read config {source}") from exc
    return loads_config(content, source=str(source))


def identity_hint(path: str | Path) -> tuple[str | None, str | None, str | None]:
    """Best-effort (environment, workspace id, workspace name) from a config
    that failed to load, so even a BLOCKED result says what it was aiming at."""
    try:
        document = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return None, None, None
    if not isinstance(document, Mapping):
        return None, None, None
    workspace = document.get("workspace")
    workspace = workspace if isinstance(workspace, Mapping) else {}

    def text(value: Any) -> str | None:
        return value if isinstance(value, str) and value else None

    return text(document.get("environment")), text(workspace.get("id")), text(workspace.get("name"))
