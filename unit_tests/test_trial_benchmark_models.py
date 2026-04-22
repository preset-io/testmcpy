"""
Unit tests for Trial Benchmark model registry — AC 2.

Verifies all models Max requested are in the registry with correct
pricing, aliases, and provider wiring.

Story: SC-104612 — Trial Benchmark
"""

import pytest

from testmcpy.src.llm_integration import create_llm_provider
from testmcpy.src.model_registry import (
    ALL_MODELS,
    Provider,
    estimate_cost,
    get_default_model,
    get_model,
    get_models_by_provider,
    list_providers,
)


# ── Must-test models (from Max's list) ───────────────────────────────────────


class TestMustTestModels:
    """All 'Must test' models should be in the registry."""

    def test_claude_sonnet_4_6(self):
        m = get_model("claude-sonnet-4-6")
        assert m is not None, "Claude Sonnet 4.6 missing from registry"
        assert m.provider == Provider.ANTHROPIC
        assert m.input_price_per_1m > 0

    def test_claude_opus_4_7(self):
        m = get_model("claude-opus-4-7")
        assert m is not None, "Claude Opus 4.7 missing from registry"
        assert m.provider == Provider.ANTHROPIC
        assert m.input_price_per_1m >= 15.0

    def test_gpt_5_4(self):
        m = get_model("gpt-5.4")
        assert m is not None, "GPT-5.4 missing from registry"
        assert m.provider == Provider.OPENAI

    def test_gemini_3_1_pro(self):
        m = get_model("gemini-3.1-pro")
        assert m is not None, "Gemini 3.1 Pro missing from registry"
        assert m.provider == Provider.GOOGLE

    def test_gemini_3_flash(self):
        m = get_model("gemini-3-flash")
        assert m is not None, "Gemini 3 Flash missing from registry"
        assert m.provider == Provider.GOOGLE

    def test_grok_4(self):
        m = get_model("grok-4")
        assert m is not None, "Grok 4 missing from registry"
        assert m.provider == Provider.XAI

    def test_grok_fast(self):
        m = get_model("grok-3-fast")
        assert m is not None, "Grok 3 Fast missing from registry"
        assert m.provider == Provider.XAI


class TestShouldTestModels:
    """All 'Should test' models should be in the registry."""

    def test_deepseek_v3(self):
        m = get_model("deepseek-v3")
        assert m is not None, "DeepSeek V3 missing from registry"
        assert m.provider == Provider.OPENROUTER

    def test_gemini_3_1_flash_lite(self):
        m = get_model("gemini-3.1-flash-lite")
        assert m is not None, "Gemini 3.1 Flash Lite missing from registry"
        assert m.provider == Provider.GOOGLE


class TestNiceToTestModels:
    """'Nice to test' models should be in the registry."""

    def test_kimi_k2(self):
        m = get_model("kimi-k2")
        assert m is not None, "Kimi K2 missing from registry"
        assert m.provider == Provider.OPENROUTER

    def test_glm(self):
        m = get_model("glm-4")
        assert m is not None, "GLM missing from registry"
        assert m.provider == Provider.OPENROUTER

    def test_qwen3_coder(self):
        m = get_model("qwen3-coder")
        assert m is not None, "Qwen3 Coder missing from registry"
        assert m.provider == Provider.OPENROUTER


class TestBenchmarkCeiling:
    """Benchmark ceiling model should be in the registry."""

    def test_gpt_5_4_pro(self):
        m = get_model("gpt-5.4-pro")
        assert m is not None, "GPT-5.4 Pro missing from registry"
        assert m.provider == Provider.OPENAI
        assert m.input_price_per_1m >= 15.0  # Premium pricing


# ── Provider wiring ──────────────────────────────────────────────────────────


class TestProviderWiring:
    """Verify providers are registered in the factory."""

    def test_xai_provider_creates(self):
        """xai provider should instantiate without error."""
        provider = create_llm_provider("xai", "grok-4-0709", api_key="test-key")
        assert provider is not None
        assert provider.model == "grok-4-0709"

    def test_grok_alias_creates(self):
        """'grok' alias should create XAIProvider."""
        provider = create_llm_provider("grok", "grok-4-0709", api_key="test-key")
        assert provider is not None

    def test_openrouter_provider_creates(self):
        """openrouter provider should instantiate."""
        provider = create_llm_provider(
            "openrouter", "deepseek/deepseek-chat-v3", api_key="test-key"
        )
        assert provider is not None

    def test_xai_base_url(self):
        """XAIProvider should use api.x.ai base URL."""
        provider = create_llm_provider("xai", "grok-4-0709", api_key="test-key")
        assert "x.ai" in provider.base_url


# ── Model registry integrity ─────────────────────────────────────────────────


class TestRegistryIntegrity:
    """Verify the registry is well-formed after additions."""

    def test_no_duplicate_ids(self):
        """No two models should share the same ID."""
        ids = [m.id for m in ALL_MODELS]
        assert len(ids) == len(set(ids)), (
            f"Duplicate model IDs: {[x for x in ids if ids.count(x) > 1]}"
        )

    def test_no_duplicate_aliases(self):
        """No alias should map to more than one model."""
        seen = {}
        for m in ALL_MODELS:
            for alias in m.aliases:
                key = alias.lower()
                if key in seen:
                    pytest.fail(f"Alias '{alias}' used by both {seen[key]} and {m.id}")
                seen[key] = m.id

    def test_all_models_have_pricing(self):
        """Every model should have non-negative pricing."""
        for m in ALL_MODELS:
            assert m.input_price_per_1m >= 0, f"{m.id} has negative input price"
            assert m.output_price_per_1m >= 0, f"{m.id} has negative output price"

    def test_all_models_have_context_window(self):
        """Every model should have a positive context window."""
        for m in ALL_MODELS:
            assert m.context_window > 0, f"{m.id} has no context window"

    def test_xai_provider_in_list(self):
        """xAI provider should be listed."""
        providers = list_providers()
        provider_ids = [p["id"] for p in providers]
        assert "xai" in provider_ids

    def test_openrouter_provider_in_list(self):
        """OpenRouter provider should be listed."""
        providers = list_providers()
        provider_ids = [p["id"] for p in providers]
        assert "openrouter" in provider_ids

    def test_xai_has_default_model(self):
        """xAI should have a default model."""
        default = get_default_model("xai")
        assert default is not None

    def test_openrouter_has_default_model(self):
        """OpenRouter should have a default model."""
        default = get_default_model("openrouter")
        assert default is not None


# ── Cost estimation ──────────────────────────────────────────────────────────


class TestCostEstimation:
    """Verify cost estimation works for new models."""

    def test_grok_cost(self):
        cost = estimate_cost("grok-4-0709", input_tokens=1000, output_tokens=500)
        assert cost > 0

    def test_deepseek_cost(self):
        cost = estimate_cost("deepseek/deepseek-chat-v3", input_tokens=1000, output_tokens=500)
        assert cost > 0

    def test_gpt_5_4_cost(self):
        cost = estimate_cost("gpt-5.4", input_tokens=1000, output_tokens=500)
        assert cost > 0

    def test_claude_sonnet_4_6_cost(self):
        cost = estimate_cost("claude-sonnet-4-6-20260401", input_tokens=1000, output_tokens=500)
        assert cost > 0

    def test_gemini_3_1_pro_cost(self):
        cost = estimate_cost("gemini-3.1-pro", input_tokens=1000, output_tokens=500)
        assert cost > 0
