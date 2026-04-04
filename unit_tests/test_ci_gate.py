"""Tests for testmcpy.src.ci_gate."""

import yaml

from testmcpy.src.ci_gate import CIGateConfig, load_gate_config


def _make_results(passed_names, failed_names=None):
    results = []
    for name in passed_names:
        results.append({"test_name": name, "passed": True})
    for name in failed_names or []:
        results.append({"test_name": name, "passed": False})
    return results


class TestEvaluatePassRate:
    def test_all_passing(self):
        config = CIGateConfig(min_pass_rate=80.0)
        results = _make_results(["t1", "t2", "t3", "t4", "t5"])
        outcome = config.evaluate(results)
        assert outcome["passed"] is True
        assert outcome["pass_rate"] == 100.0
        assert outcome["failures"] == []

    def test_below_min_pass_rate(self):
        config = CIGateConfig(min_pass_rate=80.0)
        results = _make_results(["t1"], ["t2", "t3", "t4", "t5"])
        outcome = config.evaluate(results)
        assert outcome["passed"] is False
        assert any("below minimum" in f for f in outcome["failures"])

    def test_exact_threshold(self):
        config = CIGateConfig(min_pass_rate=80.0)
        results = _make_results(["t1", "t2", "t3", "t4"], ["t5"])
        outcome = config.evaluate(results)
        assert outcome["pass_rate"] == 80.0
        assert outcome["passed"] is True

    def test_empty_results(self):
        config = CIGateConfig(min_pass_rate=80.0)
        outcome = config.evaluate([])
        assert outcome["passed"] is False
        assert outcome["pass_rate"] == 0


class TestEvaluateMaxFailures:
    def test_within_limit(self):
        config = CIGateConfig(min_pass_rate=0.0, max_failures=2)
        results = _make_results(["t1", "t2", "t3"], ["t4", "t5"])
        outcome = config.evaluate(results)
        assert outcome["passed"] is True

    def test_exceeds_limit(self):
        config = CIGateConfig(min_pass_rate=0.0, max_failures=1)
        results = _make_results(["t1"], ["t2", "t3"])
        outcome = config.evaluate(results)
        assert outcome["passed"] is False
        assert any("exceeds max" in f for f in outcome["failures"])

    def test_no_limit_set(self):
        config = CIGateConfig(min_pass_rate=0.0, max_failures=None)
        results = _make_results([], ["t1", "t2", "t3", "t4", "t5"])
        outcome = config.evaluate(results)
        assert outcome["passed"] is True


class TestEvaluateRequiredTests:
    def test_required_tests_pass(self):
        config = CIGateConfig(min_pass_rate=0.0, required_tests=["t1", "t2"])
        results = _make_results(["t1", "t2", "t3"])
        outcome = config.evaluate(results)
        assert outcome["passed"] is True

    def test_required_tests_missing(self):
        config = CIGateConfig(min_pass_rate=0.0, required_tests=["t1", "t_critical"])
        results = _make_results(["t1"], ["t_critical"])
        outcome = config.evaluate(results)
        assert outcome["passed"] is False
        assert any("Required tests failed" in f for f in outcome["failures"])

    def test_required_test_not_in_results(self):
        config = CIGateConfig(min_pass_rate=0.0, required_tests=["t_missing"])
        results = _make_results(["t1"])
        outcome = config.evaluate(results)
        assert outcome["passed"] is False


class TestEvaluateRegressions:
    def test_regressions_block(self):
        config = CIGateConfig(min_pass_rate=0.0, block_on_regression=True)
        results = _make_results(["t1", "t2"])
        regressions = [{"test_name": "t3"}, {"test_name": "t4"}]
        outcome = config.evaluate(results, regressions=regressions)
        assert outcome["passed"] is False
        assert any("regression" in f for f in outcome["failures"])

    def test_regressions_ignored_when_disabled(self):
        config = CIGateConfig(min_pass_rate=0.0, block_on_regression=False)
        results = _make_results(["t1", "t2"])
        regressions = [{"test_name": "t3"}]
        outcome = config.evaluate(results, regressions=regressions)
        assert outcome["passed"] is True

    def test_no_regressions(self):
        config = CIGateConfig(min_pass_rate=0.0, block_on_regression=True)
        results = _make_results(["t1"])
        outcome = config.evaluate(results, regressions=None)
        assert outcome["passed"] is True


class TestLoadGateConfig:
    def test_load_from_yaml(self, tmp_path):
        config_file = tmp_path / "gate.yaml"
        config_file.write_text(
            yaml.dump(
                {
                    "min_pass_rate": 90.0,
                    "max_failures": 3,
                    "required_tests": ["critical_test"],
                    "block_on_regression": False,
                }
            )
        )
        config = load_gate_config(str(config_file))
        assert config.min_pass_rate == 90.0
        assert config.max_failures == 3
        assert config.required_tests == ["critical_test"]
        assert config.block_on_regression is False

    def test_defaults_when_missing(self, tmp_path):
        config = load_gate_config(str(tmp_path / "nonexistent.yaml"))
        assert config.min_pass_rate == 80.0
        assert config.max_failures is None
        assert config.required_tests == []
        assert config.block_on_regression is True

    def test_partial_yaml(self, tmp_path):
        config_file = tmp_path / "gate.yaml"
        config_file.write_text(yaml.dump({"min_pass_rate": 95.0}))
        config = load_gate_config(str(config_file))
        assert config.min_pass_rate == 95.0
        assert config.max_failures is None
        assert config.block_on_regression is True


class TestMultipleFailureReasons:
    def test_multiple_failures_combined(self):
        config = CIGateConfig(
            min_pass_rate=90.0,
            max_failures=0,
            required_tests=["t_critical"],
            block_on_regression=True,
        )
        results = _make_results(["t1"], ["t_critical", "t3"])
        regressions = [{"test_name": "t_reg"}]
        outcome = config.evaluate(results, regressions=regressions)
        assert outcome["passed"] is False
        # Should have multiple failure reasons
        assert len(outcome["failures"]) >= 3
