"""Command line: ``python -m testmcpy.qualification {run,serve}``."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any

from testmcpy.qualification import catalog as catalog_mod
from testmcpy.qualification import evaluate, measure, policy, report, runner, server, tasks

DEFAULT_ROOT = Path("qualification/native-tools")
CATALOG_STEM = "fixtures/catalog.superset-master-100f5124"


def load_actual(root: Path) -> catalog_mod.Catalog:
    stem = root / CATALOG_STEM
    return catalog_mod.load_catalog(
        f"{stem}.json", f"{stem}.output-schemas.json", f"{stem}.search-responses.json"
    )


def blocked_items() -> list[dict[str, str]]:
    return [
        {
            "what": "LLM-driven task accuracy, argument-failure and tool-selection rates (B06 llm, B08 model part)",
            "reason": "no LLM driver ran in this baseline; the scripted reference agent only proves the surface can express each task",
        },
        {
            "what": "Observed (not simulated) approval prompts in Codex, Claude Code, Claude.ai, ChatGPT",
            "reason": "approvals are a client policy model here; observed behaviour is recorded per client in client_matrix.yaml and is BLOCKED for clients that cannot be driven non-interactively",
        },
        {
            "what": "Provider deferred loading (OpenAI Responses tool search, Anthropic tool search tool)",
            "reason": "no OPENAI_API_KEY / ANTHROPIC_API_KEY in this environment; native_deferred numbers are a client-side cost model, not provider behaviour",
        },
        {
            "what": "Producer (SC-125470) named-tool contract and gateway (SC-125471) multi-workspace shape",
            "reason": "code not merged; the gateway native shape (required workspace_id on every tool) and the Knowledge tools are labelled assumptions in the fixture",
        },
        {
            "what": "Latency against staging/sandbox/production endpoints",
            "reason": "no live endpoint is used; B04 is informational fixture protocol overhead",
        },
    ]


async def run_all(root: Path, out_dir: Path, run_id: str) -> dict[str, Any]:
    from importlib.metadata import version

    from testmcpy.qualification import tokens

    actual = load_actual(root)
    scale = catalog_mod.scale_catalog(actual, 150)
    gw = server.load_gateway_tools(str(root / "fixtures/gateway-generic-tools.json"))
    suite = tasks.load_tasks(root / "tasks.yaml")
    budgets_path = root / "budgets.yaml"
    budgets = evaluate.load_budgets(budgets_path)

    all_runs: list[runner.TaskRun] = []
    catalogs_out: dict[str, Any] = {}
    pagination: dict[str, list[dict[str, Any]]] = {}
    for cat in (actual, scale):
        record = out_dir.parent / "traffic" / "fixture" if cat.name == "actual" else None
        r = runner.SuiteRunner(cat, gw, record_dir=record)
        all_runs += await r.run_suite(suite)
        catalogs_out[cat.name] = measure.measure_catalog(cat)
        pagination[cat.name] = await measure.measure_pagination(cat, gw, (None, 1, 7, 25, 50))
    metrics = evaluate.aggregate(all_runs, tuple(policy.POLICIES))
    isolation = await measure.measure_isolation(actual, gw)
    arg_probes = await measure.measure_argument_probes(actual, gw)
    fid_path = root / "traffic/superset-real-fidelity.summary.json"
    fidelity = measure.measure_fidelity(fid_path) if fid_path.exists() else None
    verdicts = evaluate.evaluate(
        budgets, metrics, catalogs_out, pagination, isolation["leaks"], fidelity
    )
    results: dict[str, Any] = {
        "meta": {
            "run_id": run_id,
            "harness": "testmcpy.qualification v1",
            "estimator": tokens.estimator(),
            "python": sys.version.split()[0],
            "mcp": version("mcp"),
            "fastmcp": version("fastmcp"),
            "budgets_sha256": hashlib.sha256(budgets_path.read_bytes()).hexdigest(),
            "budget_amendments": len(budgets.get("amendments") or []),
        },
        "catalogs": catalogs_out,
        "metrics": {c: {s: m for (cc, s), m in metrics.items() if cc == c} for c in catalogs_out},
        "pagination": pagination,
        "isolation": isolation,
        "argument_probes": arg_probes,
        "fidelity": fidelity,
        "verdicts": verdicts,
        "runs": [r.as_dict() for r in all_runs],
        "blocked": blocked_items(),
    }
    return results


def cmd_run(args: argparse.Namespace) -> int:
    root = Path(args.root)
    out_dir = root / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    run_id = args.run_id or time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    results = asyncio.run(run_all(root, out_dir, run_id))
    (out_dir / "results.json").write_text(
        json.dumps(results, indent=1, sort_keys=True, default=str) + "\n"
    )
    reports = root / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    (reports / "baseline-results.md").write_text(report.render(results) + "\n")
    failing = [v for v in results["verdicts"] if v["status"] == "FAIL"]
    print(
        f"wrote {out_dir / 'results.json'} and baseline-results.md; gating FAIL verdicts: {len(failing)}"
    )
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    from testmcpy.qualification.world import World

    root = Path(args.root)
    cat = load_actual(root)
    if args.catalog == "scale":
        cat = catalog_mod.scale_catalog(cat, 150)
    gw = server.load_gateway_tools(str(root / "fixtures/gateway-generic-tools.json"))
    srv = server.FixtureServer(
        World(),
        cat,
        gw,
        server.SurfaceSpec(args.surface, args.topology, page_size=args.page_size),
    )

    async def app(scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] == "lifespan":
            async with srv.running():
                while True:
                    msg = await receive()
                    if msg["type"] == "lifespan.startup":
                        await send({"type": "lifespan.startup.complete"})
                    elif msg["type"] == "lifespan.shutdown":
                        await send({"type": "lifespan.shutdown.complete"})
                        return
        else:
            await srv(scope, receive, send)

    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m testmcpy.qualification")
    sub = ap.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run", help="run the suite on every surface and write results + report")
    run.add_argument("--root", default=str(DEFAULT_ROOT))
    run.add_argument("--run-id")
    run.set_defaults(fn=cmd_run)
    srv = sub.add_parser("serve", help="serve one fixture surface on localhost for a real client")
    srv.add_argument("--root", default=str(DEFAULT_ROOT))
    srv.add_argument("--surface", choices=server.SURFACES, default="native_eager")
    srv.add_argument("--topology", choices=server.TOPOLOGIES, default="single")
    srv.add_argument("--catalog", choices=("actual", "scale"), default="actual")
    srv.add_argument("--page-size", type=int)
    srv.add_argument("--port", type=int, default=8765)
    srv.set_defaults(fn=cmd_serve)
    args = ap.parse_args(argv)
    return int(args.fn(args))


if __name__ == "__main__":
    raise SystemExit(main())
