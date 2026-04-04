"""
Multi-environment orchestration runner for testmcpy.

Runs the same eval suite across multiple environments (staging, sandbox, production)
using different MCP profiles and compares results to identify environment-specific issues.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .mcp_client import MCPClient
from .test_runner import TestCase, TestResult, TestRunner

logger = logging.getLogger(__name__)


@dataclass
class EnvironmentConfig:
    """Configuration for a single target environment."""

    name: str  # e.g. "staging", "sandbox", "production"
    profile_id: str  # MCP profile ID from .mcp_services.yaml
    description: str = ""

    @classmethod
    def from_string(cls, spec: str) -> "EnvironmentConfig":
        """Parse a 'name:profile_id' string into an EnvironmentConfig.

        Examples:
            'staging:localhost'
            'sandbox:sandbox-profile'
            'production:prod-profile'
        """
        parts = spec.split(":", 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid env spec '{spec}'. Expected 'name:profile_id' format.")
        name, profile_id = parts
        return cls(name=name.strip(), profile_id=profile_id.strip())


@dataclass
class EnvironmentResult:
    """Aggregated results from running a test suite against one environment."""

    environment: EnvironmentConfig
    results: list[TestResult]
    total_tests: int
    passed: int
    failed: int
    score: float
    total_duration: float

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "environment": {
                "name": self.environment.name,
                "profile_id": self.environment.profile_id,
                "description": self.environment.description,
            },
            "total_tests": self.total_tests,
            "passed": self.passed,
            "failed": self.failed,
            "score": self.score,
            "total_duration": self.total_duration,
            "results": [r.to_dict() for r in self.results],
        }


class MultiEnvironmentRunner:
    """Run eval suites across multiple environments and compare results."""

    def __init__(
        self,
        environments: list[EnvironmentConfig],
        model: str,
        provider: str,
        verbose: bool = False,
    ):
        self.environments = environments
        self.model = model
        self.provider = provider
        self.verbose = verbose
        self._env_results: list[EnvironmentResult] = []

    async def run(self, test_cases: list[TestCase]) -> list[EnvironmentResult]:
        """Run all tests against each environment sequentially.

        For each environment: load MCP profile, create a TestRunner with the
        profile's MCP client, run all tests, and collect aggregated results.
        """
        from testmcpy.server.state import get_or_create_mcp_client

        self._env_results = []

        for env_config in self.environments:
            logger.info(
                "Running %d tests against environment '%s' (profile: %s)",
                len(test_cases),
                env_config.name,
                env_config.profile_id,
            )

            # Load MCP client for this environment's profile
            mcp_client: MCPClient | None = None
            try:
                mcp_client = await get_or_create_mcp_client(env_config.profile_id)
            except (ConnectionError, ValueError, KeyError, OSError) as e:
                logger.warning(
                    "Could not load MCP profile '%s' for env '%s': %s",
                    env_config.profile_id,
                    env_config.name,
                    e,
                )

            runner = TestRunner(
                model=self.model,
                provider=self.provider,
                mcp_client=mcp_client,
                verbose=self.verbose,
            )

            try:
                results = await runner.run_tests(test_cases)
            finally:
                await runner.cleanup()

            # Aggregate metrics
            passed = sum(1 for r in results if r.passed)
            failed = sum(1 for r in results if not r.passed)
            scores = [r.score for r in results]
            avg_score = sum(scores) / len(scores) if scores else 0.0
            total_duration = sum(r.duration for r in results)

            env_result = EnvironmentResult(
                environment=env_config,
                results=results,
                total_tests=len(results),
                passed=passed,
                failed=failed,
                score=avg_score,
                total_duration=total_duration,
            )
            self._env_results.append(env_result)

        return self._env_results

    def generate_comparison_report(self, results: list[EnvironmentResult]) -> str:
        """Generate a markdown comparison matrix across environments.

        Produces a table with test names as rows and environments as columns,
        plus summary rows for score and duration. Also lists environment-specific
        failures (tests that fail in one env but pass in others).
        """
        if not results:
            return "# Multi-Environment Comparison Report\n\nNo results to compare.\n"

        lines: list[str] = []
        lines.append("# Multi-Environment Comparison Report")
        lines.append("")
        lines.append(f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"**Environments compared:** {len(results)}")
        lines.append(f"**Model:** {self.model} ({self.provider})")
        lines.append("")

        # Collect test names from the first environment's results
        test_names = [r.test_name for r in results[0].results]
        env_names = [er.environment.name for er in results]

        # Build header
        header = "| Test | " + " | ".join(env_names) + " |"
        separator = (
            "|------|" + "|".join("---" + "-" * max(0, len(name) - 3) for name in env_names) + "|"
        )

        lines.append(header)
        lines.append(separator)

        # Build per-test rows
        for i, test_name in enumerate(test_names):
            cells = []
            for er in results:
                if i < len(er.results):
                    tr = er.results[i]
                    if tr.passed:
                        cells.append(f"PASS ({tr.duration:.1f}s)")
                    else:
                        cells.append("FAIL")
                else:
                    cells.append("N/A")
            row = f"| {test_name} | " + " | ".join(cells) + " |"
            lines.append(row)

        # Summary separator
        summary_sep = "|---|" + "|".join("---" for _ in env_names) + "|"
        lines.append(summary_sep)

        # Score row
        score_cells = [f"**{er.score * 100:.0f}%**" for er in results]
        lines.append("| **Score** | " + " | ".join(score_cells) + " |")

        # Duration row
        duration_cells = [f"**{er.total_duration:.0f}s**" for er in results]
        lines.append("| **Duration** | " + " | ".join(duration_cells) + " |")

        lines.append("")

        # Environment-specific failures
        env_issues = self.find_env_specific_issues(results)
        if env_issues:
            lines.append("## Environment-Specific Failures")
            lines.append("")
            lines.append("Tests that fail in some environments but pass in others:")
            lines.append("")
            for issue in env_issues:
                lines.append(f"- **{issue['test_name']}**")
                if issue["passed_in"]:
                    lines.append(f"  - Passed in: {', '.join(issue['passed_in'])}")
                if issue["failed_in"]:
                    lines.append(f"  - Failed in: {', '.join(issue['failed_in'])}")
            lines.append("")

        return "\n".join(lines)

    def find_env_specific_issues(self, results: list[EnvironmentResult]) -> list[dict[str, Any]]:
        """Identify tests that behave differently across environments.

        Returns a list of dicts with:
            - test_name: name of the test
            - passed_in: list of environment names where it passed
            - failed_in: list of environment names where it failed
        """
        if not results:
            return []

        issues: list[dict[str, Any]] = []
        test_names = [r.test_name for r in results[0].results]

        for i, test_name in enumerate(test_names):
            passed_in: list[str] = []
            failed_in: list[str] = []

            for er in results:
                if i < len(er.results):
                    tr = er.results[i]
                    if tr.passed:
                        passed_in.append(er.environment.name)
                    else:
                        failed_in.append(er.environment.name)

            # Only include if there is a discrepancy (not all pass or all fail)
            if passed_in and failed_in:
                issues.append(
                    {
                        "test_name": test_name,
                        "passed_in": passed_in,
                        "failed_in": failed_in,
                    }
                )

        return issues

    def to_dict(self) -> dict[str, Any]:
        """Convert multi-environment results to JSON-serializable dict."""
        return {
            "date": datetime.now().isoformat(),
            "model": self.model,
            "provider": self.provider,
            "environments": [
                {
                    "name": env.name,
                    "profile_id": env.profile_id,
                    "description": env.description,
                }
                for env in self.environments
            ],
            "results": [er.to_dict() for er in self._env_results],
            "env_specific_issues": self.find_env_specific_issues(self._env_results),
        }
