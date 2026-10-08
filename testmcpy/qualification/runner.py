"""Run the task suite on each surface with a scripted reference agent.

The reference agent is deterministic and knows which operation each step needs.
It therefore measures what the *surface* costs and can express, not how well a
model chooses tools: any failure here is a surface defect. LLM-driven
accuracy is reported separately and is BLOCKED unless a driver ran.

Surface behaviour of the agent
------------------------------
generic          ``search_tools(query)`` once per operation not yet seen in a
                 result, then ``call_tool``. A miss triggers one retry searching
                 the exact tool name.
native_eager     ``tools/list`` (all pages) then named calls.
native_deferred  SIMULATED client/provider deferral: only a tool-search
                 definition (plus pinned tools) is in context; the first use of an
                 operation costs one search whose hits' definitions are loaded.
                 MCP has no wire-level deferral, so the underlying server surface
                 is the eager one and no provider behaviour is claimed.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from testmcpy.qualification import policy as policy_mod
from testmcpy.qualification.catalog import Catalog
from testmcpy.qualification.client import CallOutcome, ConnectRefused, Session, connect
from testmcpy.qualification.recorder import Recorder
from testmcpy.qualification.search import rank_tools
from testmcpy.qualification.server import FixtureServer, SurfaceSpec
from testmcpy.qualification.tasks import Step, Task
from testmcpy.qualification.tokens import compact_json, count_tokens, tool_tokens
from testmcpy.qualification.world import World

# Model of a provider/client tool-search definition (name + one string arg).
TOOL_SEARCH_DEF: dict[str, Any] = {
    "name": "tool_search",
    "description": "Search deferred tools by natural-language query and load the matching "
    "tool definitions into context.",
    "inputSchema": {
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
    },
}
PINNED = frozenset({"list_workspaces", "get_instance_info", "health_check"})
DENIAL_CODES = frozenset({"PERMISSION_DENIED", "FEATURE_DISABLED", "UNKNOWN_TOOL"})
SURFACE_KINDS = ("generic", "native_eager", "native_deferred")


@dataclass
class StepRecord:
    tool: str
    workspace: str | None
    disposition: str  # ok | error | absent | denied | connect_refused
    error_code: str | None = None
    text: str = ""
    ok_as_expected: bool = True
    note: str = ""


@dataclass
class TaskRun:
    task: str
    surface: str
    catalog: str
    success: bool = False
    failures: list[str] = field(default_factory=list)
    tokens: dict[str, int] = field(default_factory=dict)
    latency_ms: float = 0.0
    discovery_round_trips: int = 0
    positive_ops: int = 0
    missing_ops: int = 0
    op_calls: int = 0
    arg_failures: int = 0
    approvals: dict[str, int] = field(default_factory=dict)
    steps: list[StepRecord] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        d = dict(self.__dict__)
        d["steps"] = [s.__dict__ for s in self.steps]
        return d


def _payload_failed(out: CallOutcome) -> bool:
    if out.is_error:
        return True
    s = out.structured if isinstance(out.structured, dict) else {}
    return s.get("success") is False or "error_type" in s


def _names(text: str) -> list[str]:
    try:
        data = json.loads(text)
    except ValueError:
        return []
    if isinstance(data, dict):
        data = data.get("tools") or data.get("result") or []
    return [t["name"] for t in data if isinstance(t, dict) and "name" in t]


class SuiteRunner:
    def __init__(
        self,
        catalog: Catalog,
        gateway_tools: list[dict[str, Any]],
        record_dir: str | Path | None = None,
        policies: tuple[str, ...] = tuple(policy_mod.POLICIES),
    ) -> None:
        self.catalog = catalog
        self.gateway_tools = gateway_tools
        self.record_dir = Path(record_dir) if record_dir else None
        self.policies = policies

    # -- one task on one surface -----------------------------------------
    async def run_task(self, task: Task, kind: str) -> TaskRun:
        run = TaskRun(task.id, kind, self.catalog.name)
        world = World()
        server_kind = "native_eager" if kind == "native_deferred" else kind
        server = FixtureServer(
            world, self.catalog, self.gateway_tools, SurfaceSpec(server_kind, task.topology)
        )
        rec = Recorder(f"{task.id}/{kind}")
        rec.mark(task=task.id, surface=kind, catalog=self.catalog.name)
        called: list[dict[str, Any] | None] = []
        texts: list[str] = []
        async with server.running():
            try:
                ws = task.workspace if task.topology == "single" else None
                async with connect(server, task.principal, ws, rec) as s:
                    await self._drive(task, kind, s, server, world, rec, run, called, texts)
            except ConnectRefused as refused:
                run.steps.append(
                    StepRecord(
                        "<connect>",
                        task.workspace,
                        "connect_refused",
                        refused.code,
                        refused.message or "",
                        ok_as_expected=False,
                        note="connection refused before any tool surface was available",
                    )
                )
                run.failures.append(f"connect refused: {refused.code}")
        self._finish(task, kind, world, rec, run, called, texts)
        if self.record_dir:
            rec.write_jsonl(self.record_dir / self.catalog.name / kind / f"{task.id}.jsonl")
        return run

    async def _drive(
        self,
        task: Task,
        kind: str,
        s: Session,
        server: FixtureServer,
        world: World,
        rec: Recorder,
        run: TaskRun,
        called: list[dict[str, Any] | None],
        texts: list[str],
    ) -> None:
        rec.mark(task=task.id, surface=kind, catalog=self.catalog.name, phase="tools/list")
        listing = await s.list_all_tools()
        visible = {t["name"]: t for t in listing.tools}
        tokens = {"initial": 0, "discovery": 0, "calls": 0, "results": 0, "deferred_loaded": 0}
        if kind == "native_deferred":
            tokens["initial"] = tool_tokens(TOOL_SEARCH_DEF) + sum(
                tool_tokens(t) for n, t in visible.items() if n in PINNED
            )
            loaded = {n for n in visible if n in PINNED}
        else:
            tokens["initial"] = sum(tool_tokens(t) for t in listing.tools)
            loaded = set(visible)
        known: set[str] = set()
        gateway = task.topology == "gateway"

        for i, step in enumerate(task.steps):
            rec.mark(task=task.id, surface=kind, catalog=self.catalog.name, phase=f"step{i}")
            expected = self._expectation(task, step, kind)
            positive = not step.expect_denied and not expected.get("error")
            if positive:
                run.positive_ops += 1
            ws = step.workspace
            record = StepRecord(step.tool, ws, "ok")

            # --- make the operation available to the model ------------------
            available = True
            if step.tool in PINNED and step.tool in visible:
                pass
            elif kind == "generic":
                available = await self._discover_generic(
                    s, step, ws, gateway, known, tokens, run, called, visible
                )
            elif kind == "native_deferred":
                available = self._discover_deferred(step, visible, loaded, tokens, run)
            else:
                available = step.tool in visible

            if not available:
                record.disposition = "absent"
                if positive:
                    run.missing_ops += 1
                    record.ok_as_expected = False
                    run.failures.append(f"step {i}: {step.tool} not reachable on {kind}")
                elif not step.expect_denied:
                    record.ok_as_expected = False
                run.steps.append(record)
                continue

            # --- call it ----------------------------------------------------
            call_name, call_args, surface_tool = self._wire(
                kind, gateway, step, ws, visible, server
            )
            out = await s.call(call_name, call_args)
            run.op_calls += 1
            called.append(surface_tool)
            tokens["calls"] += count_tokens(
                compact_json({"name": call_name, "arguments": call_args})
            )
            tokens["results"] += count_tokens(out.text)
            if out.is_error and "validation" in out.text.lower():
                run.arg_failures += 1
            record.text = out.text
            record.error_code = out.error_code
            self._judge(step, expected, out, record, run, i)
            if record.disposition == "ok":
                texts.append(out.text)
            run.steps.append(record)

        run.tokens = {**tokens, "total": sum(tokens.values())}

    # -- expectations ---------------------------------------------------------
    @staticmethod
    def _expectation(task: Task, step: Step, kind: str) -> dict[str, Any]:
        override = task.surface_expect.get(kind)
        if override is not None:
            return dict(override)
        if step.expect_error:
            return {"error": step.expect_error}
        return {}

    @staticmethod
    def _judge(
        step: Step,
        expected: dict[str, Any],
        out: CallOutcome,
        rec: StepRecord,
        run: TaskRun,
        i: int,
    ) -> None:
        failed = _payload_failed(out)
        if expected.get("error"):
            rec.disposition = "error"
            if out.error_code != expected["error"]:
                rec.ok_as_expected = False
                run.failures.append(
                    f"step {i}: expected error {expected['error']}, got {out.error_code or 'none'}"
                )
            return
        if step.expect_denied:
            if out.is_error and out.error_code in DENIAL_CODES:
                rec.disposition = "denied"
                return
            rec.disposition = "ok" if not failed else "error"
            rec.ok_as_expected = False
            run.failures.append(f"step {i}: {step.tool} should have been denied (LEAK)")
            return
        if failed:
            rec.disposition = "error"
            rec.ok_as_expected = False
            run.failures.append(f"step {i}: {step.tool} failed: {out.text[:120]}")
            return
        for needle in step.answer_excludes:
            if needle in out.text:
                rec.ok_as_expected = False
                run.failures.append(f"step {i}: result leaked excluded text {needle!r}")

    # -- discovery --------------------------------------------------------------
    async def _discover_generic(
        self,
        s: Session,
        step: Step,
        ws: str | None,
        gateway: bool,
        known: set[str],
        tokens: dict[str, int],
        run: TaskRun,
        called: list[dict[str, Any] | None],
        visible: dict[str, dict[str, Any]],
    ) -> bool:
        if step.tool in known:
            return True
        queries = [step.discovery or step.tool, step.tool]
        for q in queries:
            if gateway:
                name, args = "search_workspace_tools", {"workspace_id": ws, "query": q}
            else:
                name, args = "search_tools", {"query": q}
            if name not in visible:
                return False
            out = await s.call(name, args)
            run.discovery_round_trips += 1
            called.append(visible[name])
            tokens["discovery"] += count_tokens(compact_json({"name": name, "arguments": args}))
            tokens["discovery"] += count_tokens(out.text)
            known.update(_names(out.text))
            if step.tool in known:
                return True
        return False

    def _discover_deferred(
        self,
        step: Step,
        visible: dict[str, dict[str, Any]],
        loaded: set[str],
        tokens: dict[str, int],
        run: TaskRun,
    ) -> bool:
        if step.tool in loaded:
            return True
        pool = list(visible.values())
        for q in [step.discovery or step.tool, step.tool]:
            recorded = self.catalog.recorded_hits(q)
            if recorded is not None:
                hits = [h["name"] for h in recorded if h["name"] in visible]
            else:
                hits = [t["name"] for t in rank_tools(pool, q, limit=5)]
            run.discovery_round_trips += 1
            tokens["discovery"] += count_tokens(
                compact_json({"name": "tool_search", "arguments": {"query": q}})
            )
            for n in hits:
                if n not in loaded:
                    tokens["deferred_loaded"] += tool_tokens(visible[n])
                    loaded.add(n)
            if step.tool in loaded:
                return True
        return False

    # -- wire format ------------------------------------------------------------
    @staticmethod
    def _wire(
        kind: str,
        gateway: bool,
        step: Step,
        ws: str | None,
        visible: dict[str, dict[str, Any]],
        server: FixtureServer,
    ) -> tuple[str, dict[str, Any], dict[str, Any] | None]:
        if step.tool == "list_workspaces" and "list_workspaces" in visible:
            return "list_workspaces", dict(step.args), visible["list_workspaces"]
        if kind == "generic":
            if gateway:
                args = {"workspace_id": ws, "tool_name": step.tool, "args": step.args}
            else:
                args = {"name": step.tool, "arguments": step.args}
            return "call_tool", args, visible.get("call_tool")
        args = dict(step.args)
        if gateway:
            args = {"workspace_id": ws, **args}
        return step.tool, args, visible.get(step.tool)

    # -- verdict ------------------------------------------------------------------
    def _finish(
        self,
        task: Task,
        kind: str,
        world: World,
        rec: Recorder,
        run: TaskRun,
        called: list[dict[str, Any] | None],
        texts: list[str],
    ) -> None:
        run.latency_ms = round(sum(e["latency_ms"] for e in rec.entries), 3)
        answer = " ".join(texts)
        for needle in task.oracle.get("answer_contains") or []:
            if needle not in answer:
                run.failures.append(f"answer missing {needle!r}")
        for needle in task.oracle.get("answer_excludes") or []:
            if needle in answer:
                run.failures.append(f"answer leaked {needle!r}")
        ledger = sorted(w["op"] for w in world.ledger)
        if ledger != sorted(task.oracle.get("ledger") or []):
            run.failures.append(f"write ledger {ledger} != expected {task.oracle.get('ledger')}")
        run.success = not run.failures
        run.approvals = {p: policy_mod.count_prompts(p, called) for p in self.policies}
        if not run.tokens:
            run.tokens = {"initial": 0, "total": 0}

    async def run_suite(
        self, tasks: list[Task], kinds: tuple[str, ...] = SURFACE_KINDS
    ) -> list[TaskRun]:
        runs = []
        for kind in kinds:
            for task in tasks:
                runs.append(await self.run_task(task, kind))
        return runs
