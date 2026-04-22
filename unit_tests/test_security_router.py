"""
Unit tests for the security dashboard endpoint logic.

Tests security evaluator classification, severity mapping,
and result aggregation from stored test runs.

Story: SC-103127 — Red team security dashboard with risk categorization
"""

from datetime import datetime, timezone

import pytest

from testmcpy.server.routers.security import (
    SECURITY_EVALUATORS,
    SEVERITY_MAP,
    _get_severity,
    _is_security_evaluator,
)
from testmcpy.storage import TestStorage

# ── Helper classification tests ──────────────────────────────────────────────


class TestIsSecurityEvaluator:
    """Tests for _is_security_evaluator classification."""

    @pytest.mark.parametrize(
        "name",
        [
            "no_leaked_data",
            "response_not_includes",
            "no_injection",
            "no_sensitive_data",
            "no_pii",
            "no_credentials",
            "no_secrets",
            "sanitized_output",
            "input_validation",
            "no_sql_injection",
            "no_xss",
            "no_code_injection",
            "safe_output",
        ],
    )
    def test_known_security_evaluators(self, name):
        """All evaluators in SECURITY_EVALUATORS set should match."""
        assert _is_security_evaluator(name) is True

    @pytest.mark.parametrize(
        "name",
        [
            "custom_security_check",
            "check_injection_attack",
            "data_leak_detector",
            "pii_filter",
            "credential_validator",
            "xss_protection",
            "auth_token_check",
            "permission_validator",
            "access_control_test",
        ],
    )
    def test_keyword_matching(self, name):
        """Evaluator names containing security keywords should match."""
        assert _is_security_evaluator(name) is True

    @pytest.mark.parametrize(
        "name",
        [
            "was_mcp_tool_called",
            "execution_successful",
            "final_answer_contains",
            "tool_call_count",
            "within_time_limit",
            "token_usage_reasonable",
        ],
    )
    def test_non_security_evaluators(self, name):
        """Non-security evaluators should not match."""
        assert _is_security_evaluator(name) is False

    def test_case_insensitive(self):
        """Matching should be case-insensitive."""
        assert _is_security_evaluator("No_Leaked_Data") is True
        assert _is_security_evaluator("NO_PII") is True

    def test_empty_string(self):
        """Empty string should not match."""
        assert _is_security_evaluator("") is False


class TestGetSeverity:
    """Tests for _get_severity level mapping."""

    @pytest.mark.parametrize(
        "name,expected",
        [
            ("no_leaked_data", "critical"),
            ("no_credentials", "critical"),
            ("no_secrets", "critical"),
            ("no_injection", "critical"),
            ("no_sql_injection", "critical"),
            ("no_code_injection", "critical"),
            ("no_pii", "high"),
            ("no_sensitive_data", "high"),
            ("no_xss", "high"),
            ("response_not_includes", "medium"),
            ("input_validation", "medium"),
            ("sanitized_output", "medium"),
            ("safe_output", "low"),
        ],
    )
    def test_known_severity_mappings(self, name, expected):
        """Known evaluators should return their mapped severity."""
        assert _get_severity(name) == expected

    def test_unknown_with_inject_keyword(self):
        """Unknown evaluator with 'inject' keyword -> critical."""
        assert _get_severity("custom_inject_test") == "critical"

    def test_unknown_with_leak_keyword(self):
        """Unknown evaluator with 'leak' keyword -> critical."""
        assert _get_severity("check_data_leak") == "critical"

    def test_unknown_with_pii_keyword(self):
        """Unknown evaluator with 'pii' keyword -> high."""
        assert _get_severity("detect_pii_exposure") == "high"

    def test_unknown_with_sanitiz_keyword(self):
        """Unknown evaluator with 'sanitiz' keyword -> medium."""
        assert _get_severity("html_sanitizer_check") == "medium"

    def test_unknown_no_keywords(self):
        """Unknown evaluator with no matching keywords -> low."""
        assert _get_severity("some_random_check") == "low"


# ── Constant integrity tests ─────────────────────────────────────────────────


class TestConstants:
    """Ensure constants are well-formed and consistent."""

    def test_all_severity_map_keys_in_evaluators(self):
        """Every evaluator in SEVERITY_MAP should be in SECURITY_EVALUATORS."""
        for name in SEVERITY_MAP:
            assert name in SECURITY_EVALUATORS, (
                f"{name} in SEVERITY_MAP but not in SECURITY_EVALUATORS"
            )

    def test_severity_values_valid(self):
        """All severity values should be one of the valid levels."""
        valid = {"critical", "high", "medium", "low"}
        for name, sev in SEVERITY_MAP.items():
            assert sev in valid, f"{name} has invalid severity '{sev}'"


# ── Integration with storage ─────────────────────────────────────────────────


@pytest.fixture
def storage(tmp_path):
    """Create a TestStorage with an isolated temp database."""
    db_path = tmp_path / "test_security.db"
    return TestStorage(db_path=db_path)


@pytest.fixture
def storage_with_security_results(storage):
    """Storage with test runs containing security-related evaluations."""
    storage.save_suite(
        suite_id="sec-suite",
        name="Security Suite",
        questions=[{"id": "q1"}, {"id": "q2"}, {"id": "q3"}],
    )

    storage.save_run(
        run_id="sec-run-1",
        test_id="sec-suite",
        test_version=1,
        model="claude-sonnet-4-5",
        provider="anthropic",
        started_at=datetime.now(timezone.utc).isoformat(),
    )

    # q1: security eval passes
    storage.save_question_result(
        run_id="sec-run-1",
        question_id="q1",
        passed=True,
        score=1.0,
        duration_ms=200,
        evaluations=[
            {"evaluator": "no_leaked_data", "passed": True, "score": 1.0, "reason": "No PII found"},
            {"evaluator": "execution_successful", "passed": True, "score": 1.0, "reason": "OK"},
        ],
    )

    # q2: security eval fails
    storage.save_question_result(
        run_id="sec-run-1",
        question_id="q2",
        passed=False,
        score=0.0,
        duration_ms=300,
        evaluations=[
            {"evaluator": "no_pii", "passed": False, "score": 0.0, "reason": "Found SSN"},
            {"evaluator": "was_mcp_tool_called", "passed": True, "score": 1.0, "reason": "OK"},
        ],
    )

    # q3: no security evals at all
    storage.save_question_result(
        run_id="sec-run-1",
        question_id="q3",
        passed=True,
        score=1.0,
        duration_ms=100,
        evaluations=[
            {"evaluator": "execution_successful", "passed": True, "score": 1.0, "reason": "OK"},
        ],
    )

    storage.complete_run("sec-run-1", datetime.now(timezone.utc).isoformat())
    return storage


def test_security_results_stored(storage_with_security_results):
    """Verify security-tagged evaluations are stored and retrievable."""
    storage = storage_with_security_results
    run = storage.get_run("sec-run-1")
    assert run is not None
    assert len(run["question_results"]) == 3

    q1 = [q for q in run["question_results"] if q["question_id"] == "q1"][0]
    evals = q1.get("evaluations", [])
    security_evals = [e for e in evals if _is_security_evaluator(e.get("evaluator", ""))]
    assert len(security_evals) == 1
    assert security_evals[0]["evaluator"] == "no_leaked_data"


def test_non_security_evals_excluded(storage_with_security_results):
    """Non-security evaluators should not be classified as security."""
    storage = storage_with_security_results
    run = storage.get_run("sec-run-1")

    q2 = [q for q in run["question_results"] if q["question_id"] == "q2"][0]
    evals = q2.get("evaluations", [])
    non_security = [e for e in evals if not _is_security_evaluator(e.get("evaluator", ""))]
    assert len(non_security) == 1
    assert non_security[0]["evaluator"] == "was_mcp_tool_called"


def test_question_with_no_security_evals(storage_with_security_results):
    """Questions without security evaluators should have zero security results."""
    storage = storage_with_security_results
    run = storage.get_run("sec-run-1")

    q3 = [q for q in run["question_results"] if q["question_id"] == "q3"][0]
    evals = q3.get("evaluations", [])
    security_evals = [e for e in evals if _is_security_evaluator(e.get("evaluator", ""))]
    assert len(security_evals) == 0


def test_severity_assignment_on_stored_results(storage_with_security_results):
    """Verify severity is correctly assigned when processing stored results."""
    storage = storage_with_security_results
    run = storage.get_run("sec-run-1")

    q1 = [q for q in run["question_results"] if q["question_id"] == "q1"][0]
    for ev in q1.get("evaluations", []):
        if _is_security_evaluator(ev.get("evaluator", "")):
            assert _get_severity(ev["evaluator"]) == "critical"

    q2 = [q for q in run["question_results"] if q["question_id"] == "q2"][0]
    for ev in q2.get("evaluations", []):
        if _is_security_evaluator(ev.get("evaluator", "")):
            assert _get_severity(ev["evaluator"]) == "high"


def test_empty_evaluations_handled(storage):
    """Questions with empty or null evaluations should not crash."""
    storage.save_suite(
        suite_id="empty-suite",
        name="Empty Evals",
        questions=[{"id": "q1"}],
    )
    storage.save_run(
        run_id="empty-run",
        test_id="empty-suite",
        test_version=1,
        model="test",
        provider="test",
        started_at=datetime.now(timezone.utc).isoformat(),
    )
    storage.save_question_result(
        run_id="empty-run",
        question_id="q1",
        passed=True,
        score=1.0,
        duration_ms=100,
        evaluations=[],
    )
    storage.complete_run("empty-run", datetime.now(timezone.utc).isoformat())

    run = storage.get_run("empty-run")
    q1 = run["question_results"][0]
    evals = q1.get("evaluations", [])
    security_evals = [e for e in evals if _is_security_evaluator(e.get("evaluator", ""))]
    assert len(security_evals) == 0
