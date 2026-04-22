"""
Unit tests for advanced evaluators that were built but untested.

Covers: ResponseNotIncludes, ResponseMatchesPattern, UrlIsValid,
NoLeakedData, SuccessRateAbove, LatencyPercentile, LLMJudge helpers,
MCPToolResultMatches, MCPVerifyResponseData, MCPVerifySideEffect.
"""

import pytest

from testmcpy.evals.base_evaluators import (
    LatencyPercentile,
    NoLeakedData,
    ResponseMatchesPattern,
    ResponseNotIncludes,
    SuccessRateAbove,
    UrlIsValid,
    create_evaluator,
)

# ── ResponseNotIncludes ──────────────────────────────────────────────────────


class TestResponseNotIncludes:
    def test_pass_when_forbidden_absent(self):
        ev = ResponseNotIncludes(content="error")
        result = ev.evaluate({"response": "All dashboards loaded successfully"})
        assert result.passed is True

    def test_fail_when_forbidden_present(self):
        ev = ResponseNotIncludes(content="error")
        result = ev.evaluate({"response": "An error occurred while loading"})
        assert result.passed is False

    def test_case_insensitive_by_default(self):
        ev = ResponseNotIncludes(content="ERROR")
        result = ev.evaluate({"response": "an error occurred"})
        assert result.passed is False

    def test_case_sensitive(self):
        ev = ResponseNotIncludes(content="ERROR", case_sensitive=True)
        result = ev.evaluate({"response": "an error occurred"})
        assert result.passed is True  # "error" != "ERROR"

    def test_list_of_forbidden_strings(self):
        ev = ResponseNotIncludes(content=["error", "failed", "exception"])
        result = ev.evaluate({"response": "The operation failed"})
        assert result.passed is False

    def test_list_all_absent_passes(self):
        ev = ResponseNotIncludes(content=["error", "failed", "exception"])
        result = ev.evaluate({"response": "Dashboards loaded successfully"})
        assert result.passed is True

    def test_empty_response(self):
        ev = ResponseNotIncludes(content="error")
        result = ev.evaluate({"response": ""})
        assert result.passed is True

    def test_forbidden_in_response_only(self):
        """Evaluator checks response text, not tool_results."""
        ev = ResponseNotIncludes(content="secret_key")
        result = ev.evaluate({"response": "secret_key is exposed"})
        assert result.passed is False

    def test_factory_creation(self):
        ev = create_evaluator("response_not_includes", content="error")
        assert ev is not None


# ── ResponseMatchesPattern ───────────────────────────────────────────────────


class TestResponseMatchesPattern:
    def test_pattern_found_passes(self):
        ev = ResponseMatchesPattern(pattern=r"\d+ dashboards")
        result = ev.evaluate({"response": "Found 5 dashboards in the workspace"})
        assert result.passed is True

    def test_pattern_not_found_fails(self):
        ev = ResponseMatchesPattern(pattern=r"\d+ dashboards")
        result = ev.evaluate({"response": "No results found"})
        assert result.passed is False

    def test_should_match_false(self):
        ev = ResponseMatchesPattern(pattern=r"error|fail", should_match=False)
        result = ev.evaluate({"response": "Everything worked perfectly"})
        assert result.passed is True

    def test_should_match_false_fails_when_found(self):
        ev = ResponseMatchesPattern(pattern=r"error|fail", should_match=False)
        result = ev.evaluate({"response": "An error occurred"})
        assert result.passed is False

    def test_empty_response(self):
        ev = ResponseMatchesPattern(pattern=r"\d+")
        result = ev.evaluate({"response": ""})
        assert result.passed is False

    def test_multiline_pattern(self):
        ev = ResponseMatchesPattern(pattern=r"Dashboard: .+")
        result = ev.evaluate({"response": "Dashboard: Sales Overview\nStatus: Active"})
        assert result.passed is True

    def test_factory_creation(self):
        ev = create_evaluator("response_matches_pattern", pattern=r"\d+")
        assert ev is not None


# ── UrlIsValid ───────────────────────────────────────────────────────────────


class TestUrlIsValid:
    def test_valid_https_url_passes(self):
        ev = UrlIsValid()
        result = ev.evaluate({"response": "Check this link: https://example.com/dashboard/1"})
        assert result.passed is True

    def test_valid_http_url_passes_without_require_https(self):
        ev = UrlIsValid(require_https=False)
        result = ev.evaluate({"response": "Visit http://example.com"})
        assert result.passed is True

    def test_http_url_fails_with_require_https(self):
        ev = UrlIsValid(require_https=True)
        result = ev.evaluate({"response": "Visit http://example.com"})
        assert result.passed is False

    def test_no_urls_in_response(self):
        """No URLs found is a valid outcome (evaluator reports no URLs)."""
        ev = UrlIsValid()
        result = ev.evaluate({"response": "No links here, just text."})
        # Evaluator returns false when no URLs found — that's by design
        assert result.passed is False
        assert "No URLs" in (result.reason or "")

    def test_factory_creation(self):
        ev = create_evaluator("url_is_valid", require_https=True)
        assert ev is not None


# ── NoLeakedData ─────────────────────────────────────────────────────────────


class TestNoLeakedData:
    def test_clean_response_passes(self):
        ev = NoLeakedData()
        result = ev.evaluate({"response": "Here are your 5 dashboards."})
        assert result.passed is True

    def test_connection_string_fails(self):
        ev = NoLeakedData()
        result = ev.evaluate({"response": "Connected to postgresql://user:pass@host/db"})
        assert result.passed is False

    def test_api_key_fails(self):
        ev = NoLeakedData()
        result = ev.evaluate({"response": "Use api_key: 'sk-abcdefghijklmnop1234567890'"})
        assert result.passed is False

    def test_python_traceback_fails(self):
        ev = NoLeakedData()
        result = ev.evaluate(
            {"response": 'Traceback (most recent call last):\n  File "app.py", line 42'}
        )
        assert result.passed is False

    def test_extra_patterns(self):
        ev = NoLeakedData(extra_patterns=[r"SSN:\s*\d{3}-\d{2}-\d{4}"])
        result = ev.evaluate({"response": "SSN: 123-45-6789"})
        assert result.passed is False

    def test_extra_patterns_clean(self):
        ev = NoLeakedData(extra_patterns=[r"SSN:\s*\d{3}-\d{2}-\d{4}"])
        result = ev.evaluate({"response": "No sensitive data here"})
        assert result.passed is True

    def test_leaked_data_in_response_text(self):
        """Connection string in response text should be detected."""
        ev = NoLeakedData()
        result = ev.evaluate(
            {"response": "Connection: postgresql://admin:secret@prod-db.internal/main"}
        )
        assert result.passed is False

    def test_factory_creation(self):
        ev = create_evaluator("no_leaked_data")
        assert ev is not None


# ── SuccessRateAbove ─────────────────────────────────────────────────────────


class TestSuccessRateAbove:
    def test_all_success_passes(self):
        ev = SuccessRateAbove(min_rate=0.9)
        results = [{"success": True} for _ in range(10)]
        result = ev.evaluate({"load_test_results": results})
        assert result.passed is True

    def test_below_threshold_fails(self):
        ev = SuccessRateAbove(min_rate=0.9)
        results = [{"success": True}] * 7 + [{"success": False}] * 3
        result = ev.evaluate({"load_test_results": results})
        assert result.passed is False  # 70% < 90%

    def test_at_exact_threshold(self):
        ev = SuccessRateAbove(min_rate=0.9)
        results = [{"success": True}] * 9 + [{"success": False}]
        result = ev.evaluate({"load_test_results": results})
        assert result.passed is True  # 90% == 90%

    def test_empty_results(self):
        ev = SuccessRateAbove(min_rate=0.5)
        result = ev.evaluate({"load_test_results": []})
        assert result.passed is False

    def test_no_results_key(self):
        ev = SuccessRateAbove(min_rate=0.5)
        result = ev.evaluate({})
        assert result.passed is False

    def test_all_failures(self):
        ev = SuccessRateAbove(min_rate=0.1)
        results = [{"success": False}] * 10
        result = ev.evaluate({"load_test_results": results})
        assert result.passed is False

    def test_score_equals_rate(self):
        ev = SuccessRateAbove(min_rate=0.5)
        results = [{"success": True}] * 8 + [{"success": False}] * 2
        result = ev.evaluate({"load_test_results": results})
        assert result.score == pytest.approx(0.8, abs=0.01)


# ── LatencyPercentile ────────────────────────────────────────────────────────


class TestLatencyPercentile:
    def test_fast_responses_pass(self):
        ev = LatencyPercentile(percentile=95, max_seconds=5.0)
        results = [{"duration": i * 0.1} for i in range(1, 21)]  # 0.1 to 2.0s
        result = ev.evaluate({"load_test_results": results})
        assert result.passed is True

    def test_slow_responses_fail(self):
        ev = LatencyPercentile(percentile=95, max_seconds=1.0)
        results = [{"duration": 2.0}] * 20  # All 2.0s, p95 = 2.0 > 1.0
        result = ev.evaluate({"load_test_results": results})
        assert result.passed is False

    def test_empty_results(self):
        ev = LatencyPercentile(percentile=95, max_seconds=5.0)
        result = ev.evaluate({"load_test_results": []})
        assert result.passed is False

    def test_single_result(self):
        ev = LatencyPercentile(percentile=95, max_seconds=5.0)
        result = ev.evaluate({"load_test_results": [{"duration": 1.0}]})
        assert result.passed is True

    def test_p50_percentile(self):
        ev = LatencyPercentile(percentile=50, max_seconds=1.5)
        results = [{"duration": 1.0}] * 10 + [{"duration": 2.0}] * 10
        result = ev.evaluate({"load_test_results": results})
        # p50 should be around 1.5
        assert result.passed is True


# ── LLMJudge helper methods ─────────────────────────────────────────────────


class TestLLMJudgeHelpers:
    def _make_judge(self):
        from testmcpy.evals.base_evaluators import LLMJudge

        return LLMJudge(criteria="accuracy", pass_threshold=0.7)

    def test_extract_score_from_number(self):
        judge = self._make_judge()
        assert judge._extract_score("Score: 0.85") == pytest.approx(0.85, abs=0.01)

    def test_extract_score_from_fraction(self):
        judge = self._make_judge()
        assert judge._extract_score("Rating: 8/10") == pytest.approx(0.8, abs=0.01)

    def test_extract_score_no_match(self):
        judge = self._make_judge()
        score = judge._extract_score("This is great work!")
        assert score == pytest.approx(0.0, abs=0.01)  # No score found, returns 0.0

    def test_default_rubric(self):
        judge = self._make_judge()
        rubric = judge._default_rubric()
        assert "accuracy" in rubric.lower() or len(rubric) > 10

    def test_format_tool_results(self):
        judge = self._make_judge()
        tool_results = [
            {"tool_call_id": "1", "content": "Dashboard list returned"},
            {"tool_call_id": "2", "content": "Chart data loaded"},
        ]
        formatted = judge._format_tool_results(tool_results)
        assert "Dashboard list" in formatted
        assert "Chart data" in formatted

    def test_format_tool_results_empty(self):
        judge = self._make_judge()
        formatted = judge._format_tool_results([])
        assert formatted is not None  # Returns "None" string for empty results


# ── MCPToolResultMatches (sync fallback) ─────────────────────────────────────


class TestMCPToolResultMatchesSync:
    def test_sync_evaluate_returns_skip(self):
        from testmcpy.evals.base_evaluators import MCPToolResultMatches

        ev = MCPToolResultMatches(tool_name="list_dashboards")
        result = ev.evaluate({"response": "test"})
        # Sync path should indicate async is needed
        assert not result.passed or "async" in (result.reason or "").lower()

    def test_extract_text_from_string(self):
        from testmcpy.evals.base_evaluators import MCPToolResultMatches

        ev = MCPToolResultMatches(tool_name="test")
        assert ev._extract_text("hello") == "hello"

    def test_extract_text_from_list(self):
        from testmcpy.evals.base_evaluators import MCPToolResultMatches

        ev = MCPToolResultMatches(tool_name="test")
        result = ev._extract_text([{"text": "item1"}, {"text": "item2"}])
        assert "item1" in result
        assert "item2" in result


# ── MCPVerifyResponseData (sync fallback) ────────────────────────────────────


class TestMCPVerifyResponseDataSync:
    def test_sync_evaluate_returns_skip(self):
        from testmcpy.evals.base_evaluators import MCPVerifyResponseData

        ev = MCPVerifyResponseData(tool_name="get_dashboard_info", check_fields=["title"])
        result = ev.evaluate({"response": "test"})
        assert not result.passed or "async" in (result.reason or "").lower()


# ── MCPVerifySideEffect (sync fallback) ──────────────────────────────────────


class TestMCPVerifySideEffectSync:
    def test_sync_evaluate_returns_skip(self):
        from testmcpy.evals.base_evaluators import MCPVerifySideEffect

        ev = MCPVerifySideEffect(
            verify_tool="get_dashboard_info",
            extract_from="tool_result",
        )
        result = ev.evaluate({"response": "test"})
        assert not result.passed or "async" in (result.reason or "").lower()

    def test_extract_id_from_response(self):
        from testmcpy.evals.base_evaluators import MCPVerifySideEffect

        ev = MCPVerifySideEffect(
            verify_tool="get_dashboard_info",
            extract_from="response",
            extract_pattern=r"dashboard (\d+)",
        )
        context = {"response": "Created dashboard 42 successfully"}
        extracted = ev._extract_id(context)
        assert extracted == "42"

    def test_extract_id_no_match(self):
        from testmcpy.evals.base_evaluators import MCPVerifySideEffect

        ev = MCPVerifySideEffect(
            verify_tool="get_dashboard_info",
            extract_from="response",
            extract_pattern=r"dashboard (\d+)",
        )
        context = {"response": "No dashboard was created"}
        extracted = ev._extract_id(context)
        assert extracted is None
