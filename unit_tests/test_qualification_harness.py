"""Unit tests for the native-tool qualification harness (SC-125472)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
import yaml

from testmcpy.qualification import (
    catalog as catalog_mod,
)
from testmcpy.qualification import (
    evaluate,
    measure,
    policy,
    recorder,
    report,
    runner,
    server,
    tasks,
    tokens,
    world,
)
from testmcpy.qualification.client import ConnectRefused, connect

ROOT = Path(__file__).resolve().parent.parent / "qualification" / "native-tools"
STEM = ROOT / "fixtures" / "catalog.superset-master-100f5124"


@pytest.fixture(scope="module")
def actual():
    return catalog_mod.load_catalog(
        f"{STEM}.json", f"{STEM}.output-schemas.json", f"{STEM}.search-responses.json"
    )


@pytest.fixture(scope="module")
def gateway_tools():
    return server.load_gateway_tools(str(ROOT / "fixtures" / "gateway-generic-tools.json"))


@pytest.fixture(scope="module")
def suite():
    return tasks.load_tasks(ROOT / "tasks.yaml")


def run(coro):
    return asyncio.run(coro)


# --- pre-registration ---------------------------------------------------------


class TestPreRegistration:
    def test_every_budget_has_threshold_and_justification(self):
        budgets = evaluate.load_budgets(ROOT / "budgets.yaml")
        ids = [b["id"].split("-", 1)[0] for b in budgets["budgets"]]
        assert ids == [f"B{i:02d}" for i in range(1, 13)]
        for b in budgets["budgets"]:
            assert b["hard_limit"] is not None, b["id"]
            assert len(b["justification"].split()) >= 5, b["id"]
            assert isinstance(b["gating"], bool)

    def test_task_suite_matches_registered_ids(self, suite):
        budgets = evaluate.load_budgets(ROOT / "budgets.yaml")
        registered = budgets["measurement_conventions"]["task_suite"]["ids"]
        assert [t.id for t in suite] == registered

    def test_amendments_are_append_only_records(self):
        budgets = evaluate.load_budgets(ROOT / "budgets.yaml")
        for a in budgets["amendments"]:
            assert {"date", "id", "reason"} <= set(a), a


# --- tokens / catalog --------------------------------------------------------------


class TestTokensAndCatalog:
    def test_stats_are_ordered_and_consistent(self, actual):
        st = tokens.catalog_stats(actual.native_tools)
        assert st["tool_count"] == len(actual.native_tools) == 79
        assert st["median"] <= st["p95"] <= st["max"]
        assert st["total"] == sum(tokens.tool_tokens(t) for t in actual.native_tools)

    def test_fallback_estimator_is_labelled(self, monkeypatch):
        monkeypatch.setattr(tokens, "_ESTIMATOR", "bytes/4")
        monkeypatch.setattr(tokens, "_ENCODER", None)
        assert tokens.estimator() == "bytes/4"
        assert tokens.count_tokens("abcdefgh") == 2

    def test_real_catalog_provenance_and_generic_surface(self, actual):
        assert actual.provenance["live_workspace_contacted"] is False
        assert [t["name"] for t in actual.generic_tools] == [
            "get_instance_info",
            "health_check",
            "search_tools",
            "call_tool",
        ]
        by = {t["name"]: t for t in actual.generic_tools}
        assert "annotations" not in by["call_tool"]  # the dispatcher is unannotated

    def test_scale_catalog_is_deterministic_and_leaves_real_tools_alone(self, actual):
        a = catalog_mod.scale_catalog(actual, 150)
        b = catalog_mod.scale_catalog(actual, 150)
        assert [t["name"] for t in a.native_tools] == [t["name"] for t in b.native_tools]
        assert len(a.native_tools) == 150
        assert a.native_tools[:79] == actual.native_tools
        synthetic = a.native_tools[79:]
        assert all(t["_meta"]["synthetic"] for t in synthetic)
        assert len({t["name"] for t in a.native_tools}) == 150

    def test_scale_is_noop_when_catalog_already_large(self, actual):
        big = catalog_mod.scale_catalog(actual, 10)
        assert len(big.native_tools) == 79 and big.synthetic_count == 0


# --- policy ------------------------------------------------------------------------


class TestPolicy:
    def test_unannotated_tool_is_treated_as_destructive(self):
        assert policy.needs_prompt("honours_annotations", None)
        assert policy.needs_prompt("honours_annotations", {})

    def test_read_only_annotation_skips_prompt_only_under_honouring_policy(self):
        ro = {"readOnlyHint": True, "openWorldHint": False}
        assert not policy.needs_prompt("honours_annotations", ro)
        assert policy.needs_prompt("prompts_on_everything", ro)
        assert policy.needs_prompt("untrusted_server", ro)

    def test_open_world_read_still_prompts(self):
        assert policy.needs_prompt(
            "honours_annotations", {"readOnlyHint": True, "openWorldHint": True}
        )

    def test_unknown_policy_rejected(self):
        with pytest.raises(ValueError):
            policy.needs_prompt("nope", {})


# --- recorder ---------------------------------------------------------------------


class TestRecorder:
    def test_tools_list_digest_keeps_names_and_schema_digest(self):
        body = {
            "result": {
                "tools": [
                    {"name": "a", "annotations": {"readOnlyHint": True}, "inputSchema": {"x": 1}}
                ]
            }
        }
        out = recorder.digest_tools_list(body)
        tool = out["result"]["tools"][0]
        assert tool["name"] == "a" and len(tool["inputSchema_sha256_16"]) == 16
        assert "inputSchema" not in tool

    def test_authorization_header_is_redacted(self, actual, gateway_tools):
        w = world.World()
        srv = server.FixtureServer(w, actual, gateway_tools, server.SurfaceSpec("native_eager"))
        rec = recorder.Recorder("t")

        async def go():
            async with srv.running():
                async with connect(srv, "alice", "ws-a", rec) as s:
                    await s.list_all_tools()

        run(go())
        assert rec.entries
        for e in rec.entries:
            assert e["http"]["request_headers"].get("authorization") == "<redacted>"
        assert "fixture:alice" not in json.dumps(rec.entries)

    def test_recorded_digests_match_the_catalog_fixture(self):
        traffic = ROOT / "traffic" / "superset-real-fidelity.jsonl"
        cat = json.loads(Path(f"{STEM}.json").read_text())
        by_name = {t["name"]: t for page in cat["native"]["pages"] for t in page}
        checked = 0
        for line in traffic.read_text().splitlines():
            e = json.loads(line)
            if e.get("probe") == "tools/list" and e.get("surface") == "native" and e["response"]:
                for t in e["response"]["result"]["tools"]:
                    expected = recorder.schema_digest(by_name[t["name"]]["inputSchema"])
                    assert t["inputSchema_sha256_16"] == expected, t["name"]
                    checked += 1
        assert checked == 79


# --- server surfaces ------------------------------------------------------------------


class TestServerSurfaces:
    def _names(self, actual, gw, kind, who, ws="ws-a", topology="single", page=None):
        w = world.World()
        srv = server.FixtureServer(w, actual, gw, server.SurfaceSpec(kind, topology, page))

        async def go():
            async with srv.running():
                async with connect(srv, who, ws if topology == "single" else None) as s:
                    return [t["name"] for t in (await s.list_all_tools()).tools]

        return run(go())

    def test_native_lists_every_permitted_tool_with_typed_schemas(self, actual, gateway_tools):
        names = self._names(actual, gateway_tools, "native_eager", "alice")
        assert {"list_charts", "generate_chart", "execute_sql"} <= set(names)
        assert "search_tools" not in names and "call_tool" not in names

    def test_generic_lists_only_the_dispatcher_and_pinned_tools(self, actual, gateway_tools):
        names = self._names(actual, gateway_tools, "generic", "alice")
        assert names == ["get_instance_info", "health_check", "search_tools", "call_tool"]

    def test_read_only_role_never_sees_write_or_sql_tools(self, actual, gateway_tools):
        names = set(self._names(actual, gateway_tools, "native_eager", "bob"))
        assert "list_charts" in names
        assert not {"generate_chart", "execute_sql", "delete_chart"} & names

    def test_knowledge_tools_follow_the_workspace_feature_flag(self, actual, gateway_tools):
        on = self._names(actual, gateway_tools, "native_eager", "alice", "ws-a")
        off = self._names(actual, gateway_tools, "native_eager", "alice", "ws-b")
        assert "search_knowledge" in on and "search_knowledge" not in off

    def test_disabled_knowledge_is_a_typed_error_when_called_through_the_dispatcher(
        self, actual, gateway_tools
    ):
        srv = server.FixtureServer(
            world.World(), actual, gateway_tools, server.SurfaceSpec("generic")
        )

        async def go():
            outs = []
            async with srv.running():
                for ws in ("ws-b", "ws-a"):
                    async with connect(srv, "alice", ws) as s:
                        outs.append(
                            await s.call(
                                "call_tool",
                                {
                                    "name": "search_knowledge",
                                    "arguments": {"request": {"query": "revenue"}},
                                },
                            )
                        )
            return outs

        off, on = run(go())
        assert off.is_error and off.error_code == "FEATURE_DISABLED"
        assert not on.is_error and "recognised on shipment" in on.text

    @pytest.mark.parametrize("page", [1, 7, 50, None])
    def test_pagination_is_complete_with_no_duplicates(self, actual, gateway_tools, page):
        paged = self._names(actual, gateway_tools, "native_eager", "alice", page=page)
        whole = self._names(actual, gateway_tools, "native_eager", "alice")
        assert paged == whole and len(set(paged)) == len(paged)

    def test_revoked_grant_is_refused_with_typed_403(self, actual, gateway_tools):
        w = world.World()
        srv = server.FixtureServer(w, actual, gateway_tools, server.SurfaceSpec("native_eager"))

        async def go():
            async with srv.running():
                async with connect(srv, "carol", "ws-b"):
                    pass

        with pytest.raises(ConnectRefused) as exc:
            run(go())
        assert exc.value.status == 403 and exc.value.code == "ACCESS_REVOKED"

    def test_missing_token_is_401(self, actual, gateway_tools):
        from testmcpy.qualification.client import unauthenticated_status

        srv = server.FixtureServer(world.World(), actual, gateway_tools, server.SurfaceSpec())
        assert run(unauthenticated_status(srv)) == 401

    def test_writes_land_only_in_the_fixture_ledger(self, actual, gateway_tools):
        w = world.World()
        before = w.snapshot_data()
        srv = server.FixtureServer(w, actual, gateway_tools, server.SurfaceSpec("native_eager"))

        async def go():
            async with srv.running():
                async with connect(srv, "dave", "ws-a") as s:
                    return await s.call(
                        "generate_chart",
                        {
                            "request": {
                                "dataset_id": 10,
                                "chart_name": "T",
                                "save_chart": True,
                                "config": {"chart_type": "table"},
                            }
                        },
                    )

        out = run(go())
        assert not out.is_error
        assert [x["op"] for x in w.ledger] == ["create_chart"]
        assert w.snapshot_data() != before


# --- the suite --------------------------------------------------------------------------


class TestSuite:
    def test_scripted_agent_completes_every_task_on_every_surface(
        self, actual, gateway_tools, suite
    ):
        runs = run(runner.SuiteRunner(actual, gateway_tools).run_suite(suite))
        failed = [(r.surface, r.task, r.failures) for r in runs if not r.success]
        assert not failed, failed
        assert len(runs) == len(suite) * 3

    def test_old_producer_gets_typed_error_natively_and_works_on_generic(
        self, actual, gateway_tools, suite
    ):
        task = next(t for t in suite if t.id == "old-producer-unsupported")
        r = runner.SuiteRunner(actual, gateway_tools)
        native = run(r.run_task(task, "native_eager"))
        generic = run(r.run_task(task, "generic"))
        assert native.steps[-1].disposition == "error"
        assert native.steps[-1].error_code == "UNSUPPORTED_PRODUCER"
        assert generic.steps[-1].disposition == "ok"

    def test_revoked_access_is_typed_on_all_surfaces(self, actual, gateway_tools, suite):
        task = next(t for t in suite if t.id == "revoked-access")
        r = runner.SuiteRunner(actual, gateway_tools)
        for kind in runner.SURFACE_KINDS:
            res = run(r.run_task(task, kind))
            assert res.success and res.steps[-1].error_code == "ACCESS_REVOKED", kind

    def test_surface_token_costs_have_the_expected_shape(self, actual, gateway_tools, suite):
        runs = run(runner.SuiteRunner(actual, gateway_tools).run_suite(suite))
        m = evaluate.aggregate(runs, tuple(policy.POLICIES))
        generic = m[("actual", "generic")]
        eager = m[("actual", "native_eager")]
        deferred = m[("actual", "native_deferred")]
        assert generic["initial_tokens"] < 2_000
        assert eager["initial_tokens"] > 10_000  # the registered B01 hard limit
        assert deferred["initial_tokens"] < generic["initial_tokens"] + 1_000
        assert eager["discovery_round_trips"]["max"] == 0
        assert generic["discovery_round_trips"]["median"] >= 1

    def test_annotation_policy_separates_reads_from_the_generic_dispatcher(
        self, actual, gateway_tools, suite
    ):
        task = next(t for t in suite if t.id == "chart-find")
        r = runner.SuiteRunner(actual, gateway_tools)
        native = run(r.run_task(task, "native_eager"))
        generic = run(r.run_task(task, "generic"))
        assert native.approvals["honours_annotations"] == 0
        assert generic.approvals["honours_annotations"] >= 2  # search_tools + call_tool
        assert (
            generic.approvals["prompts_on_everything"]
            == native.approvals["prompts_on_everything"] + 1
        )

    def test_traffic_recording_is_written_per_task(self, actual, gateway_tools, suite, tmp_path):
        task = next(t for t in suite if t.id == "chart-find")
        run(
            runner.SuiteRunner(actual, gateway_tools, record_dir=tmp_path).run_task(task, "generic")
        )
        path = tmp_path / "actual" / "generic" / "chart-find.jsonl"
        rows = [json.loads(x) for x in path.read_text().splitlines()]
        methods = [r["request"]["method"] for r in rows if r.get("request")]
        assert "tools/list" in methods and "tools/call" in methods


# --- measurements & evaluation ---------------------------------------------------------


class TestMeasurements:
    def test_isolation_matrix_has_no_leaks(self, actual, gateway_tools):
        res = run(measure.measure_isolation(actual, gateway_tools))
        assert res["leaks"] == 0, [p for p in res["probes"] if p["leak"]]
        assert res["probe_count"] >= 15

    def test_pagination_completeness(self, actual, gateway_tools):
        rows = run(measure.measure_pagination(actual, gateway_tools, (None, 1, 25)))
        assert all(r["completeness"] == 1.0 and r["duplicates"] == 0 for r in rows)
        assert rows[1]["pages"] == rows[1]["expected"]

    def test_malformed_arguments_are_rejected_before_any_write(self, actual, gateway_tools):
        rows = run(measure.measure_argument_probes(actual, gateway_tools))
        assert rows and all(r["rejected"] and r["writes"] == 0 for r in rows)
        native = [r for r in rows if r["surface"] == "native_eager"]
        generic = [r for r in rows if r["surface"] == "generic"]
        assert all(r["operation_schema_in_tools_list"] for r in native)
        assert not any(r["operation_schema_in_tools_list"] for r in generic)

    def test_fidelity_ignores_timestamps_but_flags_real_differences(self, tmp_path):
        rows = [
            {
                "surface": "native",
                "probe": "p1",
                "isError": False,
                "has_structuredContent": True,
                "structured_keys": ["a"],
                "text_head": '{"timestamp":"1","x":1}',
                "text_len": 5,
            },
            {
                "surface": "generic",
                "probe": "p1",
                "isError": False,
                "has_structuredContent": True,
                "structured_keys": ["a"],
                "text_head": '{"timestamp":"2","x":1}',
                "text_len": 5,
            },
            {
                "surface": "native",
                "probe": "p2",
                "isError": True,
                "has_structuredContent": False,
                "structured_keys": [],
                "text_head": "Unknown tool: 'x'",
                "text_len": 17,
            },
            {
                "surface": "generic",
                "probe": "p2",
                "isError": True,
                "has_structuredContent": False,
                "structured_keys": [],
                "text_head": "Error calling tool 'call_tool': Unknown tool: 'x'",
                "text_len": 50,
            },
        ]
        path = tmp_path / "s.json"
        path.write_text(json.dumps(rows))
        res = measure.measure_fidelity(path)
        assert res["identical"] == 1 and res["total"] == 2

    def test_committed_real_probe_summary_shows_the_unknown_tool_difference(self):
        res = measure.measure_fidelity(ROOT / "traffic" / "superset-real-fidelity.summary.json")
        bad = [
            c["probe"]
            for c in res["compared"]
            if not (c["flags_identical"] and c["text_identical"])
        ]
        assert bad == ["P07-unknown-tool"]

    def test_committed_results_render_and_carry_all_budgets(self):
        path = ROOT / "results" / "results.json"
        if not path.exists():
            pytest.skip("results not generated yet")
        results = json.loads(path.read_text())
        text = report.render(results)
        assert "Budget verdicts" in text and "BLOCKED" in text
        seen = {v["budget"].split("-", 1)[0] for v in results["verdicts"]}
        assert seen == {f"B{i:02d}" for i in range(1, 13)}
        statuses = {v["status"] for v in results["verdicts"]}
        assert statuses <= {"pass", "FAIL", "would-pass", "would-fail"}

    def test_client_matrix_never_infers_support_from_docs(self):
        path = ROOT / "client_matrix.yaml"
        if not path.exists():
            pytest.skip("client matrix not generated yet")
        matrix = yaml.safe_load(path.read_text())
        for entry in matrix["entries"]:
            assert entry["status"] in {"MEASURED", "BLOCKED", "PARTIAL"}, entry["id"]
            if entry["status"] == "BLOCKED":
                assert entry["blocked_reason"], entry["id"]
            assert entry["deferred_discovery"]["evidence"] in {
                "observed",
                "blocked",
                "not_applicable",
            }, entry["id"]
