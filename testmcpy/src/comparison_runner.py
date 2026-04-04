"""
Multi-model comparison runner for testmcpy.

Runs the same test suite against multiple LLM providers/models
and produces a comparison matrix report.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .mcp_client import MCPClient
from .test_runner import TestCase, TestResult, TestRunner

logger = logging.getLogger(__name__)


@dataclass
class ModelConfig:
    """Configuration for a single LLM model to compare."""

    provider: str
    model: str
    name: str = ""  # Display name
    api_key: str | None = None

    def __post_init__(self):
        if not self.name:
            self.name = f"{self.provider}:{self.model}"

    @classmethod
    def from_string(cls, spec: str) -> "ModelConfig":
        """Parse a 'provider:model' string into a ModelConfig.

        Examples:
            'anthropic:claude-sonnet-4-20250514'
            'openai:gpt-4o'
            'openrouter:meta-llama/llama-3.1-70b'
        """
        parts = spec.split(":", 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid model spec '{spec}'. Expected 'provider:model' format.")
        provider, model = parts
        return cls(provider=provider.strip(), model=model.strip())


@dataclass
class ComparisonResult:
    """Aggregated results from running a test suite against one model."""

    model: ModelConfig
    results: list[TestResult]
    total_tests: int
    passed: int
    failed: int
    total_cost: float
    total_tokens: int
    total_duration: float
    avg_score: float

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "model": {
                "provider": self.model.provider,
                "model": self.model.model,
                "name": self.model.name,
            },
            "total_tests": self.total_tests,
            "passed": self.passed,
            "failed": self.failed,
            "total_cost": self.total_cost,
            "total_tokens": self.total_tokens,
            "total_duration": self.total_duration,
            "avg_score": self.avg_score,
            "results": [r.to_dict() for r in self.results],
        }


class ComparisonRunner:
    """Runs the same test cases against multiple LLM models and compares results."""

    def __init__(
        self,
        models: list[ModelConfig],
        mcp_url: str | None = None,
        mcp_client: MCPClient | None = None,
        verbose: bool = False,
    ):
        self.models = models
        self.mcp_url = mcp_url
        self.mcp_client = mcp_client
        self.verbose = verbose
        self._comparison_results: list[ComparisonResult] = []

    async def run(self, test_cases: list[TestCase]) -> list[ComparisonResult]:
        """Run all test cases against each model sequentially.

        For each model, creates a fresh TestRunner, runs all tests,
        and collects aggregated results.
        """
        self._comparison_results = []

        for model_config in self.models:
            logger.info(
                "Running %d tests against %s",
                len(test_cases),
                model_config.name,
            )

            runner = TestRunner(
                model=model_config.model,
                provider=model_config.provider,
                mcp_url=self.mcp_url,
                mcp_client=self.mcp_client,
                verbose=self.verbose,
            )

            try:
                results = await runner.run_tests(test_cases)
            finally:
                await runner.cleanup()

            # Aggregate metrics
            passed = sum(1 for r in results if r.passed)
            failed = sum(1 for r in results if not r.passed)
            total_cost = sum(r.cost for r in results)
            total_tokens = sum((r.token_usage or {}).get("total", 0) for r in results)
            total_duration = sum(r.duration for r in results)
            scores = [r.score for r in results]
            avg_score = sum(scores) / len(scores) if scores else 0.0

            comparison_result = ComparisonResult(
                model=model_config,
                results=results,
                total_tests=len(results),
                passed=passed,
                failed=failed,
                total_cost=total_cost,
                total_tokens=total_tokens,
                total_duration=total_duration,
                avg_score=avg_score,
            )
            self._comparison_results.append(comparison_result)

        return self._comparison_results

    def generate_comparison_report(self, results: list[ComparisonResult]) -> str:
        """Generate a markdown comparison matrix.

        Produces a table with test names as rows and models as columns,
        plus summary rows for score, cost, tokens, and duration.
        """
        if not results:
            return "# Comparison Report\n\nNo results to compare.\n"

        lines: list[str] = []
        lines.append("# Model Comparison Report")
        lines.append("")
        lines.append(f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"**Models compared:** {len(results)}")
        lines.append("")

        # Collect all test names from the first model's results
        # (all models run the same tests)
        test_names = [r.test_name for r in results[0].results]
        model_names = [r.model.name for r in results]

        # Build header
        header = "| Test | " + " | ".join(model_names) + " |"
        separator = (
            "|------|" + "|".join("---" + "-" * max(0, len(name) - 3) for name in model_names) + "|"
        )

        lines.append(header)
        lines.append(separator)

        # Build per-test rows
        for i, test_name in enumerate(test_names):
            cells = []
            for cr in results:
                if i < len(cr.results):
                    tr = cr.results[i]
                    if tr.passed:
                        cells.append(f"PASS ({tr.duration:.1f}s)")
                    else:
                        cells.append("FAIL")
                else:
                    cells.append("N/A")
            row = f"| {test_name} | " + " | ".join(cells) + " |"
            lines.append(row)

        # Summary separator
        summary_sep = "|---|" + "|".join("---" for _ in model_names) + "|"
        lines.append(summary_sep)

        # Score row
        score_cells = [f"**{cr.avg_score * 100:.0f}%**" for cr in results]
        lines.append("| **Score** | " + " | ".join(score_cells) + " |")

        # Cost row
        cost_cells = [f"**${cr.total_cost:.2f}**" for cr in results]
        lines.append("| **Cost** | " + " | ".join(cost_cells) + " |")

        # Tokens row
        token_cells = [f"**{_format_tokens(cr.total_tokens)}**" for cr in results]
        lines.append("| **Tokens** | " + " | ".join(token_cells) + " |")

        # Duration row
        duration_cells = [f"**{cr.total_duration:.0f}s**" for cr in results]
        lines.append("| **Duration** | " + " | ".join(duration_cells) + " |")

        lines.append("")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        """Convert comparison results to JSON-serializable dict."""
        return {
            "date": datetime.now().isoformat(),
            "models": [
                {
                    "provider": m.provider,
                    "model": m.model,
                    "name": m.name,
                }
                for m in self.models
            ],
            "results": [cr.to_dict() for cr in self._comparison_results],
        }


def _format_tokens(tokens: int) -> str:
    """Format token count for display (e.g., 1500 -> '2K', 2000000 -> '2.0M')."""
    if tokens >= 1_000_000:
        return f"{tokens / 1_000_000:.1f}M"
    if tokens >= 1_000:
        return f"{tokens / 1_000:.0f}K"
    return str(tokens)
