"""
Integration tests for the LLM provider factory and tool call parsing.

Tests cover:
- Provider factory (create_llm_provider) — instantiation without API calls
- LLMResult dataclass creation and field access
- Evaluator factory (create_evaluator) — instantiation and evaluation
- Tool name matching (_match_tool_name)
- New evaluators: response_not_includes, no_leaked_data, url_is_valid,
  success_rate_above, latency_percentile, response_matches_pattern
"""

import pytest

from testmcpy.evals.base_evaluators import _match_tool_name, create_evaluator
from testmcpy.src.llm_integration import (
    AnthropicProvider,
    AssistantProvider,
    LLMResult,
    OpenAIProvider,
    OpenRouterProvider,
    create_llm_provider,
)

# ---------------------------------------------------------------------------
# Provider Factory Tests
# ---------------------------------------------------------------------------


class TestProviderFactory:
    def test_create_anthropic_provider(self):
        provider = create_llm_provider("anthropic", "claude-haiku-4-5", api_key="test")
        assert isinstance(provider, AnthropicProvider)

    def test_create_openai_provider(self):
        provider = create_llm_provider("openai", "gpt-4o", api_key="test")
        assert isinstance(provider, OpenAIProvider)

    def test_create_assistant_provider(self):
        provider = create_llm_provider(
            "assistant", "default", workspace_hash="test", domain="test.com"
        )
        assert isinstance(provider, AssistantProvider)

    def test_create_openrouter_provider(self):
        provider = create_llm_provider("openrouter", "anthropic/claude-haiku-4-5", api_key="test")
        assert isinstance(provider, OpenRouterProvider)

    def test_create_unknown_provider_raises(self):
        with pytest.raises(ValueError):
            create_llm_provider("nonexistent", "model")

    def test_provider_aliases(self):
        # claude-cli, claude-code should map to ClaudeSDKProvider
        p1 = create_llm_provider("claude-cli", "claude-sonnet-4-20250514")
        p2 = create_llm_provider("claude-code", "claude-sonnet-4-20250514")
        assert type(p1).__name__ == "ClaudeSDKProvider"
        assert type(p2).__name__ == "ClaudeSDKProvider"


# ---------------------------------------------------------------------------
# LLMResult Parsing Tests
# ---------------------------------------------------------------------------


class TestLLMResult:
    def test_llm_result_creation(self):
        result = LLMResult(
            response="Hello",
            tool_calls=[{"name": "health_check", "arguments": {}}],
            tool_results=[],
            token_usage={"total": 100},
            cost=0.01,
            duration=1.5,
        )
        assert result.response == "Hello"
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0]["name"] == "health_check"
        assert result.cost == 0.01
        assert result.duration == 1.5

    def test_llm_result_empty(self):
        result = LLMResult(
            response="",
            tool_calls=[],
            tool_results=[],
            token_usage={},
            cost=0.0,
            duration=0.0,
        )
        assert result.response == ""
        assert result.tool_calls == []
        assert result.tool_results == []


# ---------------------------------------------------------------------------
# Evaluator Factory Tests
# ---------------------------------------------------------------------------


class TestEvaluatorFactory:
    def test_create_all_evaluators(self):
        """Verify all registered evaluators can be instantiated."""
        simple_evaluators = ["execution_successful", "no_leaked_data", "url_is_valid"]
        for name in simple_evaluators:
            eval_instance = create_evaluator(name)
            assert eval_instance.name is not None

    def test_create_evaluator_with_args(self):
        e = create_evaluator("response_includes", content=["hello"])
        assert "response_includes" in e.name

    def test_create_unknown_evaluator_raises(self):
        with pytest.raises(ValueError):
            create_evaluator("nonexistent_evaluator")


# ---------------------------------------------------------------------------
# Tool Name Matching Tests
# ---------------------------------------------------------------------------


class TestToolNameMatching:
    def test_match_tool_name_exact(self):
        assert _match_tool_name("health_check", "health_check")

    def test_match_tool_name_prefix(self):
        assert _match_tool_name("mcp__preset__health_check", "health_check")

    def test_match_tool_name_no_match(self):
        assert not _match_tool_name("list_charts", "health_check")


# ---------------------------------------------------------------------------
# New Evaluator Tests
# ---------------------------------------------------------------------------


class TestResponseNotIncludes:
    def test_pass(self):
        e = create_evaluator("response_not_includes", content=["error", "failed"])
        result = e.evaluate({"response": "All dashboards loaded successfully"})
        assert result.passed

    def test_fail(self):
        e = create_evaluator("response_not_includes", content=["error"])
        result = e.evaluate({"response": "An error occurred"})
        assert not result.passed


class TestNoLeakedData:
    def test_pass(self):
        e = create_evaluator("no_leaked_data")
        result = e.evaluate({"response": "Here are your dashboards"})
        assert result.passed

    def test_fail_connection_string(self):
        e = create_evaluator("no_leaked_data")
        result = e.evaluate({"response": "Error connecting to postgresql://user:pass@host/db"})
        assert not result.passed


class TestUrlIsValid:
    def test_pass(self):
        e = create_evaluator("url_is_valid")
        result = e.evaluate({"response": "View at https://example.com/dashboard/1"})
        assert result.passed

    def test_no_urls(self):
        e = create_evaluator("url_is_valid")
        result = e.evaluate({"response": "No URL here"})
        assert not result.passed


class TestSuccessRateAbove:
    def test_pass(self):
        e = create_evaluator("success_rate_above", min_rate=0.8)
        results = [{"success": True}] * 9 + [{"success": False}]
        result = e.evaluate({"load_test_results": results})
        assert result.passed  # 90% > 80%

    def test_fail(self):
        e = create_evaluator("success_rate_above", min_rate=0.9)
        results = [{"success": True}] * 7 + [{"success": False}] * 3
        result = e.evaluate({"load_test_results": results})
        assert not result.passed  # 70% < 90%


class TestLatencyPercentile:
    def test_pass(self):
        e = create_evaluator("latency_percentile", percentile=95, max_seconds=10.0)
        results = [{"duration": i * 0.5} for i in range(20)]  # 0 to 9.5s
        result = e.evaluate({"load_test_results": results})
        assert result.passed


class TestResponseMatchesPattern:
    def test_pass(self):
        e = create_evaluator("response_matches_pattern", pattern=r"dashboard_id:\s*\d+")
        result = e.evaluate({"response": "Created dashboard_id: 42"})
        assert result.passed
