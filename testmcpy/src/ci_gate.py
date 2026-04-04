"""CI gate configuration for pass/fail thresholds."""

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class CIGateConfig:
    min_pass_rate: float = 80.0  # Minimum overall pass rate
    max_failures: int | None = None  # Max allowed failures (None = no limit)
    required_tests: list[str] = field(default_factory=list)  # Tests that MUST pass
    block_on_regression: bool = True  # Fail if regression detected vs baseline

    def evaluate(self, results: list[dict], regressions: list[dict] | None = None) -> dict:
        """Evaluate results against gate config.

        Args:
            results: List of test result dicts with "passed" and "test_name" keys.
            regressions: Optional list of regression dicts (from BaselineStore.compare).

        Returns:
            Dict with passed, pass_rate, failures, total, passed_count.
        """
        total = len(results)
        passed = sum(1 for r in results if r.get("passed"))
        pass_rate = (passed / total * 100) if total > 0 else 0

        failures = []
        if pass_rate < self.min_pass_rate:
            failures.append(f"Pass rate {pass_rate:.1f}% below minimum {self.min_pass_rate}%")
        if self.max_failures is not None and (total - passed) > self.max_failures:
            failures.append(f"{total - passed} failures exceeds max {self.max_failures}")
        if self.required_tests:
            result_map = {r.get("test_name"): r.get("passed") for r in results}
            missing = [t for t in self.required_tests if not result_map.get(t)]
            if missing:
                failures.append(f"Required tests failed: {missing}")
        if self.block_on_regression and regressions:
            failures.append(
                f"{len(regressions)} regression(s) detected: "
                + ", ".join(r.get("test_name", "?") for r in regressions[:5])
            )

        return {
            "passed": len(failures) == 0,
            "pass_rate": pass_rate,
            "failures": failures,
            "total": total,
            "passed_count": passed,
        }


def load_gate_config(path: str = ".testmcpy-gate.yaml") -> CIGateConfig:
    """Load gate config from YAML file."""
    config_path = Path(path)
    if not config_path.exists():
        return CIGateConfig()

    with open(config_path) as f:
        data = yaml.safe_load(f) or {}

    return CIGateConfig(
        min_pass_rate=float(data.get("min_pass_rate", 80.0)),
        max_failures=data.get("max_failures"),
        required_tests=data.get("required_tests") or [],
        block_on_regression=data.get("block_on_regression", True),
    )
