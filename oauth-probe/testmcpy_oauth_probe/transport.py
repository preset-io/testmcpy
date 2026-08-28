"""Bounded HTTP transport with redirect, retry, and destination safety policy."""

from __future__ import annotations

import asyncio
import ipaddress
import socket
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlsplit

import httpx

from testmcpy_oauth_probe.models import TargetConfig

_TRANSIENT_STATUSES = frozenset({408, 429, 502, 503, 504})


class TransportError(RuntimeError):
    """A deliberately secret-free network or safety failure."""


@dataclass(frozen=True)
class HttpResponse:
    status: int
    headers: dict[str, str]
    body: bytes
    latency_ms: int
    url: str

    @property
    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")


class HttpTransport(Protocol):
    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        json_body: Mapping[str, Any] | None = None,
        form_body: Mapping[str, str] | None = None,
        retry_safe: bool = False,
    ) -> HttpResponse: ...

    async def aclose(self) -> None: ...


def _is_loopback_host(hostname: str) -> bool:
    if hostname.lower() == "localhost" or hostname.lower().endswith(".localhost"):
        return True
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False


def validate_url_syntax(url: str, target: TargetConfig) -> tuple[str, int]:
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as exc:
        raise TransportError("URL has invalid syntax") from exc
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise TransportError("URL must be an absolute HTTP(S) URL")
    if parsed.username is not None or parsed.password is not None:
        raise TransportError("URL userinfo is forbidden")
    if parsed.fragment:
        raise TransportError("URL fragments are forbidden")
    if parsed.scheme != "https" and not (
        target.allow_http_loopback and _is_loopback_host(parsed.hostname)
    ):
        raise TransportError("URL must use HTTPS (HTTP is allowed only for loopback fixtures)")
    return parsed.hostname, port or (443 if parsed.scheme == "https" else 80)


async def _resolved_addresses(
    hostname: str, port: int
) -> tuple[ipaddress.IPv4Address | ipaddress.IPv6Address, ...]:
    try:
        values = await asyncio.to_thread(
            socket.getaddrinfo,
            hostname,
            port,
            type=socket.SOCK_STREAM,
        )
    except (OSError, UnicodeError, ValueError) as exc:
        raise TransportError("destination hostname could not be resolved") from exc
    addresses: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
    for value in values:
        address = ipaddress.ip_address(value[4][0])
        if address not in addresses:
            addresses.append(address)
    if not addresses:
        raise TransportError("destination hostname resolved to no addresses")
    return tuple(addresses)


class HttpxTransport:
    def __init__(self, target: TargetConfig) -> None:
        self.target = target
        self._client = httpx.AsyncClient(
            timeout=target.timeout_seconds,
            follow_redirects=False,
            trust_env=False,
        )

    async def _validate_destination(self, url: str) -> None:
        hostname, port = validate_url_syntax(url, self.target)
        if self.target.allow_private_network:
            return
        addresses = await _resolved_addresses(hostname, port)
        if all(address.is_loopback for address in addresses) and self.target.allow_http_loopback:
            return
        if any(not address.is_global for address in addresses):
            raise TransportError("destination resolves to a non-public address blocked by policy")

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
        await self._validate_destination(url)
        attempts = self.target.transient_retries + 1 if retry_safe else 1
        response: httpx.Response | None = None
        started = time.monotonic()
        for attempt in range(attempts):
            try:
                response = await self._client.request(
                    method,
                    url,
                    headers=headers,
                    json=json_body,
                    data=form_body,
                )
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                if attempt + 1 < attempts:
                    await asyncio.sleep(min(0.1 * (2**attempt), 0.5))
                    continue
                raise TransportError("HTTP request failed before receiving a response") from exc
            # Deterministic 4xx and 500 responses are never retried. Only
            # explicitly classified transient statuses on retry-safe requests are.
            if response.status_code not in _TRANSIENT_STATUSES or attempt + 1 >= attempts:
                break
            await response.aclose()
            await asyncio.sleep(min(0.1 * (2**attempt), 0.5))
        assert response is not None
        body = await response.aread()
        latency_ms = int((time.monotonic() - started) * 1000)
        if len(body) > self.target.max_response_bytes:
            await response.aclose()
            raise TransportError("HTTP response exceeded the configured body-size limit")
        result = HttpResponse(
            status=response.status_code,
            headers={key.lower(): value for key, value in response.headers.items()},
            body=body,
            latency_ms=latency_ms,
            url=str(response.url),
        )
        await response.aclose()
        return result

    async def aclose(self) -> None:
        await self._client.aclose()
