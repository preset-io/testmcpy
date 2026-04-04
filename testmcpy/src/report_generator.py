"""
Eval suite report generator for testmcpy.

Produces markdown reports matching the Notion eval report format,
with grand totals, per-eval breakdowns, cost summaries, and failure analysis.
"""

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class EvalSuiteReport:
    """Data structure for an eval suite report."""

    title: str = ""
    workspace_hash: str = ""
    domain: str = ""
    build_slug: str = ""
    date: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"))
    run_by: str = "testmcpy (automated)"

    # Per-suite results: {suite_name: {tests, pass, fail, skip, score, results, ...}}
    suite_results: dict[str, dict[str, Any]] = field(default_factory=dict)

    # Cost tracking
    total_tool_calls: int = 0
    total_tokens: int = 0
    total_cost: float = 0.0

    # Category costs
    mcp_direct_tool_calls: int = 0
    mcp_direct_tokens: int = 0
    mcp_direct_cost: float = 0.0
    chatbot_requests: int = 0
    chatbot_tokens: int = 0
    chatbot_cost: float = 0.0


class ReportGenerator:
    """Generate eval suite reports in markdown format."""

    def __init__(self) -> None:
        self.report = EvalSuiteReport()

    def configure(
        self,
        title: str = "",
        workspace_hash: str = "",
        domain: str = "",
        build_slug: str = "",
        date: str = "",
        run_by: str = "",
    ) -> None:
        """Configure report metadata."""
        if title:
            self.report.title = title
        if workspace_hash:
            self.report.workspace_hash = workspace_hash
        if domain:
            self.report.domain = domain
        if build_slug:
            self.report.build_slug = build_slug
        if date:
            self.report.date = date
        if run_by:
            self.report.run_by = run_by

    def add_suite_results(self, suite_name: str, results: list[dict[str, Any]]) -> None:
        """Add results from a test suite run.

        Each result dict should have at minimum:
            - passed: bool
            - skipped: bool (optional)
            - name/test_name: str
            - reason: str (optional, for failures)
            - tool_calls: list (optional)
            - token_usage: dict with 'total' key (optional)
            - cost: float (optional)
            - duration: float (optional)
        """
        if not results:
            self.report.suite_results[suite_name] = {
                "tests": 0,
                "pass": 0,
                "fail": 0,
                "skip": 0,
                "score": "0%",
                "results": [],
                "tool_calls": 0,
                "tokens": 0,
                "cost": 0.0,
            }
            return

        passed = sum(1 for r in results if r.get("passed"))
        skipped = sum(1 for r in results if r.get("skipped"))
        failed = sum(1 for r in results if not r.get("passed") and not r.get("skipped"))

        suite_tool_calls = 0
        suite_tokens = 0
        suite_cost = 0.0
        for r in results:
            suite_tool_calls += len(r.get("tool_calls", []))
            token_usage = r.get("token_usage")
            if token_usage and isinstance(token_usage, dict):
                suite_tokens += token_usage.get("total", 0)
            suite_cost += r.get("cost", 0.0)

        total_for_score = passed + failed
        score_pct = (passed / total_for_score * 100) if total_for_score > 0 else 0
        score_str = f"{score_pct:.0f}%"

        self.report.suite_results[suite_name] = {
            "tests": len(results),
            "pass": passed,
            "fail": failed,
            "skip": skipped,
            "score": score_str,
            "results": results,
            "tool_calls": suite_tool_calls,
            "tokens": suite_tokens,
            "cost": suite_cost,
        }

        # Update totals
        self.report.total_tool_calls += suite_tool_calls
        self.report.total_tokens += suite_tokens
        self.report.total_cost += suite_cost

        # Categorize by eval naming convention:
        # C00-C09 chatbot evals, D01-D02 demo scripts → chatbot pipeline
        # Everything else → MCP direct
        lower_name = suite_name.lower()
        is_chatbot = (
            bool(re.match(r"^C\d", suite_name))  # C00, C01, etc.
            or bool(re.match(r"^D\d", suite_name))  # D01, D02, etc.
            or "chatbot" in lower_name
            or "assistant" in lower_name
        )
        if is_chatbot:
            self.report.chatbot_requests += len(results)
            self.report.chatbot_tokens += suite_tokens
            self.report.chatbot_cost += suite_cost
        else:
            self.report.mcp_direct_tool_calls += suite_tool_calls
            self.report.mcp_direct_tokens += suite_tokens
            self.report.mcp_direct_cost += suite_cost

    def _format_tokens(self, tokens: int) -> str:
        """Format token count for display (e.g., 1500 -> '1.5K', 2000000 -> '2.0M')."""
        if tokens >= 1_000_000:
            return f"{tokens / 1_000_000:.1f}M"
        if tokens >= 1_000:
            return f"{tokens / 1_000:.0f}K"
        return str(tokens)

    def _generate_header(self) -> str:
        """Generate the report header section."""
        lines = []
        title = self.report.title or "Eval Suite Run"
        lines.append(f"# Eval Suite Results — {title}")
        lines.append("")

        if self.report.workspace_hash:
            lines.append(f"**Workspace:** `{self.report.workspace_hash}` on `{self.report.domain}`")
        if self.report.build_slug:
            lines.append(f"**Build:** `{self.report.build_slug}`")
        lines.append(f"**Date:** {self.report.date}")
        lines.append(f"**Run by:** {self.report.run_by}")
        lines.append("")
        lines.append("---")
        lines.append("")
        return "\n".join(lines)

    def _generate_grand_totals(self) -> str:
        """Generate the grand totals summary table."""
        lines = []
        lines.append("## Summary")
        lines.append("")
        lines.append("## Grand Totals")
        lines.append("")
        lines.append("| Suite | Tests | Pass | Fail | Skip | Score |")
        lines.append("|-------|-------|------|------|------|-------|")

        grand_tests = 0
        grand_pass = 0
        grand_fail = 0
        grand_skip = 0

        for suite_name, data in self.report.suite_results.items():
            tests = data["tests"]
            passed = data["pass"]
            failed = data["fail"]
            skipped = data["skip"]
            score = data["score"]

            lines.append(f"| {suite_name} | {tests} | {passed} | {failed} | {skipped} | {score} |")

            grand_tests += tests
            grand_pass += passed
            grand_fail += failed
            grand_skip += skipped

        # Grand total row
        total_for_score = grand_pass + grand_fail
        grand_score = (
            f"{(grand_pass / total_for_score * 100):.0f}%" if total_for_score > 0 else "0%"
        )
        lines.append(
            f"| **Total** | **{grand_tests}** | **{grand_pass}** | "
            f"**{grand_fail}** | **{grand_skip}** | **{grand_score}** |"
        )

        lines.append("")
        lines.append("---")
        lines.append("")
        return "\n".join(lines)

    def _generate_eval_breakdown(self) -> str:
        """Generate per-eval breakdown tables grouped by suite."""
        lines = []

        for suite_name, data in self.report.suite_results.items():
            results = data.get("results", [])
            if not results:
                continue

            lines.append(f"## {suite_name} — Eval Results")
            lines.append("")
            lines.append("| # | Test | Pass | Fail | Notes |")
            lines.append("|---|------|------|------|-------|")

            for i, r in enumerate(results, 1):
                test_name = r.get("test_name") or r.get("name") or f"test_{i}"
                passed = 1 if r.get("passed") else 0
                failed = 0 if r.get("passed") or r.get("skipped") else 1
                skipped = r.get("skipped", False)

                if skipped:
                    notes = "SKIPPED"
                elif not r.get("passed"):
                    notes = r.get("reason") or r.get("error") or "Failed"
                else:
                    notes = ""

                lines.append(f"| {i:02d} | {test_name} | {passed} | {failed} | {notes} |")

            lines.append("")
            lines.append("---")
            lines.append("")

        return "\n".join(lines)

    def _generate_cost_summary(self) -> str:
        """Generate cost and token summary section."""
        lines = []
        lines.append("## Cost and Token Summary")
        lines.append("")

        if self.report.mcp_direct_tool_calls > 0 or self.report.mcp_direct_tokens > 0:
            tokens_str = self._format_tokens(self.report.mcp_direct_tokens)
            lines.append(
                f"- MCP Direct: ~{self.report.mcp_direct_tool_calls} tool calls, "
                f"~{tokens_str} tokens, est. ~${self.report.mcp_direct_cost:.2f}"
            )

        if self.report.chatbot_requests > 0 or self.report.chatbot_tokens > 0:
            tokens_str = self._format_tokens(self.report.chatbot_tokens)
            lines.append(
                f"- Chatbot Pipeline: ~{self.report.chatbot_requests} requests, "
                f"~{tokens_str} tokens, est. ~${self.report.chatbot_cost:.2f}"
            )

        lines.append(f"- **Total eval cost: ~${self.report.total_cost:.2f}**")
        lines.append("")
        lines.append("---")
        lines.append("")
        return "\n".join(lines)

    def _generate_failures_analysis(self) -> str:
        """Generate failures analysis section, grouped by failure category."""
        lines = []
        lines.append("## Failures Analysis")
        lines.append("")

        # Collect all failures across suites
        failures: list[dict[str, Any]] = []
        for suite_name, data in self.report.suite_results.items():
            for r in data.get("results", []):
                if not r.get("passed") and not r.get("skipped"):
                    failures.append(
                        {
                            "suite": suite_name,
                            "test": r.get("test_name") or r.get("name") or "unknown",
                            "reason": r.get("reason") or r.get("error") or "Unknown failure",
                        }
                    )

        if not failures:
            lines.append("No failures detected.")
            lines.append("")
            return "\n".join(lines)

        # Categorize failures by reason pattern
        categories: dict[str, list[dict[str, str]]] = {}
        for f in failures:
            reason = f["reason"]
            category = _categorize_failure(reason)
            if category not in categories:
                categories[category] = []
            categories[category].append(f)

        for category, items in categories.items():
            lines.append(f"### {category} ({len(items)})")
            lines.append("")
            for item in items:
                lines.append(f"- **{item['suite']} / {item['test']}**: {item['reason']}")
            lines.append("")

        return "\n".join(lines)

    def generate_markdown(self) -> str:
        """Generate the full markdown report."""
        sections = [
            self._generate_header(),
            self._generate_grand_totals(),
            self._generate_eval_breakdown(),
            self._generate_cost_summary(),
            self._generate_failures_analysis(),
        ]
        return "\n".join(sections)

    def save(self, path: str) -> Path:
        """Save report to file (markdown, JSON, or HTML based on extension)."""
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if output_path.suffix == ".html":
            from testmcpy.src.html_report import HTMLReportGenerator

            html_gen = HTMLReportGenerator(self.report)
            output_path.write_text(html_gen.generate())
        elif output_path.suffix == ".json":
            output_path.write_text(json.dumps(self.to_dict(), indent=2))
        else:
            output_path.write_text(self.generate_markdown())

        return output_path

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for JSON serialization."""
        report_dict = asdict(self.report)
        # Remove raw results from suite_results to keep JSON clean
        for _suite_name, data in report_dict.get("suite_results", {}).items():
            # Keep results but make them serializable
            if "results" in data:
                clean_results = []
                for r in data["results"]:
                    # Only keep essential fields
                    clean_results.append(
                        {
                            "test_name": r.get("test_name") or r.get("name"),
                            "passed": r.get("passed"),
                            "skipped": r.get("skipped", False),
                            "reason": r.get("reason"),
                            "cost": r.get("cost", 0.0),
                            "duration": r.get("duration", 0.0),
                        }
                    )
                data["results"] = clean_results
        return report_dict

    @classmethod
    def from_test_results(
        cls,
        suite_name: str,
        results: list[Any],
        title: str = "",
        workspace_hash: str = "",
        domain: str = "",
        build_slug: str = "",
    ) -> "ReportGenerator":
        """Create a ReportGenerator from TestResult objects (from test_runner).

        This is a convenience method for the common case of generating a report
        from a single suite run via the CLI.
        """
        gen = cls()
        gen.configure(
            title=title or suite_name,
            workspace_hash=workspace_hash,
            domain=domain,
            build_slug=build_slug,
        )

        # Convert TestResult objects to dicts
        result_dicts = []
        for r in results:
            if hasattr(r, "to_dict"):
                result_dicts.append(r.to_dict())
            elif isinstance(r, dict):
                result_dicts.append(r)

        gen.add_suite_results(suite_name, result_dicts)
        return gen


def _categorize_failure(reason: str) -> str:
    """Categorize a failure reason into a human-readable category."""
    lower = reason.lower()
    if "timeout" in lower or "timed out" in lower:
        return "Timeout"
    if "rate_limit" in lower or "429" in lower or "rate limit" in lower:
        return "Rate Limiting"
    if "connection" in lower or "network" in lower or "unreachable" in lower:
        return "Connection Error"
    if "auth" in lower or "unauthorized" in lower or "403" in lower or "401" in lower:
        return "Authentication Error"
    if "tool" in lower and ("not found" in lower or "not called" in lower):
        return "Tool Not Called"
    if "assertion" in lower or "expected" in lower or "mismatch" in lower:
        return "Assertion Failure"
    if "error" in lower or "exception" in lower:
        return "Runtime Error"
    return "Other"
