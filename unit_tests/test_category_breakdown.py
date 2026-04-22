"""
Unit tests for per-category-per-model breakdown — AC 8.

Tests category tagging on TestCase and category-level aggregation
in the comparison runner.

Story: SC-104612 — Trial Benchmark
"""

import csv
import io

import pytest

from testmcpy.src.comparison_runner import ComparisonResult, ComparisonRunner, ModelConfig
from testmcpy.src.test_runner import TestCase, TestResult


def _make_result(name, passed, score, cost, duration):
    return TestResult(test_name=name, passed=passed, score=score, cost=cost, duration=duration)


@pytest.fixture
def categorized_test_cases():
    """Test cases tagged with categories."""
    return [
        TestCase(
            name="test_list_dashboards",
            prompt="List dashboards",
            evaluators=[],
            category="dashboard_mgmt",
        ),
        TestCase(
            name="test_filter_dashboards",
            prompt="Filter dashboards by owner",
            evaluators=[],
            category="dashboard_mgmt",
        ),
        TestCase(
            name="test_run_sql",
            prompt="Run a SQL query",
            evaluators=[],
            category="sql_query",
        ),
        TestCase(
            name="test_create_chart",
            prompt="Create a bar chart",
            evaluators=[],
            category="chart_creation",
        ),
    ]


@pytest.fixture
def categorized_comparison_results():
    model_a = ModelConfig(provider="anthropic", model="claude-sonnet-4-6")
    model_b = ModelConfig(provider="openai", model="gpt-5.4")

    # Model A: great at dashboards, bad at SQL
    results_a = [
        _make_result("test_list_dashboards", True, 1.0, 0.005, 2.0),
        _make_result("test_filter_dashboards", True, 0.9, 0.004, 2.5),
        _make_result("test_run_sql", False, 0.1, 0.006, 5.0),
        _make_result("test_create_chart", True, 0.8, 0.007, 3.0),
    ]

    # Model B: bad at dashboards, great at SQL
    results_b = [
        _make_result("test_list_dashboards", False, 0.3, 0.003, 1.5),
        _make_result("test_filter_dashboards", False, 0.2, 0.002, 2.0),
        _make_result("test_run_sql", True, 1.0, 0.004, 3.0),
        _make_result("test_create_chart", True, 0.9, 0.005, 2.5),
    ]

    cr_a = ComparisonResult(
        model=model_a,
        results=results_a,
        total_tests=4,
        passed=3,
        failed=1,
        total_cost=0.022,
        total_tokens=400,
        total_duration=12.5,
        avg_score=0.7,
    )
    cr_b = ComparisonResult(
        model=model_b,
        results=results_b,
        total_tests=4,
        passed=2,
        failed=2,
        total_cost=0.014,
        total_tokens=400,
        total_duration=9.0,
        avg_score=0.6,
    )
    return [cr_a, cr_b]


class TestCategoryOnTestCase:
    """Test category field on TestCase."""

    def test_category_field(self):
        tc = TestCase(
            name="test1",
            prompt="test",
            evaluators=[],
            category="dashboard_mgmt",
        )
        assert tc.category == "dashboard_mgmt"

    def test_category_default_none(self):
        tc = TestCase(name="test1", prompt="test", evaluators=[])
        assert tc.category is None

    def test_category_from_dict(self):
        data = {
            "name": "test1",
            "prompt": "test",
            "evaluators": [],
            "category": "sql_query",
        }
        tc = TestCase.from_dict(data)
        assert tc.category == "sql_query"

    def test_category_from_dict_missing(self):
        data = {"name": "test1", "prompt": "test", "evaluators": []}
        tc = TestCase.from_dict(data)
        assert tc.category is None


class TestCategoryBreakdown:
    """Test the per-category-per-model breakdown."""

    def test_breakdown_has_all_categories(
        self, categorized_comparison_results, categorized_test_cases
    ):
        runner = ComparisonRunner(models=[], mcp_url=None)
        breakdown = runner.generate_category_breakdown(
            categorized_comparison_results, categorized_test_cases
        )
        assert "dashboard_mgmt" in breakdown
        assert "sql_query" in breakdown
        assert "chart_creation" in breakdown

    def test_breakdown_has_both_models(
        self, categorized_comparison_results, categorized_test_cases
    ):
        runner = ComparisonRunner(models=[], mcp_url=None)
        breakdown = runner.generate_category_breakdown(
            categorized_comparison_results, categorized_test_cases
        )
        dashboard = breakdown["dashboard_mgmt"]
        assert "anthropic:claude-sonnet-4-6" in dashboard
        assert "openai:gpt-5.4" in dashboard

    def test_claude_better_at_dashboards(
        self, categorized_comparison_results, categorized_test_cases
    ):
        """Claude should score higher on dashboard category."""
        runner = ComparisonRunner(models=[], mcp_url=None)
        breakdown = runner.generate_category_breakdown(
            categorized_comparison_results, categorized_test_cases
        )
        claude_dash = breakdown["dashboard_mgmt"]["anthropic:claude-sonnet-4-6"]
        gpt_dash = breakdown["dashboard_mgmt"]["openai:gpt-5.4"]
        assert claude_dash["avg_score"] > gpt_dash["avg_score"]

    def test_gpt_better_at_sql(self, categorized_comparison_results, categorized_test_cases):
        """GPT should score higher on SQL category."""
        runner = ComparisonRunner(models=[], mcp_url=None)
        breakdown = runner.generate_category_breakdown(
            categorized_comparison_results, categorized_test_cases
        )
        claude_sql = breakdown["sql_query"]["anthropic:claude-sonnet-4-6"]
        gpt_sql = breakdown["sql_query"]["openai:gpt-5.4"]
        assert gpt_sql["avg_score"] > claude_sql["avg_score"]

    def test_pass_rate_calculated(self, categorized_comparison_results, categorized_test_cases):
        runner = ComparisonRunner(models=[], mcp_url=None)
        breakdown = runner.generate_category_breakdown(
            categorized_comparison_results, categorized_test_cases
        )
        # Claude: 2/2 dashboard tests pass
        claude_dash = breakdown["dashboard_mgmt"]["anthropic:claude-sonnet-4-6"]
        assert claude_dash["pass_rate"] == 1.0
        # GPT: 0/2 dashboard tests pass
        gpt_dash = breakdown["dashboard_mgmt"]["openai:gpt-5.4"]
        assert gpt_dash["pass_rate"] == 0.0


class TestCategoryBreakdownFormat:
    """Test markdown formatting of category breakdown."""

    def test_format_has_categories(self, categorized_comparison_results, categorized_test_cases):
        runner = ComparisonRunner(models=[], mcp_url=None)
        breakdown = runner.generate_category_breakdown(
            categorized_comparison_results, categorized_test_cases
        )
        report = runner.format_category_breakdown(breakdown)
        assert "dashboard_mgmt" in report
        assert "sql_query" in report
        assert "chart_creation" in report

    def test_format_has_model_scores(self, categorized_comparison_results, categorized_test_cases):
        runner = ComparisonRunner(models=[], mcp_url=None)
        breakdown = runner.generate_category_breakdown(
            categorized_comparison_results, categorized_test_cases
        )
        report = runner.format_category_breakdown(breakdown)
        assert "Pass Rate" in report
        assert "Avg Score" in report
        assert "Avg Cost" in report

    def test_format_empty(self):
        runner = ComparisonRunner(models=[], mcp_url=None)
        report = runner.format_category_breakdown({})
        assert "No category data" in report


class TestCSVWithCategories:
    """Test that CSV export includes category column."""

    def test_csv_has_category_column(self, categorized_comparison_results, categorized_test_cases):
        runner = ComparisonRunner(models=[], mcp_url=None)
        csv_str = runner.to_csv(categorized_comparison_results, categorized_test_cases)
        reader = csv.DictReader(io.StringIO(csv_str))
        rows = list(reader)
        assert "category" in rows[0]

    def test_csv_category_values(self, categorized_comparison_results, categorized_test_cases):
        runner = ComparisonRunner(models=[], mcp_url=None)
        csv_str = runner.to_csv(categorized_comparison_results, categorized_test_cases)
        reader = csv.DictReader(io.StringIO(csv_str))
        categories = {r["category"] for r in reader}
        assert "dashboard_mgmt" in categories
        assert "sql_query" in categories
        assert "chart_creation" in categories
