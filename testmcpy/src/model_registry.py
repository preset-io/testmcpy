"""
Model Registry for LLM providers.

Centralized definitions for all supported models with metadata including:
- Pricing information
- Context limits
- Capabilities (tool calling, streaming, etc.)
- Provider-specific details
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Provider(str, Enum):
    """Supported LLM providers."""

    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    GOOGLE = "google"
    GEMINI = "gemini"  # Alias for google
    GEMINI_CLI = "gemini-cli"  # Gemini CLI tool
    OLLAMA = "ollama"
    BEDROCK = "bedrock"  # AWS Bedrock (Anthropic models via AWS)
    CLAUDE_SDK = "claude-sdk"  # Claude Agent SDK (also handles claude-cli/claude-code)
    OPENROUTER = "openrouter"  # OpenRouter gateway to 100+ models
    XAI = "xai"  # xAI (Grok models) — OpenAI-compatible API


class ModelCapability(str, Enum):
    """Model capabilities."""

    TOOL_CALLING = "tool_calling"
    STREAMING = "streaming"
    VISION = "vision"
    CODE_EXECUTION = "code_execution"
    LONG_CONTEXT = "long_context"
    REASONING = "reasoning"


@dataclass
class ModelInfo:
    """Information about a specific model."""

    id: str
    name: str
    provider: Provider
    description: str
    context_window: int
    max_output_tokens: int
    input_price_per_1m: float  # USD per 1M input tokens
    output_price_per_1m: float  # USD per 1M output tokens
    capabilities: list[ModelCapability] = field(default_factory=list)
    family: str = ""
    is_default: bool = False
    is_deprecated: bool = False
    aliases: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "provider": self.provider.value,
            "description": self.description,
            "context_window": self.context_window,
            "max_output_tokens": self.max_output_tokens,
            "input_price_per_1m": self.input_price_per_1m,
            "output_price_per_1m": self.output_price_per_1m,
            "capabilities": [c.value for c in self.capabilities],
            "family": self.family,
            "is_default": self.is_default,
            "is_deprecated": self.is_deprecated,
            "aliases": self.aliases,
        }


# ============================================================
# Anthropic Claude Models
# ============================================================

CLAUDE_MODELS: list[ModelInfo] = [
    ModelInfo(
        id="claude-sonnet-4-6-20260401",
        name="Claude Sonnet 4.6",
        provider=Provider.ANTHROPIC,
        description="Latest Sonnet — fast, capable, best price/performance",
        context_window=1_000_000,
        max_output_tokens=16384,
        input_price_per_1m=3.00,
        output_price_per_1m=15.00,
        capabilities=[
            ModelCapability.TOOL_CALLING,
            ModelCapability.STREAMING,
            ModelCapability.VISION,
            ModelCapability.LONG_CONTEXT,
        ],
        family="claude-4.6",
        is_default=True,
        aliases=["claude-sonnet-4-6", "claude-sonnet-4.6", "sonnet-4.6", "sonnet"],
    ),
    ModelInfo(
        id="claude-opus-4-7-20260401",
        name="Claude Opus 4.7",
        provider=Provider.ANTHROPIC,
        description="Most capable Claude model — deep reasoning and analysis",
        context_window=1_000_000,
        max_output_tokens=16384,
        input_price_per_1m=15.00,
        output_price_per_1m=75.00,
        capabilities=[
            ModelCapability.TOOL_CALLING,
            ModelCapability.STREAMING,
            ModelCapability.VISION,
            ModelCapability.LONG_CONTEXT,
            ModelCapability.REASONING,
        ],
        family="claude-4.7",
        aliases=["claude-opus-4-7", "claude-opus-4.7", "opus-4.7", "opus"],
    ),
    ModelInfo(
        id="claude-sonnet-4-20250514",
        name="Claude Sonnet 4",
        provider=Provider.ANTHROPIC,
        description="Previous generation Sonnet",
        context_window=200_000,
        max_output_tokens=8192,
        input_price_per_1m=3.00,
        output_price_per_1m=15.00,
        capabilities=[
            ModelCapability.TOOL_CALLING,
            ModelCapability.STREAMING,
            ModelCapability.VISION,
            ModelCapability.LONG_CONTEXT,
        ],
        family="claude-4",
        aliases=["claude-sonnet-4", "claude-4-sonnet"],
    ),
    ModelInfo(
        id="claude-opus-4-20250514",
        name="Claude Opus 4",
        provider=Provider.ANTHROPIC,
        description="Previous generation Opus",
        context_window=200_000,
        max_output_tokens=8192,
        input_price_per_1m=15.00,
        output_price_per_1m=75.00,
        capabilities=[
            ModelCapability.TOOL_CALLING,
            ModelCapability.STREAMING,
            ModelCapability.VISION,
            ModelCapability.LONG_CONTEXT,
            ModelCapability.REASONING,
        ],
        family="claude-4",
        aliases=["claude-opus-4", "claude-4-opus"],
    ),
    ModelInfo(
        id="claude-3-5-haiku-20241022",
        name="Claude 3.5 Haiku",
        provider=Provider.ANTHROPIC,
        description="Fastest model for simple tasks and high throughput",
        context_window=200_000,
        max_output_tokens=8192,
        input_price_per_1m=0.80,
        output_price_per_1m=4.00,
        capabilities=[
            ModelCapability.TOOL_CALLING,
            ModelCapability.STREAMING,
            ModelCapability.VISION,
            ModelCapability.LONG_CONTEXT,
        ],
        family="claude-3.5",
        aliases=["claude-3-5-haiku", "claude-3-haiku", "haiku"],
    ),
    ModelInfo(
        id="claude-3-5-sonnet-20241022",
        name="Claude 3.5 Sonnet",
        provider=Provider.ANTHROPIC,
        description="Previous generation balanced model (deprecated - use Claude 4 Sonnet)",
        context_window=200_000,
        max_output_tokens=8192,
        input_price_per_1m=3.00,
        output_price_per_1m=15.00,
        capabilities=[
            ModelCapability.TOOL_CALLING,
            ModelCapability.STREAMING,
            ModelCapability.VISION,
            ModelCapability.LONG_CONTEXT,
        ],
        family="claude-3.5",
        is_deprecated=True,
        aliases=["claude-3-5-sonnet", "claude-3.5-sonnet"],
    ),
]

# ============================================================
# OpenAI Models
# ============================================================

OPENAI_MODELS: list[ModelInfo] = [
    ModelInfo(
        id="gpt-5.4",
        name="GPT-5.4",
        provider=Provider.OPENAI,
        description="Latest GPT model — strong tool-calling and reasoning",
        context_window=256_000,
        max_output_tokens=32768,
        input_price_per_1m=2.50,
        output_price_per_1m=10.00,
        capabilities=[
            ModelCapability.TOOL_CALLING,
            ModelCapability.STREAMING,
            ModelCapability.VISION,
            ModelCapability.LONG_CONTEXT,
            ModelCapability.REASONING,
        ],
        family="gpt-5",
        is_default=True,
        aliases=["gpt-5.4", "gpt5.4", "gpt5"],
    ),
    ModelInfo(
        id="gpt-5.4-pro",
        name="GPT-5.4 Pro",
        provider=Provider.OPENAI,
        description="GPT-5.4 Pro — benchmark ceiling model",
        context_window=256_000,
        max_output_tokens=32768,
        input_price_per_1m=15.00,
        output_price_per_1m=60.00,
        capabilities=[
            ModelCapability.TOOL_CALLING,
            ModelCapability.STREAMING,
            ModelCapability.VISION,
            ModelCapability.LONG_CONTEXT,
            ModelCapability.REASONING,
        ],
        family="gpt-5",
        aliases=["gpt-5.4-pro", "gpt5.4-pro"],
    ),
    ModelInfo(
        id="gpt-4o",
        name="GPT-4o",
        provider=Provider.OPENAI,
        description="Previous generation GPT-4 model with vision",
        context_window=128_000,
        max_output_tokens=16384,
        input_price_per_1m=2.50,
        output_price_per_1m=10.00,
        capabilities=[
            ModelCapability.TOOL_CALLING,
            ModelCapability.STREAMING,
            ModelCapability.VISION,
            ModelCapability.LONG_CONTEXT,
        ],
        family="gpt-4o",
        aliases=["gpt4o"],
    ),
    ModelInfo(
        id="gpt-4o-mini",
        name="GPT-4o Mini",
        provider=Provider.OPENAI,
        description="Smaller, faster, cheaper GPT-4o variant",
        context_window=128_000,
        max_output_tokens=16384,
        input_price_per_1m=0.15,
        output_price_per_1m=0.60,
        capabilities=[
            ModelCapability.TOOL_CALLING,
            ModelCapability.STREAMING,
            ModelCapability.VISION,
            ModelCapability.LONG_CONTEXT,
        ],
        family="gpt-4o",
        aliases=["gpt4o-mini"],
    ),
    ModelInfo(
        id="gpt-4-turbo",
        name="GPT-4 Turbo",
        provider=Provider.OPENAI,
        description="GPT-4 with improved speed and larger context",
        context_window=128_000,
        max_output_tokens=4096,
        input_price_per_1m=10.00,
        output_price_per_1m=30.00,
        capabilities=[
            ModelCapability.TOOL_CALLING,
            ModelCapability.STREAMING,
            ModelCapability.VISION,
            ModelCapability.LONG_CONTEXT,
        ],
        family="gpt-4",
        aliases=["gpt4-turbo"],
    ),
    ModelInfo(
        id="o1",
        name="o1",
        provider=Provider.OPENAI,
        description="Reasoning model for complex problem solving",
        context_window=200_000,
        max_output_tokens=100_000,
        input_price_per_1m=15.00,
        output_price_per_1m=60.00,
        capabilities=[
            ModelCapability.LONG_CONTEXT,
            ModelCapability.REASONING,
        ],
        family="o1",
        aliases=["openai-o1"],
    ),
    ModelInfo(
        id="o1-mini",
        name="o1-mini",
        provider=Provider.OPENAI,
        description="Faster reasoning model for coding and math",
        context_window=128_000,
        max_output_tokens=65536,
        input_price_per_1m=3.00,
        output_price_per_1m=12.00,
        capabilities=[
            ModelCapability.LONG_CONTEXT,
            ModelCapability.REASONING,
        ],
        family="o1",
        aliases=["openai-o1-mini"],
    ),
]

# ============================================================
# Google Gemini Models
# ============================================================

GEMINI_MODELS: list[ModelInfo] = [
    ModelInfo(
        id="gemini-3.1-pro",
        name="Gemini 3.1 Pro",
        provider=Provider.GOOGLE,
        description="Latest Gemini Pro — strong reasoning and tool-calling",
        context_window=2_000_000,
        max_output_tokens=65536,
        input_price_per_1m=1.25,
        output_price_per_1m=10.00,
        capabilities=[
            ModelCapability.TOOL_CALLING,
            ModelCapability.STREAMING,
            ModelCapability.VISION,
            ModelCapability.LONG_CONTEXT,
            ModelCapability.REASONING,
        ],
        family="gemini-3.1",
        is_default=True,
        aliases=["gemini-3.1-pro", "gemini-3-pro"],
    ),
    ModelInfo(
        id="gemini-3-flash",
        name="Gemini 3 Flash",
        provider=Provider.GOOGLE,
        description="Fast and efficient latest-gen Gemini",
        context_window=1_000_000,
        max_output_tokens=65536,
        input_price_per_1m=0.15,
        output_price_per_1m=0.60,
        capabilities=[
            ModelCapability.TOOL_CALLING,
            ModelCapability.STREAMING,
            ModelCapability.VISION,
            ModelCapability.LONG_CONTEXT,
        ],
        family="gemini-3",
        aliases=["gemini-3-flash", "gemini-flash-3"],
    ),
    ModelInfo(
        id="gemini-3.1-flash-lite",
        name="Gemini 3.1 Flash Lite",
        provider=Provider.GOOGLE,
        description="Cheapest Gemini for high-throughput workloads",
        context_window=1_000_000,
        max_output_tokens=32768,
        input_price_per_1m=0.04,
        output_price_per_1m=0.15,
        capabilities=[
            ModelCapability.TOOL_CALLING,
            ModelCapability.STREAMING,
            ModelCapability.LONG_CONTEXT,
        ],
        family="gemini-3.1",
        aliases=["gemini-3.1-flash-lite", "gemini-flash-lite"],
    ),
    ModelInfo(
        id="gemini-2.5-pro",
        name="Gemini 2.5 Pro",
        provider=Provider.GOOGLE,
        description="Previous generation Gemini Pro with extended thinking",
        context_window=1_000_000,
        max_output_tokens=65536,
        input_price_per_1m=1.25,
        output_price_per_1m=10.00,
        capabilities=[
            ModelCapability.TOOL_CALLING,
            ModelCapability.STREAMING,
            ModelCapability.VISION,
            ModelCapability.LONG_CONTEXT,
            ModelCapability.REASONING,
        ],
        family="gemini-2.5",
        aliases=["gemini-2.5-pro-preview"],
    ),
    ModelInfo(
        id="gemini-2.5-flash",
        name="Gemini 2.5 Flash",
        provider=Provider.GOOGLE,
        description="Previous generation fast Gemini",
        context_window=1_000_000,
        max_output_tokens=65536,
        input_price_per_1m=0.15,
        output_price_per_1m=0.60,
        capabilities=[
            ModelCapability.TOOL_CALLING,
            ModelCapability.STREAMING,
            ModelCapability.VISION,
            ModelCapability.LONG_CONTEXT,
        ],
        family="gemini-2.5",
        aliases=["gemini-2.5-flash-preview"],
    ),
    ModelInfo(
        id="gemini-2.0-flash",
        name="Gemini 2.0 Flash",
        provider=Provider.GOOGLE,
        description="Previous generation fast model",
        context_window=1_000_000,
        max_output_tokens=8192,
        input_price_per_1m=0.10,
        output_price_per_1m=0.40,
        capabilities=[
            ModelCapability.TOOL_CALLING,
            ModelCapability.STREAMING,
            ModelCapability.VISION,
            ModelCapability.LONG_CONTEXT,
        ],
        family="gemini-2.0",
        aliases=["gemini-2.0-flash-exp"],
    ),
    ModelInfo(
        id="gemini-1.5-pro",
        name="Gemini 1.5 Pro",
        provider=Provider.GOOGLE,
        description="Stable production model with long context",
        context_window=2_000_000,
        max_output_tokens=8192,
        input_price_per_1m=1.25,
        output_price_per_1m=5.00,
        capabilities=[
            ModelCapability.TOOL_CALLING,
            ModelCapability.STREAMING,
            ModelCapability.VISION,
            ModelCapability.LONG_CONTEXT,
        ],
        family="gemini-1.5",
        aliases=["gemini-pro"],
    ),
]

# ============================================================
# Claude SDK Models (covers claude-sdk, claude-cli, claude-code)
# ============================================================

CLAUDE_SDK_MODELS: list[ModelInfo] = [
    ModelInfo(
        id="claude-sdk-sonnet",
        name="Claude Agent SDK (Sonnet)",
        provider=Provider.CLAUDE_SDK,
        description="Claude Agent SDK with Sonnet 4.5",
        context_window=200_000,
        max_output_tokens=8192,
        input_price_per_1m=3.00,
        output_price_per_1m=15.00,
        capabilities=[
            ModelCapability.TOOL_CALLING,
            ModelCapability.STREAMING,
            ModelCapability.LONG_CONTEXT,
        ],
        family="claude-sdk",
        is_default=True,
        aliases=["sdk-sonnet", "claude-code", "cc-sonnet"],
    ),
    ModelInfo(
        id="claude-sdk-opus",
        name="Claude Agent SDK (Opus)",
        provider=Provider.CLAUDE_SDK,
        description="Claude Agent SDK with Opus 4.5",
        context_window=200_000,
        max_output_tokens=8192,
        input_price_per_1m=15.00,
        output_price_per_1m=75.00,
        capabilities=[
            ModelCapability.TOOL_CALLING,
            ModelCapability.STREAMING,
            ModelCapability.LONG_CONTEXT,
            ModelCapability.REASONING,
        ],
        family="claude-sdk",
        aliases=["sdk-opus", "cc-opus"],
    ),
]

# ============================================================
# Gemini CLI Models (wraps the Gemini CLI tool)
# ============================================================

GEMINI_CLI_MODELS: list[ModelInfo] = [
    ModelInfo(
        id="gemini-cli-2.5-pro",
        name="Gemini CLI (2.5 Pro)",
        provider=Provider.GEMINI_CLI,
        description="Gemini CLI with 2.5 Pro model",
        context_window=1_000_000,
        max_output_tokens=65536,
        input_price_per_1m=1.25,
        output_price_per_1m=10.00,
        capabilities=[
            ModelCapability.TOOL_CALLING,
            ModelCapability.LONG_CONTEXT,
            ModelCapability.REASONING,
        ],
        family="gemini-cli",
        is_default=True,
        aliases=["gemini-cli", "gcli-pro", "gcli-2.5-pro"],
    ),
    ModelInfo(
        id="gemini-cli-2.5-flash",
        name="Gemini CLI (2.5 Flash)",
        provider=Provider.GEMINI_CLI,
        description="Gemini CLI with 2.5 Flash model",
        context_window=1_000_000,
        max_output_tokens=65536,
        input_price_per_1m=0.15,
        output_price_per_1m=0.60,
        capabilities=[
            ModelCapability.TOOL_CALLING,
            ModelCapability.LONG_CONTEXT,
        ],
        family="gemini-cli",
        aliases=["gcli-flash", "gcli-2.5-flash"],
    ),
]

# ============================================================
# xAI Grok Models
# ============================================================

GROK_MODELS: list[ModelInfo] = [
    ModelInfo(
        id="grok-4-0709",
        name="Grok 4",
        provider=Provider.XAI,
        description="xAI flagship model with strong tool-calling",
        context_window=131_072,
        max_output_tokens=16384,
        input_price_per_1m=3.00,
        output_price_per_1m=15.00,
        capabilities=[
            ModelCapability.TOOL_CALLING,
            ModelCapability.STREAMING,
            ModelCapability.LONG_CONTEXT,
            ModelCapability.REASONING,
        ],
        family="grok-4",
        is_default=True,
        aliases=["grok-4", "grok-4.20", "grok4"],
    ),
    ModelInfo(
        id="grok-3-fast",
        name="Grok 3 Fast",
        provider=Provider.XAI,
        description="xAI fast inference model",
        context_window=131_072,
        max_output_tokens=16384,
        input_price_per_1m=0.60,
        output_price_per_1m=3.00,
        capabilities=[
            ModelCapability.TOOL_CALLING,
            ModelCapability.STREAMING,
            ModelCapability.LONG_CONTEXT,
        ],
        family="grok-3",
        aliases=["grok-3-fast", "grok-4.1-fast", "grok-fast"],
    ),
]

# ============================================================
# OpenRouter Models (DeepSeek, Kimi, GLM, Qwen, etc.)
# ============================================================

OPENROUTER_MODELS: list[ModelInfo] = [
    ModelInfo(
        id="deepseek/deepseek-chat-v3",
        name="DeepSeek V3",
        provider=Provider.OPENROUTER,
        description="DeepSeek V3 chat model via OpenRouter",
        context_window=128_000,
        max_output_tokens=8192,
        input_price_per_1m=0.27,
        output_price_per_1m=1.10,
        capabilities=[
            ModelCapability.TOOL_CALLING,
            ModelCapability.STREAMING,
            ModelCapability.LONG_CONTEXT,
        ],
        family="deepseek-v3",
        is_default=True,
        aliases=["deepseek-v3", "deepseek-v3.2", "deepseek-chat"],
    ),
    ModelInfo(
        id="moonshotai/kimi-k2",
        name="Kimi K2",
        provider=Provider.OPENROUTER,
        description="Moonshot AI Kimi K2 via OpenRouter",
        context_window=131_072,
        max_output_tokens=8192,
        input_price_per_1m=0.60,
        output_price_per_1m=2.40,
        capabilities=[
            ModelCapability.TOOL_CALLING,
            ModelCapability.STREAMING,
            ModelCapability.LONG_CONTEXT,
        ],
        family="kimi",
        aliases=["kimi-k2", "kimi-k2.5"],
    ),
    ModelInfo(
        id="zhipu/glm-4-plus",
        name="GLM-4 Plus",
        provider=Provider.OPENROUTER,
        description="Zhipu GLM-4 Plus via OpenRouter",
        context_window=128_000,
        max_output_tokens=4096,
        input_price_per_1m=1.40,
        output_price_per_1m=1.40,
        capabilities=[
            ModelCapability.TOOL_CALLING,
            ModelCapability.STREAMING,
            ModelCapability.LONG_CONTEXT,
        ],
        family="glm",
        aliases=["glm-4", "glm-5.1"],
    ),
    ModelInfo(
        id="qwen/qwen3-coder",
        name="Qwen3 Coder",
        provider=Provider.OPENROUTER,
        description="Alibaba Qwen3 Coder via OpenRouter",
        context_window=131_072,
        max_output_tokens=8192,
        input_price_per_1m=0.30,
        output_price_per_1m=1.20,
        capabilities=[
            ModelCapability.TOOL_CALLING,
            ModelCapability.STREAMING,
            ModelCapability.LONG_CONTEXT,
            ModelCapability.CODE_EXECUTION,
        ],
        family="qwen3",
        aliases=["qwen3-coder", "qwen3-coder-480b"],
    ),
]

# ============================================================
# Model Registry
# ============================================================

ALL_MODELS: list[ModelInfo] = (
    CLAUDE_MODELS
    + OPENAI_MODELS
    + GEMINI_MODELS
    + CLAUDE_SDK_MODELS
    + GEMINI_CLI_MODELS
    + GROK_MODELS
    + OPENROUTER_MODELS
)

# Build lookup dictionaries
_MODEL_BY_ID: dict[str, ModelInfo] = {m.id: m for m in ALL_MODELS}
_MODEL_BY_ALIAS: dict[str, ModelInfo] = {}
for model in ALL_MODELS:
    for alias in model.aliases:
        _MODEL_BY_ALIAS[alias.lower()] = model
    _MODEL_BY_ALIAS[model.id.lower()] = model

_MODELS_BY_PROVIDER: dict[Provider, list[ModelInfo]] = {}
for model in ALL_MODELS:
    if model.provider not in _MODELS_BY_PROVIDER:
        _MODELS_BY_PROVIDER[model.provider] = []
    _MODELS_BY_PROVIDER[model.provider].append(model)


def get_model(model_id: str) -> ModelInfo | None:
    """Get model info by ID or alias."""
    model_id_lower = model_id.lower()
    return _MODEL_BY_ID.get(model_id) or _MODEL_BY_ALIAS.get(model_id_lower)


def get_models_by_provider(provider: str | Provider) -> list[ModelInfo]:
    """Get all models for a provider."""
    if isinstance(provider, str):
        # Handle gemini alias first (maps to google)
        if provider.lower() == "gemini":
            provider = Provider.GOOGLE
        else:
            try:
                provider = Provider(provider.lower())
            except ValueError:
                return []
    elif provider == Provider.GEMINI:
        # Also handle enum alias
        provider = Provider.GOOGLE
    return _MODELS_BY_PROVIDER.get(provider, [])


def get_default_model(provider: str | Provider) -> ModelInfo | None:
    """Get the default model for a provider."""
    models = get_models_by_provider(provider)
    for model in models:
        if model.is_default:
            return model
    return models[0] if models else None


def list_providers() -> list[dict[str, Any]]:
    """List all available providers with their models."""
    result = []
    for provider in Provider:
        # Skip GEMINI alias - it's handled by GOOGLE
        if provider == Provider.GEMINI:
            continue
        models = get_models_by_provider(provider)
        if models:
            default = get_default_model(provider)
            result.append(
                {
                    "id": provider.value,
                    "name": provider.value.replace("-", " ").title(),
                    "model_count": len(models),
                    "default_model": default.id if default else None,
                    "models": [m.to_dict() for m in models],
                }
            )
    return result


def list_all_models() -> list[dict[str, Any]]:
    """List all available models."""
    return [m.to_dict() for m in ALL_MODELS]


def estimate_cost(
    model_id: str,
    input_tokens: int,
    output_tokens: int,
) -> float:
    """Estimate cost for a given model and token usage."""
    model = get_model(model_id)
    if not model:
        return 0.0

    input_cost = (input_tokens / 1_000_000) * model.input_price_per_1m
    output_cost = (output_tokens / 1_000_000) * model.output_price_per_1m
    return input_cost + output_cost
