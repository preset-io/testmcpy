"""
Metamorphic relation testing for MCP test cases.

Metamorphic testing checks invariant properties across related inputs.
If input changes in a predictable way, output should change (or not change)
predictably. This is useful for validating LLM tool-calling behavior
without needing exact expected outputs.

Example usage:
    tester = MetamorphicTester(runner)
    results = await tester.test_relation(test_case, BUILTIN_RELATIONS["idempotency"])
"""

import copy
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .test_runner import TestCase, TestResult, TestRunner


@dataclass
class MetamorphicRelation:
    """A metamorphic relation between two test inputs.

    Defines how to transform a test case and what invariant should hold
    between the source and follow-up test results.

    Attributes:
        name: Unique identifier for this relation.
        description: Human-readable explanation of what property is tested.
        source_transform: Function to create a follow-up test case from source.
        output_relation: Function that checks whether the relation holds
            between source result and follow-up result. Returns True if
            the relation is satisfied.
    """

    name: str
    description: str
    source_transform: Callable[[TestCase], TestCase]
    output_relation: Callable[[TestResult, TestResult], bool]


def _extract_tool_names(result: TestResult) -> set[str]:
    """Extract unique tool names from a TestResult's tool_calls."""
    names: set[str] = set()
    for call in result.tool_calls:
        name = call.get("name") or call.get("tool_name") or call.get("tool")
        if name:
            names.add(name)
    return names


def _identity_transform(tc: TestCase) -> TestCase:
    """Return a deep copy of the test case (identity transform)."""
    return copy.deepcopy(tc)


def _rephrase_prompt(prompt: str) -> str:
    """Slightly rephrase a prompt while preserving intent.

    Applies simple deterministic transformations rather than
    using an LLM to rephrase. This keeps the transform predictable.
    """
    rephrased = prompt.strip()

    # Add "Please" prefix if not present
    lower = rephrased.lower()
    if not lower.startswith("please"):
        rephrased = "Please " + rephrased[0].lower() + rephrased[1:]

    # Add "for me" before trailing punctuation or at end
    if rephrased.endswith("."):
        rephrased = rephrased[:-1] + " for me."
    elif rephrased.endswith("?"):
        pass  # Don't modify questions
    else:
        rephrased = rephrased + " for me"

    return rephrased


def _rephrase_transform(tc: TestCase) -> TestCase:
    """Create a follow-up test case with a slightly rephrased prompt."""
    modified = copy.deepcopy(tc)
    modified.prompt = _rephrase_prompt(tc.prompt)
    modified.name = f"{tc.name}_rephrased"
    return modified


def _minor_variation_transform(tc: TestCase) -> TestCase:
    """Create a follow-up test case with a minor prompt variation.

    Adds a polite suffix that should not change tool selection or
    key parameters.
    """
    modified = copy.deepcopy(tc)
    suffix = " (thanks in advance)"
    modified.prompt = tc.prompt.rstrip(".!") + suffix
    modified.name = f"{tc.name}_variation"
    return modified


def _extract_tool_params(result: TestResult) -> list[dict[str, Any]]:
    """Extract tool call parameters from a TestResult.

    Returns a list of dicts with 'name' and 'input' keys.
    """
    params = []
    for call in result.tool_calls:
        name = call.get("name") or call.get("tool_name") or call.get("tool")
        input_data = call.get("input") or call.get("args") or call.get("arguments") or {}
        if name:
            params.append({"name": name, "input": input_data})
    return params


def _idempotency_check(r1: TestResult, r2: TestResult) -> bool:
    """Check that two runs produce the same tool names."""
    return _extract_tool_names(r1) == _extract_tool_names(r2)


def _tool_selection_stability_check(r1: TestResult, r2: TestResult) -> bool:
    """Check that rephrasing preserves tool selection."""
    return _extract_tool_names(r1) == _extract_tool_names(r2)


def _parameter_preservation_check(r1: TestResult, r2: TestResult) -> bool:
    """Check that minor prompt variation preserves key tool parameters.

    Compares tool names and their input parameters. Tool names must match
    exactly. Input parameters are compared by key overlap — if the same
    tool is called, at least 80% of parameter keys should be the same.
    """
    names1 = _extract_tool_names(r1)
    names2 = _extract_tool_names(r2)

    # Tool names must match
    if names1 != names2:
        return False

    # Compare parameters for matching tools
    params1 = _extract_tool_params(r1)
    params2 = _extract_tool_params(r2)

    for p1 in params1:
        # Find matching tool call in second result
        matching = [p for p in params2 if p["name"] == p1["name"]]
        if not matching:
            return False

        # Check key overlap (at least 80%)
        keys1 = set(p1["input"].keys()) if isinstance(p1["input"], dict) else set()
        keys2 = (
            set(matching[0]["input"].keys()) if isinstance(matching[0]["input"], dict) else set()
        )

        if keys1 and keys2:
            overlap = len(keys1 & keys2) / max(len(keys1), len(keys2))
            if overlap < 0.8:
                return False

    return True


BUILTIN_RELATIONS: dict[str, MetamorphicRelation] = {
    "idempotency": MetamorphicRelation(
        name="idempotency",
        description="Running the same query twice should call the same tools",
        source_transform=_identity_transform,
        output_relation=_idempotency_check,
    ),
    "tool_selection_stability": MetamorphicRelation(
        name="tool_selection_stability",
        description="Rephrasing a prompt should call the same tools",
        source_transform=_rephrase_transform,
        output_relation=_tool_selection_stability_check,
    ),
    "parameter_preservation": MetamorphicRelation(
        name="parameter_preservation",
        description="Minor prompt variation should preserve key tool parameters",
        source_transform=_minor_variation_transform,
        output_relation=_parameter_preservation_check,
    ),
}


@dataclass
class MetamorphicTestResult:
    """Result from a single metamorphic relation test."""

    relation: str
    description: str
    passed: bool
    source_test_name: str
    source_prompt: str
    followup_prompt: str
    source_tools: list[str]
    followup_tools: list[str]
    source_result: TestResult | None = None
    followup_result: TestResult | None = None
    error: str | None = None
    duration_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary (excludes full TestResult objects)."""
        return {
            "relation": self.relation,
            "description": self.description,
            "passed": self.passed,
            "source_test_name": self.source_test_name,
            "source_prompt": self.source_prompt,
            "followup_prompt": self.followup_prompt,
            "source_tools": self.source_tools,
            "followup_tools": self.followup_tools,
            "error": self.error,
            "duration_ms": self.duration_ms,
        }


class MetamorphicTester:
    """Runs metamorphic relation tests against an MCP test runner.

    Takes a TestRunner instance and executes pairs of test cases
    (source + transformed follow-up) to verify that metamorphic
    relations hold.
    """

    def __init__(self, test_runner: TestRunner):
        self.runner = test_runner

    async def test_relation(
        self,
        test_case: TestCase,
        relation: MetamorphicRelation,
    ) -> MetamorphicTestResult:
        """Run source test, apply transform, run follow-up, check relation.

        Args:
            test_case: The original test case to use as the source.
            relation: The metamorphic relation to test.

        Returns:
            MetamorphicTestResult with pass/fail and details.
        """
        start_time = datetime.now(timezone.utc)
        followup_prompt = ""

        try:
            # Run source test
            source_result = await self.runner._run_test_with_retry(test_case)

            # Apply transform to get follow-up test case
            modified_case = relation.source_transform(test_case)
            followup_prompt = modified_case.prompt

            # Run follow-up test
            followup_result = await self.runner._run_test_with_retry(modified_case)

            # Check whether the relation holds
            relation_holds = relation.output_relation(source_result, followup_result)

            elapsed = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000

            return MetamorphicTestResult(
                relation=relation.name,
                description=relation.description,
                passed=relation_holds,
                source_test_name=test_case.name,
                source_prompt=test_case.prompt,
                followup_prompt=followup_prompt,
                source_tools=sorted(_extract_tool_names(source_result)),
                followup_tools=sorted(_extract_tool_names(followup_result)),
                source_result=source_result,
                followup_result=followup_result,
                duration_ms=elapsed,
            )

        except (KeyError, TypeError, AttributeError, ValueError) as e:
            elapsed = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            return MetamorphicTestResult(
                relation=relation.name,
                description=relation.description,
                passed=False,
                source_test_name=test_case.name,
                source_prompt=test_case.prompt,
                followup_prompt=followup_prompt,
                source_tools=[],
                followup_tools=[],
                error=str(e),
                duration_ms=elapsed,
            )

    async def test_all_relations(
        self,
        test_case: TestCase,
        relations: list[str] | None = None,
    ) -> list[MetamorphicTestResult]:
        """Test all applicable relations for a test case.

        Args:
            test_case: The test case to check relations against.
            relations: Optional list of relation names to test.
                If None, all builtin relations are tested.

        Returns:
            List of MetamorphicTestResult for each relation tested.
        """
        if relations is None:
            to_test = list(BUILTIN_RELATIONS.values())
        else:
            to_test = []
            for name in relations:
                if name in BUILTIN_RELATIONS:
                    to_test.append(BUILTIN_RELATIONS[name])

        results = []
        for relation in to_test:
            result = await self.test_relation(test_case, relation)
            results.append(result)

        return results

    def generate_report(self, results: list[MetamorphicTestResult]) -> str:
        """Generate a markdown report of metamorphic test results.

        Args:
            results: List of MetamorphicTestResult from test runs.

        Returns:
            Markdown-formatted report string.
        """
        lines: list[str] = []
        lines.append("# Metamorphic Relation Test Report")
        lines.append("")
        lines.append(
            f"**Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}"
        )
        lines.append("")

        # Summary
        total = len(results)
        passed = sum(1 for r in results if r.passed)
        failed = total - passed
        lines.append("## Summary")
        lines.append("")
        lines.append(f"- **Total relations tested:** {total}")
        lines.append(f"- **Passed:** {passed}")
        lines.append(f"- **Failed:** {failed}")
        if total > 0:
            lines.append(f"- **Pass rate:** {passed / total:.0%}")
        lines.append("")

        # Details
        lines.append("## Results")
        lines.append("")

        for r in results:
            status = "PASS" if r.passed else "FAIL"
            lines.append(f"### {r.relation} — {status}")
            lines.append("")
            lines.append(f"**Description:** {r.description}")
            lines.append("")
            lines.append(f"- **Test case:** `{r.source_test_name}`")
            lines.append(f"- **Source prompt:** `{r.source_prompt}`")
            lines.append(f"- **Follow-up prompt:** `{r.followup_prompt}`")
            lines.append(f"- **Source tools:** {', '.join(r.source_tools) or '(none)'}")
            lines.append(f"- **Follow-up tools:** {', '.join(r.followup_tools) or '(none)'}")
            lines.append(f"- **Duration:** {r.duration_ms:.0f}ms")
            if r.error:
                lines.append(f"- **Error:** {r.error}")
            lines.append("")

        return "\n".join(lines)
