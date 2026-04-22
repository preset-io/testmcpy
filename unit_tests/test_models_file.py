"""
Unit tests for --models-file support — AC 9.

Tests YAML model file parsing for the evolving benchmark asset.

Story: SC-104612 — Trial Benchmark
"""

import yaml

from testmcpy.src.comparison_runner import ModelConfig


class TestModelsFileFormat:
    """Test parsing of benchmark_models.yaml format."""

    def test_dict_format_with_models_key(self, tmp_path):
        """Standard format: {models: [{provider, model}, ...]}"""
        models_yaml = {
            "models": [
                {"provider": "anthropic", "model": "claude-sonnet-4-6-20260401"},
                {"provider": "openai", "model": "gpt-5.4"},
                {"provider": "google", "model": "gemini-3.1-pro"},
            ]
        }
        file = tmp_path / "benchmark_models.yaml"
        file.write_text(yaml.dump(models_yaml))

        data = yaml.safe_load(file.read_text())
        specs = [f"{m['provider']}:{m['model']}" for m in data["models"]]
        assert len(specs) == 3
        assert "anthropic:claude-sonnet-4-6-20260401" in specs
        assert "openai:gpt-5.4" in specs

    def test_list_format(self, tmp_path):
        """Simple list format: [provider:model, ...]"""
        models_yaml = [
            "anthropic:claude-sonnet-4-6",
            "openai:gpt-5.4",
            "xai:grok-4-0709",
        ]
        file = tmp_path / "models.yaml"
        file.write_text(yaml.dump(models_yaml))

        data = yaml.safe_load(file.read_text())
        assert isinstance(data, list)
        specs = [str(m) for m in data]
        assert len(specs) == 3

    def test_model_config_from_parsed_specs(self, tmp_path):
        """Parsed specs should convert to ModelConfig."""
        models_yaml = {
            "models": [
                {"provider": "anthropic", "model": "claude-sonnet-4-6"},
                {"provider": "xai", "model": "grok-4-0709"},
            ]
        }
        file = tmp_path / "models.yaml"
        file.write_text(yaml.dump(models_yaml))

        data = yaml.safe_load(file.read_text())
        specs = [f"{m['provider']}:{m['model']}" for m in data["models"]]
        configs = [ModelConfig.from_string(s) for s in specs]

        assert configs[0].provider == "anthropic"
        assert configs[0].model == "claude-sonnet-4-6"
        assert configs[1].provider == "xai"
        assert configs[1].model == "grok-4-0709"

    def test_full_benchmark_models_file(self, tmp_path):
        """Full benchmark_models.yaml with all tiers from Max's list."""
        models_yaml = {
            "description": "Trial Benchmark model list for GA decision",
            "models": [
                # Must test
                {"provider": "anthropic", "model": "claude-sonnet-4-6-20260401", "tier": "must"},
                {"provider": "anthropic", "model": "claude-opus-4-7-20260401", "tier": "must"},
                {"provider": "openai", "model": "gpt-5.4", "tier": "must"},
                {"provider": "google", "model": "gemini-3.1-pro", "tier": "must"},
                {"provider": "google", "model": "gemini-3-flash", "tier": "must"},
                {"provider": "xai", "model": "grok-4-0709", "tier": "must"},
                {"provider": "xai", "model": "grok-3-fast", "tier": "must"},
                # Should test
                {"provider": "openrouter", "model": "deepseek/deepseek-chat-v3", "tier": "should"},
                {"provider": "google", "model": "gemini-3.1-flash-lite", "tier": "should"},
                # Nice to test
                {"provider": "openrouter", "model": "moonshotai/kimi-k2", "tier": "nice"},
                {"provider": "openrouter", "model": "zhipu/glm-4-plus", "tier": "nice"},
                {"provider": "openrouter", "model": "qwen/qwen3-coder", "tier": "nice"},
                # Ceiling
                {"provider": "openai", "model": "gpt-5.4-pro", "tier": "ceiling"},
            ],
        }
        file = tmp_path / "benchmark_models.yaml"
        file.write_text(yaml.dump(models_yaml, default_flow_style=False))

        data = yaml.safe_load(file.read_text())
        assert len(data["models"]) == 13
        specs = [f"{m['provider']}:{m['model']}" for m in data["models"]]
        configs = [ModelConfig.from_string(s) for s in specs]
        assert len(configs) == 13

        # Verify we can add a new model trivially (the "evolving asset" aspect)
        data["models"].append(
            {"provider": "anthropic", "model": "claude-sonnet-5-0", "tier": "must"}
        )
        assert len(data["models"]) == 14

    def test_models_file_empty(self, tmp_path):
        """Empty models file should produce empty list."""
        file = tmp_path / "empty.yaml"
        file.write_text("models: []\n")
        data = yaml.safe_load(file.read_text())
        specs = [f"{m['provider']}:{m['model']}" for m in data.get("models", [])]
        assert len(specs) == 0

    def test_models_file_with_extra_fields(self, tmp_path):
        """Extra fields (tier, notes) should be ignored when parsing specs."""
        models_yaml = {
            "models": [
                {
                    "provider": "anthropic",
                    "model": "claude-sonnet-4-6",
                    "tier": "must",
                    "notes": "Primary candidate for GA",
                },
            ]
        }
        file = tmp_path / "models.yaml"
        file.write_text(yaml.dump(models_yaml))

        data = yaml.safe_load(file.read_text())
        spec = f"{data['models'][0]['provider']}:{data['models'][0]['model']}"
        config = ModelConfig.from_string(spec)
        assert config.provider == "anthropic"
        assert config.model == "claude-sonnet-4-6"
