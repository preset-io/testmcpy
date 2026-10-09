"""Record raw MCP-over-HTTP traffic (JSON-RPC bodies) for checked-in evidence.

Depends only on ``httpx`` and the standard library so the same file can be
loaded by the Superset-side probe script, which runs in a different virtualenv.

Use ``Recorder.httpx_client_factory(app)`` as the ``httpx_client_factory`` of an
MCP streamable-HTTP client to talk to an in-process ASGI app, or
``Recorder.event_hooks()`` to attach to any ``httpx.AsyncClient``. Servers must
answer with plain JSON (``json_response=True``) so each body is one JSON-RPC
message.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx

_REDACT_HEADERS = {"authorization", "cookie", "x-api-key", "proxy-authorization"}


def _safe_headers(headers: Any) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in headers.items():
        out[key.lower()] = "<redacted>" if key.lower() in _REDACT_HEADERS else str(value)
    return out


def _body(raw: bytes) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except ValueError:
        return {"_non_json_body": raw[:2000].decode("utf-8", "replace")}


def schema_digest(schema: Any) -> str:
    """Stable digest of a JSON schema (compact, key-sorted JSON, sha256, 16 hex)."""
    blob = json.dumps(schema, separators=(",", ":"), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def digest_tools_list(body: Any) -> Any:
    """Replace a tools/list result's tool bodies by name, annotations and a schema digest.

    The full definitions live in the catalog fixture; the digest proves the
    traffic and the fixture describe the same typed schemas without repeating
    hundreds of kilobytes in every traffic file.
    """
    if not isinstance(body, dict):
        return body
    result = body.get("result")
    if not isinstance(result, dict) or not isinstance(result.get("tools"), list):
        return body
    digested = []
    for tool in result["tools"]:
        if not isinstance(tool, dict):
            digested.append(tool)
            continue
        schema = tool.get("inputSchema")
        digested.append(
            {
                "name": tool.get("name"),
                "annotations": tool.get("annotations"),
                "inputSchema_sha256_16": schema_digest(schema),
                "inputSchema_bytes": len(json.dumps(schema, separators=(",", ":"))),
                "has_outputSchema": "outputSchema" in tool,
            }
        )
    return {**body, "result": {**result, "tools": digested, "_tools_digested": True}}


class Recorder:
    """Collects one entry per HTTP exchange with timing."""

    def __init__(self, label: str = "", digest_tool_lists: bool = True) -> None:
        self.label = label
        self.digest_tool_lists = digest_tool_lists
        self.entries: list[dict[str, Any]] = []
        self._t0 = time.perf_counter()
        self.context: dict[str, Any] = {}

    def mark(self, **context: Any) -> None:
        """Attach fields (task id, step, surface) to the entries recorded next."""
        self.context = dict(context)

    def _maybe_digest(self, body: Any) -> Any:
        return digest_tools_list(body) if self.digest_tool_lists else body

    def event_hooks(self) -> dict[str, list[Callable[..., Any]]]:
        async def on_request(request: httpx.Request) -> None:
            request.extensions["qual_started"] = time.perf_counter()
            await request.aread()

        async def on_response(response: httpx.Response) -> None:
            await response.aread()
            req = response.request
            started = req.extensions.get("qual_started", time.perf_counter())
            self.entries.append(
                {
                    "seq": len(self.entries),
                    "t_ms": round((started - self._t0) * 1000, 3),
                    "latency_ms": round((time.perf_counter() - started) * 1000, 3),
                    **self.context,
                    "http": {
                        "method": req.method,
                        "path": req.url.path,
                        "status": response.status_code,
                        "request_headers": _safe_headers(req.headers),
                    },
                    "request": _body(req.content),
                    "response": self._maybe_digest(_body(response.content)),
                }
            )

        return {"request": [on_request], "response": [on_response]}

    def httpx_client_factory(self, app: Any) -> Callable[..., httpx.AsyncClient]:
        hooks = self.event_hooks()

        def factory(
            headers: dict[str, str] | None = None,
            timeout: httpx.Timeout | None = None,
            auth: httpx.Auth | None = None,
        ) -> httpx.AsyncClient:
            return httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://qualification.invalid",
                headers=headers,
                timeout=timeout or httpx.Timeout(30.0),
                auth=auth,
                event_hooks=hooks,
                follow_redirects=True,
            )

        return factory

    def rpc_methods(self) -> list[str]:
        out = []
        for e in self.entries:
            req = e.get("request")
            if isinstance(req, dict) and "method" in req:
                out.append(str(req["method"]))
        return out

    def write_jsonl(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w") as fh:
            for entry in self.entries:
                fh.write(json.dumps(entry, sort_keys=True, separators=(",", ":")) + "\n")
