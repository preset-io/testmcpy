"""Tests for testmcpy.src.report_generator."""

import json

import pytest

from testmcpy.src.report_generator import EvalSuiteReport, ReportGenerator, _categorize_failure


class TestEvalSuiteReportDefaults:
    def test_defaults(self):
        report = EvalSuiteReport()
        assert report.title == ""
        assert report.workspace_hash == ""
        assert report.run_by == "testmcpy (automated)"
        assert report.suite_results == {}
        assert report.total_tool_calls == 0
        assert report.total_tokens == 0
        assert report.total_cost == 0.0
        assert report.chatbot_requests == 0
        assert report.mcp_direct_tool_calls == 0


class TestAddSuiteResults:
    def test_empty_results(self):
        gen = ReportGenerator()
        gen.add_suite_results("suite1", [])
        data = gen.report.suite_results["suite1"]
        assert data["tests"] == 0
        assert data["score"] == "0%"

    def test_all_passing(self):
        gen = ReportGenerator()
        results = [
            {"passed": True, "test_name": "t1"},
            {"passed": True, "test_name": "t2"},
        ]
        gen.add_suite_results("00_basic", results)
        data = gen.report.suite_results["00_basic"]
        assert data["tests"] == 2
        assert data["pass"] == 2
        assert data["fail"] == 0
        assert data["score"] == "100%"

    def test_mixed_results_with_cost(self):
        gen = ReportGenerator()
        results = [
            {
                "passed": True,
                "test_name": "t1",
                "tool_calls": [{"name": "foo"}],
                "token_usage": {"total": 1500},
                "cost": 0.05,
            },
            {
                "passed": False,
                "test_name": "t2",
                "reason": "assertion failed",
                "cost": 0.03,
            },
        ]
        gen.add_suite_results("00_mcp", results)
        data = gen.report.suite_results["00_mcp"]
        assert data["pass"] == 1
        assert data["fail"] == 1
        assert data["score"] == "50%"
        assert data["tokens"] == 1500
        assert gen.report.total_cost == pytest.approx(0.08)

    def test_skipped_excluded_from_score(self):
        gen = ReportGenerator()
        results = [
            {"passed": True, "test_name": "t1"},
            {"passed": False, "skipped": True, "test_name": "t2"},
        ]
        gen.add_suite_results("suite", results)
        data = gen.report.suite_results["suite"]
        assert data["skip"] == 1
        assert data["score"] == "100%"


class TestSuiteCategorization:
    def test_c00_is_chatbot(self):
        gen = ReportGenerator()
        gen.add_suite_results("C00_chat", [{"passed": True, "test_name": "t1"}])
        assert gen.report.chatbot_requests == 1
        assert gen.report.mcp_direct_tool_calls == 0

    def test_d01_is_chatbot(self):
        gen = ReportGenerator()
        gen.add_suite_results("D01_demo", [{"passed": True, "test_name": "t1"}])
        assert gen.report.chatbot_requests == 1

    def test_00_is_mcp_direct(self):
        gen = ReportGenerator()
        gen.add_suite_results(
            "00_basic",
            [
                {
                    "passed": True,
                    "test_name": "t1",
                    "tool_calls": [{"name": "x"}],
                    "token_usage": {"total": 100},
                    "cost": 0.01,
                }
            ],
        )
        assert gen.report.mcp_direct_tool_calls == 1
        assert gen.report.mcp_direct_tokens == 100

    def test_chatbot_keyword_categorization(self):
        gen = ReportGenerator()
        gen.add_suite_results("my_chatbot_tests", [{"passed": True, "test_name": "t1"}])
        assert gen.report.chatbot_requests == 1


class TestCostAccumulationAcrossSuites:
    def test_cost_accumulates(self):
        gen = ReportGenerator()
        gen.add_suite_results("s1", [{"passed": True, "test_name": "t1", "cost": 0.10}])
        gen.add_suite_results("s2", [{"passed": True, "test_name": "t2", "cost": 0.20}])
        assert gen.report.total_cost == pytest.approx(0.30)


class TestFormatTokens:
    def test_zero(self):
        gen = ReportGenerator()
        assert gen._format_tokens(0) == "0"

    def test_under_thousand(self):
        gen = ReportGenerator()
        assert gen._format_tokens(500) == "500"

    def test_thousands(self):
        gen = ReportGenerator()
        assert gen._format_tokens(5000) == "5K"

    def test_half_million(self):
        gen = ReportGenerator()
        assert gen._format_tokens(500000) == "500K"

    def test_millions(self):
        gen = ReportGenerator()
        assert gen._format_tokens(5000000) == "5.0M"


class TestGenerateMarkdown:
    def test_contains_all_sections(self):
        gen = ReportGenerator()
        gen.configure(title="Test Run")
        gen.add_suite_results(
            "00_basic",
            [
                {"passed": True, "test_name": "t1"},
                {"passed": False, "test_name": "t2", "reason": "timeout occurred"},
            ],
        )
        md = gen.generate_markdown()
        assert "# Eval Suite Results" in md
        assert "## Grand Totals" in md
        assert "## 00_basic — Eval Results" in md
        assert "## Cost and Token Summary" in md
        assert "## Failures Analysis" in md
        assert "Timeout" in md

    def test_no_failures_message(self):
        gen = ReportGenerator()
        gen.add_suite_results("s1", [{"passed": True, "test_name": "t1"}])
        md = gen.generate_markdown()
        assert "No failures detected." in md


class TestSave:
    def test_save_markdown(self, tmp_path):
        gen = ReportGenerator()
        gen.add_suite_results("s1", [{"passed": True, "test_name": "t1"}])
        out = gen.save(str(tmp_path / "report.md"))
        assert out.exists()
        content = out.read_text()
        assert "# Eval Suite Results" in content

    def test_save_json(self, tmp_path):
        gen = ReportGenerator()
        gen.add_suite_results("s1", [{"passed": True, "test_name": "t1"}])
        out = gen.save(str(tmp_path / "report.json"))
        assert out.exists()
        data = json.loads(out.read_text())
        assert "suite_results" in data
        assert "s1" in data["suite_results"]


class TestCategorizeFailure:
    def test_timeout(self):
        assert _categorize_failure("Request timed out") == "Timeout"

    def test_rate_limit(self):
        assert _categorize_failure("Rate limit exceeded 429") == "Rate Limiting"

    def test_auth(self):
        assert _categorize_failure("Unauthorized 401") == "Authentication Error"

    def test_tool_not_called(self):
        assert _categorize_failure("tool was not called") == "Tool Not Called"

    def test_assertion(self):
        assert _categorize_failure("expected value mismatch") == "Assertion Failure"

    def test_other(self):
        assert _categorize_failure("something weird") == "Other"
