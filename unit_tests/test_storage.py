"""
Unit tests for testmcpy.storage module.

Tests cover:
- TestVersion and TestResult dataclasses
- Version management (save, get, diff)
- Result storage and querying with filters
- Metrics & analytics (pass rate, trends, model comparison, failing tests)
- Test suite management (save, get, list, versioning)
- Test run management (save, complete, question results, get, list)
- Content hashing and deduplication
- Edge cases (empty DB, missing records, zero results)
"""

import json
import sqlite3
from datetime import datetime, timezone

import pytest

from testmcpy.storage import TestResult, TestStorage, TestVersion

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def storage(tmp_path):
    """Create a TestStorage with an isolated temp database."""
    db_path = tmp_path / "test_storage.db"
    return TestStorage(db_path=db_path)


@pytest.fixture
def storage_with_results(storage):
    """Storage pre-populated with several test results."""
    # Save some results with different models and pass/fail states
    storage.save_result(
        test_path="tests/basic.yaml",
        test_name="test_add",
        passed=True,
        score=1.0,
        duration=0.5,
        cost=0.001,
        tokens_used=100,
        model="claude-sonnet-4-5",
        provider="anthropic",
        evaluations=[{"evaluator": "contains", "passed": True}],
    )
    storage.save_result(
        test_path="tests/basic.yaml",
        test_name="test_subtract",
        passed=False,
        score=0.0,
        duration=0.8,
        cost=0.002,
        tokens_used=200,
        model="claude-sonnet-4-5",
        provider="anthropic",
        error="Expected 5 but got 3",
        evaluations=[{"evaluator": "contains", "passed": False}],
    )
    storage.save_result(
        test_path="tests/advanced.yaml",
        test_name="test_multiply",
        passed=True,
        score=0.9,
        duration=1.2,
        cost=0.005,
        tokens_used=500,
        model="gpt-4o",
        provider="openai",
        evaluations=[{"evaluator": "contains", "passed": True}],
    )
    return storage


@pytest.fixture
def storage_with_suite(storage):
    """Storage pre-populated with a test suite."""
    questions = [
        {"id": "q1", "text": "What is 2+2?", "expected": "4"},
        {"id": "q2", "text": "What is 3+3?", "expected": "6"},
    ]
    storage.save_suite(
        suite_id="suite-001",
        name="Math Tests",
        questions=questions,
        environment_id="env-1",
        description="Basic math tests",
        metadata={"tags": ["math", "basic"]},
    )
    return storage


@pytest.fixture
def storage_with_run(storage_with_suite):
    """Storage pre-populated with a test run and question results."""
    store = storage_with_suite
    now = datetime.now(timezone.utc).isoformat()
    store.save_run(
        run_id="run-001",
        test_id="suite-001",
        test_version=1,
        model="claude-sonnet-4-5",
        provider="anthropic",
        started_at=now,
        environment_id="env-1",
        runner_tool="mcp-client",
        metadata={"trigger": "manual"},
    )
    store.save_question_result(
        run_id="run-001",
        question_id="q1",
        passed=True,
        score=1.0,
        answer="4",
        tool_uses=[{"name": "calculator", "input": {"op": "add"}}],
        tool_results=[{"result": "4"}],
        tokens_input=50,
        tokens_output=10,
        tti_ms=200,
        duration_ms=500,
        evaluations=[{"evaluator": "exact_match", "passed": True}],
    )
    store.save_question_result(
        run_id="run-001",
        question_id="q2",
        passed=False,
        score=0.0,
        answer="7",
        tokens_input=50,
        tokens_output=10,
        duration_ms=400,
        error="Expected 6 got 7",
    )
    return store


# ---------------------------------------------------------------------------
# TestVersion dataclass
# ---------------------------------------------------------------------------


class TestTestVersion:
    def test_to_dict(self):
        tv = TestVersion(
            id=1,
            test_path="tests/a.yaml",
            version=2,
            content_hash="abc123",
            content="content here",
            created_at="2024-01-01T00:00:00",
            message="initial",
        )
        d = tv.to_dict()
        assert d["id"] == 1
        assert d["test_path"] == "tests/a.yaml"
        assert d["version"] == 2
        assert d["content_hash"] == "abc123"
        assert d["message"] == "initial"

    def test_to_dict_none_message(self):
        tv = TestVersion(
            id=1,
            test_path="t.yaml",
            version=1,
            content_hash="x",
            content="c",
            created_at="now",
        )
        d = tv.to_dict()
        assert d["message"] is None


# ---------------------------------------------------------------------------
# TestResult dataclass
# ---------------------------------------------------------------------------


class TestTestResult:
    def test_to_dict_parses_evaluations_json(self):
        tr = TestResult(
            id=1,
            test_path="t.yaml",
            test_name="test_1",
            version_id=None,
            passed=True,
            score=1.0,
            duration=0.5,
            cost=0.001,
            tokens_used=100,
            model="m",
            provider="p",
            error=None,
            evaluations='[{"evaluator": "contains", "passed": true}]',
            created_at="now",
        )
        d = tr.to_dict()
        assert isinstance(d["evaluations"], list)
        assert d["evaluations"][0]["evaluator"] == "contains"
        assert d["passed"] is True

    def test_to_dict_empty_evaluations(self):
        tr = TestResult(
            id=1,
            test_path="t.yaml",
            test_name="test_1",
            version_id=None,
            passed=False,
            score=0.0,
            duration=0.0,
            cost=0.0,
            tokens_used=0,
            model="",
            provider="",
            error="boom",
            evaluations="[]",
            created_at="now",
        )
        d = tr.to_dict()
        assert d["evaluations"] == []
        assert d["error"] == "boom"


# ---------------------------------------------------------------------------
# TestStorage initialization
# ---------------------------------------------------------------------------


class TestStorageInit:
    def test_creates_db_file(self, tmp_path):
        db_path = tmp_path / "new.db"
        assert not db_path.exists()
        TestStorage(db_path=db_path)
        assert db_path.exists()

    def test_schema_tables_created(self, storage):
        with sqlite3.connect(storage.db_path) as conn:
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
            tables = {row[0] for row in cursor.fetchall()}

        expected = {"test_versions", "test_results", "test_suites", "test_runs", "question_results"}
        assert expected.issubset(tables)

    def test_default_path_creates_dir(self, tmp_path, monkeypatch):
        """When db_path is None, uses .testmcpy/storage.db in cwd."""
        monkeypatch.chdir(tmp_path)
        s = TestStorage(db_path=None)
        assert s.db_path == tmp_path / ".testmcpy" / "storage.db"
        assert s.db_path.exists()

    def test_idempotent_schema_creation(self, tmp_path):
        """Creating TestStorage twice on same DB doesn't error."""
        db_path = tmp_path / "idempotent.db"
        TestStorage(db_path=db_path)
        TestStorage(db_path=db_path)  # Should not raise


# ---------------------------------------------------------------------------
# Version Management
# ---------------------------------------------------------------------------


class TestVersionManagement:
    def test_save_version_creates_new(self, storage):
        v = storage.save_version("tests/a.yaml", "content: true", message="first")
        assert v.id is not None
        assert v.version == 1
        assert v.test_path == "tests/a.yaml"
        assert v.message == "first"
        assert v.content == "content: true"
        assert len(v.content_hash) == 16

    def test_save_version_deduplicates(self, storage):
        v1 = storage.save_version("tests/a.yaml", "same content")
        v2 = storage.save_version("tests/a.yaml", "same content")
        assert v1.id == v2.id
        assert v1.version == v2.version

    def test_save_version_increments_on_change(self, storage):
        v1 = storage.save_version("tests/a.yaml", "version 1 content")
        v2 = storage.save_version("tests/a.yaml", "version 2 content")
        assert v2.version == v1.version + 1
        assert v2.content_hash != v1.content_hash

    def test_save_version_separate_paths(self, storage):
        v1 = storage.save_version("tests/a.yaml", "content A")
        v2 = storage.save_version("tests/b.yaml", "content B")
        assert v1.version == 1
        assert v2.version == 1
        assert v1.test_path != v2.test_path

    def test_get_versions(self, storage):
        storage.save_version("tests/a.yaml", "v1")
        storage.save_version("tests/a.yaml", "v2")
        storage.save_version("tests/a.yaml", "v3")

        versions = storage.get_versions("tests/a.yaml")
        assert len(versions) == 3
        # Ordered by version DESC
        assert versions[0].version == 3
        assert versions[2].version == 1

    def test_get_versions_limit(self, storage):
        for i in range(5):
            storage.save_version("tests/a.yaml", f"content {i}")

        versions = storage.get_versions("tests/a.yaml", limit=2)
        assert len(versions) == 2
        assert versions[0].version == 5

    def test_get_versions_empty(self, storage):
        versions = storage.get_versions("nonexistent.yaml")
        assert versions == []

    def test_get_version_specific(self, storage):
        storage.save_version("tests/a.yaml", "v1 content")
        storage.save_version("tests/a.yaml", "v2 content")

        v = storage.get_version("tests/a.yaml", 1)
        assert v is not None
        assert v.version == 1
        assert v.content == "v1 content"

    def test_get_version_not_found(self, storage):
        v = storage.get_version("tests/a.yaml", 999)
        assert v is None

    def test_get_latest_version(self, storage):
        storage.save_version("tests/a.yaml", "v1")
        storage.save_version("tests/a.yaml", "v2")
        storage.save_version("tests/a.yaml", "v3")

        latest = storage.get_latest_version("tests/a.yaml")
        assert latest is not None
        assert latest.version == 3

    def test_get_latest_version_empty(self, storage):
        latest = storage.get_latest_version("nonexistent.yaml")
        assert latest is None

    def test_diff_versions(self, storage):
        storage.save_version("tests/a.yaml", "line1\nline2\n")
        storage.save_version("tests/a.yaml", "line1\nline2_modified\nline3\n")

        diff = storage.diff_versions("tests/a.yaml", 1, 2)
        assert "version1" in diff
        assert "version2" in diff
        assert diff["version1"] == 1
        assert diff["version2"] == 2
        assert diff["diff"] != ""
        assert diff["v1_hash"] != diff["v2_hash"]

    def test_diff_versions_not_found(self, storage):
        storage.save_version("tests/a.yaml", "content")

        diff = storage.diff_versions("tests/a.yaml", 1, 999)
        assert diff == {"error": "Version not found"}

    def test_diff_versions_identical(self, storage):
        storage.save_version("tests/a.yaml", "same content v1")
        # Force version 2 with different content, then compare same version
        storage.save_version("tests/a.yaml", "different content v2")
        diff = storage.diff_versions("tests/a.yaml", 1, 1)
        # Diff of same version with itself should be empty
        assert diff["diff"] == ""
        assert diff["v1_hash"] == diff["v2_hash"]


# ---------------------------------------------------------------------------
# Result Storage
# ---------------------------------------------------------------------------


class TestResultStorage:
    def test_save_result(self, storage):
        result = storage.save_result(
            test_path="tests/a.yaml",
            test_name="test_1",
            passed=True,
            duration=0.5,
            cost=0.001,
            tokens_used=100,
            model="claude-sonnet-4-5",
            provider="anthropic",
            evaluations=[{"evaluator": "contains", "passed": True}],
            score=1.0,
        )
        assert result.id is not None
        assert result.passed is True
        assert result.model == "claude-sonnet-4-5"
        assert result.score == 1.0

    def test_save_result_with_error(self, storage):
        result = storage.save_result(
            test_path="tests/a.yaml",
            test_name="test_fail",
            passed=False,
            error="Connection timeout",
        )
        assert result.passed is False
        assert result.error == "Connection timeout"

    def test_save_result_defaults(self, storage):
        result = storage.save_result(
            test_path="t.yaml",
            test_name="t",
            passed=True,
        )
        assert result.duration == 0.0
        assert result.cost == 0.0
        assert result.tokens_used == 0
        assert result.model == ""
        assert result.provider == ""
        assert result.error is None

    def test_get_results_all(self, storage_with_results):
        results = storage_with_results.get_results()
        assert len(results) == 3

    def test_get_results_filter_by_path(self, storage_with_results):
        results = storage_with_results.get_results(test_path="tests/basic.yaml")
        assert len(results) == 2
        for r in results:
            assert r.test_path == "tests/basic.yaml"

    def test_get_results_filter_by_name(self, storage_with_results):
        results = storage_with_results.get_results(test_name="test_add")
        assert len(results) == 1
        assert results[0].test_name == "test_add"

    def test_get_results_filter_by_model(self, storage_with_results):
        results = storage_with_results.get_results(model="gpt-4o")
        assert len(results) == 1
        assert results[0].model == "gpt-4o"

    def test_get_results_filter_combined(self, storage_with_results):
        results = storage_with_results.get_results(
            test_path="tests/basic.yaml", model="claude-sonnet-4-5"
        )
        assert len(results) == 2

    def test_get_results_limit(self, storage_with_results):
        results = storage_with_results.get_results(limit=1)
        assert len(results) == 1

    def test_get_results_since(self, storage_with_results):
        # All results were just created, so a future date should return nothing
        results = storage_with_results.get_results(since="2099-01-01T00:00:00")
        assert len(results) == 0

    def test_get_results_empty(self, storage):
        results = storage.get_results()
        assert results == []

    def test_get_results_ordered_by_created_at_desc(self, storage):
        storage.save_result(test_path="t.yaml", test_name="first", passed=True)
        storage.save_result(test_path="t.yaml", test_name="second", passed=True)
        storage.save_result(test_path="t.yaml", test_name="third", passed=True)
        results = storage.get_results()
        # Most recent first
        assert results[0].test_name == "third"
        assert results[2].test_name == "first"


# ---------------------------------------------------------------------------
# Metrics & Analytics
# ---------------------------------------------------------------------------


class TestMetrics:
    def test_get_pass_rate(self, storage_with_results):
        rate = storage_with_results.get_pass_rate()
        assert rate["total"] == 3
        assert rate["passed"] == 2
        assert rate["failed"] == 1
        assert rate["pass_rate"] == pytest.approx(66.67, abs=0.1)
        assert rate["avg_score"] > 0
        assert rate["total_cost"] > 0
        assert rate["total_tokens"] > 0
        assert rate["period_days"] == 30

    def test_get_pass_rate_by_model(self, storage_with_results):
        rate = storage_with_results.get_pass_rate(model="claude-sonnet-4-5")
        assert rate["total"] == 2
        assert rate["passed"] == 1
        assert rate["failed"] == 1
        assert rate["pass_rate"] == 50.0

    def test_get_pass_rate_by_path(self, storage_with_results):
        rate = storage_with_results.get_pass_rate(test_path="tests/advanced.yaml")
        assert rate["total"] == 1
        assert rate["passed"] == 1
        assert rate["pass_rate"] == 100.0

    def test_get_pass_rate_empty(self, storage):
        rate = storage.get_pass_rate()
        assert rate["total"] == 0
        assert rate["passed"] == 0
        assert rate["pass_rate"] == 0
        assert rate["avg_score"] == 0

    def test_get_trends(self, storage_with_results):
        trends = storage_with_results.get_trends(days=30, group_by="day")
        # All results were saved today, so there should be 1 day entry
        assert len(trends) >= 1
        day = trends[0]
        assert "period" in day
        assert "total" in day
        assert "passed" in day
        assert "failed" in day
        assert "pass_rate" in day
        assert "avg_score" in day

    def test_get_trends_by_model(self, storage_with_results):
        trends = storage_with_results.get_trends(model="gpt-4o", days=30)
        total = sum(t["total"] for t in trends)
        assert total == 1

    def test_get_trends_group_by_hour(self, storage_with_results):
        trends = storage_with_results.get_trends(group_by="hour")
        assert len(trends) >= 1

    def test_get_trends_group_by_week(self, storage_with_results):
        trends = storage_with_results.get_trends(group_by="week")
        assert len(trends) >= 1

    def test_get_trends_empty(self, storage):
        trends = storage.get_trends()
        assert trends == []

    def test_get_model_comparison(self, storage_with_results):
        comparison = storage_with_results.get_model_comparison(days=30)
        assert len(comparison) == 2
        models = {c["model"] for c in comparison}
        assert models == {"claude-sonnet-4-5", "gpt-4o"}

        for c in comparison:
            assert "total" in c
            assert "passed" in c
            assert "failed" in c
            assert "pass_rate" in c
            assert "avg_score" in c
            assert "total_cost" in c

    def test_get_model_comparison_empty(self, storage):
        comparison = storage.get_model_comparison()
        assert comparison == []

    def test_get_failing_tests(self, storage):
        # Save multiple failures for the same test
        for _ in range(3):
            storage.save_result(
                test_path="tests/flaky.yaml",
                test_name="test_flaky",
                passed=False,
                error="flaky failure",
            )
        storage.save_result(
            test_path="tests/flaky.yaml",
            test_name="test_flaky",
            passed=True,
        )

        failing = storage.get_failing_tests(days=30, min_failures=2)
        assert len(failing) == 1
        assert failing[0]["test_name"] == "test_flaky"
        assert failing[0]["failures"] == 3
        assert failing[0]["total"] == 4
        assert failing[0]["failure_rate"] == 75.0
        assert failing[0]["last_error"] == "flaky failure"

    def test_get_failing_tests_below_threshold(self, storage):
        storage.save_result(
            test_path="tests/a.yaml",
            test_name="test_one_fail",
            passed=False,
            error="once",
        )
        # min_failures=2 default, so 1 failure should not appear
        failing = storage.get_failing_tests(days=30, min_failures=2)
        assert len(failing) == 0

    def test_get_failing_tests_empty(self, storage):
        failing = storage.get_failing_tests()
        assert failing == []


# ---------------------------------------------------------------------------
# Test Suite Management
# ---------------------------------------------------------------------------


class TestSuiteManagement:
    def test_save_suite_new(self, storage):
        questions = [{"id": "q1", "text": "Hello?"}]
        result = storage.save_suite(
            suite_id="s1",
            name="My Suite",
            questions=questions,
            description="A test suite",
        )
        assert result is not None
        assert result["id"] == "s1"
        assert result["name"] == "My Suite"
        assert result["version"] == 1
        assert result["description"] == "A test suite"
        assert len(result["questions"]) == 1

    def test_save_suite_deduplicates(self, storage):
        questions = [{"id": "q1", "text": "Hello?"}]
        r1 = storage.save_suite(suite_id="s1", name="Suite", questions=questions)
        r2 = storage.save_suite(suite_id="s1", name="Suite", questions=questions)
        assert r1["version"] == r2["version"]  # No change, same version

    def test_save_suite_increments_version_on_change(self, storage):
        q1 = [{"id": "q1", "text": "Hello?"}]
        q2 = [{"id": "q1", "text": "Hello?"}, {"id": "q2", "text": "World?"}]
        r1 = storage.save_suite(suite_id="s1", name="Suite", questions=q1)
        r2 = storage.save_suite(suite_id="s1", name="Suite", questions=q2)
        assert r2["version"] == r1["version"] + 1

    def test_save_suite_with_metadata(self, storage):
        result = storage.save_suite(
            suite_id="s1",
            name="Suite",
            questions=[{"id": "q1"}],
            metadata={"tags": ["core"], "priority": "high"},
        )
        assert result["metadata"]["tags"] == ["core"]
        assert result["metadata"]["priority"] == "high"

    def test_save_suite_with_environment(self, storage):
        result = storage.save_suite(
            suite_id="s1",
            name="Suite",
            questions=[{"id": "q1"}],
            environment_id="prod-env",
        )
        assert result["environment_id"] == "prod-env"

    def test_get_suite(self, storage_with_suite):
        suite = storage_with_suite.get_suite("suite-001")
        assert suite is not None
        assert suite["id"] == "suite-001"
        assert suite["name"] == "Math Tests"
        assert suite["version"] == 1
        assert len(suite["questions"]) == 2
        assert suite["metadata"]["tags"] == ["math", "basic"]

    def test_get_suite_not_found(self, storage):
        suite = storage.get_suite("nonexistent")
        assert suite is None

    def test_list_suites(self, storage):
        storage.save_suite(suite_id="s1", name="Suite A", questions=[{"id": "q1"}])
        storage.save_suite(suite_id="s2", name="Suite B", questions=[{"id": "q1"}, {"id": "q2"}])

        suites = storage.list_suites()
        assert len(suites) == 2
        # Check that question_count is populated
        ids = {s["id"] for s in suites}
        assert ids == {"s1", "s2"}
        for s in suites:
            assert "question_count" in s
            assert "created_at" in s
            assert "updated_at" in s

    def test_list_suites_limit(self, storage):
        for i in range(5):
            storage.save_suite(suite_id=f"s{i}", name=f"Suite {i}", questions=[{"id": f"q{i}"}])
        suites = storage.list_suites(limit=3)
        assert len(suites) == 3

    def test_list_suites_empty(self, storage):
        suites = storage.list_suites()
        assert suites == []


# ---------------------------------------------------------------------------
# Test Run Management
# ---------------------------------------------------------------------------


class TestRunManagement:
    def test_save_run(self, storage):
        now = datetime.now(timezone.utc).isoformat()
        # Should not raise
        storage.save_run(
            run_id="run-001",
            test_id="suite-001",
            test_version=1,
            model="claude-sonnet-4-5",
            provider="anthropic",
            started_at=now,
        )
        # Verify it was saved by checking directly
        with sqlite3.connect(storage.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM test_runs WHERE run_id = ?", ("run-001",)).fetchone()
        assert row is not None
        assert row["model"] == "claude-sonnet-4-5"
        assert row["runner_tool"] == "mcp-client"  # default

    def test_save_run_with_metadata(self, storage):
        now = datetime.now(timezone.utc).isoformat()
        storage.save_run(
            run_id="run-m",
            test_id="s1",
            test_version=1,
            model="m",
            provider="p",
            started_at=now,
            metadata={"trigger": "ci", "branch": "main"},
        )
        with sqlite3.connect(storage.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT metadata FROM test_runs WHERE run_id = ?", ("run-m",)
            ).fetchone()
        meta = json.loads(row["metadata"])
        assert meta["trigger"] == "ci"
        assert meta["branch"] == "main"

    def test_complete_run(self, storage):
        now = datetime.now(timezone.utc).isoformat()
        storage.save_run(
            run_id="run-c",
            test_id="s1",
            test_version=1,
            model="m",
            provider="p",
            started_at=now,
        )
        completed_at = datetime.now(timezone.utc).isoformat()
        storage.complete_run("run-c", completed_at)

        with sqlite3.connect(storage.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT completed_at FROM test_runs WHERE run_id = ?", ("run-c",)
            ).fetchone()
        assert row["completed_at"] == completed_at

    def test_save_question_result(self, storage):
        now = datetime.now(timezone.utc).isoformat()
        storage.save_run(
            run_id="run-qr",
            test_id="s1",
            test_version=1,
            model="m",
            provider="p",
            started_at=now,
        )
        storage.save_question_result(
            run_id="run-qr",
            question_id="q1",
            passed=True,
            score=0.95,
            answer="42",
            tool_uses=[{"tool": "calc"}],
            tool_results=[{"res": "42"}],
            tokens_input=100,
            tokens_output=20,
            tti_ms=150,
            duration_ms=300,
            evaluations=[{"eval": "exact", "passed": True}],
        )
        # Verify
        with sqlite3.connect(storage.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM question_results WHERE run_id = ? AND question_id = ?",
                ("run-qr", "q1"),
            ).fetchone()
        assert row is not None
        assert bool(row["passed"]) is True
        assert row["score"] == 0.95
        assert row["answer"] == "42"
        assert row["tti_ms"] == 150
        tool_uses = json.loads(row["tool_uses"])
        assert tool_uses[0]["tool"] == "calc"

    def test_save_question_result_minimal(self, storage):
        now = datetime.now(timezone.utc).isoformat()
        storage.save_run(
            run_id="run-min",
            test_id="s1",
            test_version=1,
            model="m",
            provider="p",
            started_at=now,
        )
        storage.save_question_result(
            run_id="run-min",
            question_id="q1",
            passed=False,
            error="timeout",
        )
        with sqlite3.connect(storage.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM question_results WHERE run_id = ?", ("run-min",)
            ).fetchone()
        assert row["error"] == "timeout"
        assert row["answer"] is None
        assert row["tool_uses"] is None

    def test_get_run(self, storage_with_run):
        run = storage_with_run.get_run("run-001")
        assert run is not None
        assert run["run_id"] == "run-001"
        assert run["test_id"] == "suite-001"
        assert run["model"] == "claude-sonnet-4-5"
        assert run["provider"] == "anthropic"
        assert run["runner_tool"] == "mcp-client"
        assert run["metadata"]["trigger"] == "manual"

        # Question results
        assert len(run["question_results"]) == 2
        q1 = next(q for q in run["question_results"] if q["question_id"] == "q1")
        assert q1["passed"] is True
        assert q1["answer"] == "4"
        assert len(q1["tool_uses"]) == 1
        assert q1["tti_ms"] == 200

        q2 = next(q for q in run["question_results"] if q["question_id"] == "q2")
        assert q2["passed"] is False
        assert q2["error"] == "Expected 6 got 7"

        # Summary
        summary = run["summary"]
        assert summary["total"] == 2
        assert summary["passed"] == 1
        assert summary["failed"] == 1
        assert summary["pass_rate"] == 50.0
        assert summary["total_tokens"] == 120  # (50+10) + (50+10)
        assert summary["total_duration_ms"] == 900  # 500 + 400

    def test_get_run_not_found(self, storage):
        run = storage.get_run("nonexistent")
        assert run is None

    def test_get_run_no_questions(self, storage):
        now = datetime.now(timezone.utc).isoformat()
        storage.save_run(
            run_id="run-empty",
            test_id="s1",
            test_version=1,
            model="m",
            provider="p",
            started_at=now,
        )
        run = storage.get_run("run-empty")
        assert run is not None
        assert run["question_results"] == []
        assert run["summary"]["total"] == 0
        assert run["summary"]["pass_rate"] == 0

    def test_list_runs(self, storage_with_run):
        runs = storage_with_run.list_runs()
        assert len(runs) == 1
        r = runs[0]
        assert r["run_id"] == "run-001"
        assert r["total_questions"] == 2
        assert r["passed_questions"] == 1
        assert r["pass_rate"] == 50.0

    def test_list_runs_filter_by_test_id(self, storage):
        now = datetime.now(timezone.utc).isoformat()
        storage.save_run(
            run_id="r1",
            test_id="suite-A",
            test_version=1,
            model="m",
            provider="p",
            started_at=now,
        )
        storage.save_run(
            run_id="r2",
            test_id="suite-B",
            test_version=1,
            model="m",
            provider="p",
            started_at=now,
        )
        runs = storage.list_runs(test_id="suite-A")
        assert len(runs) == 1
        assert runs[0]["test_id"] == "suite-A"

    def test_list_runs_filter_by_model(self, storage):
        now = datetime.now(timezone.utc).isoformat()
        storage.save_run(
            run_id="r1",
            test_id="s",
            test_version=1,
            model="claude-sonnet-4-5",
            provider="anthropic",
            started_at=now,
        )
        storage.save_run(
            run_id="r2",
            test_id="s",
            test_version=1,
            model="gpt-4o",
            provider="openai",
            started_at=now,
        )
        runs = storage.list_runs(model="gpt-4o")
        assert len(runs) == 1
        assert runs[0]["model"] == "gpt-4o"

    def test_list_runs_limit(self, storage):
        now = datetime.now(timezone.utc).isoformat()
        for i in range(5):
            storage.save_run(
                run_id=f"r{i}",
                test_id="s",
                test_version=1,
                model="m",
                provider="p",
                started_at=now,
            )
        runs = storage.list_runs(limit=2)
        assert len(runs) == 2

    def test_list_runs_empty(self, storage):
        runs = storage.list_runs()
        assert runs == []


# ---------------------------------------------------------------------------
# Content hashing
# ---------------------------------------------------------------------------


class TestContentHashing:
    def test_hash_deterministic(self, storage):
        h1 = storage._hash_content("hello world")
        h2 = storage._hash_content("hello world")
        assert h1 == h2

    def test_hash_different_content(self, storage):
        h1 = storage._hash_content("hello")
        h2 = storage._hash_content("world")
        assert h1 != h2

    def test_hash_length(self, storage):
        h = storage._hash_content("test")
        assert len(h) == 16  # SHA256 truncated to 16 chars
