"""Tests for testmcpy.evals.evaluator_packs."""

import pytest
import yaml

from testmcpy.evals.evaluator_packs import (
    BUILTIN_PACKS,
    _custom_packs,
    list_packs,
    register_custom_pack,
    resolve_evaluator_pack,
    resolve_evaluators,
)


@pytest.fixture(autouse=True)
def _clean_custom_packs():
    """Ensure custom packs don't leak between tests."""
    _custom_packs.clear()
    yield
    _custom_packs.clear()


class TestResolveEvaluatorPack:
    def test_resolve_tool_basics(self):
        evals = resolve_evaluator_pack("tool-basics")
        names = [e["name"] for e in evals]
        assert "execution_successful" in names
        assert "was_mcp_tool_called" in names

    def test_resolve_security_v1(self):
        evals = resolve_evaluator_pack("security-v1")
        names = [e["name"] for e in evals]
        assert "no_leaked_data" in names
        assert "no_hallucination" in names

    def test_resolve_chart_creation(self):
        evals = resolve_evaluator_pack("chart-creation")
        names = [e["name"] for e in evals]
        assert "was_chart_created" in names
        assert "url_is_valid" in names

    def test_resolve_sql_execution(self):
        evals = resolve_evaluator_pack("sql-execution")
        names = [e["name"] for e in evals]
        assert "sql_query_valid" in names

    def test_resolve_response_quality(self):
        evals = resolve_evaluator_pack("response-quality")
        names = [e["name"] for e in evals]
        assert "no_hallucination" in names

    def test_unknown_pack_raises(self):
        with pytest.raises(ValueError, match="Unknown evaluator pack"):
            resolve_evaluator_pack("nonexistent-pack")

    def test_returns_copy_not_reference(self):
        evals1 = resolve_evaluator_pack("tool-basics")
        evals2 = resolve_evaluator_pack("tool-basics")
        assert evals1 is not evals2


class TestResolveEvaluators:
    def test_expands_packs(self):
        configs = [
            {"pack": "tool-basics"},
            {"name": "response_includes", "args": {"content": ["dashboard"]}},
        ]
        resolved = resolve_evaluators(configs)
        names = [e.get("name") for e in resolved]
        assert "execution_successful" in names
        assert "was_mcp_tool_called" in names
        assert "response_includes" in names

    def test_no_packs(self):
        configs = [{"name": "execution_successful"}]
        resolved = resolve_evaluators(configs)
        assert resolved == configs

    def test_empty_list(self):
        assert resolve_evaluators([]) == []

    def test_multiple_packs(self):
        configs = [{"pack": "tool-basics"}, {"pack": "security-v1"}]
        resolved = resolve_evaluators(configs)
        assert len(resolved) == len(BUILTIN_PACKS["tool-basics"]["evaluators"]) + len(
            BUILTIN_PACKS["security-v1"]["evaluators"]
        )


class TestRegisterCustomPack:
    def test_register_and_resolve(self):
        register_custom_pack(
            name="my-pack",
            evaluators=[{"name": "custom_eval"}],
            version="2.0",
            description="A custom pack",
        )
        evals = resolve_evaluator_pack("my-pack")
        assert len(evals) == 1
        assert evals[0]["name"] == "custom_eval"

    def test_custom_overrides_builtin(self):
        register_custom_pack(
            name="tool-basics",
            evaluators=[{"name": "overridden_eval"}],
        )
        evals = resolve_evaluator_pack("tool-basics")
        assert len(evals) == 1
        assert evals[0]["name"] == "overridden_eval"


class TestListPacks:
    def test_list_includes_builtins(self):
        packs = list_packs()
        assert "tool-basics" in packs
        assert "security-v1" in packs
        assert packs["tool-basics"]["source"] == "builtin"

    def test_list_includes_custom(self):
        register_custom_pack(name="my-pack", evaluators=[{"name": "x"}])
        packs = list_packs()
        assert "my-pack" in packs
        assert packs["my-pack"]["source"] == "custom"
        assert packs["my-pack"]["evaluator_count"] == 1

    def test_list_has_required_fields(self):
        packs = list_packs()
        for _name, info in packs.items():
            assert "version" in info
            assert "description" in info
            assert "evaluator_count" in info
            assert "source" in info


class TestLoadCustomPacksFromYaml:
    def test_load_from_yaml(self, tmp_path):
        from testmcpy.evals.evaluator_packs import load_custom_packs_from_yaml

        pack_file = tmp_path / "packs.yaml"
        pack_file.write_text(
            yaml.dump(
                {
                    "packs": {
                        "yaml-pack": {
                            "version": "1.0",
                            "description": "From YAML",
                            "evaluators": [{"name": "eval_a"}, {"name": "eval_b"}],
                        }
                    }
                }
            )
        )
        count = load_custom_packs_from_yaml(str(pack_file))
        assert count == 1
        evals = resolve_evaluator_pack("yaml-pack")
        assert len(evals) == 2

    def test_load_missing_file_raises(self, tmp_path):
        from testmcpy.evals.evaluator_packs import load_custom_packs_from_yaml

        with pytest.raises(FileNotFoundError):
            load_custom_packs_from_yaml(str(tmp_path / "missing.yaml"))
