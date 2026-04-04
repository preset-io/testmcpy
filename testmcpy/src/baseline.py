"""
Baseline storage and regression detection for testmcpy.

Supports saving test results as named baselines, comparing current results
against baselines, and generating regression reports with failure fingerprinting.
"""

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from .test_runner import TestResult


@dataclass
class BaselineEntry:
    """A single test result stored in a baseline."""

    test_name: str
    passed: bool
    score: float
    tool_calls: list[str]  # Just tool names
    duration: float
    model: str
    provider: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    failure_fingerprint: str | None = None  # Hash of failure for dedup


@dataclass
class RegressionReport:
    """Report comparing current results against a baseline."""

    new_failures: list[dict[str, Any]]  # Tests that passed in baseline but fail now
    new_passes: list[dict[str, Any]]  # Tests that failed in baseline but pass now
    stable_failures: list[dict[str, Any]]  # Tests that fail in both (known issues)
    stable_passes: list[dict[str, Any]]  # Tests that pass in both
    score_changes: list[dict[str, Any]]  # Tests where score changed significantly


class BaselineStore:
    """Store and compare test baselines."""

    # Threshold for reporting a score change as significant
    SCORE_CHANGE_THRESHOLD = 0.1

    def __init__(self, baseline_dir: str = ".baselines"):
        self.baseline_dir = Path(baseline_dir)
        self.baseline_dir.mkdir(parents=True, exist_ok=True)

    def save_baseline(
        self,
        name: str,
        results: list[TestResult],
        model: str,
        provider: str,
    ) -> Path:
        """Save test results as a named baseline. Returns the path written."""
        entries = []
        for r in results:
            fp = self._fingerprint(r) if not r.passed else None
            entries.append(
                BaselineEntry(
                    test_name=r.test_name,
                    passed=r.passed,
                    score=r.score,
                    tool_calls=[tc.get("name", "") for tc in (r.tool_calls or [])],
                    duration=r.duration,
                    model=model,
                    provider=provider,
                    failure_fingerprint=fp,
                )
            )

        path = self.baseline_dir / f"{name}.json"
        payload = {
            "entries": [asdict(e) for e in entries],
            "model": model,
            "provider": provider,
            "created": datetime.now().isoformat(),
        }
        path.write_text(json.dumps(payload, indent=2))
        return path

    def load_baseline(self, name: str) -> list[BaselineEntry]:
        """Load a named baseline. Raises FileNotFoundError if missing."""
        path = self.baseline_dir / f"{name}.json"
        if not path.exists():
            raise FileNotFoundError(f"Baseline '{name}' not found at {path}")

        data = json.loads(path.read_text())
        entries: list[BaselineEntry] = []
        for raw in data.get("entries", []):
            entries.append(
                BaselineEntry(
                    test_name=raw["test_name"],
                    passed=raw["passed"],
                    score=raw["score"],
                    tool_calls=raw.get("tool_calls", []),
                    duration=raw["duration"],
                    model=raw.get("model", ""),
                    provider=raw.get("provider", ""),
                    timestamp=raw.get("timestamp", ""),
                    failure_fingerprint=raw.get("failure_fingerprint"),
                )
            )
        return entries

    def list_baselines(self) -> list[dict[str, Any]]:
        """List available baselines with metadata."""
        baselines: list[dict[str, Any]] = []
        for path in sorted(self.baseline_dir.glob("*.json")):
            try:
                data = json.loads(path.read_text())
            except (json.JSONDecodeError, OSError):
                continue
            entries = data.get("entries", [])
            passed = sum(1 for e in entries if e.get("passed"))
            baselines.append(
                {
                    "name": path.stem,
                    "model": data.get("model", ""),
                    "provider": data.get("provider", ""),
                    "created": data.get("created", ""),
                    "tests": len(entries),
                    "passed": passed,
                    "failed": len(entries) - passed,
                }
            )
        return baselines

    def compare(
        self,
        baseline_name: str,
        current_results: list[TestResult],
    ) -> RegressionReport:
        """Compare current results against a baseline."""
        baseline_entries = self.load_baseline(baseline_name)

        # Index baseline by test name
        baseline_by_name: dict[str, BaselineEntry] = {e.test_name: e for e in baseline_entries}

        new_failures: list[dict[str, Any]] = []
        new_passes: list[dict[str, Any]] = []
        stable_failures: list[dict[str, Any]] = []
        stable_passes: list[dict[str, Any]] = []
        score_changes: list[dict[str, Any]] = []

        for result in current_results:
            baseline_entry = baseline_by_name.get(result.test_name)
            if baseline_entry is None:
                # New test not in baseline -- treat as new failure or new pass
                if result.passed:
                    new_passes.append(
                        {
                            "test_name": result.test_name,
                            "current_passed": True,
                            "current_score": result.score,
                            "note": "new test (not in baseline)",
                        }
                    )
                else:
                    current_fp = self._fingerprint(result)
                    new_failures.append(
                        {
                            "test_name": result.test_name,
                            "current_passed": False,
                            "current_score": result.score,
                            "fingerprint": current_fp,
                            "error": result.error or result.reason or "",
                            "note": "new test (not in baseline)",
                        }
                    )
                continue

            # Both exist -- compare
            if baseline_entry.passed and not result.passed:
                # Regression: was passing, now failing
                current_fp = self._fingerprint(result)
                new_failures.append(
                    {
                        "test_name": result.test_name,
                        "baseline_passed": True,
                        "baseline_score": baseline_entry.score,
                        "current_passed": False,
                        "current_score": result.score,
                        "fingerprint": current_fp,
                        "error": result.error or result.reason or "",
                    }
                )
            elif not baseline_entry.passed and result.passed:
                # Improvement: was failing, now passing
                new_passes.append(
                    {
                        "test_name": result.test_name,
                        "baseline_passed": False,
                        "baseline_score": baseline_entry.score,
                        "current_passed": True,
                        "current_score": result.score,
                        "baseline_fingerprint": baseline_entry.failure_fingerprint,
                    }
                )
            elif not baseline_entry.passed and not result.passed:
                # Stable failure
                current_fp = self._fingerprint(result)
                same_mode = current_fp == baseline_entry.failure_fingerprint
                stable_failures.append(
                    {
                        "test_name": result.test_name,
                        "baseline_score": baseline_entry.score,
                        "current_score": result.score,
                        "baseline_fingerprint": baseline_entry.failure_fingerprint,
                        "current_fingerprint": current_fp,
                        "same_failure_mode": same_mode,
                        "error": result.error or result.reason or "",
                    }
                )
            else:
                # Both passing
                stable_passes.append(
                    {
                        "test_name": result.test_name,
                        "baseline_score": baseline_entry.score,
                        "current_score": result.score,
                    }
                )

            # Check for significant score changes regardless of pass/fail
            delta = result.score - baseline_entry.score
            if abs(delta) >= self.SCORE_CHANGE_THRESHOLD:
                score_changes.append(
                    {
                        "test_name": result.test_name,
                        "baseline_score": baseline_entry.score,
                        "current_score": result.score,
                        "delta": round(delta, 4),
                        "direction": "improved" if delta > 0 else "regressed",
                    }
                )

        return RegressionReport(
            new_failures=new_failures,
            new_passes=new_passes,
            stable_failures=stable_failures,
            stable_passes=stable_passes,
            score_changes=score_changes,
        )

    def _fingerprint(self, result: TestResult) -> str:
        """Create a failure fingerprint from error type + test name + tool calls."""
        parts = [
            result.test_name,
            result.error or "",
            str(result.tool_calls or []),
        ]
        return hashlib.sha256("|".join(parts).encode()).hexdigest()[:12]

    def generate_regression_report(self, report: RegressionReport) -> str:
        """Generate a markdown regression report."""
        lines: list[str] = []
        lines.append("# Regression Report")
        lines.append("")
        lines.append(f"**Generated:** {datetime.now().isoformat()}")
        lines.append("")

        # Summary counts
        total = (
            len(report.new_failures)
            + len(report.new_passes)
            + len(report.stable_failures)
            + len(report.stable_passes)
        )
        lines.append(f"**Total tests compared:** {total}")
        lines.append("")

        # New failures (regressions)
        lines.append(f"## New Failures ({len(report.new_failures)})")
        lines.append("")
        if report.new_failures:
            lines.append("| Test | Baseline Score | Current Score | Fingerprint | Error |")
            lines.append("|------|---------------|---------------|-------------|-------|")
            for f in report.new_failures:
                b_score = f.get("baseline_score", "N/A")
                lines.append(
                    f"| {f['test_name']} | {b_score} "
                    f"| {f['current_score']} "
                    f"| `{f.get('fingerprint', '')}` "
                    f"| {f.get('error', '')[:80]} |"
                )
            lines.append("")
        else:
            lines.append("No new failures detected.")
            lines.append("")

        # Improvements
        lines.append(f"## Improvements ({len(report.new_passes)})")
        lines.append("")
        if report.new_passes:
            lines.append("| Test | Baseline Score | Current Score |")
            lines.append("|------|---------------|---------------|")
            for p in report.new_passes:
                b_score = p.get("baseline_score", "N/A")
                lines.append(f"| {p['test_name']} | {b_score} | {p['current_score']} |")
            lines.append("")
        else:
            lines.append("No improvements detected.")
            lines.append("")

        # Stable failures
        lines.append(f"## Stable Failures ({len(report.stable_failures)})")
        lines.append("")
        if report.stable_failures:
            lines.append("| Test | Score | Same Failure Mode | Fingerprint | Error |")
            lines.append("|------|-------|-------------------|-------------|-------|")
            for sf in report.stable_failures:
                same = "Yes" if sf.get("same_failure_mode") else "No"
                lines.append(
                    f"| {sf['test_name']} | {sf['current_score']} "
                    f"| {same} "
                    f"| `{sf.get('current_fingerprint', '')}` "
                    f"| {sf.get('error', '')[:80]} |"
                )
            lines.append("")
        else:
            lines.append("No stable failures.")
            lines.append("")

        # Stable passes
        lines.append(f"## Stable Passes ({len(report.stable_passes)})")
        lines.append("")
        if report.stable_passes:
            lines.append("| Test | Baseline Score | Current Score |")
            lines.append("|------|---------------|---------------|")
            for sp in report.stable_passes:
                lines.append(
                    f"| {sp['test_name']} | {sp['baseline_score']} | {sp['current_score']} |"
                )
            lines.append("")
        else:
            lines.append("No stable passes.")
            lines.append("")

        # Score changes
        lines.append(f"## Score Changes ({len(report.score_changes)})")
        lines.append("")
        if report.score_changes:
            lines.append("| Test | Baseline | Current | Delta | Direction |")
            lines.append("|------|----------|---------|-------|-----------|")
            for sc in report.score_changes:
                lines.append(
                    f"| {sc['test_name']} | {sc['baseline_score']} "
                    f"| {sc['current_score']} "
                    f"| {sc['delta']:+.4f} "
                    f"| {sc['direction']} |"
                )
            lines.append("")
        else:
            lines.append("No significant score changes.")
            lines.append("")

        return "\n".join(lines)
