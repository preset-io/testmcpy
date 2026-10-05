"""Gateway-aware tool-call evaluation.

Covers the shared trace normalization (``testmcpy.evals.tool_trace``) and the
evaluators built on it: search-only traces never count as tool execution, and
the current ``call_tool(workspace_id, tool_name, args)`` gateway shape is read
the same way as direct, prefixed and legacy gateway calls.
"""

from dataclasses import dataclass
from typing import Any

import pytest

from testmcpy.evals.base_evaluators import (
    MCPToolResultMatches,
    ParameterValueInRange,
    ToolCallCount,
    ToolCalledWithParameter,
    ToolCalledWithParameters,
    ToolCallSequence,
    WasChartCreated,
    WasMCPToolCalled,
)
from testmcpy.evals.tool_trace import (
    KIND_DISCOVERY,
    KIND_EXECUTION,
    KIND_MALFORMED,
    flatten_request,
    normalize_tool_call,
)


def gateway(tool: str, args: Any, workspace: str | None = "123", *, name: str = "call_tool"):
    """The current gateway dispatch shape."""
    arguments: dict[str, Any] = {"tool_name": tool, "args": args}
    if workspace is not None:
        arguments["workspace_id"] = workspace
    return {"name": name, "arguments": arguments}


def legacy_gateway(tool: str, args: Any, key: str = "name", name: str = "call_tool"):
    return {"name": name, "arguments": {key: tool, "arguments": args}}


def search(query: str, name: str = "search_tools"):
    return {"name": name, "arguments": {"query": query}}


def ctx(*calls):
    return {"tool_calls": list(calls)}


PARAMS = {"page": 1, "page_size": 5}
REAL = gateway("list_dashboards", {"request": dict(PARAMS)})


class TestNormalization:
    def test_direct(self):
        n = normalize_tool_call({"name": "list_dashboards", "arguments": {"page": 1}})
        assert (n.kind, n.name, n.gateway, n.workspace_id) == (
            KIND_EXECUTION,
            "list_dashboards",
            None,
            None,
        )
        assert n.arguments == {"page": 1}

    def test_prefixed(self):
        n = normalize_tool_call({"name": "mcp__ns__list_dashboards", "arguments": {}})
        assert n.name == "list_dashboards"
        assert n.raw_name == "mcp__ns__list_dashboards"

    def test_current_gateway_keeps_workspace_and_nested_request(self):
        n = normalize_tool_call(REAL)
        assert n.kind == KIND_EXECUTION
        assert n.name == "list_dashboards"
        assert n.gateway == "call_tool"
        assert n.workspace_id == "123"
        assert n.arguments == {"request": PARAMS}
        assert n.effective_arguments == PARAMS
        assert n.as_dict()["workspace_id"] == "123"

    @pytest.mark.parametrize("key", ["name", "tool_name"])
    def test_legacy_gateway(self, key):
        n = normalize_tool_call(legacy_gateway("list_dashboards", PARAMS, key=key))
        assert n.name == "list_dashboards"
        assert n.arguments == PARAMS
        assert n.workspace_id is None

    def test_prefixed_gateway_and_prefixed_inner(self):
        n = normalize_tool_call(
            gateway("mcp__ns__list_dashboards", PARAMS, name="mcp__ns__call_tool")
        )
        assert n.name == "list_dashboards"
        assert n.gateway == "mcp__ns__call_tool"

    def test_json_string_args(self):
        n = normalize_tool_call(gateway("t", '{"a": 1}'))
        assert n.arguments == {"a": 1}
        assert n.arguments_valid

    @pytest.mark.parametrize("name", ["search_tools", "mcp__ns__search_tools"])
    def test_discovery(self, name):
        n = normalize_tool_call(search("list_dashboards", name=name))
        assert n.kind == KIND_DISCOVERY
        assert n.name == "search_tools"
        assert not n.is_execution

    @pytest.mark.parametrize(
        "call",
        [
            {"name": "call_tool", "arguments": {"args": {"a": 1}}},  # no target tool
            {"name": "call_tool", "arguments": {"tool_name": 7, "args": {}}},
            {"name": "call_tool", "arguments": {"tool_name": ""}},
            {"name": "call_tool", "arguments": ["not", "a", "dict"]},
            {"name": "call_tool", "arguments": "{not json"},
            {"name": "call_tool"},
        ],
    )
    def test_malformed_wrapper_is_not_an_execution(self, call):
        n = normalize_tool_call(call)
        assert n.kind == KIND_MALFORMED
        assert n.name == "call_tool"
        assert not n.is_execution

    def test_unreadable_inner_args_flagged(self):
        n = normalize_tool_call(gateway("list_dashboards", ["x"]))
        assert n.kind == KIND_EXECUTION
        assert n.arguments == {}
        assert not n.arguments_valid

    def test_non_dict_entry_does_not_raise(self):
        assert normalize_tool_call("oops").kind == KIND_MALFORMED  # type: ignore[arg-type]

    def test_flatten_request(self):
        assert flatten_request({"request": {"a": 1}}) == {"a": 1}
        assert flatten_request({"x": 0, "request": {"a": 1}}) == {"x": 0, "a": 1}
        assert flatten_request({"request": "str"}) == {"request": "str"}


class TestWasMCPToolCalled:
    def test_search_only_does_not_satisfy(self):
        r = WasMCPToolCalled("list_dashboards").evaluate(ctx(search("list_dashboards")))
        assert r.passed is False
        assert r.score == 0.0
        assert r.details["match_type"] == "discovery_only"
        assert r.details["discovery_calls"][0]["kind"] == KIND_DISCOVERY
        assert "never executed" in r.reason

    def test_search_workspace_tools_does_not_satisfy(self):
        call = {
            "name": "search_workspace_tools",
            "arguments": {"workspace_id": "123", "query": "list_dashboards"},
        }
        assert WasMCPToolCalled("list_dashboards").evaluate(ctx(call)).passed is False

    def test_search_then_execute_passes_as_gateway(self):
        r = WasMCPToolCalled("list_dashboards").evaluate(ctx(search("dashboards"), REAL))
        assert r.passed is True
        assert r.score == 1.0
        assert r.details["match_type"] == "gateway"
        assert r.details["workspace_id"] == "123"
        assert r.details["actual_name"] == "list_dashboards"

    def test_unrelated_search_reports_plain_none(self):
        r = WasMCPToolCalled("list_dashboards").evaluate(ctx(search("charts")))
        assert r.passed is False
        assert r.details["match_type"] == "none"

    def test_asserting_the_search_tool_itself_still_works(self):
        assert WasMCPToolCalled("search_tools").evaluate(ctx(search("x"))).passed is True

    def test_any_tool_requires_an_execution(self):
        r = WasMCPToolCalled().evaluate(ctx(search("x")))
        assert r.passed is False
        assert WasMCPToolCalled().evaluate(ctx(search("x"), REAL)).passed is True
        assert WasMCPToolCalled().evaluate(ctx({"name": "t", "arguments": {}})).passed is True

    def test_wrong_tool(self):
        r = WasMCPToolCalled("list_charts").evaluate(ctx(REAL))
        assert r.passed is False
        assert r.details["match_type"] == "none"

    def test_malformed_wrapper_does_not_match(self):
        bad = {"name": "call_tool", "arguments": {"args": {}}}
        assert WasMCPToolCalled("list_dashboards").evaluate(ctx(bad)).passed is False

    def test_gateway_wrapper_name_is_not_a_loose_match(self):
        # "call" is a substring of "call_tool" but names no tool that ran.
        assert WasMCPToolCalled("call").evaluate(ctx(REAL)).passed is False

    def test_expecting_the_gateway_tool_itself(self):
        r = WasMCPToolCalled("call_tool").evaluate(ctx(REAL))
        assert r.passed is True
        assert r.details["match_type"] == "exact"

    def test_workspace_filter(self):
        ev_a = WasMCPToolCalled("list_dashboards", workspace_id="123")
        ev_b = WasMCPToolCalled("list_dashboards", workspace_id="999")
        assert ev_a.evaluate(ctx(REAL)).passed is True
        r = ev_b.evaluate(ctx(REAL))
        assert r.passed is False
        assert r.details["workspace_id"] == "999"
        # A direct call has no workspace, so it cannot satisfy a workspace assertion.
        assert ev_a.evaluate(ctx({"name": "list_dashboards", "arguments": {}})).passed is False

    def test_native_direct_and_prefixed_unchanged(self):
        direct = WasMCPToolCalled("health_check").evaluate(
            ctx({"name": "health_check", "arguments": {}})
        )
        assert direct.details["match_type"] == "exact"
        prefixed = WasMCPToolCalled("health_check").evaluate(
            ctx({"name": "mcp__s__health_check", "arguments": {}})
        )
        assert prefixed.details["match_type"] == "direct_prefixed"
        assert prefixed.details["actual_name"] == "mcp__s__health_check"


class TestToolCalledWithParameters:
    def test_real_gateway_shape_with_nested_request(self):
        r = ToolCalledWithParameters("list_dashboards", PARAMS).evaluate(ctx(REAL))
        assert r.passed is True
        assert r.score == 1.0
        assert r.details["workspace_id"] == "123"

    def test_legacy_gateway_shape_unchanged(self):
        r = ToolCalledWithParameters("list_dashboards", PARAMS).evaluate(
            ctx(legacy_gateway("list_dashboards", PARAMS))
        )
        assert r.passed is True and r.score == 1.0

    def test_flat_gateway_args(self):
        call = gateway("list_dashboards", dict(PARAMS))
        assert ToolCalledWithParameters("list_dashboards", PARAMS).evaluate(ctx(call)).passed

    def test_native_direct_unchanged(self):
        direct = {"name": "list_dashboards", "arguments": {"request": dict(PARAMS)}}
        assert ToolCalledWithParameters("list_dashboards", PARAMS).evaluate(ctx(direct)).passed

    def test_wrong_parameter_value(self):
        call = gateway("list_dashboards", {"request": {"page": 2, "page_size": 5}})
        r = ToolCalledWithParameters("list_dashboards", PARAMS).evaluate(ctx(call))
        assert r.passed is False
        assert r.details["mismatched"][0]["parameter"] == "page"

    def test_wrong_tool(self):
        r = ToolCalledWithParameters("list_charts", PARAMS).evaluate(ctx(REAL))
        assert r.passed is False
        assert "was not called" in r.reason

    def test_search_only_never_matches(self):
        # The query text names the tool and even carries the parameters.
        call = search("list_dashboards page=1 page_size=5")
        assert (
            ToolCalledWithParameters("list_dashboards", PARAMS).evaluate(ctx(call)).passed is False
        )

    @pytest.mark.parametrize("bad", [["x"], "{not json", 7])
    def test_malformed_wrapper_arguments_fail(self, bad):
        r = ToolCalledWithParameters("list_dashboards", PARAMS).evaluate(
            ctx(gateway("list_dashboards", bad))
        )
        assert r.passed is False
        assert "malformed" in r.reason

    def test_wrapper_without_tool_fails(self):
        call = {"name": "call_tool", "arguments": {"workspace_id": "123", "args": PARAMS}}
        assert (
            ToolCalledWithParameters("list_dashboards", PARAMS).evaluate(ctx(call)).passed is False
        )

    def test_exact_mode_flags_extra_parameters(self):
        call = gateway("list_dashboards", {"request": {**PARAMS, "q": "x"}})
        r = ToolCalledWithParameters("list_dashboards", PARAMS).evaluate(ctx(call))
        assert r.passed is False
        assert r.details["extra_parameters"] == ["q"]
        assert (
            ToolCalledWithParameters("list_dashboards", PARAMS, partial_match=True)
            .evaluate(ctx(call))
            .passed
        )

    def test_two_workspaces_same_tool_are_not_conflated(self):
        in_a = gateway("list_dashboards", {"request": dict(PARAMS)}, workspace="A")
        in_b = gateway("list_dashboards", {"request": {"page": 9, "page_size": 5}}, workspace="B")
        trace = ctx(in_a, in_b)
        ev_a = ToolCalledWithParameters("list_dashboards", PARAMS, workspace_id="A")
        ev_b = ToolCalledWithParameters("list_dashboards", PARAMS, workspace_id="B")
        assert ev_a.evaluate(trace).passed is True
        assert ev_a.evaluate(trace).details["workspace_id"] == "A"
        # Workspace B called it with different parameters; A's call must not satisfy B.
        assert ev_b.evaluate(trace).passed is False
        # Without a workspace constraint either call may satisfy it.
        assert ToolCalledWithParameters("list_dashboards", PARAMS).evaluate(trace).passed

    def test_asserting_gateway_tool_params_targets_the_envelope(self):
        r = ToolCalledWithParameters(
            "call_tool", {"workspace_id": "123", "tool_name": "list_dashboards"}, partial_match=True
        ).evaluate(ctx(REAL))
        assert r.passed is True


class TestToolCalledWithParameter:
    def test_finds_parameter_inside_gateway_request(self):
        r = ToolCalledWithParameter("list_dashboards", "page_size", 5).evaluate(ctx(REAL))
        assert r.passed is True

    def test_wrong_value_and_missing(self):
        assert (
            not ToolCalledWithParameter("list_dashboards", "page_size", 6)
            .evaluate(ctx(REAL))
            .passed
        )
        assert not ToolCalledWithParameter("list_dashboards", "nope").evaluate(ctx(REAL)).passed

    def test_search_only(self):
        assert (
            not ToolCalledWithParameter("list_dashboards", "query")
            .evaluate(ctx(search("list_dashboards")))
            .passed
        )

    def test_native_top_level_and_request_key_itself(self):
        direct = {"name": "t", "arguments": {"request": {"a": 1}, "b": 2}}
        assert ToolCalledWithParameter("t", "b", 2).evaluate(ctx(direct)).passed
        assert ToolCalledWithParameter("t", "request").evaluate(ctx(direct)).passed


class TestParameterValueInRange:
    def test_gateway_and_prefixed(self):
        ev = ParameterValueInRange("list_dashboards", "page_size", min_value=1, max_value=10)
        assert ev.evaluate(ctx(REAL)).passed is True
        prefixed = {"name": "mcp__s__list_dashboards", "arguments": {"page_size": 5}}
        assert ev.evaluate(ctx(prefixed)).passed is True

    def test_out_of_range_and_wrong_tool(self):
        assert (
            not ParameterValueInRange("list_dashboards", "page_size", max_value=3)
            .evaluate(ctx(REAL))
            .passed
        )
        assert (
            not ParameterValueInRange("list_charts", "page_size", max_value=10)
            .evaluate(ctx(REAL))
            .passed
        )

    def test_exact_name_semantics_kept(self):
        near = {"name": "list_dashboards_v2", "arguments": {"page_size": 5}}
        r = ParameterValueInRange("list_dashboards", "page_size", max_value=10).evaluate(ctx(near))
        assert r.passed is False


class TestToolCallCount:
    def test_counts_gateway_executions_not_discovery(self):
        trace = ctx(
            search("list_dashboards"), REAL, gateway("list_dashboards", {}, workspace="456")
        )
        assert ToolCallCount("list_dashboards", expected_count=2).evaluate(trace).passed
        assert ToolCallCount("search_tools", expected_count=1).evaluate(trace).passed

    def test_search_only_counts_zero(self):
        assert (
            ToolCallCount("list_dashboards", expected_count=0)
            .evaluate(ctx(search("list_dashboards")))
            .passed
        )

    def test_exact_name_semantics_kept(self):
        near = {"name": "list_dashboards_v2", "arguments": {}}
        assert ToolCallCount("list_dashboards", expected_count=0).evaluate(ctx(near)).passed

    def test_untargeted_count_is_every_call(self):
        assert ToolCallCount(expected_count=2).evaluate(ctx(search("x"), REAL)).passed


class TestToolCallSequence:
    def test_discovery_then_gateway_execution(self):
        trace = ctx(search("dashboards"), REAL)
        assert ToolCallSequence(["search_tools", "list_dashboards"]).evaluate(trace).passed

    def test_legacy_sequence_naming_the_gateway_tool_still_passes(self):
        trace = ctx(search("dashboards"), REAL)
        assert ToolCallSequence(["search_tools", "call_tool"]).evaluate(trace).passed

    def test_search_only_does_not_complete_the_sequence(self):
        r = ToolCallSequence(["search_tools", "list_dashboards"], strict=False).evaluate(
            ctx(search("list_dashboards"))
        )
        assert r.passed is False
        assert r.details["missing_tools"] == ["list_dashboards"]

    def test_wrong_order_and_non_strict_intermediates(self):
        trace = ctx(REAL, search("x"))
        assert not ToolCallSequence(["search_tools", "list_dashboards"]).evaluate(trace).passed
        mixed = ctx(search("x"), gateway("other", {}), REAL)
        assert (
            ToolCallSequence(
                ["search_tools", "list_dashboards"], strict=False, allow_intermediate=True
            )
            .evaluate(mixed)
            .passed
        )
        assert (
            not ToolCallSequence(["search_tools", "list_dashboards"], strict=False)
            .evaluate(mixed)
            .passed
        )

    def test_native_direct_unchanged(self):
        trace = ctx({"name": "a", "arguments": {}}, {"name": "b", "arguments": {}})
        assert ToolCallSequence(["a", "b"]).evaluate(trace).passed
        assert not ToolCallSequence(["a"]).evaluate(trace).passed


@dataclass
class _Result:
    content: Any = ""
    is_error: bool = False


class TestChartAndResultEvaluators:
    def test_chart_created_through_gateway(self):
        trace = {
            "tool_calls": [gateway("create_chart", {})],
            "tool_results": [_Result("chart_id: 7")],
        }
        r = WasChartCreated().evaluate(trace)
        assert r.passed and r.details == {"chart_id": "7"}

    def test_searching_for_chart_tool_is_not_creation(self):
        trace = {"tool_calls": [search("create_chart")], "tool_results": [_Result("ok")]}
        assert WasChartCreated().evaluate(trace).passed is False

    def test_result_lookup_finds_current_gateway_shape(self):
        call = {**REAL, "result": {"content": "payload"}}
        found = MCPToolResultMatches("list_dashboards")._find_llm_result({"tool_calls": [call]})
        assert found == "payload"
        none = MCPToolResultMatches("list_dashboards")._find_llm_result(
            {"tool_calls": [{**search("list_dashboards"), "result": {"content": "x"}}]}
        )
        assert none == ""
