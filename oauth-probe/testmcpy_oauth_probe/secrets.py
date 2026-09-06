"""Secret resolution and structural redaction for every output boundary."""

from __future__ import annotations

import os
import re
from dataclasses import asdict, is_dataclass
from typing import Any, Mapping
from urllib.parse import urlsplit, urlunsplit

from testmcpy_oauth_probe.models import SecretRef, ValueRef

REDACTED = "[REDACTED]"

_SENSITIVE_KEYS = frozenset(
    {
        "access_token",
        "authorization",
        "authorization_code",
        "client_assertion",
        "client_secret",
        "code",
        "code_verifier",
        "cookie",
        "id_token",
        "password",
        "pkce_verifier",
        "private_key",
        "proxy_authorization",
        "refresh_token",
        "secret",
        "session_id",
        "set_cookie",
        "token",
    }
)
_BEARER_RE = re.compile(r"(?i)(\bBearer\s+)[A-Za-z0-9._~+/=-]+")
_PRIVATE_KEY_RE = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"
)


class MissingSecretError(ValueError):
    def __init__(self, env_name: str) -> None:
        super().__init__(f"required credential environment variable {env_name!r} is unset")
        self.env_name = env_name


class SecretRegistry:
    """Per-run secret registry; values never leave this object unsanitized."""

    def __init__(self, environ: Mapping[str, str] | None = None) -> None:
        self._environ = environ if environ is not None else os.environ
        self._values: set[str] = set()

    def resolve(self, reference: SecretRef | None) -> str | None:
        if reference is None:
            return None
        value = self._environ.get(reference.env)
        if not value:
            raise MissingSecretError(reference.env)
        self.register(value)
        return value

    def resolve_value(self, reference: ValueRef | None) -> str | None:
        if reference is None:
            return None
        if reference.value is not None:
            return reference.value
        if reference.env is None:
            return None
        value = self._environ.get(reference.env)
        if not value:
            raise ValueError(f"required environment variable {reference.env!r} is unset")
        return value

    def register(self, value: str | None) -> None:
        if value:
            self._values.add(value)

    def scrub_text(self, value: str) -> str:
        for secret in sorted(self._values, key=len, reverse=True):
            value = value.replace(secret, REDACTED)
        value = _BEARER_RE.sub(rf"\1{REDACTED}", value)
        return _PRIVATE_KEY_RE.sub(REDACTED, value)

    def scrub(self, value: Any, key: str | None = None) -> Any:
        if key is not None and key.lower().replace("-", "_") in _SENSITIVE_KEYS:
            return REDACTED if value is not None else None
        if is_dataclass(value) and not isinstance(value, type):
            return self.scrub(asdict(value))
        if isinstance(value, str):
            return self.scrub_text(value)
        if isinstance(value, Mapping):
            return {str(item_key): self.scrub(item, str(item_key)) for item_key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [self.scrub(item) for item in value]
        return value

    def assert_clean(self, rendered: str) -> None:
        leaked = [secret for secret in self._values if secret and secret in rendered]
        if leaked:
            raise RuntimeError("refusing to emit a report containing a credential")


def safe_url(value: str) -> str:
    """Remove userinfo, query, and fragment from a URL before evidence output."""
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        return "[INVALID URL]"
    host = parsed.hostname or ""
    if ":" in host:
        host = f"[{host}]"
    if port is not None:
        host = f"{host}:{port}"
    return urlunsplit((parsed.scheme, host, parsed.path, "", ""))
