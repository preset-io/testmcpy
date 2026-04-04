"""Tests for testmcpy.src.coverage_analyzer."""

import yaml

from testmcpy.src.coverage_analyzer import CoverageAnalyzer, _categorize_test


class TestCategorizeTest:
    def test_happy_path_default(self):
        assert _categorize_test("test_list_charts") == "happy_path"

    def test_error_case(self):
        assert _categorize_test("test_invalid_input") == "error_case"
        assert _categorize_test("test_not_found") == "error_case"

    def test_edge_case(self):
        assert _categorize_test("test_unicode_names") == "edge_case"
        assert _categorize_test("test_empty_results") == "edge_case"
        assert _categorize_test("test_large_payload") == "edge_case"

    def test_security(self):
        assert _categorize_test("test_sql_injection") == "security"
        assert _categorize_test("test_xss_attack") == "security"
        assert _categorize_test("test_rls_filter") == "security"

    def test_security_takes_priority_over_error(self):
        # "auth" matches security keywords, should be security not error
        assert _categorize_test("test_auth_bypass") == "security"


class TestScanTestFiles:
    def test_scan_yaml_with_tool_evaluator(self, tmp_path):
        test_file = tmp_path / "test_basic.yaml"
        test_file.write_text(
            yaml.dump(
                {
                    "tests": [
                        {
                            "name": "test_list_charts",
                            "prompt": "List charts",
                            "evaluators": [
                                {
                                    "name": "was_mcp_tool_called",
                                    "args": {"tool_name": "list_charts"},
                                }
                            ],
                        }
                    ]
                }
            )
        )
        analyzer = CoverageAnalyzer()
        analyzer.scan_test_files(str(tmp_path))
        assert "list_charts" in analyzer.tool_tests
        assert len(analyzer.tool_tests["list_charts"]) == 1
        assert analyzer.test_files == [str(test_file)]

    def test_scan_with_expected_tools(self, tmp_path):
        test_file = tmp_path / "test_exp.yaml"
        test_file.write_text(
            yaml.dump(
                {
                    "tests": [
                        {
                            "name": "test_create",
                            "prompt": "Create chart",
                            "evaluators": [],
                            "expected_tools": ["generate_chart", "list_datasets"],
                        }
                    ]
                }
            )
        )
        analyzer = CoverageAnalyzer()
        analyzer.scan_test_files(str(tmp_path))
        assert "generate_chart" in analyzer.tool_tests
        assert "list_datasets" in analyzer.tool_tests

    def test_scan_with_metadata_expected_tool(self, tmp_path):
        test_file = tmp_path / "test_meta.yaml"
        test_file.write_text(
            yaml.dump(
                {
                    "tests": [
                        {
                            "name": "test_foo",
                            "prompt": "Do foo",
                            "evaluators": [],
                            "metadata": {"expected_tool": "execute_sql"},
                        }
                    ]
                }
            )
        )
        analyzer = CoverageAnalyzer()
        analyzer.scan_test_files(str(tmp_path))
        assert "execute_sql" in analyzer.tool_tests

    def test_scan_empty_directory(self, tmp_path):
        analyzer = CoverageAnalyzer()
        analyzer.scan_test_files(str(tmp_path))
        assert analyzer.tool_tests == {}
        assert analyzer.test_files == []

    def test_scan_nonexistent_directory(self, tmp_path):
        analyzer = CoverageAnalyzer()
        analyzer.scan_test_files(str(tmp_path / "nope"))
        assert analyzer.tool_tests == {}

    def test_tool_deduplication_within_test(self, tmp_path):
        test_file = tmp_path / "test_dedup.yaml"
        test_file.write_text(
            yaml.dump(
                {
                    "tests": [
                        {
                            "name": "test_dup",
                            "prompt": "Test",
                            "evaluators": [
                                {
                                    "name": "was_mcp_tool_called",
                                    "args": {"tool_name": "list_charts"},
                                },
                                {
                                    "name": "tool_called_with_parameters",
                                    "args": {"tool_name": "list_charts"},
                                },
                            ],
                        }
                    ]
                }
            )
        )
        analyzer = CoverageAnalyzer()
        analyzer.scan_test_files(str(tmp_path))
        # Same tool referenced twice in same test should be deduplicated
        assert len(analyzer.tool_tests["list_charts"]) == 1

    def test_scan_with_steps(self, tmp_path):
        test_file = tmp_path / "test_steps.yaml"
        test_file.write_text(
            yaml.dump(
                {
                    "tests": [
                        {
                            "name": "test_multi",
                            "prompt": "Step 1",
                            "evaluators": [],
                            "steps": [
                                {
                                    "prompt": "Step 1",
                                    "evaluators": [
                                        {
                                            "name": "was_mcp_tool_called",
                                            "args": {"tool_name": "list_datasets"},
                                        }
                                    ],
                                },
                                {
                                    "prompt": "Step 2",
                                    "evaluators": [
                                        {
                                            "name": "was_mcp_tool_called",
                                            "args": {"tool_name": "execute_sql"},
                                        }
                                    ],
                                },
                            ],
                        }
                    ]
                }
            )
        )
        analyzer = CoverageAnalyzer()
        analyzer.scan_test_files(str(tmp_path))
        assert "list_datasets" in analyzer.tool_tests
        assert "execute_sql" in analyzer.tool_tests


class TestScanMcpTools:
    def test_registers_tools_and_finds_uncovered(self):
        analyzer = CoverageAnalyzer()
        # Manually add a covered tool
        analyzer.tool_tests["list_charts"] = [
            {"name": "t1", "file": "f.yaml", "category": "happy_path"}
        ]
        analyzer.scan_mcp_tools(
            [
                {"name": "list_charts"},
                {"name": "get_chart_info"},
                {"name": "execute_sql"},
            ]
        )
        assert analyzer.available_tools == ["list_charts", "get_chart_info", "execute_sql"]
        assert "get_chart_info" in analyzer.uncovered_tools
        assert "execute_sql" in analyzer.uncovered_tools
        assert "list_charts" not in analyzer.uncovered_tools


class TestGenerateReport:
    def test_report_contains_matrix(self, tmp_path):
        test_file = tmp_path / "test.yaml"
        test_file.write_text(
            yaml.dump(
                {
                    "tests": [
                        {
                            "name": "test_list",
                            "prompt": "List",
                            "evaluators": [
                                {
                                    "name": "was_mcp_tool_called",
                                    "args": {"tool_name": "list_charts"},
                                }
                            ],
                        }
                    ]
                }
            )
        )
        analyzer = CoverageAnalyzer()
        analyzer.scan_test_files(str(tmp_path))
        analyzer.scan_mcp_tools([{"name": "list_charts"}, {"name": "unused_tool"}])
        report = analyzer.generate_report()
        assert "## Tool Coverage Matrix" in report
        assert "list_charts" in report
        assert "unused_tool" in report
        assert "**GAP**" in report
        assert "Coverage Summary" in report

    def test_empty_report(self):
        analyzer = CoverageAnalyzer()
        report = analyzer.generate_report()
        assert "No tools or test files found." in report
