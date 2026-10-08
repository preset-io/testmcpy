"""In-process MCP client for the fixture server, with raw traffic recording."""

from __future__ import annotations

import time
import warnings
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

import httpx
from mcp import ClientSession, types
from mcp.client.streamable_http import streamablehttp_client

from testmcpy.qualification.recorder import Recorder
from testmcpy.qualification.server import FixtureServer, bearer


class ConnectRefused(Exception):
    """The endpoint refused the connection with an HTTP error carrying a typed body."""

    def __init__(self, status: int, code: str | None, message: str | None) -> None:
        super().__init__(f"HTTP {status} {code}: {message}")
        self.status = status
        self.code = code
        self.message = message


@dataclass
class CallOutcome:
    name: str
    arguments: dict[str, Any]
    is_error: bool
    structured: Any
    text: str
    latency_ms: float
    protocol_error: str | None = None

    @property
    def error_code(self) -> str | None:
        err = (self.structured or {}).get("error") if isinstance(self.structured, dict) else None
        return err.get("code") if isinstance(err, dict) else None


@dataclass
class ListOutcome:
    pages: int
    tools: list[dict[str, Any]]
    latency_ms: float
    cursors_seen: list[str] = field(default_factory=list)


class Session:
    def __init__(self, session: ClientSession, recorder: Recorder) -> None:
        self.session = session
        self.recorder = recorder
        self.initialize_result: Any = None

    async def list_all_tools(self, max_pages: int = 100) -> ListOutcome:
        tools: list[dict[str, Any]] = []
        cursor: str | None = None
        pages = 0
        started = time.perf_counter()
        seen: list[str] = []
        while pages < max_pages:
            res = await self.session.list_tools(cursor=cursor)
            pages += 1
            tools += [
                t.model_dump(mode="json", by_alias=True, exclude_none=True) for t in res.tools
            ]
            cursor = res.nextCursor
            if not cursor or cursor in seen:
                break
            seen.append(cursor)
        return ListOutcome(pages, tools, (time.perf_counter() - started) * 1000, seen)

    async def call(self, name: str, arguments: dict[str, Any] | None = None) -> CallOutcome:
        arguments = arguments or {}
        started = time.perf_counter()
        try:
            res = await self.session.call_tool(name, arguments)
        except Exception as exc:  # protocol-level failure
            return CallOutcome(
                name,
                arguments,
                True,
                None,
                "",
                (time.perf_counter() - started) * 1000,
                f"{type(exc).__name__}: {exc}"[:300],
            )
        text = " ".join(c.text for c in res.content if isinstance(c, types.TextContent))
        return CallOutcome(
            name,
            arguments,
            bool(res.isError),
            res.structuredContent,
            text,
            (time.perf_counter() - started) * 1000,
        )


@asynccontextmanager
async def connect(
    server: FixtureServer,
    principal: str,
    workspace: str | None = None,
    recorder: Recorder | None = None,
) -> AsyncIterator[Session]:
    """Open an initialised session against ``server`` as ``principal``."""
    recorder = recorder or Recorder(f"{principal}")
    factory = recorder.httpx_client_factory(server)
    # mcp>=1.28 deprecates streamablehttp_client in favour of an API that is absent
    # from the mcp>=1.24 floor this project supports, so keep using it quietly.
    warnings.filterwarnings(
        "ignore", message=".*streamable_http_client.*", category=DeprecationWarning
    )
    try:
        async with streamablehttp_client(
            "http://qualification.invalid/mcp",
            headers={"Authorization": f"Bearer {bearer(principal, workspace)}"},
            httpx_client_factory=factory,
        ) as (read, write, _):
            async with ClientSession(read, write) as session:
                wrapper = Session(session, recorder)
                wrapper.initialize_result = await session.initialize()
                yield wrapper
    except BaseException:
        refusal = _refusal(recorder)
        if refusal is not None:
            raise refusal from None
        raise


def _refusal(recorder: Recorder) -> ConnectRefused | None:
    for entry in recorder.entries:
        status = entry["http"]["status"]
        if status >= 400:
            body = entry.get("response") or {}
            err = body.get("error") if isinstance(body, dict) else None
            err = err if isinstance(err, dict) else {}
            return ConnectRefused(status, err.get("code"), err.get("message"))
    return None


def unauthenticated_status(server: FixtureServer) -> Any:
    """Helper for tests: status of a request that carries no bearer token."""

    async def _go() -> int:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=server), base_url="http://qualification.invalid"
        ) as c:
            r = await c.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "ping"})
            return r.status_code

    return _go()
