"""Stage-visible raw Streamable HTTP MCP initialize and tools/list probe."""

from __future__ import annotations

import json
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from testmcpy_oauth_probe.models import CheckResult, CheckStatus, TargetConfig
from testmcpy_oauth_probe.secrets import SecretRegistry
from testmcpy_oauth_probe.transport import HttpResponse, HttpTransport, TransportError


@dataclass(frozen=True)
class McpProbeResult:
    checks: tuple[CheckResult, ...]


def _check(
    check_id: str,
    stage: str,
    status: CheckStatus,
    message: str,
    *,
    started: float,
    http_status: int | None = None,
    evidence: dict[str, Any] | None = None,
) -> CheckResult:
    return CheckResult(
        id=check_id,
        stage=stage,
        status=status,
        message=message,
        duration_ms=int((time.monotonic() - started) * 1000),
        reference="MCP Streamable HTTP / JSON-RPC 2.0",
        http_status=http_status,
        evidence=evidence or {},
    )


def _rpc_messages(response: HttpResponse) -> list[dict[str, Any]]:
    content_type = response.headers.get("content-type", "").lower()
    values: list[Any] = []
    if "text/event-stream" in content_type:
        for line in response.text.splitlines():
            if line.startswith("data:"):
                try:
                    values.append(json.loads(line[5:].strip()))
                except json.JSONDecodeError as exc:
                    raise ValueError("MCP SSE response contains malformed JSON data") from exc
    elif "application/json" in content_type or "+json" in content_type:
        try:
            value = json.loads(response.body)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ValueError("MCP response contains malformed JSON") from exc
        values.extend(value if isinstance(value, list) else [value])
    else:
        raise ValueError("MCP response content type is neither JSON nor SSE")
    messages = [value for value in values if isinstance(value, dict)]
    if not messages:
        raise ValueError("MCP response contains no JSON-RPC object")
    return messages


def _correlated(response: HttpResponse, request_id: str) -> dict[str, Any]:
    matches = [message for message in _rpc_messages(response) if message.get("id") == request_id]
    if len(matches) != 1:
        raise ValueError("MCP response does not contain exactly one correlated JSON-RPC message")
    message = matches[0]
    if message.get("jsonrpc") != "2.0":
        raise ValueError("MCP response jsonrpc is not 2.0")
    if "error" in message:
        error = message.get("error")
        code = error.get("code") if isinstance(error, dict) else "invalid"
        raise ValueError(f"MCP JSON-RPC response is an error (code {code})")
    if "result" not in message:
        raise ValueError("MCP JSON-RPC response has neither result nor error")
    return message


def _headers(
    target: TargetConfig,
    token: str,
    session_id: str | None = None,
) -> dict[str, str]:
    headers = {
        "accept": "application/json, text/event-stream",
        "authorization": f"Bearer {token}",
        "content-type": "application/json",
        "mcp-protocol-version": target.spec_profile.removeprefix("mcp-"),
    }
    if session_id:
        headers["mcp-session-id"] = session_id
    return headers


async def probe_mcp(
    target: TargetConfig,
    transport: HttpTransport,
    registry: SecretRegistry,
    access_token: str,
) -> McpProbeResult:
    checks: list[CheckResult] = []
    expected_protocol = target.spec_profile.removeprefix("mcp-")
    initialize_id = "initialize-1"
    initialized_session: str | None = None
    started = time.monotonic()
    try:
        response = await transport.request(
            "POST",
            target.mcp_url,
            headers=_headers(target, access_token),
            json_body={
                "jsonrpc": "2.0",
                "id": initialize_id,
                "method": "initialize",
                "params": {
                    "protocolVersion": expected_protocol,
                    "capabilities": {},
                    "clientInfo": {"name": "testmcpy-oauth-probe", "version": "1"},
                },
            },
        )
        expected_status = target.expectations.initialize_status
        if response.status != expected_status:
            checks.append(
                _check(
                    "mcp.initialize.http_status",
                    "mcp_initialize",
                    CheckStatus.FAIL,
                    f"authenticated initialize returned HTTP {response.status}; expected {expected_status}",
                    started=started,
                    http_status=response.status,
                )
            )
            return McpProbeResult(tuple(checks))
        checks.append(
            _check(
                "mcp.initialize.http_status",
                "mcp_initialize",
                CheckStatus.PASS,
                f"authenticated initialize returned HTTP {response.status}",
                started=started,
                http_status=response.status,
            )
        )
        message = _correlated(response, initialize_id)
        result = message.get("result")
        if not isinstance(result, Mapping):
            raise ValueError("MCP initialize result is not an object")
        protocol = result.get("protocolVersion")
        server_info = result.get("serverInfo")
        capabilities = result.get("capabilities")
        contract_ok = (
            protocol == expected_protocol
            and isinstance(server_info, Mapping)
            and isinstance(capabilities, Mapping)
        )
        checks.append(
            _check(
                "mcp.initialize.protocol_contract",
                "mcp_initialize",
                CheckStatus.PASS if contract_ok else CheckStatus.FAIL,
                "initialize response is correlated and negotiated the requested protocol"
                if contract_ok
                else "initialize response violates correlation or protocol contracts",
                started=started,
                evidence={
                    "protocol_version": protocol if isinstance(protocol, str) else "invalid",
                    "server_info_present": isinstance(server_info, Mapping),
                    "capabilities_present": isinstance(capabilities, Mapping),
                },
            )
        )
        if not contract_ok:
            return McpProbeResult(tuple(checks))
        initialized_session = response.headers.get("mcp-session-id")
        registry.register(initialized_session)
    except (TransportError, ValueError) as exc:
        checks.append(
            _check(
                "mcp.initialize.protocol_contract",
                "mcp_initialize",
                CheckStatus.ERROR,
                str(exc),
                started=started,
            )
        )
        return McpProbeResult(tuple(checks))

    started = time.monotonic()
    try:
        response = await transport.request(
            "POST",
            target.mcp_url,
            headers=_headers(target, access_token, initialized_session),
            json_body={"jsonrpc": "2.0", "method": "notifications/initialized"},
        )
        accepted = response.status in target.expectations.initialized_statuses
        checks.append(
            _check(
                "mcp.initialized.http_status",
                "mcp_initialized",
                CheckStatus.PASS if accepted else CheckStatus.FAIL,
                f"initialized notification returned HTTP {response.status}; expected one of {list(target.expectations.initialized_statuses)}",
                started=started,
                http_status=response.status,
            )
        )
        if not accepted:
            return McpProbeResult(tuple(checks))
    except TransportError as exc:
        checks.append(
            _check(
                "mcp.initialized.http_status",
                "mcp_initialized",
                CheckStatus.ERROR,
                str(exc),
                started=started,
            )
        )
        return McpProbeResult(tuple(checks))

    tool_count = 0
    cursor: str | None = None
    for page in range(20):
        started = time.monotonic()
        request_id = f"tools-list-{page + 1}"
        params: dict[str, str] = {}
        if cursor is not None:
            params["cursor"] = cursor
        try:
            response = await transport.request(
                "POST",
                target.mcp_url,
                headers=_headers(target, access_token, initialized_session),
                json_body={
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "method": "tools/list",
                    "params": params,
                },
            )
            expected_status = target.expectations.tools_list_status
            if response.status != expected_status:
                checks.append(
                    _check(
                        "mcp.tools_list.http_status",
                        "mcp_tools_list",
                        CheckStatus.FAIL,
                        f"tools/list returned HTTP {response.status}; expected {expected_status}",
                        started=started,
                        http_status=response.status,
                    )
                )
                return McpProbeResult(tuple(checks))
            message = _correlated(response, request_id)
            result = message.get("result")
            if not isinstance(result, Mapping):
                raise ValueError("tools/list result is not an object")
            tools = result.get("tools")
            if not isinstance(tools, list) or not all(isinstance(tool, Mapping) for tool in tools):
                raise ValueError("tools/list tools is not an array of objects")
            tool_count += len(tools)
            next_cursor = result.get("nextCursor")
            if next_cursor is None:
                break
            if not isinstance(next_cursor, str) or not next_cursor:
                raise ValueError("tools/list nextCursor is invalid")
            cursor = next_cursor
        except (TransportError, ValueError) as exc:
            checks.append(
                _check(
                    "mcp.tools_list.protocol_contract",
                    "mcp_tools_list",
                    CheckStatus.ERROR,
                    str(exc),
                    started=started,
                )
            )
            return McpProbeResult(tuple(checks))
    else:
        checks.append(
            _check(
                "mcp.tools_list.pagination",
                "mcp_tools_list",
                CheckStatus.FAIL,
                "tools/list exceeded the 20-page safety limit",
                started=time.monotonic(),
            )
        )
        return McpProbeResult(tuple(checks))

    min_tools = target.expectations.min_tools
    checks.append(
        _check(
            "mcp.tools_list.protocol_contract",
            "mcp_tools_list",
            CheckStatus.PASS if tool_count >= min_tools else CheckStatus.FAIL,
            "tools/list returned correlated JSON-RPC pages"
            if tool_count >= min_tools
            else "tools/list returned fewer tools than deployment policy requires",
            started=started,
            http_status=target.expectations.tools_list_status,
            evidence={"tool_count": tool_count, "minimum": min_tools},
        )
    )
    return McpProbeResult(tuple(checks))
