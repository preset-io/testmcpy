"""Minimal bounded MCP Streamable HTTP session for the smoke lane.

The probe's ``probe_mcp`` discards the tool catalogue and the session id and has
no byte budget or ``tools/call``; the lane needs all three. JSON-RPC/SSE framing
is shared with the probe (``_rpc_messages``) rather than reimplemented.
"""

from __future__ import annotations

import json
from typing import Any

from testmcpy_oauth_probe.mcp import _rpc_messages
from testmcpy_oauth_probe.transport import HttpResponse, HttpTransport


class McpProtocolError(ValueError):
    """A response was not well-formed MCP. Reported as ERROR."""


class McpSession:
    def __init__(
        self, transport: HttpTransport, url: str, protocol_version: str, token: str
    ) -> None:
        self._transport = transport
        self._url = url
        self._protocol = protocol_version
        self._token = token
        self.session_id: str | None = None

    def _headers(self) -> dict[str, str]:
        headers = {
            "accept": "application/json, text/event-stream",
            "authorization": f"Bearer {self._token}",
            "content-type": "application/json",
            "mcp-protocol-version": self._protocol,
        }
        if self.session_id:
            headers["mcp-session-id"] = self.session_id
        return headers

    async def request(
        self, request_id: str, method: str, params: dict[str, Any]
    ) -> tuple[HttpResponse, dict[str, Any] | None]:
        """Send one JSON-RPC request.

        Returns the HTTP response and the correlated JSON-RPC message, or
        ``None`` for the message when the HTTP status is not 200 (the caller
        reports the status). A JSON-RPC ``error`` object is returned as-is.
        """
        response = await self._transport.request(
            "POST",
            self._url,
            headers=self._headers(),
            json_body={"jsonrpc": "2.0", "id": request_id, "method": method, "params": params},
        )
        if response.status != 200:
            return response, None
        return response, correlated(response, request_id)

    async def notify(self, method: str) -> HttpResponse:
        return await self._transport.request(
            "POST",
            self._url,
            headers=self._headers(),
            json_body={"jsonrpc": "2.0", "method": method},
        )


def correlated(response: HttpResponse, request_id: str) -> dict[str, Any]:
    try:
        messages = _rpc_messages(response)
    except ValueError as exc:
        raise McpProtocolError(str(exc)) from exc
    matches = [m for m in messages if m.get("id") == request_id]
    if len(matches) != 1:
        raise McpProtocolError("response does not contain exactly one correlated JSON-RPC message")
    message: dict[str, Any] = matches[0]
    if message.get("jsonrpc") != "2.0":
        raise McpProtocolError("response jsonrpc is not 2.0")
    if "result" not in message and "error" not in message:
        raise McpProtocolError("JSON-RPC response has neither result nor error")
    return message


def tool_payload(result: dict[str, Any]) -> Any:
    """The tool's data: ``structuredContent``, else the first JSON text block."""
    structured = result.get("structuredContent")
    if isinstance(structured, (dict, list)):
        return structured
    content = result.get("content")
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text")
                if isinstance(text, str):
                    try:
                        return json.loads(text)
                    except json.JSONDecodeError as exc:
                        raise McpProtocolError("tool result text content is not JSON") from exc
    raise McpProtocolError("tool result has neither structuredContent nor JSON text content")
