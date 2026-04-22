"""
Unit tests for per-eval cost tracking — AC 3.

Verifies cost_usd is stored and retrieved per question result.

Story: SC-104612 — Trial Benchmark
"""

from datetime import datetime, timezone

import pytest

from testmcpy.storage import TestStorage


@pytest.fixture
def storage(tmp_path):
    db_path = tmp_path / "test_cost.db"
    return TestStorage(db_path=db_path)


@pytest.fixture
def storage_with_run(storage):
    storage.save_suite(
        suite_id="cost-suite",
        name="Cost Suite",
        questions=[{"id": "q1"}, {"id": "q2"}],
    )
    storage.save_run(
        run_id="cost-run-1",
        test_id="cost-suite",
        test_version=1,
        model="gpt-5.4",
        provider="openai",
        started_at=datetime.now(timezone.utc).isoformat(),
    )
    return storage


def test_save_question_result_with_cost(storage_with_run):
    """cost_usd should be stored when provided."""
    storage_with_run.save_question_result(
        run_id="cost-run-1",
        question_id="q1",
        passed=True,
        score=1.0,
        duration_ms=500,
        tokens_input=150,
        tokens_output=50,
        cost_usd=0.00125,
    )
    storage_with_run.complete_run("cost-run-1", datetime.now(timezone.utc).isoformat())

    run = storage_with_run.get_run("cost-run-1")
    q1 = run["question_results"][0]
    assert q1["cost_usd"] == pytest.approx(0.00125, abs=1e-6)


def test_save_question_result_cost_default_zero(storage_with_run):
    """cost_usd should default to 0.0 when not provided."""
    storage_with_run.save_question_result(
        run_id="cost-run-1",
        question_id="q1",
        passed=True,
        score=1.0,
        duration_ms=500,
    )
    storage_with_run.complete_run("cost-run-1", datetime.now(timezone.utc).isoformat())

    run = storage_with_run.get_run("cost-run-1")
    q1 = run["question_results"][0]
    assert q1["cost_usd"] == 0.0


def test_multiple_questions_different_costs(storage_with_run):
    """Each question should track its own cost independently."""
    storage_with_run.save_question_result(
        run_id="cost-run-1",
        question_id="q1",
        passed=True,
        score=1.0,
        duration_ms=500,
        cost_usd=0.005,
    )
    storage_with_run.save_question_result(
        run_id="cost-run-1",
        question_id="q2",
        passed=False,
        score=0.0,
        duration_ms=800,
        cost_usd=0.012,
    )
    storage_with_run.complete_run("cost-run-1", datetime.now(timezone.utc).isoformat())

    run = storage_with_run.get_run("cost-run-1")
    costs = {q["question_id"]: q["cost_usd"] for q in run["question_results"]}
    assert costs["q1"] == pytest.approx(0.005, abs=1e-6)
    assert costs["q2"] == pytest.approx(0.012, abs=1e-6)


def test_summary_includes_total_cost(storage_with_run):
    """Run summary should include total_cost_usd from all questions."""
    storage_with_run.save_question_result(
        run_id="cost-run-1",
        question_id="q1",
        passed=True,
        score=1.0,
        duration_ms=500,
        cost_usd=0.005,
    )
    storage_with_run.save_question_result(
        run_id="cost-run-1",
        question_id="q2",
        passed=True,
        score=0.8,
        duration_ms=600,
        cost_usd=0.010,
    )
    storage_with_run.complete_run("cost-run-1", datetime.now(timezone.utc).isoformat())

    run = storage_with_run.get_run("cost-run-1")
    assert run["summary"]["total_cost_usd"] == pytest.approx(0.015, abs=1e-6)


def test_cost_zero_when_no_questions(storage):
    """Run with no questions should have zero cost."""
    storage.save_suite(
        suite_id="empty-suite",
        name="Empty",
        questions=[],
    )
    storage.save_run(
        run_id="empty-run",
        test_id="empty-suite",
        test_version=1,
        model="test",
        provider="test",
        started_at=datetime.now(timezone.utc).isoformat(),
    )
    storage.complete_run("empty-run", datetime.now(timezone.utc).isoformat())

    run = storage.get_run("empty-run")
    assert run["summary"]["total_cost_usd"] == 0.0


def test_cost_usd_in_dataset_format(storage_with_run):
    """Verify the output matches Max's dataset spec: suite_id, eval_id, duration, success, score, cost_usd."""
    storage_with_run.save_question_result(
        run_id="cost-run-1",
        question_id="test_list_dashboards",
        passed=True,
        score=0.95,
        duration_ms=1200,
        cost_usd=0.008,
    )
    storage_with_run.complete_run("cost-run-1", datetime.now(timezone.utc).isoformat())

    run = storage_with_run.get_run("cost-run-1")
    q = run["question_results"][0]

    # Max's required dataset fields
    assert "question_id" in q  # eval_id
    assert "passed" in q  # success
    assert "score" in q  # score
    assert "duration_ms" in q  # duration
    assert "cost_usd" in q  # cost_usd

    # Values
    assert q["question_id"] == "test_list_dashboards"
    assert q["passed"] is True
    assert q["score"] == 0.95
    assert q["duration_ms"] == 1200
    assert q["cost_usd"] == pytest.approx(0.008, abs=1e-6)

    # Run-level has suite_id and model
    assert run["test_id"] == "cost-suite"  # suite_id
    assert run["model"] == "gpt-5.4"
