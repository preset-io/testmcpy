"""The assistant/chatbot provider now prices its token usage by the
(overridden) model instead of hardcoding cost = 0."""

from testmcpy.src.llm_integration import AssistantProvider


def _provider(model="default", model_override=None):
    return AssistantProvider(
        model=model,
        model_override=model_override,
        conversations_path="/c",
        completions_path="/x",
    )


def test_priced_when_model_known():
    # claude-sonnet-4-6 = $3/1M in, $15/1M out → 69k+69k tokens ≈ $1.242
    cost = _provider(model="claude-sonnet-4-6")._estimate_cost(
        {"prompt": 69000, "completion": 69000, "total": 138000}
    )
    assert round(cost, 3) == 1.242


def test_model_override_is_priced():
    cost = _provider(model="default", model_override="claude-sonnet-4-6")._estimate_cost(
        {"prompt": 1_000_000, "completion": 0}
    )
    assert round(cost, 2) == 3.00


def test_default_model_is_unpriceable():
    # The chatbot backend picks the model server-side; we can't price it.
    assert _provider(model="default")._estimate_cost({"prompt": 1000, "completion": 1000}) == 0.0


def test_no_usage_is_zero():
    assert _provider(model="claude-sonnet-4-6")._estimate_cost(None) == 0.0
    assert _provider(model="claude-sonnet-4-6")._estimate_cost({}) == 0.0
