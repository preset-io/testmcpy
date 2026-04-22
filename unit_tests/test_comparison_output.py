"""
Unit tests for enhanced comparison output — AC 5.

Tests cost columns, performance/cost ratio, avg duration,
and CSV export in the comparison runner.

Story: SC-104612 — Trial Benchmark
"""

import csv
import io

import pytest

from testmcpy.src.comparison_runner import ComparisonResult, ComparisonRunner, ModelConfig
from testmcpy.src.test_runner import TestResult


def _make_result(name: str, passed: bool, score: float, cost: float, duration: float):
    return TestResult(
        test_name=name,
        passed=passed,
        score=score,
        cost=cost,
        duration=duration,
        token_usage={"total": 100, "prompt": 80, "completion": 20},
    )


@pytest.fixture
def comparison_results():
    """Two models with different performance profiles."""
    model_a = ModelConfig(provider="anthropic", model="claude-sonnet-4-6")
    model_b = ModelConfig(provider="openai", model="gpt-5.4")

    results_a = [
        _make_result("test_list_dashboards", True, 1.0, 0.005, 2.0),
        _make_result("test_list_charts", True, 0.9, 0.004, 3.0),
        _make_result("test_create_chart", False, 0.2, 0.008, 5.0),
    ]

    results_b = [
        _make_result("test_list_dashboards", True, 1.0, 0.003, 1.5),
        _make_result("test_list_charts", False, 0.3, 0.002, 2.5),
        _make_result("test_create_chart", True, 0.85, 0.006, 4.0),
    ]

    cr_a = ComparisonResult(
        model=model_a,
        results=results_a,
        total_tests=3,
        passed=2,
        failed=1,
        total_cost=0.017,
        total_tokens=300,
        total_duration=10.0,
        avg_score=0.7,
    )
    cr_b = ComparisonResult(
        model=model_b,
        results=results_b,
        total_tests=3,
        passed=2,
        failed=1,
        total_cost=0.011,
        total_tokens=300,
        total_duration=8.0,
        avg_score=0.717,
    )
    return [cr_a, cr_b]


class TestEnhancedComparisonReport:
    """Test the enhanced markdown comparison report."""

    def test_report_has_avg_cost_per_test(self, comparison_results):
        runner = ComparisonRunner(models=[], mcp_url=None)
        report = runner.generate_comparison_report(comparison_results)
        assert "Avg Cost" in report

    def test_report_has_avg_time_per_test(self, comparison_results):
        runner = ComparisonRunner(models=[], mcp_url=None)
        report = runner.generate_comparison_report(comparison_results)
        assert "Avg Time" in report

    def test_report_has_score_cost_ratio(self, comparison_results):
        runner = ComparisonRunner(models=[], mcp_url=None)
        report = runner.generate_comparison_report(comparison_results)
        assert "Score/Cost" in report

    def test_avg_cost_per_test_calculated(self, comparison_results):
        runner = ComparisonRunner(models=[], mcp_url=None)
        report = runner.generate_comparison_report(comparison_results)
        # Model A: 0.017 / 3 tests
        assert "$0.005" in report or "$0.006" in report

    def test_score_cost_values_present(self, comparison_results):
        runner = ComparisonRunner(models=[], mcp_url=None)
        report = runner.generate_comparison_report(comparison_results)
        lines = report.split("\n")
        score_cost_line = [line for line in lines if "Score/Cost" in line]
        assert len(score_cost_line) == 1
        assert "**" in score_cost_line[0]


class TestCSVExport:
    """Test CSV export matches Max's dataset spec."""

    def test_csv_header(self, comparison_results):
        runner = ComparisonRunner(models=[], mcp_url=None)
        csv_str = runner.to_csv(comparison_results)
        lines = csv_str.strip().split("\n")
        header = lines[0]
        assert "suite_id" in header
        assert "cost_usd" in header
        assert "duration" in header
        assert "success" in header
        assert "score" in header

    def test_csv_row_count(self, comparison_results):
        runner = ComparisonRunner(models=[], mcp_url=None)
        csv_str = runner.to_csv(comparison_results)
        lines = csv_str.strip().split("\n")
        # Header + 3 tests * 2 models = 7 lines
        assert len(lines) == 7

    def test_csv_parseable(self, comparison_results):
        runner = ComparisonRunner(models=[], mcp_url=None)
        csv_str = runner.to_csv(comparison_results)
        reader = csv.DictReader(io.StringIO(csv_str))
        rows = list(reader)
        assert len(rows) == 6

    def test_csv_contains_model_info(self, comparison_results):
        runner = ComparisonRunner(models=[], mcp_url=None)
        csv_str = runner.to_csv(comparison_results)
        reader = csv.DictReader(io.StringIO(csv_str))
        rows = list(reader)
        models = {r["model"] for r in rows}
        assert "claude-sonnet-4-6" in models
        assert "gpt-5.4" in models

    def test_csv_has_cost_per_row(self, comparison_results):
        runner = ComparisonRunner(models=[], mcp_url=None)
        csv_str = runner.to_csv(comparison_results)
        reader = csv.DictReader(io.StringIO(csv_str))
        for row in reader:
            cost = float(row["cost_usd"])
            assert cost >= 0

    def test_csv_has_duration(self, comparison_results):
        runner = ComparisonRunner(models=[], mcp_url=None)
        csv_str = runner.to_csv(comparison_results)
        reader = csv.DictReader(io.StringIO(csv_str))
        for row in reader:
            duration = float(row["duration"])
            assert duration > 0

    def test_csv_has_success_boolean(self, comparison_results):
        runner = ComparisonRunner(models=[], mcp_url=None)
        csv_str = runner.to_csv(comparison_results)
        reader = csv.DictReader(io.StringIO(csv_str))
        for row in reader:
            assert row["success"] in ("true", "false")

    def test_csv_empty_results(self):
        runner = ComparisonRunner(models=[], mcp_url=None)
        csv_str = runner.to_csv([])
        assert csv_str.startswith("suite_id")
        lines = csv_str.strip().split("\n")
        assert len(lines) == 1  # Just header
