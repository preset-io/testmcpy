"""Compact, read-only, deterministic MCP gateway smoke lane (no LLM calls).

Built on the headless OAuth probe (`testmcpy_oauth_probe`): destination-safe
transport, RFC 9728/8414 discovery, non-interactive token acquisition and secret
redaction are reused as-is. See ``docs/gateway-smoke-lane.md``.
"""

from testmcpy.gateway_smoke.config import (
    CONFIG_SCHEMA,
    REPORT_SCHEMA,
    ConfigError,
    SmokeConfig,
    load_config,
    loads_config,
)
from testmcpy.gateway_smoke.models import SmokeReport, Status
from testmcpy.gateway_smoke.runner import run_smoke

__all__ = [
    "CONFIG_SCHEMA",
    "REPORT_SCHEMA",
    "ConfigError",
    "SmokeConfig",
    "SmokeReport",
    "Status",
    "load_config",
    "loads_config",
    "run_smoke",
]
