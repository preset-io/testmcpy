"""Unit tests for the authoritative scoring module (testmcpy.scoring).

Covers the base mean, the false-positive penalty (including the multi-primary
tool fix), the 0.5 floor, manual false positives, the read-path override, and
the edge cases the storage layer used to handle inline.
"""

from testmcpy.scoring import (
    MANUAL_FP_MULTIPLIER,
    compute_score_breakdown,
    compute_tool_call_breakdown,
    primary_tools_from_evaluations,
    real_tool_name,
)


def ev(name, score=1.0, passed=True):
    return {"evaluator": name, "score": score, "passed": passed}


def test_base_score_is_mean_of_evaluators():
    bd = compute_score_breakdown(
        base_score=0.75,
        evaluations=[ev("a", 1.0), ev("b", 0.5)],
        tool_uses=[],
    )
    assert bd["base_score"] == 0.75
    assert bd["final_score"] == 0.75
    assert bd["penalty_source"] is None
    assert len(bd["evaluator_breakdown"]) == 2
    assert bd["evaluator_breakdown"][0]["weight"] == 0.5


def test_no_expected_tool_means_no_false_positive():
    # Without a was_tool_called evaluator, nothing can be "extra".
    bd = compute_score_breakdown(
        base_score=1.0,
        evaluations=[ev("final_answer_contains", 1.0)],
        tool_uses=[{"name": "list_dashboards"}, {"name": "get_chart"}],
    )
    assert bd["false_positive_rate"] == 0.0
    assert bd["final_score"] == 1.0


def test_false_positive_penalty_applied():
    # Expected get_dashboard; 1 of 2 calls is something else → rate 0.5.
    bd = compute_score_breakdown(
        base_score=1.0,
        evaluations=[ev("was_tool_called:get_dashboard", 1.0)],
        tool_uses=[{"name": "get_dashboard"}, {"name": "list_dashboards"}],
    )
    assert bd["false_positive_rate"] == 0.5
    assert bd["penalty_multiplier"] == 0.5
    assert bd["final_score"] == 0.5
    assert bd["penalty_source"] == "false_positive"


def test_penalty_floor_caps_at_half():
    # Every call is unexpected → rate 1.0, but the floor keeps multiplier at 0.5.
    bd = compute_score_breakdown(
        base_score=1.0,
        evaluations=[ev("was_tool_called:get_dashboard", 1.0)],
        tool_uses=[{"name": "list_dashboards"}, {"name": "get_chart"}],
    )
    assert bd["false_positive_rate"] == 1.0
    assert bd["penalty_multiplier"] == 0.5
    assert bd["final_score"] == 0.5


def test_multiple_primary_tools_not_penalised():
    # Gap C: a test may legitimately expect two tools; calling both is clean.
    evals = [
        ev("was_tool_called:get_dashboard", 1.0),
        ev("was_mcp_tool_called:list_dashboards", 1.0),
    ]
    bd = compute_score_breakdown(
        base_score=1.0,
        evaluations=evals,
        tool_uses=[{"name": "get_dashboard"}, {"name": "list_dashboards"}],
    )
    assert bd["false_positive_rate"] == 0.0
    assert bd["final_score"] == 1.0
    assert set(bd["primary_tools"]) == {"get_dashboard", "list_dashboards"}


def test_duplicate_primary_calls_are_not_false_positives():
    # Duplicates of the primary tool stay "primary" — the unnecessary_tool_calls
    # evaluator (not this penalty) handles duplication, so no double counting.
    bd = compute_score_breakdown(
        base_score=1.0,
        evaluations=[ev("was_tool_called:get_dashboard", 1.0)],
        tool_uses=[{"name": "get_dashboard"}, {"name": "get_dashboard"}],
    )
    assert bd["false_positive_rate"] == 0.0
    assert bd["final_score"] == 1.0


def test_manual_false_positive_applies_floor():
    # Gap D: a human flag must actually move the number.
    bd = compute_score_breakdown(
        base_score=1.0,
        evaluations=[ev("final_answer_contains", 1.0)],
        tool_uses=[],
        manual_false_positive=True,
    )
    assert bd["penalty_source"] == "manual"
    assert bd["final_score"] == MANUAL_FP_MULTIPLIER
    assert bd["manual_false_positive"] is True


def test_override_final_score_for_read_path():
    # Historical rows: stored score is authoritative; multiplier derived from it.
    bd = compute_score_breakdown(
        base_score=1.0,
        evaluations=[ev("was_tool_called:get_dashboard", 1.0)],
        tool_uses=[{"name": "get_dashboard"}, {"name": "list_dashboards"}],
        override_final_score=0.6,
    )
    assert bd["final_score"] == 0.6
    assert bd["penalty_multiplier"] == 0.6
    assert bd["penalty_source"] == "false_positive"


def test_no_tool_calls_and_no_evaluators_edge_cases():
    assert compute_score_breakdown(0.0, [], [])["final_score"] == 0.0
    tb = compute_tool_call_breakdown([], [])
    assert tb["total_calls"] == 0
    assert tb["false_positive_rate"] == 0.0


def test_real_tool_name_normalisation():
    assert real_tool_name({"name": "mcp__superset__get_dashboard"}) == "get_dashboard"
    assert real_tool_name({"name": "get_dashboard"}) == "get_dashboard"
    assert (
        real_tool_name({"name": "mcp__superset__call_tool", "arguments": {"name": "get_chart"}})
        == "get_chart"
    )


def test_primary_tools_strips_mcp_prefix_in_declaration():
    tools = primary_tools_from_evaluations(
        [ev("was_tool_called:mcp__superset__get_dashboard", 1.0)]
    )
    assert tools == ["get_dashboard"]
