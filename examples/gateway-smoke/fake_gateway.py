"""A local fake MCP gateway for exercising the smoke lane. Stdlib only.

It serves RFC 9728/8414 metadata, a client-credentials token endpoint and a
Streamable HTTP MCP endpoint whose tool catalogue is the generic gateway surface
from ``qualification/native-tools/fixtures/gateway-generic-tools.json``. Every
value it returns is synthetic. Misbehaviour is selected through ``Behavior``.

    python examples/gateway-smoke/fake_gateway.py --port 8765

then point a config at ``http://127.0.0.1:8765/mcp`` with ``allow_http_loopback:
true``. The synthetic credentials are client id ``fake-client`` and the secret in
``FAKE_GATEWAY_CLIENT_SECRET``.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

CATALOGUE = Path(__file__).resolve().parents[2] / (
    "qualification/native-tools/fixtures/gateway-generic-tools.json"
)
CANARY_WORKSPACE_ID = "fake-workspace-0001"
CANARY_WORKSPACE_NAME = "fake-smoke-canary"
CLIENT_ID = "fake-client"
ACCESS_TOKEN = "fake-gateway-access-token-0123456789"


@dataclass
class Behavior:
    client_secret: str = "fake-client-secret-0123456789"
    token_mode: str = "ok"  # ok | invalid_client | server_error | malformed
    # Challenge / protocol
    unauth_status: int = 401
    send_challenge: bool = True
    prm_resource: str | None = None  # None = the real MCP URL
    protocol_version: str | None = None  # None = echo the client's version
    capabilities: dict[str, Any] = field(default_factory=lambda: {"tools": {}})
    initialize_status: int = 200
    initialize_body: str | None = None  # raw body to send instead of JSON-RPC
    # Catalogue
    page_size: int = 100
    pad_description: int = 0  # bytes of padding on every tool description
    drop_tools: tuple[str, ...] = ()
    extra_tools: list[dict[str, Any]] = field(default_factory=list)
    endless_cursor: bool = False
    # Fixture call
    call_mode: str = (
        "ok"  # ok | wrong_value | is_error | rpc_error | malformed | slow | echo_token | status_500
    )
    call_delay: float = 0.0
    # Recording
    requests: list[dict[str, Any]] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)


def _tools(behavior: Behavior) -> list[dict[str, Any]]:
    tools = json.loads(CATALOGUE.read_text(encoding="utf-8"))["tools"]
    tools = [t for t in tools if t["name"] not in behavior.drop_tools]
    for tool in tools:
        if behavior.pad_description:
            tool["description"] = tool["description"] + ("x" * behavior.pad_description)
    return tools + list(behavior.extra_tools)


def _make_handler(behavior: Behavior) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args: Any) -> None:  # silence
            return

        @property
        def base(self) -> str:
            return f"http://127.0.0.1:{self.server.server_address[1]}"

        def _send(
            self, status: int, body: bytes = b"", headers: dict[str, str] | None = None
        ) -> None:
            try:
                self.send_response(status)
                for key, value in (headers or {}).items():
                    self.send_header(key, value)
                self.send_header("content-length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass  # the client gave up (a timeout test); nothing to report

        def _json(self, status: int, payload: Any, headers: dict[str, str] | None = None) -> None:
            merged = {"content-type": "application/json", **(headers or {})}
            self._send(status, json.dumps(payload).encode(), merged)

        def _body(self) -> bytes:
            return self.rfile.read(int(self.headers.get("content-length", "0")))

        def do_GET(self) -> None:  # noqa: N802
            behavior.requests.append({"method": "GET", "path": self.path})
            if self.path == "/.well-known/oauth-protected-resource/mcp":
                self._json(
                    200,
                    {
                        "resource": behavior.prm_resource or f"{self.base}/mcp",
                        "authorization_servers": [self.base],
                    },
                )
            elif self.path == "/.well-known/oauth-authorization-server":
                self._json(
                    200,
                    {
                        "issuer": self.base,
                        "token_endpoint": f"{self.base}/token",
                        "response_types_supported": ["code"],
                        "grant_types_supported": ["client_credentials"],
                        "token_endpoint_auth_methods_supported": [
                            "client_secret_basic",
                            "client_secret_post",
                        ],
                    },
                )
            else:
                self._send(404)

        def do_POST(self) -> None:  # noqa: N802
            body = self._body()
            behavior.requests.append({"method": "POST", "path": self.path})
            if self.path == "/token":
                self._token(body)
            elif self.path == "/mcp":
                self._mcp(body)
            else:
                self._send(404)

        def _token(self, body: bytes) -> None:
            mode = behavior.token_mode
            if mode == "server_error":
                self._json(503, {"error": "temporarily_unavailable"})
                return
            if mode == "malformed":
                self._send(200, b"<html>not json</html>", {"content-type": "text/html"})
                return
            auth = self.headers.get("authorization", "")
            expected = base64.b64encode(f"{CLIENT_ID}:{behavior.client_secret}".encode()).decode()
            if mode == "invalid_client" or auth != f"Basic {expected}":
                self._json(401, {"error": "invalid_client"})
                return
            self._json(
                200,
                {"access_token": ACCESS_TOKEN, "token_type": "Bearer", "expires_in": 300},
                {"cache-control": "no-store", "pragma": "no-cache"},
            )

        def _mcp(self, raw: bytes) -> None:
            if self.headers.get("authorization") != f"Bearer {ACCESS_TOKEN}":
                headers = {}
                if behavior.send_challenge:
                    headers["www-authenticate"] = (
                        f'Bearer resource_metadata="{self.base}'
                        '/.well-known/oauth-protected-resource/mcp"'
                    )
                self._json(behavior.unauth_status, {"error": "unauthorized"}, headers)
                return
            message = json.loads(raw)
            method, request_id = message.get("method"), message.get("id")
            if method == "notifications/initialized":
                self._send(202)
                return
            if method == "initialize":
                if behavior.initialize_status != 200:
                    self._send(behavior.initialize_status)
                    return
                if behavior.initialize_body is not None:
                    self._send(
                        200,
                        behavior.initialize_body.encode(),
                        {"content-type": "application/json"},
                    )
                    return
                version = behavior.protocol_version or message["params"]["protocolVersion"]
                self._rpc(
                    request_id,
                    {
                        "protocolVersion": version,
                        "capabilities": behavior.capabilities,
                        "serverInfo": {"name": "fake-gateway", "version": "0"},
                    },
                    {"mcp-session-id": "fake-session-0123456789"},
                )
            elif method == "tools/list":
                self._list(message)
            elif method == "tools/call":
                self._call(message)
            else:
                self._rpc_error(request_id, -32601, "method not found")

        def _rpc(self, request_id: Any, result: Any, headers: dict[str, str] | None = None) -> None:
            self._json(200, {"jsonrpc": "2.0", "id": request_id, "result": result}, headers)

        def _rpc_error(self, request_id: Any, code: int, text: str) -> None:
            self._json(
                200, {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": text}}
            )

        def _list(self, message: dict[str, Any]) -> None:
            tools = _tools(behavior)
            cursor = (message.get("params") or {}).get("cursor")
            start = int(cursor) if cursor else 0
            page = tools[start : start + behavior.page_size]
            result: dict[str, Any] = {"tools": page}
            if behavior.endless_cursor:
                # A server that never stops paging: the lane's page cap must bite.
                result["tools"] = [
                    {"name": f"filler_{start}_{i}", "inputSchema": {"type": "object"}}
                    for i in range(2)
                ]
                result["nextCursor"] = str(start + 1)
            elif start + behavior.page_size < len(tools):
                result["nextCursor"] = str(start + behavior.page_size)
            self._rpc(message["id"], result)

        def _call(self, message: dict[str, Any]) -> None:
            params = message["params"]
            behavior.tool_calls.append(params)
            request_id = message["id"]
            mode = behavior.call_mode
            if behavior.call_delay:
                time.sleep(behavior.call_delay)
            if mode == "status_500":
                self._send(500)
            elif mode == "rpc_error":
                self._rpc_error(request_id, -32000, "boom")
            elif mode == "is_error":
                self._rpc(
                    request_id,
                    {"isError": True, "content": [{"type": "text", "text": "workspace not found"}]},
                )
            elif mode == "malformed":
                self._send(200, b"{not json", {"content-type": "application/json"})
            else:
                workspace = (params.get("arguments") or {}).get("workspace_id")
                payload = {
                    "workspace_id": workspace,
                    "workspace_name": CANARY_WORKSPACE_NAME,
                    "services": ["databases", "datasets", "charts", "dashboards"],
                }
                if mode == "wrong_value":
                    payload["workspace_name"] = "some-other-workspace"
                if mode == "echo_token":
                    payload["workspace_name"] = f"leaked {ACCESS_TOKEN}"
                self._rpc(
                    request_id,
                    {"content": [{"type": "text", "text": json.dumps(payload)}], "isError": False},
                )

    return Handler


@contextmanager
def serve(behavior: Behavior | None = None) -> Iterator[tuple[str, Behavior]]:
    behavior = behavior or Behavior()
    server = ThreadingHTTPServer(("127.0.0.1", 0), _make_handler(behavior))
    thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.01), daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}", behavior
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    behavior = Behavior(client_secret=os.environ.get("FAKE_GATEWAY_CLIENT_SECRET", "unset-secret"))
    server = ThreadingHTTPServer(("127.0.0.1", args.port), _make_handler(behavior))
    print(f"fake gateway listening on http://127.0.0.1:{args.port}/mcp", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
