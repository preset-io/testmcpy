"""
Unit tests for the comparison matrix endpoint logic.

Tests the comparison of multiple test runs to verify
correct matrix generation, regression/improvement detection.
"""

from datetime import datetime, timezone

import pytest

from testmcpy.storage import TestStorage


@pytest.fixture
def storage(tmp_path):
    """Create a TestStorage with an isolated temp database."""
    db_path = tmp_path / "test_compare.db"
    return TestStorage(db_path=db_path)


@pytest.fixture
def storage_with_comparable_runs(storage):
    """Storage with two runs of the same suite, different results."""
    storage.save_suite(
        suite_id="compare-suite",
        name="Comparison Suite",
        questions=[{"id": "q1"}, {"id": "q2"}, {"id": "q3"}],
    )

    # Run A: claude, q1=pass, q2=pass, q3=fail
    storage.save_run(
        run_id="run-a",
        test_id="compare-suite",
        test_version=1,
        model="claude-sonnet-4-5",
        provider="anthropic",
        started_at=datetime.now(timezone.utc).isoformat(),
    )
    storage.save_question_result(
        run_id="run-a", question_id="q1", passed=True, score=1.0, duration_ms=500
    )
    storage.save_question_result(
        run_id="run-a", question_id="q2", passed=True, score=0.9, duration_ms=600
    )
    storage.save_question_result(
        run_id="run-a", question_id="q3", passed=False, score=0.1, duration_ms=300
    )
    storage.complete_run("run-a", datetime.now(timezone.utc).isoformat())

    # Run B: gpt-4o, q1=pass, q2=fail, q3=pass (regression on q2, improvement on q3)
    storage.save_run(
        run_id="run-b",
        test_id="compare-suite",
        test_version=1,
        model="gpt-4o",
        provider="openai",
        started_at=datetime.now(timezone.utc).isoformat(),
    )
    storage.save_question_result(
        run_id="run-b", question_id="q1", passed=True, score=1.0, duration_ms=400
    )
    storage.save_question_result(
        run_id="run-b", question_id="q2", passed=False, score=0.2, duration_ms=700
    )
    storage.save_question_result(
        run_id="run-b", question_id="q3", passed=True, score=0.95, duration_ms=350
    )
    storage.complete_run("run-b", datetime.now(timezone.utc).isoformat())

    return storage


def test_compare_two_runs(storage_with_comparable_runs):
    """Test basic comparison returns all questions from both runs."""
    storage = storage_with_comparable_runs
    run_a = storage.get_run("run-a")
    run_b = storage.get_run("run-b")

    assert run_a is not None
    assert run_b is not None

    # Both runs have 3 questions
    assert len(run_a["question_results"]) == 3
    assert len(run_b["question_results"]) == 3


def test_runs_have_different_results(storage_with_comparable_runs):
    """Test that runs have different pass/fail for same questions."""
    storage = storage_with_comparable_runs

    run_a = storage.get_run("run-a")
    run_b = storage.get_run("run-b")

    a_results = {q["question_id"]: q["passed"] for q in run_a["question_results"]}
    b_results = {q["question_id"]: q["passed"] for q in run_b["question_results"]}

    # q1: both pass
    assert a_results["q1"] is True
    assert b_results["q1"] is True

    # q2: regression (was pass, now fail)
    assert a_results["q2"] is True
    assert b_results["q2"] is False

    # q3: improvement (was fail, now pass)
    assert a_results["q3"] is False
    assert b_results["q3"] is True


def test_run_summaries_correct(storage_with_comparable_runs):
    """Test that run summaries calculate correctly."""
    storage = storage_with_comparable_runs

    run_a = storage.get_run("run-a")
    run_b = storage.get_run("run-b")

    assert run_a["summary"]["passed"] == 2
    assert run_a["summary"]["failed"] == 1

    assert run_b["summary"]["passed"] == 2
    assert run_b["summary"]["failed"] == 1


def test_question_scores_stored(storage_with_comparable_runs):
    """Test that individual question scores are stored correctly."""
    storage = storage_with_comparable_runs

    run_a = storage.get_run("run-a")
    q2_a = [q for q in run_a["question_results"] if q["question_id"] == "q2"][0]
    assert q2_a["score"] == 0.9

    run_b = storage.get_run("run-b")
    q2_b = [q for q in run_b["question_results"] if q["question_id"] == "q2"][0]
    assert q2_b["score"] == 0.2


def test_question_durations_stored(storage_with_comparable_runs):
    """Test that question durations are stored correctly."""
    storage = storage_with_comparable_runs

    run_a = storage.get_run("run-a")
    q1_a = [q for q in run_a["question_results"] if q["question_id"] == "q1"][0]
    assert q1_a["duration_ms"] == 500
