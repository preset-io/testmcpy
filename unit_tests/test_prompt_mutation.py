"""Tests for testmcpy.src.prompt_mutation."""

from testmcpy.src.prompt_mutation import MutationResult, PromptMutator


class TestPromptMutatorSeed:
    def test_seed_produces_reproducible_results(self):
        m1 = PromptMutator(seed=42)
        m2 = PromptMutator(seed=42)
        prompt = "Show me all the dashboards in my workspace"
        result1 = m1.mutate(prompt)
        result2 = m2.mutate(prompt)
        assert result1 == result2

    def test_different_seeds_produce_different_results(self):
        m1 = PromptMutator(seed=42)
        m2 = PromptMutator(seed=99)
        prompt = "Show me all the dashboards in my workspace"
        result1 = m1.mutate(prompt)
        result2 = m2.mutate(prompt)
        # At least one strategy should differ (typo or verbose use randomness)
        typo1 = next(r for r in result1 if r["strategy"] == "typo")
        typo2 = next(r for r in result2 if r["strategy"] == "typo")
        # They could theoretically be same but very unlikely with different seeds
        verbose1 = next(r for r in result1 if r["strategy"] == "verbose")
        verbose2 = next(r for r in result2 if r["strategy"] == "verbose")
        assert typo1["prompt"] != typo2["prompt"] or verbose1["prompt"] != verbose2["prompt"]


class TestMutateTypo:
    def test_typo_swaps_chars(self):
        m = PromptMutator(seed=42)
        prompt = "Show me all dashboards"
        result = m._mutate_typo(prompt)
        assert result != prompt
        # Should still have same number of words
        assert len(result.split()) == len(prompt.split())

    def test_typo_short_prompt_unchanged(self):
        m = PromptMutator(seed=42)
        prompt = "Hi there"
        result = m._mutate_typo(prompt)
        assert result == prompt  # < 3 words


class TestMutateCasual:
    def test_casual_replaces_formal(self):
        m = PromptMutator(seed=42)
        result = m._mutate_casual("Show me the dashboards please")
        assert "please" not in result
        assert "show" in result.lower()

    def test_casual_could_you(self):
        m = PromptMutator(seed=42)
        result = m._mutate_casual("Could you list the charts")
        assert "can u" in result


class TestMutateVerbose:
    def test_verbose_adds_prefix(self):
        m = PromptMutator(seed=42)
        result = m._mutate_verbose("List charts")
        assert result.endswith("list charts")
        assert len(result) > len("List charts")


class TestMutateMinimal:
    def test_minimal_removes_stopwords(self):
        m = PromptMutator(seed=42)
        result = m._mutate_minimal("Show me the dashboards in my workspace")
        assert "the" not in result.split()
        assert "me" not in result.split()
        assert "in" not in result.split()
        assert "my" not in result.split()
        assert "dashboards" in result


class TestMutateRephrase:
    def test_rephrase_substitutes(self):
        m = PromptMutator(seed=42)
        result = m._mutate_rephrase("list all charts")
        # "list" -> "show all", then "show" -> "display", "charts" -> "chart list"
        # Final: "display all all chart list"
        assert result.lower() != "list all charts"
        assert "display" in result.lower() or "show" in result.lower()

    def test_rephrase_capitalizes(self):
        m = PromptMutator(seed=42)
        result = m._mutate_rephrase("get dashboard info")
        assert result[0].isupper()


class TestMutateNegation:
    def test_negation_adds_prefix(self):
        m = PromptMutator(seed=42)
        result = m._mutate_negation("List all dashboards")
        assert result.startswith("Don't skip this - ")
        assert "list all dashboards" in result


class TestMutateAll:
    def test_mutate_returns_all_strategies(self):
        m = PromptMutator(seed=42)
        mutations = m.mutate("Show me all dashboards")
        strategies = [mut["strategy"] for mut in mutations]
        assert strategies == ["rephrase", "typo", "casual", "verbose", "minimal", "negation"]

    def test_mutate_custom_strategies(self):
        m = PromptMutator(seed=42)
        mutations = m.mutate("Show me all dashboards", strategies=["typo", "casual"])
        assert len(mutations) == 2
        assert mutations[0]["strategy"] == "typo"
        assert mutations[1]["strategy"] == "casual"

    def test_each_mutation_has_description(self):
        m = PromptMutator(seed=42)
        mutations = m.mutate("Hello world test prompt here")
        for mut in mutations:
            assert "strategy" in mut
            assert "prompt" in mut
            assert "description" in mut
            assert "mutation" in mut["description"]


class TestMutationResult:
    def test_to_dict(self):
        r = MutationResult(
            strategy="typo",
            prompt="Shwo me dashboards",
            description="typo mutation",
            passed=True,
            matched_original=True,
            score=1.0,
        )
        d = r.to_dict()
        assert d["strategy"] == "typo"
        assert d["passed"] is True
        assert d["matched_original"] is True

    def test_defaults(self):
        r = MutationResult(strategy="test", prompt="p", description="d")
        assert r.passed is False
        assert r.tool_calls == []
        assert r.error is None
