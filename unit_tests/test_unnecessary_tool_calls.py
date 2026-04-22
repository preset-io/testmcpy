"""
Unit tests for UnnecessaryToolCalls evaluator — false positive detection.

Detects when the LLM makes redundant tool calls that waste tokens/cost.
"""

from testmcpy.evals.base_evaluators import UnnecessaryToolCalls, create_evaluator


class TestUnnecessaryToolCalls:
    def test_no_tool_calls_passes(self):
        ev = UnnecessaryToolCalls()
        result = ev.evaluate({"tool_calls": []})
        assert result.passed is True

    def test_unique_calls_pass(self):
        ev = UnnecessaryToolCalls()
        result = ev.evaluate(
            {
                "tool_calls": [
                    {"name": "list_dashboards", "arguments": {}},
                    {"name": "list_charts", "arguments": {}},
                    {"name": "get_dashboard_info", "arguments": {"id": 1}},
                ]
            }
        )
        assert result.passed is True

    def test_duplicate_same_args_fails(self):
        """Calling get_dashboard_info(id=1) twice should fail."""
        ev = UnnecessaryToolCalls()
        result = ev.evaluate(
            {
                "tool_calls": [
                    {"name": "get_dashboard_info", "arguments": {"id": 1}},
                    {"name": "get_dashboard_info", "arguments": {"id": 1}},
                ]
            }
        )
        assert result.passed is False
        assert "get_dashboard_info" in result.reason

    def test_same_tool_different_args_ok(self):
        """Calling get_dashboard_info with different IDs is fine."""
        ev = UnnecessaryToolCalls()
        result = ev.evaluate(
            {
                "tool_calls": [
                    {"name": "get_dashboard_info", "arguments": {"id": 1}},
                    {"name": "get_dashboard_info", "arguments": {"id": 2}},
                ]
            }
        )
        assert result.passed is True

    def test_check_args_false_flags_same_tool(self):
        """With check_args=False, any repeat of same tool name fails."""
        ev = UnnecessaryToolCalls(check_args=False)
        result = ev.evaluate(
            {
                "tool_calls": [
                    {"name": "get_dashboard_info", "arguments": {"id": 1}},
                    {"name": "get_dashboard_info", "arguments": {"id": 2}},
                ]
            }
        )
        assert result.passed is False

    def test_max_duplicates_allows_repeats(self):
        """With max_duplicates=2, two identical calls are OK."""
        ev = UnnecessaryToolCalls(max_duplicates=2)
        result = ev.evaluate(
            {
                "tool_calls": [
                    {"name": "get_dashboard_info", "arguments": {"id": 1}},
                    {"name": "get_dashboard_info", "arguments": {"id": 1}},
                ]
            }
        )
        assert result.passed is True

    def test_max_duplicates_exceeded(self):
        """With max_duplicates=2, three identical calls fail."""
        ev = UnnecessaryToolCalls(max_duplicates=2)
        result = ev.evaluate(
            {
                "tool_calls": [
                    {"name": "get_dashboard_info", "arguments": {"id": 1}},
                    {"name": "get_dashboard_info", "arguments": {"id": 1}},
                    {"name": "get_dashboard_info", "arguments": {"id": 1}},
                ]
            }
        )
        assert result.passed is False

    def test_ignore_tools(self):
        """Ignored tools should not be flagged even if duplicated."""
        ev = UnnecessaryToolCalls(ignore_tools=["search_tools"])
        result = ev.evaluate(
            {
                "tool_calls": [
                    {"name": "search_tools", "arguments": {"q": "dashboard"}},
                    {"name": "search_tools", "arguments": {"q": "dashboard"}},
                ]
            }
        )
        assert result.passed is True

    def test_score_reflects_waste(self):
        """Score should decrease with more duplicate calls."""
        ev = UnnecessaryToolCalls()
        result = ev.evaluate(
            {
                "tool_calls": [
                    {"name": "get_info", "arguments": {}},
                    {"name": "get_info", "arguments": {}},
                    {"name": "get_info", "arguments": {}},
                    {"name": "list_items", "arguments": {}},
                ]
            }
        )
        assert result.passed is False
        assert result.score < 1.0
        assert result.score > 0.0

    def test_realistic_false_positive_scenario(self):
        """Real scenario from meeting: LLM calls get_instance_info 3x and get_chart_info 2x."""
        ev = UnnecessaryToolCalls()
        result = ev.evaluate(
            {
                "tool_calls": [
                    {"name": "get_instance_info", "arguments": {}},
                    {"name": "list_dashboards", "arguments": {}},
                    {"name": "get_instance_info", "arguments": {}},
                    {"name": "get_chart_info", "arguments": {"id": 5}},
                    {"name": "get_instance_info", "arguments": {}},
                    {"name": "get_chart_info", "arguments": {"id": 5}},
                ]
            }
        )
        assert result.passed is False
        assert (
            result.details["total_excess_calls"] == 3
        )  # 2 extra get_instance_info + 1 extra get_chart_info

    def test_factory_creation(self):
        ev = create_evaluator("unnecessary_tool_calls")
        assert isinstance(ev, UnnecessaryToolCalls)

    def test_factory_with_args(self):
        ev = create_evaluator("unnecessary_tool_calls", max_duplicates=3, check_args=False)
        assert ev.max_duplicates == 3
        assert ev.check_args is False
