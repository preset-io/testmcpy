"""
Coverage analyzer for MCP tool test coverage.

Analyzes which MCP tools are covered by test files and identifies gaps.
"""

import os
from pathlib import Path
from typing import Any

import yaml


def _categorize_test(test_name: str) -> str:
    """Categorize a test based on its name.

    Args:
        test_name: The name of the test case.

    Returns:
        Category string: "happy_path", "error_case", "edge_case", or "security".
    """
    name_lower = test_name.lower()

    error_keywords = ["error", "invalid", "not_found", "notfound", "fail"]
    edge_keywords = ["edge", "unicode", "parallel", "boundary", "empty", "large"]
    security_keywords = ["security", "injection", "xss", "rls", "auth", "csrf"]

    for kw in security_keywords:
        if kw in name_lower:
            return "security"

    for kw in error_keywords:
        if kw in name_lower:
            return "error_case"

    for kw in edge_keywords:
        if kw in name_lower:
            return "edge_case"

    return "happy_path"


def _extract_tool_names_from_evaluators(evaluators: list[dict[str, Any]]) -> list[str]:
    """Extract tool names referenced in evaluator configurations.

    Args:
        evaluators: List of evaluator dicts from a test case.

    Returns:
        List of tool name strings found in the evaluators.
    """
    tool_names: list[str] = []
    for ev in evaluators:
        ev_name = ev.get("name", "")
        args = ev.get("args", {})
        if (
            ev_name
            in ("was_mcp_tool_called", "tool_called_with_parameters", "tool_called_with_parameter")
            and args
        ):
            tool_name = args.get("tool_name")
            if tool_name:
                tool_names.append(tool_name)
        if ev_name == "tool_call_sequence" and args:
            sequence = args.get("expected_sequence", [])
            tool_names.extend(sequence)
    return tool_names


class CoverageAnalyzer:
    """Analyze test coverage of MCP tools."""

    def __init__(self):
        self.tool_tests: dict[str, list[dict[str, Any]]] = {}
        self.uncovered_tools: list[str] = []
        self.test_files: list[str] = []
        self.available_tools: list[str] = []

    def scan_test_files(self, test_dir: str) -> None:
        """Scan all YAML test files in a directory tree.

        Walks the directory, loads each YAML file, and extracts tool names from:
        - was_mcp_tool_called evaluator args
        - tool_called_with_parameters evaluator args
        - tool_called_with_parameter evaluator args
        - tool_call_sequence evaluator args
        - expected_tools field on test cases
        - metadata.expected_tool field on test cases

        Args:
            test_dir: Path to directory containing YAML test files.
        """
        test_path = Path(test_dir)
        if not test_path.is_dir():
            return

        for root, _dirs, files in os.walk(test_path):
            for filename in sorted(files):
                if not filename.endswith((".yaml", ".yml")):
                    continue
                filepath = os.path.join(root, filename)
                self._process_test_file(filepath)

    def _process_test_file(self, filepath: str) -> None:
        """Load and process a single YAML test file.

        Args:
            filepath: Absolute path to the YAML file.
        """
        try:
            with open(filepath) as f:
                data = yaml.safe_load(f)
        except (yaml.YAMLError, OSError):
            return

        if not isinstance(data, dict):
            return

        tests = data.get("tests", [])
        if not isinstance(tests, list):
            return

        self.test_files.append(filepath)

        for test in tests:
            if not isinstance(test, dict):
                continue
            self._process_test_case(test, filepath)

    def _process_test_case(self, test: dict[str, Any], filepath: str) -> None:
        """Extract tool references from a single test case dict.

        Args:
            test: Test case dictionary from YAML.
            filepath: Source file path for reference.
        """
        test_name = test.get("name", "unknown")
        category = _categorize_test(test_name)
        test_info = {
            "name": test_name,
            "file": filepath,
            "category": category,
        }

        tool_names: list[str] = []

        # From top-level evaluators
        evaluators = test.get("evaluators", [])
        if isinstance(evaluators, list):
            tool_names.extend(_extract_tool_names_from_evaluators(evaluators))

        # From steps (multi-turn tests)
        steps = test.get("steps", [])
        if isinstance(steps, list):
            for step in steps:
                if isinstance(step, dict):
                    step_evaluators = step.get("evaluators", [])
                    if isinstance(step_evaluators, list):
                        tool_names.extend(_extract_tool_names_from_evaluators(step_evaluators))

        # From expected_tools field
        expected_tools = test.get("expected_tools", [])
        if isinstance(expected_tools, list):
            tool_names.extend(expected_tools)

        # From metadata.expected_tool field
        metadata = test.get("metadata", {})
        if isinstance(metadata, dict):
            expected_tool = metadata.get("expected_tool")
            if expected_tool:
                tool_names.append(expected_tool)

        # Deduplicate while preserving order
        seen: set[str] = set()
        unique_tools: list[str] = []
        for tn in tool_names:
            if tn not in seen:
                seen.add(tn)
                unique_tools.append(tn)

        for tool_name in unique_tools:
            if tool_name not in self.tool_tests:
                self.tool_tests[tool_name] = []
            self.tool_tests[tool_name].append(test_info)

    def scan_mcp_tools(self, tools: list[dict[str, Any]]) -> None:
        """Register available MCP tools from a tool listing.

        After scanning, identifies which tools have no test coverage.

        Args:
            tools: List of tool dicts, each expected to have a "name" key.
        """
        self.available_tools = []
        for tool in tools:
            name = tool.get("name", "")
            if name:
                self.available_tools.append(name)

        self.uncovered_tools = [t for t in self.available_tools if t not in self.tool_tests]

    def generate_report(self) -> str:
        """Generate a coverage report as markdown.

        Returns:
            Markdown-formatted coverage report string.
        """
        lines: list[str] = []
        lines.append("# MCP Tool Test Coverage Report")
        lines.append("")

        # Determine the full set of tools to report on
        all_tools = sorted(set(list(self.tool_tests.keys()) + self.available_tools))

        if not all_tools:
            lines.append("No tools or test files found.")
            return "\n".join(lines)

        # Coverage matrix
        lines.append("## Tool Coverage Matrix")
        lines.append("")
        lines.append("| Tool | Tests | Happy Path | Error Case | Edge Case | Security |")
        lines.append("|------|-------|------------|------------|-----------|----------|")

        for tool in all_tools:
            tests = self.tool_tests.get(tool, [])
            count = len(tests)
            categories = {t["category"] for t in tests}

            happy = "Y" if "happy_path" in categories else "-"
            error = "Y" if "error_case" in categories else "-"
            edge = "Y" if "edge_case" in categories else "-"
            security = "Y" if "security" in categories else "-"

            gap_marker = " **GAP**" if count == 0 else ""
            lines.append(
                f"| {tool} | {count}{gap_marker} | {happy} | {error} | {edge} | {security} |"
            )

        lines.append("")

        # Coverage summary
        total_tools = len(all_tools)
        covered = sum(1 for t in all_tools if t in self.tool_tests)
        pct = (covered / total_tools * 100) if total_tools > 0 else 0.0

        lines.append("## Coverage Summary")
        lines.append("")
        lines.append(f"- Tools covered: {covered}/{total_tools} ({pct:.0f}%)")

        if self.uncovered_tools:
            lines.append(f"- Uncovered tools: {', '.join(sorted(self.uncovered_tools))}")

        # Aggregate category counts across all tests
        all_tests: list[dict[str, Any]] = []
        for tests in self.tool_tests.values():
            all_tests.extend(tests)

        # Deduplicate by (name, file) to avoid counting a test multiple times
        # when it references multiple tools
        seen_tests: set[tuple[str, str]] = set()
        category_counts: dict[str, int] = {
            "happy_path": 0,
            "error_case": 0,
            "edge_case": 0,
            "security": 0,
        }
        for t in all_tests:
            key = (t["name"], t["file"])
            if key not in seen_tests:
                seen_tests.add(key)
                cat = t["category"]
                category_counts[cat] = category_counts.get(cat, 0) + 1

        lines.append(
            f"- Tests by category: "
            f"Happy={category_counts['happy_path']}, "
            f"Error={category_counts['error_case']}, "
            f"Edge={category_counts['edge_case']}, "
            f"Security={category_counts['security']}"
        )

        lines.append(f"- Test files scanned: {len(self.test_files)}")
        lines.append("")

        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-serializable coverage data.

        Returns:
            Dictionary with tool_coverage, uncovered_tools, summary, and test_files.
        """
        all_tools = sorted(set(list(self.tool_tests.keys()) + self.available_tools))
        total_tools = len(all_tools)
        covered = sum(1 for t in all_tools if t in self.tool_tests)

        tool_coverage: dict[str, Any] = {}
        for tool in all_tools:
            tests = self.tool_tests.get(tool, [])
            categories = {t["category"] for t in tests}
            tool_coverage[tool] = {
                "test_count": len(tests),
                "tests": tests,
                "has_happy_path": "happy_path" in categories,
                "has_error_case": "error_case" in categories,
                "has_edge_case": "edge_case" in categories,
                "has_security": "security" in categories,
            }

        # Deduplicated category counts
        all_tests: list[dict[str, Any]] = []
        for tests in self.tool_tests.values():
            all_tests.extend(tests)

        seen_tests: set[tuple[str, str]] = set()
        category_counts: dict[str, int] = {
            "happy_path": 0,
            "error_case": 0,
            "edge_case": 0,
            "security": 0,
        }
        for t in all_tests:
            key = (t["name"], t["file"])
            if key not in seen_tests:
                seen_tests.add(key)
                category_counts[t["category"]] = category_counts.get(t["category"], 0) + 1

        return {
            "tool_coverage": tool_coverage,
            "uncovered_tools": sorted(self.uncovered_tools),
            "summary": {
                "total_tools": total_tools,
                "covered_tools": covered,
                "coverage_percent": (
                    round(covered / total_tools * 100, 1) if total_tools > 0 else 0.0
                ),
                "test_files_scanned": len(self.test_files),
                "tests_by_category": category_counts,
            },
            "test_files": self.test_files,
        }
