"""Credential scrubbing for persisted test data.

Everything testmcpy writes to disk (SQLite rows, ``.results/*.json``
sidecars, checkpoints, ``--report`` files, smoke reports, generation
logs) passes through :func:`scrub_obj` first. Tool calls and results are
captured verbatim from the LLM session, so any secret that surfaces in a
tool result — an echoed env var, a token in an error message — would
otherwise be persisted in plaintext and can end up committed to a public
repo (this happened: a ``.results`` file containing live Datadog keys
was flagged by Datadog after appearing in a public fork).

Three tiers, ordered by precision:

1. **Known values** — exact occurrences of secrets testmcpy was handed
   (CLI ``--jwt-secret`` etc., profile auth configs) plus the values of
   any environment variable whose NAME looks sensitive
   (``*_API_KEY``, ``*_TOKEN``, ``*_SECRET``, ...). Zero false positives.
2. **Patterns** — high-precision shapes for well-known credential
   formats (Anthropic/GitHub/AWS/Slack tokens, ``Bearer`` headers,
   private-key blocks). Bare 32/40-char hex is deliberately NOT matched:
   it would mangle git SHAs and UUIDs in legitimate tool output.
3. **Field names** — dict values whose key is a well-known credential
   field (``jwt_secret``, ``auth_token``, ...) are masked to their first
   8 characters, matching the masking style used by the profiles API.
"""

from __future__ import annotations

import os
import re
from typing import Any

REDACTED = "***REDACTED***"

_MIN_SECRET_LEN = 8

# Matches whole `_`/`-`-delimited segments only, so MY_API_KEY and
# X-API-Key are sensitive but MONKEY / HOCKEY / TOKENIZER are not.
_SENSITIVE_ENV_NAME_RE = re.compile(
    r"(?:^|[_-])(?:KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL|AUTHORIZATION)S?(?:$|[_-])",
    re.IGNORECASE,
)

# Dict keys whose values are credentials by definition. Exact match on
# the lowercased key — deliberately not substring matching, so fields
# like "token_usage" or "tokens_input" are untouched.
_SENSITIVE_FIELD_NAMES = frozenset(
    {
        "access_token",
        "api_key",
        "api_secret",
        "api_token",
        "auth_token",
        "client_secret",
        "jwt_secret",
        "jwt_token",
        "password",
        "refresh_token",
        "secret",
        "token",
    }
)

# (compiled regex, replacement) — shapes specific enough to never match
# legitimate non-secret output.
_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}"), REDACTED),
    (re.compile(r"sk-proj-[A-Za-z0-9_-]{20,}"), REDACTED),
    (re.compile(r"ghp_[A-Za-z0-9]{36}"), REDACTED),
    (re.compile(r"github_pat_[A-Za-z0-9_]{20,}"), REDACTED),
    (re.compile(r"AKIA[0-9A-Z]{16}"), REDACTED),
    (re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"), REDACTED),
    (re.compile(r"(Bearer\s+)[A-Za-z0-9._~+/=-]{20,}"), rf"\1{REDACTED}"),
    (re.compile(r"(DD-API-KEY:\s*)\S+", re.IGNORECASE), rf"\1{REDACTED}"),
    (re.compile(r"(DD-APPLICATION-KEY:\s*)\S+", re.IGNORECASE), rf"\1{REDACTED}"),
    (
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
        REDACTED,
    ),
]

_registered_secrets: set[str] = set()
_env_secrets_cache: set[str] | None = None


def register_secret(value: str | None) -> None:
    """Register a known secret value to be redacted from all persisted data."""
    if isinstance(value, str) and len(value) >= _MIN_SECRET_LEN:
        _registered_secrets.add(value)


def register_secrets_from_auth(auth: dict[str, Any] | None) -> None:
    """Register secret values from an auth config dict.

    Walks nested dicts/lists so shapes like custom_headers auth
    (``{"type": "custom_headers", "headers": {"X-API-Key": "..."}}``)
    are covered — a string value is registered when its key matches the
    sensitive-name pattern (KEY/TOKEN/SECRET/AUTHORIZATION/...).
    """
    if isinstance(auth, list):
        for item in auth:
            register_secrets_from_auth(item)
        return
    if not isinstance(auth, dict):
        return
    for key, value in auth.items():
        if isinstance(value, str):
            if isinstance(key, str) and _SENSITIVE_ENV_NAME_RE.search(key):
                register_secret(value)
        elif isinstance(value, (dict, list)):
            register_secrets_from_auth(value)


def _env_secrets() -> set[str]:
    """Values of env vars whose names look credential-ish. Cached: the
    environment doesn't change mid-run, and this gets called per string."""
    global _env_secrets_cache
    if _env_secrets_cache is None:
        _env_secrets_cache = {
            v
            for k, v in os.environ.items()
            if _SENSITIVE_ENV_NAME_RE.search(k) and len(v) >= _MIN_SECRET_LEN
        }
    return _env_secrets_cache


def reset_cache() -> None:
    """Clear cached env secrets and registrations (for tests)."""
    global _env_secrets_cache
    _env_secrets_cache = None
    _registered_secrets.clear()


def _mask(value: str) -> str:
    """first8... masking for field-name hits, matching the profiles API style."""
    if len(value) > 12:
        return value[:8] + "..."
    return "***"


def scrub_text(text: str) -> str:
    """Redact known secret values and credential-shaped patterns from a string."""
    if not text:
        return text
    for secret in sorted(_registered_secrets | _env_secrets(), key=len, reverse=True):
        if secret in text:
            text = text.replace(secret, REDACTED)
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def scrub_obj(obj: Any) -> Any:
    """Recursively scrub strings in dicts/lists/tuples. Non-string scalars
    pass through untouched. Returns a new object; the input is not mutated."""
    if isinstance(obj, str):
        return scrub_text(obj)
    if isinstance(obj, dict):
        out = {}
        for key, value in obj.items():
            if (
                isinstance(key, str)
                and key.lower() in _SENSITIVE_FIELD_NAMES
                and isinstance(value, str)
                and value
            ):
                out[key] = _mask(value)
            else:
                out[key] = scrub_obj(value)
        return out
    if isinstance(obj, list):
        return [scrub_obj(item) for item in obj]
    if isinstance(obj, tuple):
        return tuple(scrub_obj(item) for item in obj)
    return obj
