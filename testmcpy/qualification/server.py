"""Fixture MCP server exposing one tool surface over stateless streamable HTTP.

One server is built per (catalog, surface, topology). The principal and, in the
``single`` topology, the workspace come from the bearer token
``fixture:<principal>[:<workspace>]``; nothing else is trusted. The ASGI app can
be driven in-process (``httpx.ASGITransport``) or served on a port for real
clients (``python -m testmcpy.qualification serve``).

Surfaces
--------
``generic``         ``search_tools``/``call_tool`` (single) or the gateway's
                    ``search_workspace_tools``/``call_tool(workspace_id, ...)``.
``native_eager``    every permitted operation as its own typed tool.
``native_deferred`` the same server surface as eager; deferral is a client or
                    provider behaviour (MCP has no wire-level deferral), so it is
                    modelled in the runner and never claimed observed.

Topologies
----------
``single``   one workspace per connection (today's producer endpoint).
``gateway``  one connection, many workspaces. The native gateway shape here
             (a required ``workspace_id`` property on every tool) is an
             ASSUMPTION pending SC-125471, isolated in ``_native_gateway_tools``.
"""

from __future__ import annotations

import base64
import contextvars
import copy
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

import jsonschema
from mcp import types
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager

from testmcpy.qualification.catalog import Catalog
from testmcpy.qualification.search import rank_tools, search_result_entry
from testmcpy.qualification.world import (
    KNOWLEDGE_TOOLS,
    FixtureError,
    Principal,
    Workspace,
    World,
    tool_allowed,
)

SURFACES = ("generic", "native_eager", "native_deferred")
TOPOLOGIES = ("single", "gateway")
GATEWAY_META_TOOLS = ("list_workspaces", "list_workspace_services", "get_workspace_catalog")

_current: contextvars.ContextVar[tuple[Principal, str | None]] = contextvars.ContextVar(
    "qualification_session"
)


@dataclass(frozen=True)
class SurfaceSpec:
    kind: str = "native_eager"
    topology: str = "single"
    page_size: int | None = None  # tools/list page size; None = one page
    search_limit: int = 5

    def __post_init__(self) -> None:
        if self.kind not in SURFACES or self.topology not in TOPOLOGIES:
            raise ValueError(f"unknown surface/topology: {self.kind}/{self.topology}")


def bearer(principal: str, workspace: str | None = None) -> str:
    return f"fixture:{principal}" + (f":{workspace}" if workspace else "")


def _text_result(payload: Any, is_error: bool = False) -> types.CallToolResult:
    structured = payload if isinstance(payload, dict) else {"result": payload}
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=json.dumps(payload, separators=(",", ":")))],
        structuredContent=structured,
        isError=is_error,
    )


def _error_result(err: FixtureError) -> types.CallToolResult:
    return _text_result(err.payload(), is_error=True)


def _validate(schema: dict[str, Any], arguments: dict[str, Any]) -> str | None:
    try:
        jsonschema.validate(instance=arguments, schema=schema)
    except jsonschema.ValidationError as exc:
        return f"Input validation error: {exc.message}"
    return None


class FixtureServer:
    def __init__(
        self, world: World, catalog: Catalog, gateway_tools: list[dict], spec: SurfaceSpec
    ):
        self.world = world
        self.catalog = catalog
        self.gateway_tools = gateway_tools
        self.spec = spec
        self.server: Server = Server("qualification-fixture")
        self.server.request_handlers[types.ListToolsRequest] = self._handle_list
        self.server.request_handlers[types.CallToolRequest] = self._handle_call
        self.manager = StreamableHTTPSessionManager(
            app=self.server, json_response=True, stateless=True
        )
        self.calls: list[dict[str, Any]] = []  # server-side call log (name, principal)

    # -- catalog views ---------------------------------------------------
    def _native_for(self, principal: Principal, ws: Workspace | None) -> list[dict[str, Any]]:
        tools = [t for t in self.catalog.native_tools if tool_allowed(principal, t)]
        if self.spec.topology == "gateway":
            # A gateway list is workspace-independent, so Knowledge tools are always
            # listed and a disabled workspace answers FEATURE_DISABLED at call time.
            tools += [t for t in copy.deepcopy(KNOWLEDGE_TOOLS) if tool_allowed(principal, t)]
            tools = _native_gateway_tools(tools)
        elif ws is not None:
            tools += [t for t in self.world.extra_tools(ws) if tool_allowed(principal, t)]
        return tools

    def visible_tools(self, principal: Principal, ws: Workspace | None) -> list[dict[str, Any]]:
        if self.spec.kind == "generic":
            if self.spec.topology == "gateway":
                return copy.deepcopy(self.gateway_tools)
            return copy.deepcopy(self.catalog.generic_tools)
        tools = self._native_for(principal, ws)
        if self.spec.topology == "gateway":
            tools = [t for t in self.gateway_tools if t["name"] == "list_workspaces"] + tools
        return copy.deepcopy(tools)

    def _session(self) -> tuple[Principal, Workspace | None]:
        principal, ws_id = _current.get()
        ws = self.world.workspace_for(principal, ws_id) if ws_id else None
        return principal, ws

    # -- tools/list ------------------------------------------------------
    async def _handle_list(self, req: types.ListToolsRequest) -> types.ServerResult:
        try:
            principal, ws = self._session()
        except FixtureError:
            return types.ServerResult(types.ListToolsResult(tools=[]))
        tools = self.visible_tools(principal, ws)
        start = 0
        cursor = getattr(req.params, "cursor", None) if req.params else None
        if cursor:
            start = int(base64.urlsafe_b64decode(cursor.encode()).decode())
        size = self.spec.page_size or len(tools) or 1
        page = tools[start : start + size]
        nxt = None
        if start + size < len(tools):
            nxt = base64.urlsafe_b64encode(str(start + size).encode()).decode()
        return types.ServerResult(
            types.ListToolsResult(
                tools=[types.Tool.model_validate(t) for t in page], nextCursor=nxt
            )
        )

    # -- tools/call ------------------------------------------------------
    async def _handle_call(self, req: types.CallToolRequest) -> types.ServerResult:
        name = req.params.name
        arguments = req.params.arguments or {}
        principal, ws_id = _current.get()
        self.calls.append({"tool": name, "principal": principal.name, "workspace": ws_id})
        try:
            result = self._dispatch(principal, ws_id, name, arguments)
        except FixtureError as err:
            result = _error_result(err)
        return types.ServerResult(result)

    def _surface_tool(self, principal: Principal, ws: Workspace | None, name: str) -> dict:
        for t in self.visible_tools(principal, ws):
            if t["name"] == name:
                return t
        raise FixtureError("UNKNOWN_TOOL", f"Unknown tool: '{name}'", tool=name)

    def _dispatch(
        self, principal: Principal, ws_id: str | None, name: str, arguments: dict[str, Any]
    ) -> types.CallToolResult:
        ws = None
        if ws_id and self.spec.topology == "single":
            ws = self.world.workspace_for(principal, ws_id)
        surface_tool = self._surface_tool(principal, ws, name)
        bad = _validate(surface_tool.get("inputSchema") or {}, arguments)
        if bad:
            return _text_result(bad, is_error=True)

        if self.spec.topology == "gateway":
            return self._gateway(principal, name, arguments)

        if self.spec.kind == "generic" and name == "search_tools":
            return _text_result(self._search(principal, ws, arguments.get("query")))
        if self.spec.kind == "generic" and name == "call_tool":
            inner = arguments["name"]
            if inner in {"search_tools", "call_tool"}:
                raise FixtureError(
                    "RECURSIVE_CALL", f"'{inner}' is a synthetic search tool and cannot be called"
                )
            return self._run_named(principal, ws, inner, arguments.get("arguments") or {})
        return self._run_named(principal, ws, name, arguments)

    def _find_native(self, ws: Workspace | None, name: str) -> dict[str, Any]:
        for t in self.catalog.native_tools:
            if t["name"] == name:
                return t
        for t in KNOWLEDGE_TOOLS:
            if t["name"] == name:
                return copy.deepcopy(t)
        raise FixtureError("UNKNOWN_TOOL", f"Unknown tool: '{name}'", tool=name)

    def _run_named(
        self, principal: Principal, ws: Workspace | None, name: str, args: dict[str, Any]
    ) -> types.CallToolResult:
        assert ws is not None, "single topology requires a workspace in the token"
        tool = self._find_native(ws, name)
        bad = _validate(tool.get("inputSchema") or {}, args)
        if bad:
            return _text_result(bad, is_error=True)
        return _text_result(self.world.execute(principal, ws, tool, args))

    def _search(self, principal: Principal, ws: Workspace | None, query: str | None) -> list:
        visible = self._native_for(principal, ws)
        recorded = self.catalog.recorded_hits(query)
        if recorded is not None:
            # Real ranking, restricted to what this principal may use. Superset filters
            # before ranking, so a real filtered search could backfill; this is the
            # conservative subset.
            names = {t["name"] for t in visible}
            return [h for h in recorded if h["name"] in names]
        hits = rank_tools(visible, query or "", limit=self.spec.search_limit)
        return [search_result_entry(t) for t in hits]

    # -- gateway ---------------------------------------------------------
    def _gateway(
        self, principal: Principal, name: str, arguments: dict[str, Any]
    ) -> types.CallToolResult:
        if name == "list_workspaces":
            rows = [
                {"id": w.id, "name": w.name}
                for w in self.world.workspaces.values()
                if principal.grants.get(w.id) == "active"
            ]
            return _text_result({"workspaces": rows, "has_more": False})
        if name == "list_workspace_services":
            self.world.workspace_for(principal, arguments["workspace_id"])
            return _text_result({"services": ["superset"]})
        if name == "get_workspace_catalog":
            ws = self.world.workspace_for(principal, arguments["workspace_id"])
            return _text_result({"items": ws.data.get(arguments["asset_type"], [])})
        if name == "search_workspace_tools":
            ws = self.world.workspace_for(principal, arguments["workspace_id"])
            visible = self._native_for_ws(principal, ws)
            hits = rank_tools(
                visible, arguments["query"], limit=arguments.get("limit") or self.spec.search_limit
            )
            return _text_result({"tools": [search_result_entry(t) for t in hits]})
        if name == "call_tool":
            ws = self.world.workspace_for(principal, arguments["workspace_id"])
            tool = self._find_native(ws, arguments["tool_name"])
            args = arguments.get("args") or {}
            bad = _validate(tool.get("inputSchema") or {}, args)
            if bad:
                return _text_result(bad, is_error=True)
            return _text_result(self.world.execute(principal, ws, tool, args))
        # native gateway: tool name is the operation, workspace_id routes it
        ws = self.world.workspace_for(principal, arguments["workspace_id"])
        if ws.producer == "legacy":
            raise FixtureError(
                "UNSUPPORTED_PRODUCER",
                f"Workspace '{ws.id}' runs a producer without named tools; "
                "use compatibility mode (search_workspace_tools/call_tool).",
                workspace_id=ws.id,
                required="named-tools producer",
            )
        tool = self._find_native(ws, name)
        args = {k: v for k, v in arguments.items() if k != "workspace_id"}
        bad = _validate(tool.get("inputSchema") or {}, args)
        if bad:
            return _text_result(bad, is_error=True)
        return _text_result(self.world.execute(principal, ws, tool, args))

    def _native_for_ws(self, principal: Principal, ws: Workspace) -> list[dict[str, Any]]:
        tools = [t for t in self.catalog.native_tools if tool_allowed(principal, t)]
        return tools + [t for t in self.world.extra_tools(ws) if tool_allowed(principal, t)]

    # -- ASGI --------------------------------------------------------------
    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            return
        headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
        auth = headers.get("authorization", "")
        token = auth[7:] if auth.lower().startswith("bearer ") else ""
        parts = token.split(":")
        principal = (
            self.world.principals.get(parts[1])
            if len(parts) >= 2 and parts[0] == "fixture"
            else None
        )
        if principal is None:
            body = json.dumps({"error": "unauthorized"}).encode()
            await send(
                {
                    "type": "http.response.start",
                    "status": 401,
                    "headers": [(b"content-type", b"application/json")],
                }
            )
            await send({"type": "http.response.body", "body": body})
            return
        ws_id = parts[2] if len(parts) >= 3 else None
        if ws_id:
            try:
                self.world.workspace_for(principal, ws_id)
            except FixtureError as err:  # a single-workspace endpoint refuses the connection
                status = 403 if err.code in {"ACCESS_REVOKED", "ACCESS_DENIED"} else 404
                await send(
                    {
                        "type": "http.response.start",
                        "status": status,
                        "headers": [(b"content-type", b"application/json")],
                    }
                )
                await send(
                    {"type": "http.response.body", "body": json.dumps(err.payload()).encode()}
                )
                return
        reset = _current.set((principal, ws_id))
        try:
            await self.manager.handle_request(scope, receive, send)
        finally:
            _current.reset(reset)

    @asynccontextmanager
    async def running(self) -> AsyncIterator[FixtureServer]:
        async with self.manager.run():
            yield self


def _native_gateway_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """ASSUMED SC-125471 shape: every named tool also takes a required workspace_id."""
    out = []
    for t in tools:
        c = copy.deepcopy(t)
        schema = c.setdefault("inputSchema", {"type": "object", "properties": {}})
        props = schema.setdefault("properties", {})
        props["workspace_id"] = {
            "type": "string",
            "description": "Workspace to run this operation in (from list_workspaces).",
        }
        schema["required"] = sorted(set(schema.get("required", [])) | {"workspace_id"})
        out.append(c)
    return out


def load_gateway_tools(path: str) -> list[dict[str, Any]]:
    with open(path) as fh:
        return json.load(fh)["tools"]
