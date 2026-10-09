"""Surface-level measurements that are not task runs.

catalog sizes, tools/list pagination completeness, permission/workspace
isolation, argument-rejection behaviour, and result fidelity.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from testmcpy.qualification.catalog import Catalog
from testmcpy.qualification.client import ConnectRefused, connect
from testmcpy.qualification.runner import PINNED, TOOL_SEARCH_DEF
from testmcpy.qualification.server import FixtureServer, SurfaceSpec
from testmcpy.qualification.tokens import (
    catalog_stats,
    compact_json,
    count_tokens,
    estimator,
    tool_tokens,
)
from testmcpy.qualification.world import KNOWLEDGE_TOOLS, ROLE_PERMS, World, required_permission

# --- catalog -------------------------------------------------------------------


def measure_catalog(catalog: Catalog) -> dict[str, Any]:
    native = catalog_stats(catalog.native_tools)
    generic = catalog_stats(catalog.generic_tools)
    pinned = [t for t in catalog.native_tools if t["name"] in PINNED]
    out: dict[str, Any] = {
        "catalog": catalog.name,
        "estimator": estimator(),
        "provenance": catalog.provenance,
        "synthetic_tools": catalog.synthetic_count,
        "native": native,
        "generic": generic,
        "native_deferred_initial": tool_tokens(TOOL_SEARCH_DEF)
        + sum(tool_tokens(t) for t in pinned),
    }
    instructions = (catalog.initialize or {}).get("instructions") or ""
    out["server_instructions_tokens"] = count_tokens(instructions) if instructions else None
    if catalog.output_schemas:
        out["output_schema_tokens_total"] = sum(
            count_tokens(compact_json(s)) for s in catalog.output_schemas.values()
        )
    searches: dict[str, dict[str, Any]] = {}
    for query, resp in catalog.search_responses.items():
        text = resp["content"][0]["text"]
        searches[query] = {
            "content_tokens": count_tokens(text),
            "structured_content_tokens": count_tokens(compact_json(resp.get("structuredContent"))),
            "hits": [h["name"] for h in json.loads(text)],
        }
    if searches:
        out["recorded_search_responses"] = searches
        toks = sorted(int(v["content_tokens"]) for v in searches.values())
        out["recorded_search_content_tokens_median"] = toks[len(toks) // 2]
    return out


# --- pagination ----------------------------------------------------------------


async def measure_pagination(
    catalog: Catalog, gateway_tools: list[dict[str, Any]], page_sizes: tuple[int | None, ...]
) -> list[dict[str, Any]]:
    rows = []
    for size in page_sizes:
        world = World()
        server = FixtureServer(
            world, catalog, gateway_tools, SurfaceSpec("native_eager", "single", page_size=size)
        )
        principal = world.principals["alice"]
        expected = [t["name"] for t in server.visible_tools(principal, world.workspaces["ws-a"])]
        async with server.running():
            async with connect(server, "alice", "ws-a") as s:
                listing = await s.list_all_tools()
        got = [t["name"] for t in listing.tools]
        first_page = size if size is not None else len(expected)
        rows.append(
            {
                "page_size": size,
                "pages": listing.pages,
                "expected": len(expected),
                "received": len(got),
                "unique": len(set(got)),
                "completeness": round(len(set(got) & set(expected)) / len(expected), 4),
                "duplicates": len(got) - len(set(got)),
                "first_page_only_coverage": round(
                    min(first_page, len(expected)) / len(expected), 4
                ),
                "latency_ms": round(listing.latency_ms, 2),
            }
        )
    return rows


# --- isolation -----------------------------------------------------------------


def _probe(pid: str, surface: str, expected: str, observed: str, leak: bool) -> dict[str, Any]:
    return {
        "id": pid,
        "surface": surface,
        "expected": expected,
        "observed": observed,
        "leak": leak,
    }


async def measure_isolation(
    catalog: Catalog, gateway_tools: list[dict[str, Any]]
) -> dict[str, Any]:
    probes: list[dict[str, Any]] = []
    ledger_total = 0
    for surface in ("native_eager", "generic"):
        world = World()
        single = FixtureServer(world, catalog, gateway_tools, SurfaceSpec(surface, "single"))
        gateway = FixtureServer(world, catalog, gateway_tools, SurfaceSpec(surface, "gateway"))
        async with single.running(), gateway.running():
            # 1. tools/list never exceeds the role
            for who in ("alice", "bob", "dave"):
                async with connect(single, who, "ws-a") as s:
                    names = [t["name"] for t in (await s.list_all_tools()).tools]
                allowed_perms = ROLE_PERMS[world.principals[who].role]
                by_name = {t["name"]: t for t in catalog.native_tools + KNOWLEDGE_TOOLS}
                if surface == "native_eager":
                    over = [
                        n
                        for n in names
                        if n in by_name and required_permission(by_name[n]) not in allowed_perms
                    ]
                    probes.append(
                        _probe(
                            f"visible-{who}",
                            surface,
                            "no tool above role",
                            f"{len(names)} tools, {len(over)} above role",
                            bool(over),
                        )
                    )
            # 2. direct call of a tool the role may not use
            native_args = {"request": {"database_id": 1, "sql": "SELECT 1"}}
            async with connect(single, "bob", "ws-a") as s:
                if surface == "native_eager":
                    out = await s.call("execute_sql", native_args)
                else:
                    out = await s.call(
                        "call_tool", {"name": "execute_sql", "arguments": native_args}
                    )
            ok = out.is_error and out.error_code in {"PERMISSION_DENIED", "UNKNOWN_TOOL"}
            probes.append(
                _probe(
                    "call-denied-tool-bob",
                    surface,
                    "error PERMISSION_DENIED|UNKNOWN_TOOL",
                    f"isError={out.is_error} code={out.error_code}",
                    not ok,
                )
            )
            # 3. data stays inside the workspace
            async with connect(single, "alice", "ws-b") as s:
                if surface == "native_eager":
                    out = await s.call("list_charts", {"request": {}})
                else:
                    out = await s.call(
                        "call_tool", {"name": "list_charts", "arguments": {"request": {}}}
                    )
            leaked = "Revenue by Region" in out.text or "Store Footfall" not in out.text
            probes.append(
                _probe(
                    "workspace-data-alice-ws-b",
                    surface,
                    "only ws-b data",
                    "ws-b data only" if not leaked else "foreign or missing data",
                    leaked,
                )
            )
            # 4. connections to a workspace without an active grant are refused
            for who, ws_id, code in (
                ("carol", "ws-b", "ACCESS_REVOKED"),
                ("bob", "ws-b", "ACCESS_DENIED"),
            ):
                try:
                    async with connect(single, who, ws_id):
                        probes.append(
                            _probe(
                                f"connect-{who}-{ws_id}",
                                surface,
                                f"refused {code}",
                                "connected",
                                True,
                            )
                        )
                except ConnectRefused as refused:
                    probes.append(
                        _probe(
                            f"connect-{who}-{ws_id}",
                            surface,
                            f"refused {code}",
                            f"HTTP {refused.status} {refused.code}",
                            refused.code != code or refused.status != 403,
                        )
                    )
            # 5. gateway: routing respects grants on one connection
            async with connect(gateway, "carol") as s:
                out = await s.call("list_workspaces", {})
                ids = [w["id"] for w in (out.structured or {}).get("workspaces", [])]
                probes.append(
                    _probe(
                        "gateway-list-carol",
                        surface,
                        "ws-a only (ws-b revoked)",
                        ",".join(ids),
                        ids != ["ws-a"],
                    )
                )
                if surface == "native_eager":
                    out = await s.call("list_charts", {"workspace_id": "ws-b", "request": {}})
                else:
                    out = await s.call(
                        "call_tool",
                        {
                            "workspace_id": "ws-b",
                            "tool_name": "list_charts",
                            "args": {"request": {}},
                        },
                    )
                probes.append(
                    _probe(
                        "gateway-call-carol-ws-b",
                        surface,
                        "error ACCESS_REVOKED",
                        f"isError={out.is_error} code={out.error_code}",
                        out.error_code != "ACCESS_REVOKED",
                    )
                )
            async with connect(gateway, "bob") as s:
                if surface == "native_eager":
                    out = await s.call("list_charts", {"workspace_id": "ws-b", "request": {}})
                else:
                    out = await s.call(
                        "call_tool",
                        {
                            "workspace_id": "ws-b",
                            "tool_name": "list_charts",
                            "args": {"request": {}},
                        },
                    )
                probes.append(
                    _probe(
                        "gateway-call-bob-ws-b",
                        surface,
                        "error ACCESS_DENIED",
                        f"isError={out.is_error} code={out.error_code}",
                        out.error_code != "ACCESS_DENIED",
                    )
                )
        ledger_total += len(world.ledger)
        probes.append(
            _probe(
                "no-writes-from-denied-attempts",
                surface,
                "ledger empty",
                f"{len(world.ledger)} writes",
                bool(world.ledger),
            )
        )
    return {
        "probes": probes,
        "leaks": sum(1 for p in probes if p["leak"]),
        "probe_count": len(probes),
    }


# --- argument rejection ---------------------------------------------------------

MALFORMED: tuple[tuple[str, str, dict[str, Any]], ...] = (
    ("wrong-type", "list_charts", {"request": {"page": "not-a-number"}}),
    ("unknown-key", "list_charts", {"unexpected": 1}),
    ("missing-required", "generate_chart", {"request": {}}),
    ("wrong-container", "get_dataset_info", {"request": "10"}),
)


async def measure_argument_probes(
    catalog: Catalog, gateway_tools: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    rows = []
    for surface in ("native_eager", "generic"):
        world = World()
        server = FixtureServer(world, catalog, gateway_tools, SurfaceSpec(surface, "single"))
        async with server.running():
            async with connect(server, "dave", "ws-a") as s:
                listing = await s.list_all_tools()
                typed = {
                    t["name"]
                    for t in listing.tools
                    if (t.get("inputSchema") or {}).get("properties")
                }
                for pid, tool, args in MALFORMED:
                    if surface == "native_eager":
                        out = await s.call(tool, args)
                    else:
                        out = await s.call("call_tool", {"name": tool, "arguments": args})
                    rows.append(
                        {
                            "probe": pid,
                            "surface": surface,
                            "rejected": out.is_error,
                            "message": out.text[:110],
                            "operation_schema_in_tools_list": tool in typed,
                            "writes": len(world.ledger),
                        }
                    )
    return rows


# --- fidelity (real Superset app probes) --------------------------------------------


# Only these response-model metadata paths vary in the committed captures.
# Paths are relative to structuredContent or the JSON envelope in content[0].
_VOLATILE_PATHS = {
    "P01-list-empty": ("timestamp",),
    "P02-get-missing": ("timestamp",),
    "P04-instance-info": ("timestamp",),
    "P09-write-missing-dataset": ("error", "timestamp"),
}


def _stable(result: dict[str, Any], probe: str) -> dict[str, Any]:
    """Mask known metadata only; leave data rows and other timestamps untouched."""
    out = copy.deepcopy(result)
    path = _VOLATILE_PATHS.get(probe)
    if path is None:
        return out
    parent = out.get("structuredContent")
    for key in path[:-1]:
        parent = parent.get(key) if isinstance(parent, dict) else None
    if isinstance(parent, dict) and isinstance(parent.get(path[-1]), str):
        parent[path[-1]] = "<t>"

    # Walk JSON text by offsets so only the metadata value is replaced, not
    # whitespace, key order, embedded strings, or any other content bytes.
    decoder = json.JSONDecoder()

    def timestamp_span(text: str, start: int, keys: tuple[str, ...]) -> tuple[int, int] | None:
        while start < len(text) and text[start].isspace():
            start += 1
        if not keys:
            value, end = decoder.raw_decode(text, start)
            return (start, end) if isinstance(value, str) else None
        if text[start : start + 1] != "{":
            return None
        pos = start + 1
        while True:
            while text[pos].isspace():
                pos += 1
            if text[pos] == "}":
                return None
            key, pos = decoder.raw_decode(text, pos)
            while text[pos].isspace():
                pos += 1
            pos += 1  # colon (the complete text was validated before walking)
            while text[pos].isspace():
                pos += 1
            if key == keys[0]:
                return timestamp_span(text, pos, keys[1:])
            _, pos = decoder.raw_decode(text, pos)
            while text[pos].isspace():
                pos += 1
            if text[pos] == "}":
                return None
            pos += 1  # comma

    for block in out.get("content", [])[:1]:
        if block.get("type") != "text" or not isinstance(block.get("text"), str):
            continue
        text = block["text"]
        try:
            json.loads(text)
        except ValueError:
            continue  # Plain error text is not a JSON response envelope.
        span = timestamp_span(text, 0, path)
        if span is not None:
            start, end = span
            block["text"] = text[:start] + '"<t>"' + text[end:]
    return out


def measure_fidelity(summary_path: str | Path) -> dict[str, Any]:
    rows = json.loads(Path(summary_path).read_text())
    native = {r["probe"]: r for r in rows if r["surface"] == "native"}
    generic = {r["probe"]: r for r in rows if r["surface"] == "generic"}
    compared = []
    for probe, n in native.items():
        g = generic.get(probe)
        if g is None:
            continue
        # Fail closed on legacy summaries: keys and excerpts are not fidelity evidence.
        if "result" not in n or "result" not in g:
            raise ValueError(f"Full result evidence missing for {probe}; recapture the summary")
        nr, gr = _stable(n["result"], probe), _stable(g["result"], probe)
        same_flags = (
            bool(nr.get("isError")) == bool(gr.get("isError"))
            and ("structuredContent" in nr) == ("structuredContent" in gr)
            and nr.get("structuredContent") == gr.get("structuredContent")
        )
        same_text = nr.get("content") == gr.get("content")
        compared.append(
            {
                "probe": probe,
                "flags_identical": same_flags,
                "text_identical": same_text,
                "native_text": n["text_head"][:90],
                "generic_text": g["text_head"][:90],
            }
        )
    exact = sum(1 for c in compared if c["flags_identical"] and c["text_identical"])
    return {
        "source": "real Superset app, in-memory, local sqlite (not fixtures)",
        "compared": compared,
        "identical": exact,
        "total": len(compared),
        "fraction": round(exact / len(compared), 4) if compared else None,
        "generic_only_probes": [p for p in generic if p not in native],
    }
