"""Probe error/result fidelity of a REAL local Superset MCP app, native vs generic.

Run like capture_superset_catalog.py (inside a Superset checkout, its venv,
initialised sqlite metadata DB with a user matching MCP_DEV_USERNAME):

    SUPERSET_CONFIG_PATH=/path/config.py PYTHONPATH=. python probe_superset_fidelity.py \
        --recorder <repo>/testmcpy/qualification/recorder.py \
        --traffic-out <repo>/qualification/native-tools/traffic/superset-real-fidelity.jsonl \
        --summary-out <repo>/qualification/native-tools/traffic/superset-real-fidelity.summary.json

It exercises only read paths and requests that fail before any write
(unknown identifiers, malformed arguments). It targets the in-process app and
an empty local sqlite DB; no network, no live workspace.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import sys
from typing import Any

PROBES: list[dict[str, Any]] = [
    {"id": "P01-list-empty", "tool": "list_charts", "args": {"request": {}}},
    {
        "id": "P02-get-missing",
        "tool": "get_chart_info",
        "args": {"request": {"identifier": 999999}},
    },
    {
        "id": "P03-sql-bad-db",
        "tool": "execute_sql",
        "args": {"request": {"database_id": 999999, "sql": "SELECT 1"}},
    },
    {"id": "P04-instance-info", "tool": "get_instance_info", "args": {"request": {}}},
    {
        "id": "P05-arg-wrong-type",
        "tool": "list_charts",
        "args": {"request": {"page": "not-a-number"}},
    },
    {"id": "P06-arg-unknown-key", "tool": "list_charts", "args": {"unexpected": 1}},
    {"id": "P07-unknown-tool", "tool": "no_such_tool", "args": {}},
    {"id": "P08-arg-missing-required", "tool": "generate_chart", "args": {"request": {}}},
    {
        "id": "P09-write-missing-dataset",
        "tool": "generate_chart",
        "args": {
            "request": {
                "dataset_id": 999999,
                "config": {"chart_type": "table", "columns": [{"name": "x"}]},
                "save_chart": False,
            }
        },
    },
]


def _load_recorder(path: str) -> Any:
    spec = importlib.util.spec_from_file_location("qual_recorder", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["qual_recorder"] = mod
    spec.loader.exec_module(mod)
    return mod


def _norm(result: Any) -> dict[str, Any]:
    d = result.model_dump(mode="json", by_alias=True, exclude_none=True)
    text = " ".join(c.get("text", "") for c in d.get("content", []) if c.get("type") == "text")
    return {
        "isError": bool(d.get("isError")),
        "has_structuredContent": "structuredContent" in d,
        "structured_keys": sorted((d.get("structuredContent") or {}).keys())[:12],
        "text_head": text[:240],
        "text_len": len(text),
    }


async def _run(rec_mod: Any) -> tuple[Any, list[dict[str, Any]]]:
    import superset  # noqa: F401
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client
    from superset.app import create_app

    app = create_app()
    rec = rec_mod.Recorder("superset-real")
    summary: list[dict[str, Any]] = []
    with app.app_context():
        from superset.mcp_service.app import mcp
        from superset.mcp_service.mcp_config import MCP_TOOL_SEARCH_CONFIG
        from superset.mcp_service.server import _apply_tool_search_transform

        async def session_run(surface: str) -> None:
            asgi = mcp.http_app(path="/mcp", json_response=True, stateless_http=True)
            async with asgi.router.lifespan_context(asgi):
                factory = rec.httpx_client_factory(asgi)
                async with streamablehttp_client(
                    "http://qualification.invalid/mcp", httpx_client_factory=factory
                ) as (read, write, _):
                    async with ClientSession(read, write) as session:
                        rec.mark(surface=surface, probe="initialize")
                        await session.initialize()
                        rec.mark(surface=surface, probe="tools/list")
                        await session.list_tools()
                        for probe in PROBES:
                            rec.mark(surface=surface, probe=probe["id"])
                            if surface == "native":
                                name, arguments = probe["tool"], probe["args"]
                            else:
                                name = "call_tool"
                                arguments = {"name": probe["tool"], "arguments": probe["args"]}
                            try:
                                res = await session.call_tool(name, arguments)
                                out = _norm(res)
                            except Exception as exc:  # protocol-level error
                                out = {"protocol_error": f"{type(exc).__name__}: {exc}"[:240]}
                            summary.append({"surface": surface, "probe": probe["id"], **out})
                        if surface == "generic":
                            rec.mark(surface=surface, probe="P10-call-tool-recursion")
                            res = await session.call_tool(
                                "call_tool", {"name": "call_tool", "arguments": {"name": "x"}}
                            )
                            summary.append(
                                {
                                    "surface": surface,
                                    "probe": "P10-call-tool-recursion",
                                    **_norm(res),
                                }
                            )

        await session_run("native")
        _apply_tool_search_transform(mcp, dict(MCP_TOOL_SEARCH_CONFIG))
        await session_run("generic")
    return rec, summary


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--recorder", required=True)
    ap.add_argument("--traffic-out", required=True)
    ap.add_argument("--summary-out", required=True)
    args = ap.parse_args()
    rec_mod = _load_recorder(args.recorder)
    rec, summary = asyncio.run(_run(rec_mod))
    rec.write_jsonl(args.traffic_out)
    with open(args.summary_out, "w") as fh:
        json.dump(summary, fh, indent=1, sort_keys=True)
        fh.write("\n")
    print(f"exchanges={len(rec.entries)} probes={len(summary)}", file=sys.stderr)


if __name__ == "__main__":
    main()
