"""Hard-limit enforcement around the probe's destination-safe transport."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit

from testmcpy_oauth_probe.secrets import safe_url
from testmcpy_oauth_probe.transport import HttpResponse, HttpTransport, TransportError

from testmcpy.gateway_smoke.config import Limits


class LimitExceeded(TransportError):  # type: ignore[misc]  # base resolves to Any without the probe's stubs
    """A configured hard limit stopped the run. Reported as ERROR, never PASS."""


class LimitedTransport:
    """Counts and bounds every request the lane makes.

    Wraps any ``HttpTransport`` (the real ``HttpxTransport`` keeps its redirect,
    HTTPS and private-network policy). A request over ``max_calls`` is refused
    before it is sent; a response that pushes the cumulative body size over
    ``max_total_bytes`` aborts the run. Per-response size is capped by the inner
    transport, and each call has its own timeout.
    """

    def __init__(self, inner: HttpTransport, limits: Limits) -> None:
        self._inner = inner
        self._limits = limits
        self.phase = "setup"
        self.calls: list[dict[str, Any]] = []
        self.total_bytes = 0

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
        if len(self.calls) >= self._limits.max_calls:
            raise LimitExceeded(f"max_calls limit of {self._limits.max_calls} reached")
        entry: dict[str, Any] = {
            "phase": self.phase,
            "method": method,
            "url": safe_url(url),
            "status": None,
            "bytes": 0,
            "duration_ms": 0,
            "error": None,
        }
        self.calls.append(entry)
        started = time.monotonic()
        try:
            response = await asyncio.wait_for(
                self._inner.request(
                    method,
                    url,
                    headers=headers,
                    json_body=json_body,
                    form_body=form_body,
                    # The lane never retries: a retry would hide a flaky
                    # gateway and would make the call count unpredictable.
                    retry_safe=False,
                ),
                timeout=self._limits.per_call_timeout_seconds,
            )
        except asyncio.TimeoutError as exc:
            entry["error"] = "per-call timeout"
            raise LimitExceeded(
                f"per-call timeout of {self._limits.per_call_timeout_seconds:g}s exceeded"
            ) from exc
        except TransportError as exc:
            entry["error"] = type(exc).__name__
            raise
        finally:
            entry["duration_ms"] = int((time.monotonic() - started) * 1000)
        entry["status"] = response.status
        entry["bytes"] = len(response.body)
        self.total_bytes += len(response.body)
        if self.total_bytes > self._limits.max_total_bytes:
            raise LimitExceeded(f"max_total_bytes limit of {self._limits.max_total_bytes} exceeded")
        return response

    async def aclose(self) -> None:
        await self._inner.aclose()

    # Token-phase introspection, used to separate "machine OAuth unavailable"
    # (BLOCKED) from an unexpected malfunction (ERROR).
    def phase_unavailable(self, phase: str) -> bool:
        for call in self.calls:
            if call["phase"] != phase:
                continue
            if call["error"] is not None:
                return True
            if call["status"] is not None and call["status"] != 200:
                return True
        return False


def path_of(url: str) -> str:
    return urlsplit(url).path or "/"
