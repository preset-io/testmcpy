"""Unit tests for the benchmark matrix builder + websocket ad-hoc helpers."""

import pytest

from testmcpy.benchmarks import (
    BenchmarkComboError,
    build_benchmark_combos,
    combo_label,
)
from testmcpy.server.websocket import _assistant_config_from_data, _inline_auth_from_data


def test_single_model_repeat():
    combos = build_benchmark_combos(["m1"], repeat=3)
    assert len(combos) == 3
    assert [c.iteration for c in combos] == [1, 2, 3]
    assert all(c.model == "m1" and c.provider is None and c.profile is None for c in combos)


def test_accepts_comma_string_or_list():
    from_str = build_benchmark_combos("m1,m2", providers="assistant", repeat=1)
    from_list = build_benchmark_combos(["m1", "m2"], providers=["assistant"], repeat=1)
    assert [combo_label(c) for c in from_str] == [combo_label(c) for c in from_list]
    assert [combo_label(c) for c in from_str] == ["assistant/m1", "assistant/m2"]


def test_single_provider_broadcasts_to_all_models():
    combos = build_benchmark_combos(["m1", "m2", "m3"], providers="assistant")
    assert all(c.provider == "assistant" for c in combos)
    assert len(combos) == 3


def test_aligned_providers_per_model():
    combos = build_benchmark_combos(["m1", "m2"], providers=["assistant", "claude-sdk"])
    assert combos[0].provider == "assistant"
    assert combos[1].provider == "claude-sdk"


def test_provider_count_mismatch_raises():
    with pytest.raises(BenchmarkComboError):
        build_benchmark_combos(["m1", "m2", "m3"], providers=["a", "b"])


def test_profiles_are_a_product_dimension():
    combos = build_benchmark_combos(["m1"], profiles=["p1", "p2"], repeat=2)
    # 1 model × 2 profiles × 2 repeats = 4
    assert len(combos) == 4
    assert {c.profile for c in combos} == {"p1", "p2"}


def test_full_matrix_size_and_order():
    combos = build_benchmark_combos(["m1", "m2"], providers="assistant", profiles=["p1"], repeat=2)
    # 2 models × 1 profile × 2 repeats = 4; order is model → profile → iteration
    assert len(combos) == 4
    assert [(c.model, c.iteration) for c in combos] == [
        ("m1", 1),
        ("m1", 2),
        ("m2", 1),
        ("m2", 2),
    ]


def test_no_models_and_bad_repeat_raise():
    with pytest.raises(BenchmarkComboError):
        build_benchmark_combos([])
    with pytest.raises(BenchmarkComboError):
        build_benchmark_combos(["m1"], repeat=0)


def test_combo_label_includes_profile():
    (combo,) = build_benchmark_combos(["m1"], providers="assistant", profiles=["prod"])
    assert combo_label(combo) == "assistant/m1 @ prod"


# --- websocket ad-hoc connection helpers (no saved profile) -----------------


def test_inline_auth_jwt_from_data():
    auth = _inline_auth_from_data(
        {
            "auth_type": "jwt",
            "jwt_url": "https://example.com/auth/",
            "jwt_token": "tok",
            "jwt_secret": "sec",
        }
    )
    assert auth == {
        "type": "jwt",
        "api_url": "https://example.com/auth/",
        "api_token": "tok",
        "api_secret": "sec",
    }


def test_inline_auth_none_without_auth_type():
    assert _inline_auth_from_data({"mcp_url": "https://x/mcp"}) is None


def test_assistant_config_from_data_uses_jwt_fallback():
    cfg = _assistant_config_from_data(
        {
            "workspace_hash": "abc",
            "domain": "us1a.example.com",
            "jwt_url": "https://example.com/auth/",
            "jwt_token": "tok",
            "jwt_secret": "sec",
            "assistant_conversations_path": "/c",
            "assistant_completions_path": "/x",
        }
    )
    assert cfg["workspace_hash"] == "abc"
    assert cfg["domain"] == "us1a.example.com"
    # assistant api_* fall back to the jwt_* values
    assert cfg["api_url"] == "https://example.com/auth/"
    assert cfg["api_token"] == "tok"
    assert cfg["api_secret"] == "sec"
    assert cfg["conversations_path"] == "/c"
    assert cfg["completions_path"] == "/x"
    # empty/absent keys are omitted so callers can setdefault safely
    assert "environment" not in cfg
