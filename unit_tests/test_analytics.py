"""Tests for testmcpy.analytics (matrix / leaderboard / flaky / history)."""

import pytest

from testmcpy.analytics import (
    config_key,
    flaky_tests,
    leaderboard,
    question_history,
    test_matrix,
)
from testmcpy.storage import TestStorage

# pytest tries to collect imported callables named test_*; this is a
# query helper, not a test.
test_matrix.__test__ = False


@pytest.fixture
def storage(tmp_path):
    return TestStorage(db_path=tmp_path / "analytics.db")


def _seed_run(storage, run_id, model, provider, profile, day, results):
    """results: list of (question_id, passed) tuples."""
    started = f"2026-06-{day:02d}T10:00:00"
    storage.save_run(
        run_id=run_id,
        test_id="suite-A",
        test_version=1,
        model=model,
        provider=provider,
        started_at=started,
        mcp_profile_id=profile,
    )
    for question_id, passed in results:
        storage.save_question_result(
            run_id=run_id,
            question_id=question_id,
            passed=passed,
            score=1.0 if passed else 0.0,
            duration_ms=1000,
            cost_usd=0.01,
        )
    storage.complete_run(run_id, started)


@pytest.fixture
def seeded(storage):
    """Two configs over two questions.

    claude @ staging — 3 runs: q1 always passes, q2 flaky (2/3).
    gpt @ staging    — 3 runs: q1 always fails, q2 always passes.
    """
    for i, q2_passed in enumerate([True, True, False], start=1):
        _seed_run(
            storage,
            f"claude-run-{i}",
            "claude-sonnet-4-5",
            "anthropic",
            "staging",
            day=i,
            results=[("q1", True), ("q2", q2_passed)],
        )
    for i in range(1, 4):
        _seed_run(
            storage,
            f"gpt-run-{i}",
            "gpt-4o",
            "openai",
            "staging",
            day=i,
            results=[("q1", False), ("q2", True)],
        )
    return storage


CLAUDE_KEY = "anthropic/claude-sonnet-4-5 @ staging"
GPT_KEY = "openai/gpt-4o @ staging"


def test_config_key():
    assert config_key("m", "p") == "p/m"
    assert config_key("m", "p", "prof") == "p/m @ prof"


def test_matrix_cells(seeded):
    with seeded.session() as session:
        matrix = test_matrix(session, suite_id="suite-A")

    rows = {r["question_id"]: r["cells"] for r in matrix["rows"]}
    assert set(rows) == {"q1", "q2"}

    q1_claude = rows["q1"][CLAUDE_KEY]
    assert q1_claude["n"] == 3
    assert q1_claude["pass_rate"] == 1.0
    assert q1_claude["flaky"] is False

    q1_gpt = rows["q1"][GPT_KEY]
    assert q1_gpt["pass_rate"] == 0.0
    assert q1_gpt["flaky"] is False  # consistently failing is not flaky

    q2_claude = rows["q2"][CLAUDE_KEY]
    assert q2_claude["n"] == 3
    assert 0.0 < q2_claude["pass_rate"] < 1.0
    assert q2_claude["flaky"] is True

    # Trend: one bucket per seeded day
    assert len(q2_claude["trend"]) == 3


def test_matrix_configs_aggregate(seeded):
    with seeded.session() as session:
        matrix = test_matrix(session, suite_id="suite-A")

    configs = {c["key"]: c for c in matrix["configs"]}
    assert configs[CLAUDE_KEY]["n_runs"] == 3
    # claude: q1 3/3 + q2 2/3 = 5/6
    assert configs[CLAUDE_KEY]["pass_rate"] == pytest.approx(5 / 6, abs=1e-3)
    # gpt: q1 0/3 + q2 3/3 = 3/6
    assert configs[GPT_KEY]["pass_rate"] == pytest.approx(0.5, abs=1e-3)
    assert configs[CLAUDE_KEY]["flaky_cells"] == 1
    assert configs[GPT_KEY]["flaky_cells"] == 0


def test_matrix_excludes_incomplete_runs(storage):
    _seed_run(storage, "done", "m", "p", "prof", 1, [("q1", True)])
    # Running (not completed) run must be excluded
    storage.save_run(
        run_id="in-flight",
        test_id="suite-A",
        test_version=1,
        model="m",
        provider="p",
        started_at="2026-06-02T10:00:00",
        mcp_profile_id="prof",
    )
    storage.save_question_result(run_id="in-flight", question_id="q1", passed=False, score=0.0)
    with storage.session() as session:
        matrix = test_matrix(session)
    cell = matrix["rows"][0]["cells"]["p/m @ prof"]
    assert cell["n"] == 1
    assert cell["pass_rate"] == 1.0


def test_matrix_single_run_warning(storage):
    _seed_run(storage, "only", "m", "p", None, 1, [("q1", True)])
    with storage.session() as session:
        matrix = test_matrix(session)
    assert any("n=1" in w for w in matrix["warnings"])


def test_matrix_min_runs_filter(seeded):
    _seed_run(seeded, "solo", "other-model", "p", "staging", 5, [("q1", True)])
    with seeded.session() as session:
        matrix = test_matrix(session, min_runs=2)
    for row in matrix["rows"]:
        assert "p/other-model @ staging" not in row["cells"]


def test_matrix_date_filter(seeded):
    with seeded.session() as session:
        matrix = test_matrix(session, date_from="2026-06-03")
    rows = {r["question_id"]: r["cells"] for r in matrix["rows"]}
    assert rows["q1"][CLAUDE_KEY]["n"] == 1  # only day-3 run


def test_leaderboard_ranking(seeded):
    with seeded.session() as session:
        ranked = leaderboard(session, suite_id="suite-A")
    assert [c["key"] for c in ranked] == [CLAUDE_KEY, GPT_KEY]
    assert ranked[0]["cost_per_pass"] is not None
    assert ranked[0]["avg_duration_ms"] == 1000.0


def test_flaky_tests(seeded):
    with seeded.session() as session:
        flaky = flaky_tests(session, suite_id="suite-A")
    assert len(flaky) == 1
    assert flaky[0]["question_id"] == "q2"
    assert flaky[0]["config"] == CLAUDE_KEY
    assert flaky[0]["n"] == 3


def test_question_history(seeded):
    with seeded.session() as session:
        points = question_history(session, "q2", suite_id="suite-A", model="claude-sonnet-4-5")
    assert len(points) == 3
    assert [p["passed"] for p in points] == [True, True, False]  # chronological
    assert points[0]["config"] == CLAUDE_KEY
    assert points[0]["run_id"] == "claude-run-1"


# --- effort / suite grouping + Python-side extras -------------------------


def _seed_effort_run(storage, run_id, effort, score, tokens, steps, suite="suite-A", day=1):
    storage.save_run(
        run_id=run_id,
        test_id=suite,
        test_version=1,
        model="claude-opus-4-8",
        provider="claude-sdk",
        started_at=f"2026-07-{day:02d}T10:00:00",
        effort=effort,
    )
    tool_uses = [
        {"name": "list_datasets", "arguments": {}, "id": f"{run_id}-{i}"} for i in range(steps)
    ]
    storage.save_question_result(
        run_id=run_id,
        question_id="q1",
        passed=score >= 0.5,
        score=score,
        base_score=score,
        tool_uses=tool_uses,
        tokens_output=tokens,
        duration_ms=1000,
        cost_usd=0.01,
    )
    storage.complete_run(run_id, f"2026-07-{day:02d}T10:01:00")


def test_leaderboard_splits_by_effort_with_variance(storage):
    # two 'high' repeats (0.8, 1.0) + one 'low'
    _seed_effort_run(storage, "r1", "high", 0.8, 100, 3)
    _seed_effort_run(storage, "r2", "high", 1.0, 120, 5)
    _seed_effort_run(storage, "r3", "low", 0.6, 50, 2)

    with storage.session() as session:
        ranked = leaderboard(session, include_effort=True)

    by_effort = {c["effort"]: c for c in ranked}
    assert set(by_effort) == {"high", "low"}
    high = by_effort["high"]
    assert high["n_results"] == 2
    assert high["avg_score"] == 0.9
    assert high["score_stddev"] == 0.1  # pstdev([0.8, 1.0])
    assert high["avg_tokens_output"] == 110.0
    assert high["avg_steps"] == 4.0  # mean([3, 5])
    assert "[high]" in high["key"]

    low = by_effort["low"]
    assert low["n_results"] == 1
    assert low["score_stddev"] == 0.0  # single run -> no spread


def test_leaderboard_merges_effort_when_flag_off(storage):
    _seed_effort_run(storage, "r1", "high", 0.8, 100, 3)
    _seed_effort_run(storage, "r2", "low", 1.0, 120, 5)

    with storage.session() as session:
        ranked = leaderboard(session, include_effort=False)

    assert len(ranked) == 1
    assert ranked[0]["effort"] is None
    assert ranked[0]["n_results"] == 2


def test_leaderboard_splits_by_suite(storage):
    _seed_effort_run(storage, "a1", None, 1.0, 100, 3, suite="suite-A")
    _seed_effort_run(storage, "b1", None, 0.5, 100, 3, suite="suite-B")

    with storage.session() as session:
        ranked = leaderboard(session, include_suite=True)

    suites = {c["suite"] for c in ranked}
    assert suites == {"suite-A", "suite-B"}
    # suite is folded into the unique key
    assert any(c["key"].startswith("suite-A ::") for c in ranked)
