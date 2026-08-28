"""Strict loader for the versioned OAuth probe manifest."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml

from testmcpy_oauth_probe.models import (
    CONFIG_SCHEMA,
    AuthFlow,
    CapabilityPolicy,
    ClientAuthMethod,
    Correlation,
    Expectations,
    Manifest,
    OAuthConfig,
    RunProfile,
    SecretRef,
    TargetConfig,
    ValueRef,
)


class ConfigError(ValueError):
    pass


_ENV_RE = re.compile(r"^\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-(.*))?\}$")


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
    if not isinstance(value, str) or not value:
        raise ConfigError(f"{path} must be a non-empty string")
    match = _ENV_RE.match(value)
    if match:
        env_name, default = match.groups()
        resolved = os.environ.get(env_name, default)
        if resolved is None:
            raise ConfigError(f"{path} references unset environment variable {env_name!r}")
        return resolved
    return value


def _strings(value: Any, path: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise ConfigError(f"{path} must be an array of non-empty strings")
    return tuple(value)


def _secret_ref(value: Any, path: str) -> SecretRef | None:
    if value is None:
        return None
    data = _mapping(value, path)
    _only(data, {"env"}, path)
    env_name = _string(data.get("env"), f"{path}.env", required=True)
    assert env_name is not None
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", env_name):
        raise ConfigError(f"{path}.env must be an environment variable name")
    return SecretRef(env=env_name)


def _value_ref(value: Any, path: str) -> ValueRef | None:
    if value is None:
        return None
    if isinstance(value, str):
        return ValueRef(value=value)
    data = _mapping(value, path)
    _only(data, {"env"}, path)
    env_name = _string(data.get("env"), f"{path}.env", required=True)
    assert env_name is not None
    return ValueRef(env=env_name)


def _policies(value: Any, path: str) -> dict[str, CapabilityPolicy]:
    data = _mapping(value, path)
    result: dict[str, CapabilityPolicy] = {}
    for name, raw_policy in data.items():
        try:
            result[name] = CapabilityPolicy(raw_policy)
        except ValueError as exc:
            choices = ", ".join(policy.value for policy in CapabilityPolicy)
            raise ConfigError(f"{path}.{name} must be one of: {choices}") from exc
    return result


def _oauth(value: Any, path: str) -> OAuthConfig:
    data = _mapping(value, path)
    _only(
        data,
        {
            "flow",
            "access_token",
            "refresh_token",
            "authorization_code",
            "pkce_verifier",
            "client_id",
            "client_secret",
            "client_auth_method",
            "scopes",
            "resource",
            "audience",
            "token_endpoint",
            "redirect_uri",
            "error_probe",
        },
        path,
    )
    try:
        flow = AuthFlow(data.get("flow", "none"))
        auth_method = ClientAuthMethod(data.get("client_auth_method", "none"))
    except ValueError as exc:
        raise ConfigError(f"{path} contains an unsupported flow or client auth method") from exc
    error_probe = data.get("error_probe", True)
    if not isinstance(error_probe, bool):
        raise ConfigError(f"{path}.error_probe must be a boolean")
    config = OAuthConfig(
        flow=flow,
        access_token=_secret_ref(data.get("access_token"), f"{path}.access_token"),
        refresh_token=_secret_ref(data.get("refresh_token"), f"{path}.refresh_token"),
        authorization_code=_secret_ref(
            data.get("authorization_code"), f"{path}.authorization_code"
        ),
        pkce_verifier=_secret_ref(data.get("pkce_verifier"), f"{path}.pkce_verifier"),
        client_id=_value_ref(data.get("client_id"), f"{path}.client_id"),
        client_secret=_secret_ref(data.get("client_secret"), f"{path}.client_secret"),
        client_auth_method=auth_method,
        scopes=_strings(data.get("scopes"), f"{path}.scopes"),
        resource=_string(data.get("resource"), f"{path}.resource"),
        audience=_string(data.get("audience"), f"{path}.audience"),
        token_endpoint=_string(data.get("token_endpoint"), f"{path}.token_endpoint"),
        redirect_uri=_string(data.get("redirect_uri"), f"{path}.redirect_uri"),
        error_probe=error_probe,
    )
    required: dict[AuthFlow, tuple[tuple[str, Any], ...]] = {
        AuthFlow.BEARER: (("access_token", config.access_token),),
        AuthFlow.REFRESH_TOKEN: (("refresh_token", config.refresh_token),),
        AuthFlow.AUTHORIZATION_CODE: (
            ("authorization_code", config.authorization_code),
            ("pkce_verifier", config.pkce_verifier),
            ("redirect_uri", config.redirect_uri),
        ),
        AuthFlow.CLIENT_CREDENTIALS: (("client_id", config.client_id),),
    }
    missing = [name for name, item in required.get(flow, ()) if item is None]
    if missing:
        raise ConfigError(f"{path} flow {flow.value!r} requires: {', '.join(missing)}")
    if auth_method is not ClientAuthMethod.NONE and config.client_id is None:
        raise ConfigError(f"{path}.client_id is required for {auth_method.value}")
    if auth_method is not ClientAuthMethod.NONE and config.client_secret is None:
        raise ConfigError(f"{path}.client_secret is required for {auth_method.value}")
    return config


def _expectations(value: Any, path: str) -> Expectations:
    data = _mapping(value, path)
    _only(
        data,
        {
            "issuers",
            "resources",
            "audiences",
            "scopes",
            "grants",
            "auth_methods",
            "endpoints",
            "capabilities",
            "unauthorized_status",
            "initialize_status",
            "initialized_statuses",
            "tools_list_status",
            "min_tools",
        },
        path,
    )
    status_fields: dict[str, int] = {}
    for name, default in (
        ("unauthorized_status", 401),
        ("initialize_status", 200),
        ("tools_list_status", 200),
        ("min_tools", 0),
    ):
        raw = data.get(name, default)
        if not isinstance(raw, int) or raw < 0:
            raise ConfigError(f"{path}.{name} must be a non-negative integer")
        status_fields[name] = raw
    initialized_statuses = data.get("initialized_statuses", [200, 202])
    if not isinstance(initialized_statuses, list) or not all(
        isinstance(item, int) and 100 <= item <= 599 for item in initialized_statuses
    ):
        raise ConfigError(f"{path}.initialized_statuses must be an array of HTTP statuses")
    return Expectations(
        issuers=_strings(data.get("issuers"), f"{path}.issuers"),
        resources=_strings(data.get("resources"), f"{path}.resources"),
        audiences=_strings(data.get("audiences"), f"{path}.audiences"),
        scopes=_strings(data.get("scopes"), f"{path}.scopes"),
        grants=_policies(data.get("grants"), f"{path}.grants"),
        auth_methods=_policies(data.get("auth_methods"), f"{path}.auth_methods"),
        endpoints=_policies(data.get("endpoints"), f"{path}.endpoints"),
        capabilities=_policies(data.get("capabilities"), f"{path}.capabilities"),
        unauthorized_status=status_fields["unauthorized_status"],
        initialize_status=status_fields["initialize_status"],
        initialized_statuses=tuple(initialized_statuses),
        tools_list_status=status_fields["tools_list_status"],
        min_tools=status_fields["min_tools"],
    )


def _correlation(value: Any, path: str) -> Correlation:
    data = _mapping(value, path)
    _only(data, {"service", "region", "revision", "deployment_id"}, path)
    return Correlation(
        service=_string(data.get("service"), f"{path}.service"),
        region=_string(data.get("region"), f"{path}.region"),
        revision=_string(data.get("revision"), f"{path}.revision"),
        deployment_id=_string(data.get("deployment_id"), f"{path}.deployment_id"),
    )


def _target(target_id: str, value: Any, defaults: Mapping[str, Any]) -> TargetConfig:
    path = f"targets.{target_id}"
    data = _mapping(value, path)
    _only(
        data,
        {
            "mcp_url",
            "spec_profile",
            "correlation",
            "oauth",
            "expectations",
            "timeout_seconds",
            "max_response_bytes",
            "transient_retries",
            "allow_http_loopback",
            "allow_private_network",
        },
        path,
    )
    merged = {**defaults, **data}
    mcp_url = _string(merged.get("mcp_url"), f"{path}.mcp_url", required=True)
    spec_profile = _string(merged.get("spec_profile", "mcp-2025-06-18"), f"{path}.spec_profile")
    assert mcp_url is not None and spec_profile is not None
    timeout = merged.get("timeout_seconds", 20.0)
    if not isinstance(timeout, (int, float)) or timeout <= 0:
        raise ConfigError(f"{path}.timeout_seconds must be positive")
    max_bytes = merged.get("max_response_bytes", 1_048_576)
    retries = merged.get("transient_retries", 1)
    if not isinstance(max_bytes, int) or max_bytes < 1024:
        raise ConfigError(f"{path}.max_response_bytes must be an integer >= 1024")
    if not isinstance(retries, int) or not 0 <= retries <= 5:
        raise ConfigError(f"{path}.transient_retries must be between 0 and 5")
    for boolean_name in ("allow_http_loopback", "allow_private_network"):
        if not isinstance(merged.get(boolean_name, boolean_name == "allow_http_loopback"), bool):
            raise ConfigError(f"{path}.{boolean_name} must be a boolean")
    return TargetConfig(
        id=target_id,
        mcp_url=mcp_url,
        spec_profile=spec_profile,
        correlation=_correlation(merged.get("correlation"), f"{path}.correlation"),
        oauth=_oauth(merged.get("oauth"), f"{path}.oauth"),
        expectations=_expectations(merged.get("expectations"), f"{path}.expectations"),
        timeout_seconds=float(timeout),
        max_response_bytes=max_bytes,
        transient_retries=retries,
        allow_http_loopback=merged.get("allow_http_loopback", True),
        allow_private_network=merged.get("allow_private_network", False),
    )


def _parse(document: Any) -> Manifest:
    root = _mapping(document, "manifest")
    _only(root, {"schema", "defaults", "targets", "profiles"}, "manifest")
    schema = _string(root.get("schema"), "schema", required=True)
    if schema != CONFIG_SCHEMA:
        raise ConfigError(f"unsupported schema {schema!r}; expected {CONFIG_SCHEMA!r}")
    defaults = _mapping(root.get("defaults"), "defaults")
    _only(
        defaults,
        {
            "spec_profile",
            "timeout_seconds",
            "max_response_bytes",
            "transient_retries",
            "allow_http_loopback",
            "allow_private_network",
        },
        "defaults",
    )
    target_values = _mapping(root.get("targets"), "targets")
    if not target_values:
        raise ConfigError("manifest must define at least one target")
    targets = {
        target_id: _target(target_id, value, defaults) for target_id, value in target_values.items()
    }
    profile_values = _mapping(root.get("profiles"), "profiles")
    profiles: dict[str, RunProfile] = {}
    for profile_name, value in profile_values.items():
        data = _mapping(value, f"profiles.{profile_name}")
        _only(data, {"targets"}, f"profiles.{profile_name}")
        selected = _strings(data.get("targets"), f"profiles.{profile_name}.targets")
        missing = sorted(set(selected) - set(targets))
        if missing:
            raise ConfigError(
                f"profiles.{profile_name} names unknown targets: {', '.join(missing)}"
            )
        profiles[profile_name] = RunProfile(targets=selected)
    return Manifest(schema=schema, targets=targets, profiles=profiles)


def loads_manifest(content: str, *, source: str = "<string>") -> Manifest:
    try:
        document = yaml.safe_load(content)
    except yaml.YAMLError as exc:
        raise ConfigError(f"invalid YAML/JSON in {source}") from exc
    return _parse(document)


def load_manifest(path: str | Path) -> Manifest:
    source = Path(path)
    try:
        content = source.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"cannot read manifest {source}") from exc
    return loads_manifest(content, source=str(source))


def manifest_json_schema() -> dict[str, Any]:
    """Small machine-readable schema descriptor for adapters and editors."""
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": CONFIG_SCHEMA,
        "type": "object",
        "required": ["schema", "targets"],
        "properties": {
            "schema": {"const": CONFIG_SCHEMA},
            "targets": {"type": "object", "minProperties": 1},
            "profiles": {"type": "object"},
        },
        "additionalProperties": False,
    }


def dump_manifest_schema() -> str:
    return json.dumps(manifest_json_schema(), indent=2, sort_keys=True)
