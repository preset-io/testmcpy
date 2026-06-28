"""
Unit tests for metrics aggregation logic.

Tests the metrics router's aggregation of cost, latency,
pass rate, and token usage from test runs.
"""

from datetime import datetime, timezone

import pytest

from testmcpy.storage import TestStorage


@pytest.fixture
def storage(tmp_path):
    """Create a TestStorage with an isolated temp database."""
    db_path = tmp_path / "test_metrics.db"
    return TestStorage(db_path=db_path)


@pytest.fixture
def storage_with_runs(storage):
    """Storage pre-populated with test suites and runs."""
    # Create a suite
    storage.save_suite(
        suite_id="basic-tests",
        name="Basic Tests",
        questions=[{"id": "q1"}, {"id": "q2"}, {"id": "q3"}],
    )

    # Create two runs
    storage.save_run(
        run_id="run-1",
        test_id="basic-tests",
        test_version=1,
        model="claude-sonnet-4-5",
        provider="anthropic",
        started_at=datetime.now(timezone.utc).isoformat(),
        mcp_profile_id="my-profile",
    )

    storage.save_question_result(
        run_id="run-1",
        question_id="q1",
        passed=True,
        score=1.0,
        duration_ms=500,
        tokens_input=100,
        tokens_output=50,
    )
    storage.save_question_result(
        run_id="run-1",
        question_id="q2",
        passed=True,
        score=0.8,
        duration_ms=800,
        tokens_input=120,
        tokens_output=60,
    )
    storage.save_question_result(
        run_id="run-1",
        question_id="q3",
        passed=False,
        score=0.0,
        duration_ms=300,
        tokens_input=80,
        tokens_output=40,
        error="Expected X got Y",
    )
    storage.complete_run("run-1", datetime.now(timezone.utc).isoformat())

    # Second run with different model
    storage.save_run(
        run_id="run-2",
        test_id="basic-tests",
        test_version=1,
        model="gpt-4o",
        provider="openai",
        started_at=datetime.now(timezone.utc).isoformat(),
    )
    storage.save_question_result(
        run_id="run-2",
        question_id="q1",
        passed=True,
        score=1.0,
        duration_ms=400,
    )
    storage.save_question_result(
        run_id="run-2",
        question_id="q2",
        passed=False,
        score=0.3,
        duration_ms=600,
    )
    storage.complete_run("run-2", datetime.now(timezone.utc).isoformat())

    return storage


def test_list_runs_returns_data(storage_with_runs):
    """Test that list_runs returns the correct number of runs."""
    runs = storage_with_runs.list_runs()
    assert len(runs) == 2


def test_get_run_returns_question_results(storage_with_runs):
    """Test that get_run includes question results with correct pass/fail."""
    run = storage_with_runs.get_run("run-1")
    assert run is not None
    assert len(run["question_results"]) == 3
    assert run["summary"]["passed"] == 2
    assert run["summary"]["failed"] == 1


def test_get_run_summary_calculations(storage_with_runs):
    """Test that run summary calculates pass rate correctly."""
    run = storage_with_runs.get_run("run-1")
    summary = run["summary"]
    assert summary["total"] == 3
    assert summary["passed"] == 2
    # pass_rate = 2/3 * 100 = 66.67
    assert abs(summary["pass_rate"] - 66.67) < 1


def test_get_run_not_found(storage_with_runs):
    """Test that get_run returns None for missing run."""
    run = storage_with_runs.get_run("nonexistent-run")
    assert run is None


def test_list_runs_filter_by_model(storage_with_runs):
    """Test filtering runs by model."""
    runs = storage_with_runs.list_runs(model="gpt-4o")
    assert len(runs) == 1
    assert runs[0]["model"] == "gpt-4o"


def test_question_result_error_stored(storage_with_runs):
    """Test that error messages are stored in question results."""
    run = storage_with_runs.get_run("run-1")
    q3 = [q for q in run["question_results"] if q["question_id"] == "q3"][0]
    assert q3["error"] == "Expected X got Y"
    assert not q3["passed"]


def test_empty_storage_returns_empty(storage):
    """Test that empty storage returns empty lists."""
    runs = storage.list_runs()
    assert runs == []

    run = storage.get_run("nonexistent")
    assert run is None


def test_base_score_persisted_and_returned(storage):
    """save_question_result stores the pre-penalty base_score and get_run
    surfaces it (NULL stays None for rows that don't supply one)."""
    storage.save_suite(suite_id="s", name="s", questions=[{"id": "q1"}])
    storage.save_run(
        run_id="r1",
        test_id="s",
        test_version=1,
        model="m",
        provider="p",
        started_at=datetime.now(timezone.utc).isoformat(),
    )
    storage.save_question_result(
        run_id="r1", question_id="q1", passed=True, score=1.0, base_score=1.0
    )
    qr = storage.get_run("r1")["question_results"][0]
    assert qr["base_score"] == 1.0


def test_manual_fp_rescore_is_idempotent():
    """Regression: toggling a manual false positive must re-score from the
    stored pre-penalty base, not the already-penalised score — otherwise each
    toggle would halve again (1.0 → 0.5 → 0.25 …) and un-marking would never
    restore. Mirrors metrics.set_false_positive's fallback logic."""
    from testmcpy.scoring import compute_score_breakdown

    def rescore(stored_score, base_score, evaluations, manual):
        base = (
            sum(e["score"] for e in evaluations) / len(evaluations)
            if evaluations
            else (base_score if base_score is not None else stored_score)
        )
        return compute_score_breakdown(base, evaluations, None, manual_false_positive=manual)[
            "final_score"
        ]

    base = 1.0
    on = rescore(1.0, base, [], True)  # mark FP
    assert on == 0.5
    off = rescore(on, base, [], False)  # unmark -> restored, not stuck at 0.5
    assert off == 1.0
    on2 = rescore(off, base, [], True)  # re-mark -> 0.5 again, not 0.25
    assert on2 == 0.5
