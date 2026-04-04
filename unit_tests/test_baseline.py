"""Tests for testmcpy.src.baseline."""

import json

import pytest

from testmcpy.src.baseline import BaselineStore, RegressionReport
from testmcpy.src.test_runner import TestResult


def _make_result(name, passed=True, score=1.0, error=None, tool_calls=None):
    return TestResult(
        test_name=name,
        passed=passed,
        score=score,
        duration=1.0,
        error=error,
        tool_calls=tool_calls or [],
    )


class TestSaveBaseline:
    def test_save_creates_json_file(self, tmp_path):
        store = BaselineStore(str(tmp_path))
        results = [_make_result("t1"), _make_result("t2", passed=False, score=0.0, error="fail")]
        path = store.save_baseline("v1", results, model="gpt-4o", provider="openai")
        assert path.exists()
        assert path.suffix == ".json"
        data = json.loads(path.read_text())
        assert data["model"] == "gpt-4o"
        assert data["provider"] == "openai"
        assert len(data["entries"]) == 2

    def test_save_includes_fingerprint_for_failures(self, tmp_path):
        store = BaselineStore(str(tmp_path))
        results = [_make_result("t1", passed=False, score=0.0, error="timeout")]
        store.save_baseline("v1", results, model="m", provider="p")
        data = json.loads((tmp_path / "v1.json").read_text())
        entry = data["entries"][0]
        assert entry["failure_fingerprint"] is not None
        assert len(entry["failure_fingerprint"]) == 12

    def test_save_no_fingerprint_for_passes(self, tmp_path):
        store = BaselineStore(str(tmp_path))
        results = [_make_result("t1", passed=True)]
        store.save_baseline("v1", results, model="m", provider="p")
        data = json.loads((tmp_path / "v1.json").read_text())
        assert data["entries"][0]["failure_fingerprint"] is None


class TestLoadBaseline:
    def test_load_reads_back_correctly(self, tmp_path):
        store = BaselineStore(str(tmp_path))
        results = [_make_result("t1", score=0.9), _make_result("t2", passed=False, score=0.3)]
        store.save_baseline("b1", results, model="gpt-4o", provider="openai")
        entries = store.load_baseline("b1")
        assert len(entries) == 2
        assert entries[0].test_name == "t1"
        assert entries[0].passed is True
        assert entries[0].score == 0.9
        assert entries[1].test_name == "t2"
        assert entries[1].passed is False

    def test_load_missing_raises(self, tmp_path):
        store = BaselineStore(str(tmp_path))
        with pytest.raises(FileNotFoundError, match="not found"):
            store.load_baseline("nonexistent")


class TestListBaselines:
    def test_list_returns_metadata(self, tmp_path):
        store = BaselineStore(str(tmp_path))
        store.save_baseline("alpha", [_make_result("t1")], model="m1", provider="p1")
        store.save_baseline(
            "beta",
            [_make_result("t1"), _make_result("t2", passed=False, score=0.0)],
            model="m2",
            provider="p2",
        )
        baselines = store.list_baselines()
        assert len(baselines) == 2
        names = [b["name"] for b in baselines]
        assert "alpha" in names
        assert "beta" in names
        beta = next(b for b in baselines if b["name"] == "beta")
        assert beta["tests"] == 2
        assert beta["passed"] == 1
        assert beta["failed"] == 1

    def test_list_empty_dir(self, tmp_path):
        store = BaselineStore(str(tmp_path))
        assert store.list_baselines() == []


class TestCompare:
    def test_detects_new_failure(self, tmp_path):
        store = BaselineStore(str(tmp_path))
        # Baseline: t1 passes
        store.save_baseline("b", [_make_result("t1", passed=True)], model="m", provider="p")
        # Current: t1 fails
        current = [_make_result("t1", passed=False, score=0.0, error="broke")]
        report = store.compare("b", current)
        assert len(report.new_failures) == 1
        assert report.new_failures[0]["test_name"] == "t1"

    def test_detects_improvement(self, tmp_path):
        store = BaselineStore(str(tmp_path))
        # Baseline: t1 fails
        store.save_baseline(
            "b", [_make_result("t1", passed=False, score=0.0, error="err")], model="m", provider="p"
        )
        # Current: t1 passes
        current = [_make_result("t1", passed=True, score=1.0)]
        report = store.compare("b", current)
        assert len(report.new_passes) == 1
        assert report.new_passes[0]["test_name"] == "t1"

    def test_stable_passes(self, tmp_path):
        store = BaselineStore(str(tmp_path))
        store.save_baseline(
            "b", [_make_result("t1", passed=True, score=1.0)], model="m", provider="p"
        )
        current = [_make_result("t1", passed=True, score=1.0)]
        report = store.compare("b", current)
        assert len(report.stable_passes) == 1
        assert len(report.new_failures) == 0

    def test_score_change_detected(self, tmp_path):
        store = BaselineStore(str(tmp_path))
        store.save_baseline(
            "b", [_make_result("t1", passed=True, score=0.5)], model="m", provider="p"
        )
        current = [_make_result("t1", passed=True, score=0.9)]
        report = store.compare("b", current)
        assert len(report.score_changes) == 1
        assert report.score_changes[0]["direction"] == "improved"

    def test_new_test_not_in_baseline(self, tmp_path):
        store = BaselineStore(str(tmp_path))
        store.save_baseline("b", [_make_result("t1")], model="m", provider="p")
        current = [_make_result("t1"), _make_result("t_new", passed=True)]
        report = store.compare("b", current)
        assert len(report.new_passes) == 1
        assert report.new_passes[0]["note"] == "new test (not in baseline)"


class TestFingerprint:
    def test_consistent_hash(self, tmp_path):
        store = BaselineStore(str(tmp_path))
        r = _make_result("test1", passed=False, error="timeout")
        fp1 = store._fingerprint(r)
        fp2 = store._fingerprint(r)
        assert fp1 == fp2
        assert len(fp1) == 12

    def test_different_errors_different_hash(self, tmp_path):
        store = BaselineStore(str(tmp_path))
        r1 = _make_result("test1", passed=False, error="timeout")
        r2 = _make_result("test1", passed=False, error="connection refused")
        assert store._fingerprint(r1) != store._fingerprint(r2)


class TestGenerateRegressionReport:
    def test_report_markdown(self, tmp_path):
        store = BaselineStore(str(tmp_path))
        report = RegressionReport(
            new_failures=[
                {
                    "test_name": "t1",
                    "baseline_score": 1.0,
                    "current_score": 0.0,
                    "fingerprint": "abc123",
                    "error": "timeout",
                }
            ],
            new_passes=[{"test_name": "t2", "baseline_score": 0.0, "current_score": 1.0}],
            stable_failures=[],
            stable_passes=[{"test_name": "t3", "baseline_score": 1.0, "current_score": 1.0}],
            score_changes=[],
        )
        md = store.generate_regression_report(report)
        assert "# Regression Report" in md
        assert "## New Failures (1)" in md
        assert "t1" in md
        assert "## Improvements (1)" in md
        assert "t2" in md
        assert "## Stable Passes (1)" in md
        assert "No significant score changes." in md
