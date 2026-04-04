"""Tests for testmcpy.src.metamorphic."""

from testmcpy.src.metamorphic import (
    BUILTIN_RELATIONS,
    MetamorphicTestResult,
    _identity_transform,
    _rephrase_prompt,
    _rephrase_transform,
)
from testmcpy.src.test_runner import TestCase


def _make_test_case(name="test_foo", prompt="List all dashboards"):
    return TestCase(
        name=name,
        prompt=prompt,
        evaluators=[],
    )


class TestBuiltinRelations:
    def test_builtin_relations_exist(self):
        assert "idempotency" in BUILTIN_RELATIONS
        assert "tool_selection_stability" in BUILTIN_RELATIONS
        assert "parameter_preservation" in BUILTIN_RELATIONS

    def test_builtin_relations_have_required_fields(self):
        for name, rel in BUILTIN_RELATIONS.items():
            assert rel.name == name
            assert rel.description
            assert callable(rel.source_transform)
            assert callable(rel.output_relation)

    def test_three_builtin_relations(self):
        assert len(BUILTIN_RELATIONS) == 3


class TestIdentityTransform:
    def test_identity_preserves_test_case(self):
        tc = _make_test_case()
        result = _identity_transform(tc)
        assert result.name == tc.name
        assert result.prompt == tc.prompt
        assert result.evaluators == tc.evaluators

    def test_identity_returns_deep_copy(self):
        tc = _make_test_case()
        result = _identity_transform(tc)
        assert result is not tc
        # Modifying copy should not affect original
        result.name = "modified"
        assert tc.name == "test_foo"


class TestRephraseTransform:
    def test_rephrase_modifies_prompt(self):
        tc = _make_test_case(prompt="List all dashboards")
        result = _rephrase_transform(tc)
        assert result.prompt != tc.prompt
        assert result.name == "test_foo_rephrased"

    def test_rephrase_adds_please_prefix(self):
        result = _rephrase_prompt("List all dashboards")
        assert result.lower().startswith("please")

    def test_rephrase_adds_for_me(self):
        result = _rephrase_prompt("List all dashboards")
        assert "for me" in result

    def test_rephrase_preserves_question_mark(self):
        result = _rephrase_prompt("What are the dashboards?")
        assert result.endswith("?")
        assert "for me" not in result

    def test_rephrase_handles_period(self):
        result = _rephrase_prompt("Show me the charts.")
        assert result.endswith("for me.")

    def test_rephrase_does_not_double_please(self):
        result = _rephrase_prompt("Please list charts")
        # Should not add "Please" again
        assert not result.lower().startswith("please please")


class TestMetamorphicTestResult:
    def test_dataclass_creation(self):
        r = MetamorphicTestResult(
            relation="idempotency",
            description="test desc",
            passed=True,
            source_test_name="test_foo",
            source_prompt="List charts",
            followup_prompt="List charts",
            source_tools=["list_charts"],
            followup_tools=["list_charts"],
        )
        assert r.passed is True
        assert r.error is None
        assert r.duration_ms == 0.0

    def test_to_dict(self):
        r = MetamorphicTestResult(
            relation="idempotency",
            description="test desc",
            passed=False,
            source_test_name="test_foo",
            source_prompt="p1",
            followup_prompt="p2",
            source_tools=["t1"],
            followup_tools=["t2"],
            error="mismatch",
            duration_ms=150.5,
        )
        d = r.to_dict()
        assert d["relation"] == "idempotency"
        assert d["passed"] is False
        assert d["error"] == "mismatch"
        assert d["duration_ms"] == 150.5
        # to_dict should not include full TestResult objects
        assert "source_result" not in d
        assert "followup_result" not in d

    def test_defaults(self):
        r = MetamorphicTestResult(
            relation="x",
            description="d",
            passed=True,
            source_test_name="t",
            source_prompt="p",
            followup_prompt="p",
            source_tools=[],
            followup_tools=[],
        )
        assert r.source_result is None
        assert r.followup_result is None
        assert r.error is None
