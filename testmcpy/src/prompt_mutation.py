"""
Prompt mutation engine for testing LLM robustness.

Generates prompt variations to verify that the same tool is called
regardless of how the prompt is phrased (typos, casual language,
verbose wording, etc.).
"""

import copy
import random
import time
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class MutationResult:
    """Result from running a single mutation variant."""

    strategy: str
    prompt: str
    description: str
    passed: bool = False
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    matched_original: bool = False
    score: float = 0.0
    duration: float = 0.0
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MutationTestReport:
    """Report from running all mutations for a single test case."""

    test_name: str
    original_prompt: str
    original_tool_calls: list[str] = field(default_factory=list)
    mutation_results: list[MutationResult] = field(default_factory=list)
    consistency_score: float = 0.0
    total_mutations: int = 0
    matched_mutations: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class PromptMutator:
    """Generate prompt variations to test robustness."""

    def __init__(self, seed: int | None = None):
        self._rng = random.Random(seed)

    def mutate(self, prompt: str, strategies: list[str] | None = None) -> list[dict]:
        """Generate mutations of a prompt.

        Returns list of {"strategy": str, "prompt": str, "description": str}
        """
        strategies = strategies or [
            "rephrase",
            "typo",
            "casual",
            "verbose",
            "minimal",
            "negation",
        ]
        mutations = []
        for strategy in strategies:
            mutated = getattr(self, f"_mutate_{strategy}", self._mutate_identity)(prompt)
            mutations.append(
                {
                    "strategy": strategy,
                    "prompt": mutated,
                    "description": f"{strategy} mutation",
                }
            )
        return mutations

    def _mutate_typo(self, prompt: str) -> str:
        """Introduce realistic typos."""
        words = prompt.split()
        if len(words) < 3:
            return prompt
        idx = self._rng.randint(1, len(words) - 1)
        word = words[idx]
        if len(word) > 3:
            # Swap two adjacent chars
            i = self._rng.randint(0, len(word) - 2)
            word = word[:i] + word[i + 1] + word[i] + word[i + 2 :]
        words[idx] = word
        return " ".join(words)

    def _mutate_casual(self, prompt: str) -> str:
        """Make prompt more casual/informal."""
        replacements = {
            "Show me": "show",
            "List": "gimme",
            "What is": "whats",
            "How many": "how many",
            "Create": "make",
            "Generate": "create",
            "please": "",
            "Could you": "can u",
            "I would like": "i want",
        }
        result = prompt
        for formal, casual in replacements.items():
            result = result.replace(formal, casual)
        return result.strip()

    def _mutate_verbose(self, prompt: str) -> str:
        """Make prompt more verbose/detailed."""
        prefixes = [
            "I would really appreciate it if you could ",
            "Could you please help me by ",
            "I'm looking for information about this: ",
        ]
        return self._rng.choice(prefixes) + prompt.lower()

    def _mutate_minimal(self, prompt: str) -> str:
        """Reduce to minimal keywords."""
        stopwords = {
            "the",
            "a",
            "an",
            "is",
            "are",
            "was",
            "were",
            "be",
            "been",
            "to",
            "of",
            "in",
            "for",
            "on",
            "with",
            "at",
            "by",
            "from",
            "me",
            "my",
            "i",
            "you",
            "your",
            "please",
            "could",
            "would",
            "can",
        }
        words = [w for w in prompt.split() if w.lower() not in stopwords]
        return " ".join(words)

    def _mutate_rephrase(self, prompt: str) -> str:
        """Simple rephrasing."""
        rephrases = {
            "list": "show all",
            "show": "display",
            "get": "retrieve",
            "create": "make",
            "what": "which",
            "how many": "count of",
            "dashboards": "dashboard list",
            "charts": "chart list",
        }
        result = prompt.lower()
        for orig, new in rephrases.items():
            result = result.replace(orig, new, 1)
        return result.capitalize()

    def _mutate_negation(self, prompt: str) -> str:
        """Ask the same thing via negation."""
        return f"Don't skip this - {prompt.lower()}"

    def _mutate_identity(self, prompt: str) -> str:
        return prompt


class MutationTestRunner:
    """Run tests with prompt mutations and check consistency."""

    def __init__(self, test_runner, mutator: PromptMutator | None = None):
        self.runner = test_runner
        self.mutator = mutator or PromptMutator()

    async def run_mutation_test(
        self,
        test_case,
        strategies: list[str] | None = None,
    ) -> MutationTestReport:
        """Run a test with its original prompt and all mutations.

        Returns a MutationTestReport with original result and mutation results,
        plus consistency score (% of mutations that matched original tool calls).
        """
        # Run original test
        original_result = await self.runner._run_test_with_retry(test_case)
        original_tool_names = _extract_tool_names(original_result.tool_calls)

        report = MutationTestReport(
            test_name=test_case.name,
            original_prompt=test_case.prompt,
            original_tool_calls=original_tool_names,
        )

        # Generate mutations
        mutations = self.mutator.mutate(test_case.prompt, strategies=strategies)
        report.total_mutations = len(mutations)

        for mutation in mutations:
            # Create a modified copy of the test case with the mutated prompt
            mutated_case = _clone_test_case_with_prompt(
                test_case, mutation["prompt"], mutation["strategy"]
            )

            mutation_result = MutationResult(
                strategy=mutation["strategy"],
                prompt=mutation["prompt"],
                description=mutation["description"],
            )

            start = time.time()
            try:
                result = await self.runner._run_test_with_retry(mutated_case)
                mutation_result.passed = result.passed
                mutation_result.tool_calls = result.tool_calls
                mutation_result.score = result.score

                # Check if the same tools were called
                mutated_tool_names = _extract_tool_names(result.tool_calls)
                mutation_result.matched_original = set(mutated_tool_names) == set(
                    original_tool_names
                )
                if mutation_result.matched_original:
                    report.matched_mutations += 1

            except Exception as ex:  # noqa: BLE001 — we want to capture all failures
                mutation_result.error = str(ex)

            mutation_result.duration = time.time() - start
            report.mutation_results.append(mutation_result)

        # Calculate consistency score
        if report.total_mutations > 0:
            report.consistency_score = report.matched_mutations / report.total_mutations

        return report


def _extract_tool_names(tool_calls: list[dict[str, Any]]) -> list[str]:
    """Extract tool names from a list of tool call dicts."""
    names = []
    for tc in tool_calls:
        name = tc.get("name") or tc.get("tool_name") or tc.get("function", "")
        if name:
            names.append(name)
    return names


def _clone_test_case_with_prompt(test_case, new_prompt: str, suffix: str):
    """Create a shallow copy of a TestCase with a different prompt."""
    from .test_runner import TestCase

    return TestCase(
        name=f"{test_case.name}__{suffix}",
        prompt=new_prompt,
        evaluators=copy.deepcopy(test_case.evaluators),
        metadata=test_case.metadata.copy(),
        expected_tools=test_case.expected_tools,
        timeout=test_case.timeout,
        auth=test_case.auth,
        steps=test_case.steps,
        load_test=test_case.load_test,
    )
