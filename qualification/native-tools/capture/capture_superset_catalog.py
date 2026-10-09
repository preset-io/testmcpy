"""Capture a real Superset MCP catalog for the SC-125472 qualification harness.

Run from inside a Superset checkout, with that checkout's virtualenv, after
`superset db upgrade && superset init` and a user matching MCP_DEV_USERNAME:

    SUPERSET_CONFIG_PATH=/path/to/config.py \
    python capture_superset_catalog.py --superset-sha <sha> --out catalog.json

The script talks to the real FastMCP app in memory (no network, no live
workspace) and records, as MCP wire objects:

* ``initialize`` result (server info + instructions),
* the native ``tools/list`` (every page),
* the generic surface after Superset's own ``_apply_tool_search_transform``
  using the shipped ``MCP_TOOL_SEARCH_CONFIG`` (``search_tools`` + ``call_tool``
  + pinned tools), and the real ``search_tools`` response for each query in
  ``--queries``.

Nothing is written to Superset; ``--queries`` are read-only searches.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from typing import Any

DEFAULT_QUERIES = [
    "list charts",
    "list datasets",
    "generate chart",
    "list databases",
    "execute sql query",
    "get dataset info",
    "list dashboards",
    "get dashboard info",
]


def emit(obj: Any, depth: int = 0) -> str:
    """Diff-friendly JSON: containers to depth 3 one entry per line, leaves compact."""
    pad = " " * (depth + 1)
    if depth < 3 and isinstance(obj, dict) and obj:
        body = ",\n".join(
            f"{pad}{json.dumps(k)}: {emit(v, depth + 1)}" for k, v in sorted(obj.items())
        )
        return "{\n" + body + "\n" + " " * depth + "}"
    if depth < 3 and isinstance(obj, list) and obj:
        body = ",\n".join(pad + emit(v, depth + 1) for v in obj)
        return "[\n" + body + "\n" + " " * depth + "]"
    return json.dumps(obj, separators=(",", ":"), sort_keys=True)


def _dump(obj: Any) -> Any:
    return obj.model_dump(mode="json", by_alias=True, exclude_none=True)


async def _capture(queries: list[str]) -> dict[str, Any]:
    import superset  # noqa: F401  (must import before the MCP app)
    from fastmcp import Client
    from superset.app import create_app

    app = create_app()
    with app.app_context():
        from superset.mcp_service.app import mcp
        from superset.mcp_service.mcp_config import MCP_TOOL_SEARCH_CONFIG
        from superset.mcp_service.server import _apply_tool_search_transform

        out: dict[str, Any] = {}
        async with Client(mcp) as client:
            init = client.initialize_result
            out["initialize"] = _dump(init)
            pages = []
            cursor = None
            while True:
                res = await client.session.list_tools(cursor=cursor)
                pages.append([_dump(t) for t in res.tools])
                cursor = res.nextCursor
                if not cursor:
                    break
            out["native"] = {"pages": pages}

        _apply_tool_search_transform(mcp, dict(MCP_TOOL_SEARCH_CONFIG))
        async with Client(mcp) as client:
            res = await client.session.list_tools()
            generic: dict[str, Any] = {"tools": [_dump(t) for t in res.tools]}
            searches = {}
            for q in queries:
                r = await client.session.call_tool("search_tools", {"query": q})
                searches[q] = _dump(r)
            generic["search_responses"] = searches
            out["generic"] = generic
            out["search_config"] = dict(MCP_TOOL_SEARCH_CONFIG)
        return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--superset-sha", required=True)
    ap.add_argument("--superset-date", default="")
    ap.add_argument("--out", required=True)
    ap.add_argument(
        "--out-output-schemas",
        required=True,
        help="outputSchema payloads are split out (they are ~60% of the bytes and "
        "most clients never put them in the model prompt)",
    )
    ap.add_argument("--queries", nargs="*", default=DEFAULT_QUERIES)
    ap.add_argument("--out-search-responses", required=True)
    ap.add_argument(
        "--tasks",
        help="tasks.yaml: also record the search for every step's discovery phrase and "
        "exact tool name (the miss-retry query)",
    )
    args = ap.parse_args()
    import fastmcp
    import mcp as mcp_pkg

    queries = list(args.queries)
    if args.tasks:
        import yaml

        with open(args.tasks) as fh:
            for task in yaml.safe_load(fh)["tasks"]:
                for step in task["steps"]:
                    for q in (step.get("discovery"), step["tool"]):
                        if q and q != "list_workspaces" and q not in queries:
                            queries.append(q)
    data = asyncio.run(_capture(queries))
    data["provenance"] = {
        "source": "apache/superset superset.mcp_service (in-memory FastMCP app, no network)",
        "superset_sha": args.superset_sha,
        "superset_commit_date": args.superset_date,
        "fastmcp_version": fastmcp.__version__,
        "mcp_version": getattr(mcp_pkg, "__version__", "unknown"),
        "python": sys.version.split()[0],
        "live_workspace_contacted": False,
        "note": "Metadata-only: tools/list and read-only search_tools. No tool was executed.",
    }
    output_schemas: dict[str, Any] = {}
    for tool_list in [*data["native"]["pages"], data["generic"]["tools"]]:
        for tool in tool_list:
            if "outputSchema" in tool:
                output_schemas[tool["name"]] = tool.pop("outputSchema")
    search_responses = data["generic"].pop("search_responses")
    with open(args.out_search_responses, "w") as fh:
        fh.write(emit({"search_responses": search_responses}) + "\n")
    with open(args.out, "w") as fh:
        fh.write(emit(data) + "\n")
    with open(args.out_output_schemas, "w") as fh:
        fh.write(emit({"output_schemas": output_schemas}) + "\n")
    print(
        f"native={sum(len(p) for p in data['native']['pages'])} generic={len(data['generic']['tools'])} "
        f"searches={len(search_responses)}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    os.environ.setdefault("SUPERSET_CONFIG_PATH", "")
    main()
