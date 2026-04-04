"""Tests for testmcpy.src.comparison_runner."""

from unittest.mock import MagicMock

import pytest

from testmcpy.src.comparison_runner import (
    ComparisonResult,
    ComparisonRunner,
    ModelConfig,
    _format_tokens,
)


class TestModelConfig:
    def test_from_string_basic(self):
        config = ModelConfig.from_string("anthropic:claude-sonnet-4-20250514")
        assert config.provider == "anthropic"
        assert config.model == "claude-sonnet-4-20250514"
        assert config.name == "anthropic:claude-sonnet-4-20250514"

    def test_from_string_openai(self):
        config = ModelConfig.from_string("openai:gpt-4o")
        assert config.provider == "openai"
        assert config.model == "gpt-4o"

    def test_from_string_with_slash(self):
        config = ModelConfig.from_string("openrouter:meta-llama/llama-3.1-70b")
        assert config.provider == "openrouter"
        assert config.model == "meta-llama/llama-3.1-70b"

    def test_from_string_strips_whitespace(self):
        config = ModelConfig.from_string("  openai : gpt-4o  ")
        assert config.provider == "openai"
        assert config.model == "gpt-4o"

    def test_from_string_invalid_no_colon(self):
        with pytest.raises(ValueError, match="Invalid model spec"):
            ModelConfig.from_string("just-a-model")

    def test_custom_name(self):
        config = ModelConfig(provider="openai", model="gpt-4o", name="GPT4")
        assert config.name == "GPT4"

    def test_auto_name(self):
        config = ModelConfig(provider="openai", model="gpt-4o")
        assert config.name == "openai:gpt-4o"


class TestComparisonResultToDict:
    def test_to_dict_structure(self):
        model = ModelConfig(provider="anthropic", model="claude-sonnet-4-20250514")
        # Create a mock TestResult with to_dict method
        mock_result = MagicMock()
        mock_result.to_dict.return_value = {"test_name": "t1", "passed": True}

        cr = ComparisonResult(
            model=model,
            results=[mock_result],
            total_tests=1,
            passed=1,
            failed=0,
            total_cost=0.05,
            total_tokens=1500,
            total_duration=3.2,
            avg_score=1.0,
        )
        d = cr.to_dict()
        assert d["model"]["provider"] == "anthropic"
        assert d["model"]["model"] == "claude-sonnet-4-20250514"
        assert d["total_tests"] == 1
        assert d["passed"] == 1
        assert d["total_cost"] == 0.05
        assert d["avg_score"] == 1.0
        assert len(d["results"]) == 1


class TestFormatTokens:
    def test_small(self):
        assert _format_tokens(500) == "500"

    def test_thousands(self):
        assert _format_tokens(5000) == "5K"

    def test_millions(self):
        assert _format_tokens(2000000) == "2.0M"

    def test_zero(self):
        assert _format_tokens(0) == "0"


class TestGenerateComparisonReport:
    def test_empty_results(self):
        runner = ComparisonRunner(models=[], mcp_url=None)
        report = runner.generate_comparison_report([])
        assert "No results to compare." in report

    def test_report_with_results(self):
        model_a = ModelConfig(provider="openai", model="gpt-4o")
        model_b = ModelConfig(provider="anthropic", model="claude-sonnet-4-20250514")

        # Mock TestResult-like objects
        tr_a1 = MagicMock()
        tr_a1.test_name = "test_list"
        tr_a1.passed = True
        tr_a1.duration = 1.5

        tr_b1 = MagicMock()
        tr_b1.test_name = "test_list"
        tr_b1.passed = False
        tr_b1.duration = 2.0

        cr_a = ComparisonResult(
            model=model_a,
            results=[tr_a1],
            total_tests=1,
            passed=1,
            failed=0,
            total_cost=0.02,
            total_tokens=1000,
            total_duration=1.5,
            avg_score=1.0,
        )
        cr_b = ComparisonResult(
            model=model_b,
            results=[tr_b1],
            total_tests=1,
            passed=0,
            failed=1,
            total_cost=0.03,
            total_tokens=2000,
            total_duration=2.0,
            avg_score=0.0,
        )

        runner = ComparisonRunner(models=[model_a, model_b], mcp_url=None)
        report = runner.generate_comparison_report([cr_a, cr_b])
        assert "# Model Comparison Report" in report
        assert "openai:gpt-4o" in report
        assert "PASS" in report
        assert "FAIL" in report
        assert "**Score**" in report
        assert "**Cost**" in report
        assert "**Tokens**" in report
        assert "**Duration**" in report
