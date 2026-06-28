"""
LLM integration module for supporting multiple model providers.
"""

import asyncio
import functools
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

# Import MCP components (we'll handle the import error gracefully)
try:
    from ..config import get_config
    from .mcp_client import MCPClient, MCPError, MCPTool, MCPToolCall, MCPToolResult
except ImportError:
    # Fallback for when running as script
    import os
    import sys

    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    from mcp_client import (  # type: ignore[no-redef]
        MCPClient,
        MCPError,
        MCPTool,
        MCPToolCall,
        MCPToolResult,
    )

    # Config will fall back to environment variables
    def get_config():
        class FallbackConfig:
            def get(self, key, default=None):
                return os.getenv(key, default)

        return FallbackConfig()


_logger = logging.getLogger(__name__)


@dataclass
class LLMResult:
    """Result from LLM generation."""

    response: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    tool_results: list[dict[str, Any]] = field(
        default_factory=list
    )  # Pre-executed tool results (for CLI providers)
    thinking: str | None = None  # Extended thinking content (Claude 4 models)
    token_usage: dict[str, int] | None = None
    cost: float = 0.0
    duration: float = 0.0
    tti_ms: int | None = None  # Time to first token in milliseconds
    raw_response: Any | None = None
    logs: list[str] = field(default_factory=list)  # Provider execution logs


@dataclass
class ToolSchema:
    """Sanitized tool schema without internal URLs."""

    name: str
    description: str
    parameters: dict[str, Any]

    @classmethod
    def from_mcp_tool(cls, tool: MCPTool) -> "ToolSchema":
        """Create sanitized tool schema from MCP tool."""
        return cls(name=tool.name, description=tool.description, parameters=tool.input_schema)


class LLMProvider(ABC):
    """Base class for LLM providers."""

    @abstractmethod
    async def initialize(self):
        """Initialize the provider."""
        pass

    @abstractmethod
    async def generate_with_tools(
        self,
        prompt: str,
        tools: list[dict[str, Any]],
        timeout: float = 30.0,
        messages: list[dict[str, Any]] | None = None,
    ) -> LLMResult:
        """Generate response with tool calling capability.

        Args:
            prompt: The user's message
            tools: List of tool schemas
            timeout: Request timeout
            messages: Optional chat history (list of {role: str, content: str})
        """
        pass

    @abstractmethod
    async def close(self):
        """Clean up resources."""
        pass


def _estimate_cost_with_fallback(
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    fallback_input_per_1m: float,
    fallback_output_per_1m: float,
) -> float:
    """Estimate cost in USD from model-registry pricing.

    Falls back to the caller-supplied per-1M rates when the model is not in
    the registry, so unknown/custom models keep their previous estimates.
    Distinct from ``BaseSDKProvider._estimate_cost_from_registry``, which
    returns 0.0 for unknown models and resolves ``self._registry_model_id``.
    """
    from .model_registry import get_model  # noqa: PLC0415

    info = get_model(model)
    in_rate = info.input_price_per_1m if info else fallback_input_per_1m
    out_rate = info.output_price_per_1m if info else fallback_output_per_1m
    return (prompt_tokens * in_rate + completion_tokens * out_rate) / 1_000_000


class OllamaProvider(LLMProvider):
    """Ollama provider for local models."""

    def __init__(self, model: str, base_url: str = "http://localhost:11434"):
        self.model = model
        self.base_url = base_url
        self.client = httpx.AsyncClient(timeout=60.0)

    async def initialize(self):
        """Check if model is available and pull if needed."""
        # Check if model exists
        try:
            response = await self.client.get(f"{self.base_url}/api/tags")
            if response.status_code == 200:
                models = response.json().get("models", [])
                model_names = [m["name"] for m in models]

                if self.model not in model_names:
                    # Try to pull the model
                    print(f"Model {self.model} not found locally. Attempting to pull...")
                    await self._pull_model()
        except Exception as e:
            raise Exception(f"Failed to connect to Ollama: {e}")

    async def _pull_model(self):
        """Pull model from Ollama registry."""
        try:
            response = await self.client.post(
                f"{self.base_url}/api/pull",
                json={"name": self.model},
                timeout=600.0,  # 10 minutes for large models
            )
            if response.status_code != 200:
                raise Exception(f"Failed to pull model: {response.text}")
        except Exception as e:
            raise Exception(f"Failed to pull model {self.model}: {e}")

    async def generate_with_tools(
        self,
        prompt: str,
        tools: list[dict[str, Any]],
        timeout: float = 30.0,
        messages: list[dict[str, Any]] | None = None,
    ) -> LLMResult:
        """Generate with Ollama's tool calling support."""
        start_time = time.time()

        # Format the prompt with tool information
        formatted_prompt = self._format_prompt_with_tools(prompt, tools)

        try:
            # Ollama API request
            request_data = {
                "model": self.model,
                "prompt": formatted_prompt,
                "format": "json",  # Request JSON format for tool calls
                "stream": False,
                "options": {
                    "temperature": 0.1,  # Low temperature for consistent tool calling
                    "num_predict": 1024,
                },
            }

            response = await self.client.post(
                f"{self.base_url}/api/generate", json=request_data, timeout=timeout
            )

            if response.status_code != 200:
                raise Exception(f"Ollama API error: {response.status_code} - {response.text}")

            result = response.json()
            response_text = result.get("response", "")

            # Parse tool calls from response
            tool_calls = self._parse_tool_calls(response_text, tools)

            # Calculate token usage (Ollama provides this)
            token_usage = {
                "prompt": result.get("prompt_eval_count", 0),
                "completion": result.get("eval_count", 0),
                "total": result.get("prompt_eval_count", 0) + result.get("eval_count", 0),
            }

            return LLMResult(
                response=response_text,
                tool_calls=tool_calls,
                token_usage=token_usage,
                cost=0.0,  # Local models have no API cost
                duration=time.time() - start_time,
                raw_response=result,
            )

        except Exception as e:
            return LLMResult(
                response=f"Error: {str(e)}", tool_calls=[], duration=time.time() - start_time
            )

    def _format_prompt_with_tools(self, prompt: str, tools: list[dict[str, Any]]) -> str:
        """Format prompt with tool descriptions for Ollama."""
        tool_descriptions = []

        for tool in tools:
            func = tool.get("function", tool)
            name = func.get("name", "unknown")
            desc = func.get("description", "")
            params = func.get("parameters", {})

            tool_desc = f"- {name}: {desc}"
            if params.get("properties"):
                param_list = ", ".join(params["properties"].keys())
                tool_desc += f" (parameters: {param_list})"

            tool_descriptions.append(tool_desc)

        formatted = f"""You have access to the following tools:
{chr(10).join(tool_descriptions)}

When you need to use a tool, respond with a JSON object in this format:
{{"tool": "tool_name", "arguments": {{"param1": "value1", "param2": "value2"}}}}

User request: {prompt}

Response (use JSON format if calling a tool):"""

        return formatted

    def _parse_tool_calls(self, response: str, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Parse tool calls from Ollama response."""
        tool_calls = []

        try:
            # Try to parse as JSON
            data = json.loads(response)

            # Check common patterns
            if "tool" in data and "arguments" in data:
                tool_calls.append({"name": data["tool"], "arguments": data["arguments"]})
            elif "function" in data and "arguments" in data:
                tool_calls.append({"name": data["function"], "arguments": data["arguments"]})
            elif "name" in data and ("arguments" in data or "parameters" in data):
                tool_calls.append(
                    {
                        "name": data["name"],
                        "arguments": data.get("arguments", data.get("parameters", {})),
                    }
                )

        except json.JSONDecodeError:
            # Try to extract JSON from the response
            import re

            json_pattern = r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}"
            matches = re.findall(json_pattern, response)

            for match in matches:
                try:
                    data = json.loads(match)
                    if "tool" in data or "function" in data or "name" in data:
                        parsed = self._parse_tool_calls(match, tools)
                        if parsed:
                            tool_calls.extend(parsed)
                except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                    continue

        return tool_calls

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()


class OpenAIProvider(LLMProvider):
    """OpenAI API provider (also works with OpenAI-compatible APIs)."""

    def __init__(
        self, model: str, api_key: str | None = None, base_url: str = "https://api.openai.com/v1"
    ):
        self.model = model
        self.api_key = api_key or ""
        self.base_url = base_url
        self.client = httpx.AsyncClient(timeout=60.0)

    async def initialize(self):
        """Initialize OpenAI provider."""
        if not self.api_key and self.base_url == "https://api.openai.com/v1":
            config = get_config()
            self.api_key = config.get("OPENAI_API_KEY", "")
            if not self.api_key:
                raise ValueError(
                    "OpenAI API key not provided. Set OPENAI_API_KEY in ~/.testmcpy or environment."
                )

    def _convert_to_openai_tools(self, mcp_tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Convert MCP tool schemas to OpenAI function calling format.

        MCP format:
        {
            "name": "tool_name",
            "description": "...",
            "inputSchema": {"type": "object", "properties": {...}}
        }
        or
        {
            "name": "tool_name",
            "description": "...",
            "input_schema": {"type": "object", "properties": {...}}
        }

        OpenAI format:
        {
            "type": "function",
            "function": {
                "name": "tool_name",
                "description": "...",
                "parameters": {"type": "object", "properties": {...}}
            }
        }
        """
        openai_tools = []
        for tool in mcp_tools:
            # Check if already in OpenAI format
            if tool.get("type") == "function" and "function" in tool:
                openai_tools.append(tool)
                continue

            # Get parameters from various possible keys (MCP uses input_schema or inputSchema)
            parameters = (
                tool.get("inputSchema")
                or tool.get("input_schema")
                or tool.get("parameters")
                or {"type": "object"}
            )

            # Simplify complex schemas that OpenAI can't handle
            parameters = self._simplify_schema_for_openai(parameters)

            # Convert MCP format to OpenAI format
            openai_tool = {
                "type": "function",
                "function": {
                    "name": tool.get("name", "unknown"),
                    "description": tool.get("description", ""),
                    "parameters": parameters,
                },
            }
            openai_tools.append(openai_tool)

        return openai_tools

    def _simplify_schema_for_openai(self, schema: dict[str, Any]) -> dict[str, Any]:
        """
        Simplify complex JSON schemas that OpenAI can't handle.

        OpenAI has issues with:
        - $defs and $ref (JSON Schema references)
        - Complex anyOf/oneOf structures
        - Missing properties on objects

        This method resolves $refs and ensures object types have properties.
        """
        if not isinstance(schema, dict):
            return {"type": "object", "properties": {}}

        # Store $defs for reference resolution
        defs = schema.pop("$defs", {})

        def resolve_refs(obj: Any) -> Any:
            """Recursively resolve $ref references."""
            if isinstance(obj, dict):
                if "$ref" in obj:
                    ref_path = obj["$ref"]
                    # Handle #/$defs/Name format
                    if ref_path.startswith("#/$defs/"):
                        def_name = ref_path.split("/")[-1]
                        if def_name in defs:
                            resolved = defs[def_name].copy()
                            # Recursively resolve nested refs
                            return resolve_refs(resolved)
                    return {"type": "string"}  # Fallback

                return {k: resolve_refs(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [resolve_refs(item) for item in obj]
            return obj

        # Resolve all $refs
        resolved = resolve_refs(schema)

        # Ensure object types have properties
        if resolved.get("type") == "object" and "properties" not in resolved:
            resolved["properties"] = {}

        # Handle anyOf by taking the first valid option or simplifying
        if "anyOf" in resolved and "type" not in resolved:
            any_of = resolved.get("anyOf", [])
            # Find first non-null type
            for opt in any_of:
                if isinstance(opt, dict) and opt.get("type") != "null":
                    # Merge the option into the schema
                    resolved = {**resolved, **opt}
                    del resolved["anyOf"]
                    break

        return resolved

    async def generate_with_tools(
        self,
        prompt: str,
        tools: list[dict[str, Any]],
        timeout: float = 30.0,
        messages: list[dict[str, Any]] | None = None,
    ) -> LLMResult:
        """Generate with OpenAI's function calling."""
        start_time = time.time()

        try:
            headers = {
                "Content-Type": "application/json",
            }
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"

            # Format for OpenAI API
            messages = [{"role": "user", "content": prompt}]

            # o1 models don't support tools, temperature, or max_tokens
            is_o1_model = self.model.startswith("o1")

            request_data = {
                "model": self.model,
                "messages": messages,
            }

            # o1 models use max_completion_tokens, don't support tools/temperature
            if is_o1_model:
                request_data["max_completion_tokens"] = 1000
            else:
                # Convert MCP tool format to OpenAI function calling format
                openai_tools = self._convert_to_openai_tools(tools)
                request_data["tools"] = openai_tools
                request_data["tool_choice"] = "auto"
                request_data["temperature"] = 0.1
                request_data["max_tokens"] = 1000

            response = await self.client.post(
                f"{self.base_url}/chat/completions",
                json=request_data,
                headers=headers,
                timeout=timeout,
            )

            if response.status_code != 200:
                raise Exception(f"OpenAI API error: {response.status_code} - {response.text}")

            result = response.json()
            choice = result["choices"][0]
            message = choice["message"]

            # Extract tool calls
            tool_calls = []
            if "tool_calls" in message:
                for tc in message["tool_calls"]:
                    tool_calls.append(
                        {
                            "name": tc["function"]["name"],
                            "arguments": json.loads(tc["function"]["arguments"]),
                        }
                    )

            # Token usage
            usage = result.get("usage", {})
            token_usage = {
                "prompt": usage.get("prompt_tokens", 0),
                "completion": usage.get("completion_tokens", 0),
                "total": usage.get("total_tokens", 0),
            }

            cost = _estimate_cost_with_fallback(
                self.model,
                token_usage["prompt"],
                token_usage["completion"],
                fallback_input_per_1m=30.0,
                fallback_output_per_1m=60.0,
            )

            duration = time.time() - start_time
            tti_ms = int(duration * 1000)  # Non-streaming: TTI = total duration

            return LLMResult(
                response=message.get("content") or "",
                tool_calls=tool_calls,
                token_usage=token_usage,
                cost=cost,
                duration=duration,
                tti_ms=tti_ms,
                raw_response=result,
            )

        except Exception as e:
            duration = time.time() - start_time
            return LLMResult(
                response=f"Error: {str(e)}",
                tool_calls=[],
                duration=duration,
                tti_ms=int(duration * 1000),
            )

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()


class OpenRouterProvider(OpenAIProvider):
    """OpenRouter API provider — OpenAI-compatible gateway to 100+ models.

    Uses the same OpenAI chat/completions format but routes through
    https://openrouter.ai/api/v1 with an OpenRouter API key.
    """

    def __init__(self, model: str, api_key: str | None = None):
        super().__init__(
            model=model,
            api_key=api_key or "",
            base_url="https://openrouter.ai/api/v1",
        )

    async def initialize(self):
        """Validate that an API key is available."""
        if not self.api_key:
            raise ValueError(
                "OpenRouter API key not provided. "
                "Configure it in .llm_providers.yaml using ${OPENROUTER_API_KEY} "
                "substitution, or pass api_key directly."
            )

    async def generate_with_tools(
        self,
        prompt: str,
        tools: list[dict[str, Any]],
        timeout: float = 30.0,
        messages: list[dict[str, Any]] | None = None,
    ) -> LLMResult:
        """Generate with OpenRouter — adds required extra headers."""
        start_time = time.time()

        try:
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
                "HTTP-Referer": "https://testmcpy.dev",
                "X-Title": "testmcpy",
            }

            if messages:
                api_messages = messages + [{"role": "user", "content": prompt}]
            else:
                api_messages = [{"role": "user", "content": prompt}]

            is_o1_model = self.model.startswith("o1")

            request_data: dict[str, Any] = {
                "model": self.model,
                "messages": api_messages,
            }

            if is_o1_model:
                request_data["max_completion_tokens"] = 1000
            else:
                openai_tools = self._convert_to_openai_tools(tools)
                request_data["tools"] = openai_tools
                request_data["tool_choice"] = "auto"
                request_data["temperature"] = 0.1
                request_data["max_tokens"] = 1000

            response = await self.client.post(
                f"{self.base_url}/chat/completions",
                json=request_data,
                headers=headers,
                timeout=timeout,
            )

            if response.status_code != 200:
                raise ValueError(f"OpenRouter API error: {response.status_code} - {response.text}")

            result = response.json()
            choice = result["choices"][0]
            message = choice["message"]

            tool_calls = []
            if "tool_calls" in message:
                for tc in message["tool_calls"]:
                    tool_calls.append(
                        {
                            "name": tc["function"]["name"],
                            "arguments": json.loads(tc["function"]["arguments"]),
                        }
                    )

            usage = result.get("usage", {})
            token_usage = {
                "prompt": usage.get("prompt_tokens", 0),
                "completion": usage.get("completion_tokens", 0),
                "total": usage.get("total_tokens", 0),
            }

            # OpenRouter returns cost info when available
            cost = 0.0
            if "usage" in result and "cost" in result["usage"]:
                cost = float(result["usage"]["cost"])
            else:
                # Fallback estimate when OpenRouter omits usage cost
                cost = _estimate_cost_with_fallback(
                    self.model,
                    token_usage["prompt"],
                    token_usage["completion"],
                    fallback_input_per_1m=30.0,
                    fallback_output_per_1m=60.0,
                )

            duration = time.time() - start_time
            tti_ms = int(duration * 1000)

            return LLMResult(
                response=message.get("content") or "",
                tool_calls=tool_calls,
                token_usage=token_usage,
                cost=cost,
                duration=duration,
                tti_ms=tti_ms,
                raw_response=result,
            )

        except ValueError:
            raise
        except (httpx.HTTPError, KeyError, json.JSONDecodeError) as e:
            duration = time.time() - start_time
            return LLMResult(
                response=f"Error: {str(e)}",
                tool_calls=[],
                duration=duration,
                tti_ms=int(duration * 1000),
            )


class XAIProvider(OpenAIProvider):
    """xAI (Grok) API provider — OpenAI-compatible API at api.x.ai.

    Uses the same OpenAI chat/completions format but routes through
    https://api.x.ai/v1 with an xAI API key.
    """

    def __init__(self, model: str, api_key: str | None = None):
        super().__init__(
            model=model,
            api_key=api_key or "",
            base_url="https://api.x.ai/v1",
        )

    async def initialize(self):
        """Validate that an API key is available."""
        if not self.api_key:
            raise ValueError(
                "xAI API key not provided. "
                "Configure it in .llm_providers.yaml using ${XAI_API_KEY} "
                "substitution, or pass api_key directly."
            )


class LocalModelProvider(LLMProvider):
    """Provider for local models using transformers or llama.cpp."""

    def __init__(self, model: str, device: str = "cpu"):
        self.model = model
        self.device = device
        self.pipeline = None

    async def initialize(self):
        """Load the local model."""
        try:
            from transformers import pipeline

            # Load model pipeline
            self.pipeline = pipeline(
                "text-generation", model=self.model, device=self.device, max_new_tokens=1000
            )
        except ImportError:
            raise ImportError("transformers library required for local models")
        except Exception as e:
            raise Exception(f"Failed to load local model {self.model}: {e}")

    async def generate_with_tools(
        self,
        prompt: str,
        tools: list[dict[str, Any]],
        timeout: float = 30.0,
        messages: list[dict[str, Any]] | None = None,
    ) -> LLMResult:
        """Generate with local model."""
        start_time = time.time()

        # Format prompt with tools
        formatted_prompt = self._format_prompt_with_tools(prompt, tools)

        try:
            # Run generation in executor to avoid blocking
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, self.pipeline, formatted_prompt)

            response_text = result[0]["generated_text"]
            # Remove the prompt from response
            if response_text.startswith(formatted_prompt):
                response_text = response_text[len(formatted_prompt) :].strip()

            # Parse tool calls
            tool_calls = self._parse_tool_calls(response_text)

            return LLMResult(
                response=response_text, tool_calls=tool_calls, duration=time.time() - start_time
            )

        except Exception as e:
            return LLMResult(
                response=f"Error: {str(e)}", tool_calls=[], duration=time.time() - start_time
            )

    def _format_prompt_with_tools(self, prompt: str, tools: list[dict[str, Any]]) -> str:
        """Format prompt for local model."""
        # Similar to Ollama formatting
        tool_descriptions = []
        for tool in tools:
            func = tool.get("function", tool)
            name = func.get("name", "unknown")
            desc = func.get("description", "")
            tool_descriptions.append(f"- {name}: {desc}")

        return f"""Available tools:
{chr(10).join(tool_descriptions)}

Respond with JSON if using a tool: {{"tool": "name", "arguments": {{}}}}

User: {prompt}
Assistant:"""

    def _parse_tool_calls(self, response: str) -> list[dict[str, Any]]:
        """Parse tool calls from response."""
        tool_calls = []
        try:
            import re

            json_pattern = r"\{[^{}]*\}"
            matches = re.findall(json_pattern, response)
            for match in matches:
                data = json.loads(match)
                if "tool" in data:
                    tool_calls.append(
                        {"name": data["tool"], "arguments": data.get("arguments", {})}
                    )
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            pass
        return tool_calls

    async def close(self):
        """Clean up resources."""
        self.pipeline = None


class MCPURLFilter:
    """Security class to prevent MCP URLs from reaching external APIs."""

    MCP_URL_PATTERNS = [
        r"http://localhost:\d+/mcp",
        r"https://localhost:\d+/mcp",
        r"http://127\.0\.0\.1:\d+/mcp",
        r"https://127\.0\.0\.1:\d+/mcp",
        r"http://0\.0\.0\.0:\d+/mcp",
        r"https://0\.0\.0\.0:\d+/mcp",
        r"mcp://",
        r"localhost:\d+/mcp",
        r"127\.0\.0\.1:\d+/mcp",
        r"0\.0\.0\.0:\d+/mcp",
    ]

    @classmethod
    def contains_mcp_url(cls, text: str) -> bool:
        """Check if text contains any MCP URL patterns."""
        if not isinstance(text, str):
            text = str(text)

        for pattern in cls.MCP_URL_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        return False

    @classmethod
    def validate_request_data(cls, data: Any) -> bool:
        """Validate that request data contains no MCP URLs."""

        def _check_recursive(obj):
            if isinstance(obj, str):
                return cls.contains_mcp_url(obj)
            elif isinstance(obj, dict):
                return any(_check_recursive(v) for v in obj.values())
            elif isinstance(obj, list):
                return any(_check_recursive(item) for item in obj)
            return False

        return not _check_recursive(data)

    @classmethod
    def sanitize_tool_schema(cls, tool_schema: dict[str, Any]) -> dict[str, Any]:
        """Remove any URLs from tool schema."""

        def _sanitize_recursive(obj):
            if isinstance(obj, str):
                # Remove URLs but keep the rest of the text
                for pattern in cls.MCP_URL_PATTERNS:
                    obj = re.sub(pattern, "[REDACTED]", obj, flags=re.IGNORECASE)
                return obj
            elif isinstance(obj, dict):
                return {
                    k: _sanitize_recursive(v)
                    for k, v in obj.items()
                    if k not in ["url", "endpoint", "base_url"]
                }
            elif isinstance(obj, list):
                return [_sanitize_recursive(item) for item in obj]
            return obj

        return _sanitize_recursive(tool_schema)


class ToolDiscoveryService:
    """Discovers MCP tools locally and creates sanitized schemas."""

    def __init__(self, mcp_url: str, auth: dict[str, Any] | None = None):
        self.mcp_url = mcp_url
        self.auth = auth
        self._tools_cache: list[ToolSchema] | None = None
        self._mcp_client: MCPClient | None = None

    async def discover_tools(self, force_refresh: bool = False) -> list[ToolSchema]:
        """Connect to MCP service and extract tool schemas only."""
        if not force_refresh and self._tools_cache is not None:
            return self._tools_cache

        if not self._mcp_client:
            self._mcp_client = MCPClient(self.mcp_url, auth=self.auth)
            await self._mcp_client.initialize()

        try:
            mcp_tools = await self._mcp_client.list_tools(force_refresh=force_refresh)
            tool_schemas = []

            for mcp_tool in mcp_tools:
                schema = ToolSchema.from_mcp_tool(mcp_tool)
                # Apply URL sanitization
                sanitized_params = MCPURLFilter.sanitize_tool_schema(schema.parameters)
                schema.parameters = sanitized_params
                tool_schemas.append(schema)

            self._tools_cache = tool_schemas
            return tool_schemas

        except Exception as e:
            raise MCPError(f"Failed to discover MCP tools: {e}") from e

    async def execute_tool_call(self, tool_call: dict[str, Any]) -> MCPToolResult:
        """Execute tool call via local MCP client."""
        if not self._mcp_client:
            raise MCPError("MCP client not initialized")

        mcp_call = MCPToolCall(
            name=tool_call["name"],
            arguments=tool_call.get("arguments", {}),
            id=tool_call.get("id", "unknown"),
        )

        return await self._mcp_client.call_tool(mcp_call)

    async def close(self):
        """Close MCP client connection."""
        if self._mcp_client:
            await self._mcp_client.close()
            self._mcp_client = None


class AnthropicProvider(LLMProvider):
    """Anthropic API provider with strict MCP URL protection."""

    def __init__(
        self,
        model: str,
        api_key: str | None = None,
        base_url: str = "https://api.anthropic.com",
        mcp_url: str | None = None,
        auth: dict[str, Any] | None = None,
    ):
        self.model = model
        # Use config system for API key
        config = get_config()
        self.api_key = api_key or config.get("ANTHROPIC_API_KEY", "")
        self.base_url = base_url
        self.client = httpx.AsyncClient(timeout=60.0)
        # Use MCP_URL and auth from default profile if not provided
        if mcp_url is None:
            mcp_url = config.get_mcp_url()
        if auth is None:
            default_mcp = config.get_default_mcp_server()
            if default_mcp and default_mcp.auth:
                auth = default_mcp.auth.to_dict()
        self.tool_discovery = ToolDiscoveryService(mcp_url, auth=auth)

    async def initialize(self):
        """Initialize Anthropic provider."""
        if not self.api_key:
            raise ValueError(
                "Anthropic API key not provided. Set ANTHROPIC_API_KEY in ~/.testmcpy, .env, or environment."
            )

        # Try to pre-discover tools, but don't fail if MCP service is unavailable
        try:
            await self.tool_discovery.discover_tools()
            print(f"✅ Successfully connected to MCP service at {self.tool_discovery.mcp_url}")
        except Exception as e:
            print(f"⚠️  Warning: Failed to initialize MCP tools: {e}")
            print(f"   MCP URL: {self.tool_discovery.mcp_url}")
            print("   The provider will work without MCP tools (direct API calls only)")
            # Continue without tools - the provider can still work for non-tool interactions

    async def generate_with_tools(
        self,
        prompt: str,
        tools: list[dict[str, Any]],
        timeout: float = 30.0,
        messages: list[dict[str, Any]] | None = None,
    ) -> LLMResult:
        """Generate response with tool calling capability."""
        start_time = time.time()

        try:
            # CRITICAL: Validate NO MCP URLs in request
            request_data = {"prompt": prompt, "tools": tools}

            if not MCPURLFilter.validate_request_data(request_data):
                raise Exception("SECURITY VIOLATION: MCP URLs detected in request data")

            # Convert tool schemas to Anthropic format
            anthropic_tools = []
            for tool in tools:
                # Handle OpenAI-style tool format
                if "function" in tool:
                    func = tool["function"]
                    tool_dict = {
                        "name": func.get("name", ""),
                        "description": func.get("description", ""),
                        "parameters": func.get("parameters", {}),
                    }
                else:
                    # Direct tool schema format
                    tool_dict = tool

                # Sanitize tool schema
                sanitized_tool = MCPURLFilter.sanitize_tool_schema(tool_dict)

                input_schema = sanitized_tool.get(
                    "inputSchema", sanitized_tool.get("parameters", {})
                )
                # Ensure input_schema has required type field
                if "type" not in input_schema:
                    input_schema["type"] = "object"

                anthropic_tools.append(
                    {
                        "name": sanitized_tool.get("name", ""),
                        "description": sanitized_tool.get("description", ""),
                        "input_schema": input_schema,
                    }
                )

            # Check if model supports extended thinking (Claude 4 models)
            supports_thinking = "claude-sonnet-4" in self.model or "claude-opus-4" in self.model

            # Prepare Anthropic API request with caching and optional extended thinking
            beta_features = ["prompt-caching-2024-07-31"]
            if supports_thinking:
                beta_features.append("interleaved-thinking-2025-05-14")

            headers = {
                "Content-Type": "application/json",
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "anthropic-beta": ",".join(beta_features),
            }

            # Build messages list - include history if provided, otherwise just current prompt
            if messages:
                # Use provided message history, but filter out messages with empty content
                # Anthropic API requires all messages to have non-empty content
                api_messages = [
                    msg
                    for msg in messages
                    if msg.get("content") and str(msg.get("content")).strip()
                ]
                # Only add new message if it's not already the last message
                if not api_messages or api_messages[-1].get("content") != prompt:
                    api_messages.append({"role": "user", "content": prompt})
            else:
                # No history, just the current prompt
                api_messages = [{"role": "user", "content": prompt}]

            # Set max_tokens - higher for extended thinking models
            max_tokens = 16000 if supports_thinking else 1000

            api_request = {"model": self.model, "max_tokens": max_tokens, "messages": api_messages}

            # Enable extended thinking for Claude 4 models
            if supports_thinking:
                api_request["thinking"] = {"type": "enabled", "budget_tokens": 10000}

            # Add system parameter if we have tools (not in messages array)
            if anthropic_tools:
                tools_description = f"You have access to these tools:\n{json.dumps(anthropic_tools, indent=2)}\n\nUse these tools to help answer the user's questions."
                api_request["system"] = [
                    {
                        "type": "text",
                        "text": tools_description,
                        "cache_control": {"type": "ephemeral"},
                    }
                ]

            if anthropic_tools:
                api_request["tools"] = anthropic_tools
                api_request["tool_choice"] = {"type": "auto"}

            # Final security check
            if not MCPURLFilter.validate_request_data(api_request):
                raise Exception("SECURITY VIOLATION: MCP URLs in final API request")

            # Make API call
            response = await self.client.post(
                f"{self.base_url}/v1/messages", json=api_request, headers=headers, timeout=timeout
            )

            if response.status_code != 200:
                raise Exception(f"Anthropic API error: {response.status_code} - {response.text}")

            result = response.json()

            # Extract response, thinking, and tool calls
            content = result.get("content", [])
            response_text = ""
            thinking_text = ""
            tool_calls = []

            for item in content:
                if item.get("type") == "thinking":
                    # Extended thinking block
                    thinking_text += item.get("thinking", "")
                elif item.get("type") == "text":
                    response_text += item.get("text", "")
                elif item.get("type") == "tool_use":
                    tool_calls.append(
                        {
                            "id": item.get("id", ""),
                            "name": item.get("name", ""),
                            "arguments": item.get("input", {}),
                        }
                    )

            # Execute tool calls locally (don't append to response_text - tool results shown separately in UI)
            # call_tool() reports tool failures as MCPToolResult(is_error=True);
            # only client-not-initialized or a malformed tool_call dict raise.
            for tool_call in tool_calls:
                try:
                    await self.tool_discovery.execute_tool_call(tool_call)
                    # Tool results are returned separately, not appended to response text
                except (MCPError, KeyError) as e:
                    _logger.warning(
                        "Tool call %s failed locally: %s", tool_call.get("name", "?"), e
                    )

            # Calculate usage and cost
            usage = result.get("usage", {})
            token_usage = {
                "prompt": usage.get("input_tokens", 0),
                "completion": usage.get("output_tokens", 0),
                "total": usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
                "cache_creation": usage.get("cache_creation_input_tokens", 0),
                "cache_read": usage.get("cache_read_input_tokens", 0),
            }

            cost = _estimate_cost_with_fallback(
                self.model,
                token_usage["prompt"],
                token_usage["completion"],
                fallback_input_per_1m=3.0,
                fallback_output_per_1m=15.0,
            )

            duration = time.time() - start_time
            # For non-streaming, TTI equals total duration (response arrives all at once)
            tti_ms = int(duration * 1000)

            return LLMResult(
                response=response_text,
                tool_calls=tool_calls,
                thinking=thinking_text if thinking_text else None,
                token_usage=token_usage,
                cost=cost,
                duration=duration,
                tti_ms=tti_ms,
                raw_response=result,
            )

        except Exception as e:
            # Detailed error information for debugging
            error_type = type(e).__name__
            error_msg = str(e)

            # Get more details if available
            error_details = f"Error Type: {error_type}\nError Message: {error_msg}"

            # If it's an HTTP error, try to get more details
            if hasattr(e, "response"):
                try:
                    error_details += f"\nHTTP Status: {e.response.status_code}"
                    error_details += f"\nHTTP Response: {e.response.text}"
                except (AttributeError, TypeError):
                    pass

            # Check if it's a timeout
            if "timeout" in error_msg.lower():
                error_details += "\nThis appears to be a timeout error. Consider increasing the timeout parameter."

            # Check if it's a rate limit
            if "rate" in error_msg.lower() or "429" in error_msg:
                error_details += "\nThis appears to be a rate limiting error. The system should have handled this automatically."

            return LLMResult(
                response=f"Error: {error_details}", tool_calls=[], duration=time.time() - start_time
            )

    async def close(self):
        """Close connections."""
        await self.tool_discovery.close()
        await self.client.aclose()


_bedrock_logger = logging.getLogger(__name__ + ".BedrockProvider")


def _normalize_bedrock_model_id(model: str) -> str:
    """Map a Bedrock model id to its model-registry equivalent.

    e.g. ``us.anthropic.claude-sonnet-4-20250514-v1:0`` → ``claude-sonnet-4-20250514``.
    """
    normalized = re.sub(r"^(us|eu|apac|global|jp)\.", "", model)
    normalized = re.sub(r"^anthropic\.", "", normalized)
    return re.sub(r"-v\d+(:\d+)?$", "", normalized)


class BedrockProvider(LLMProvider):
    """AWS Bedrock provider using the Anthropic SDK's built-in Bedrock client.

    Uses AsyncAnthropicBedrock which handles SigV4 signing automatically.
    AWS credentials are read from the environment (AWS_ACCESS_KEY_ID,
    AWS_SECRET_ACCESS_KEY, AWS_SESSION_TOKEN) — typically set by OIDC
    role assumption in CI.

    Requires: pip install testmcpy[bedrock]  (adds boto3)
    """

    def __init__(
        self,
        model: str,
        aws_region: str = "us-west-2",
        mcp_url: str | None = None,
    ):
        self.model = model
        self.aws_region = aws_region
        self.client = None  # Initialized lazily in initialize()

        # Use config system for MCP URL if not provided
        config = get_config()
        if mcp_url is None:
            mcp_url = config.get_mcp_url()
        # Get auth from default MCP server
        auth = None
        default_mcp = config.get_default_mcp_server()
        if default_mcp and default_mcp.auth:
            auth = default_mcp.auth.to_dict()
        self.tool_discovery = ToolDiscoveryService(mcp_url, auth=auth)

    async def initialize(self):
        """Initialize Bedrock provider with lazy boto3/anthropic import."""
        try:
            from anthropic import AsyncAnthropicBedrock
        except ImportError as e:
            raise ImportError(
                "AWS Bedrock support requires boto3. Install with: pip install testmcpy[bedrock]"
            ) from e

        self.client = AsyncAnthropicBedrock(aws_region=self.aws_region)
        _bedrock_logger.info(
            "[Bedrock] Initialized client for region=%s model=%s", self.aws_region, self.model
        )

        # Try to pre-discover tools
        try:
            await self.tool_discovery.discover_tools()
            _bedrock_logger.info(
                "[Bedrock] Connected to MCP service at %s", self.tool_discovery.mcp_url
            )
        except Exception as e:
            _bedrock_logger.warning("[Bedrock] Failed to initialize MCP tools: %s", e)
            print(f"⚠️  Warning: Failed to initialize MCP tools: {e}")
            print("   The provider will work without MCP tools (direct API calls only)")

    async def generate_with_tools(
        self,
        prompt: str,
        tools: list[dict[str, Any]],
        timeout: float = 30.0,
        messages: list[dict[str, Any]] | None = None,
    ) -> LLMResult:
        """Generate response with tool calling via Bedrock."""
        start_time = time.time()

        try:
            if self.client is None:
                raise RuntimeError("BedrockProvider not initialized. Call initialize() first.")

            # CRITICAL: Validate NO MCP URLs in request
            request_data = {"prompt": prompt, "tools": tools}
            if not MCPURLFilter.validate_request_data(request_data):
                raise Exception("SECURITY VIOLATION: MCP URLs detected in request data")

            # Convert tool schemas to Anthropic format
            anthropic_tools = []
            for tool in tools:
                if "function" in tool:
                    func = tool["function"]
                    tool_dict = {
                        "name": func.get("name", ""),
                        "description": func.get("description", ""),
                        "parameters": func.get("parameters", {}),
                    }
                else:
                    tool_dict = tool

                sanitized_tool = MCPURLFilter.sanitize_tool_schema(tool_dict)
                input_schema = sanitized_tool.get(
                    "inputSchema", sanitized_tool.get("parameters", {})
                )
                if "type" not in input_schema:
                    input_schema["type"] = "object"

                anthropic_tools.append(
                    {
                        "name": sanitized_tool.get("name", ""),
                        "description": sanitized_tool.get("description", ""),
                        "input_schema": input_schema,
                    }
                )

            # Build messages
            if messages:
                api_messages = [
                    msg
                    for msg in messages
                    if msg.get("content") and str(msg.get("content")).strip()
                ]
                if not api_messages or api_messages[-1].get("content") != prompt:
                    api_messages.append({"role": "user", "content": prompt})
            else:
                api_messages = [{"role": "user", "content": prompt}]

            # Check thinking support
            supports_thinking = "claude-sonnet-4" in self.model or "claude-opus-4" in self.model
            max_tokens = 16000 if supports_thinking else 4096

            # Build SDK call kwargs
            kwargs: dict[str, Any] = {
                "model": self.model,
                "max_tokens": max_tokens,
                "messages": api_messages,
            }

            if supports_thinking:
                kwargs["thinking"] = {"type": "enabled", "budget_tokens": 10000}

            if anthropic_tools:
                kwargs["tools"] = anthropic_tools
                kwargs["tool_choice"] = {"type": "auto"}

            # Final security check
            if not MCPURLFilter.validate_request_data(kwargs):
                raise Exception("SECURITY VIOLATION: MCP URLs in final API request")

            # Call Bedrock via SDK (handles SigV4 signing)
            response = await self.client.messages.create(**kwargs)

            # Parse SDK response objects
            response_text = ""
            thinking_text = ""
            tool_calls = []

            for block in response.content:
                if block.type == "thinking":
                    thinking_text += block.thinking
                elif block.type == "text":
                    response_text += block.text
                elif block.type == "tool_use":
                    tool_calls.append(
                        {
                            "id": block.id,
                            "name": block.name,
                            "arguments": block.input,
                        }
                    )

            # Execute tool calls locally
            for tool_call in tool_calls:
                try:
                    await self.tool_discovery.execute_tool_call(tool_call)
                except (MCPError, KeyError) as e:
                    _logger.warning(
                        "Tool call %s failed locally: %s", tool_call.get("name", "?"), e
                    )

            # Calculate usage and cost
            usage = response.usage
            token_usage = {
                "prompt": usage.input_tokens,
                "completion": usage.output_tokens,
                "total": usage.input_tokens + usage.output_tokens,
            }

            cost = _estimate_cost_with_fallback(
                _normalize_bedrock_model_id(self.model),
                token_usage["prompt"],
                token_usage["completion"],
                fallback_input_per_1m=3.0,
                fallback_output_per_1m=15.0,
            )

            duration = time.time() - start_time
            tti_ms = int(duration * 1000)

            return LLMResult(
                response=response_text,
                tool_calls=tool_calls,
                thinking=thinking_text if thinking_text else None,
                token_usage=token_usage,
                cost=cost,
                duration=duration,
                tti_ms=tti_ms,
                raw_response=response.model_dump() if hasattr(response, "model_dump") else None,
            )

        except Exception as e:
            error_type = type(e).__name__
            error_msg = str(e)
            error_details = f"Error Type: {error_type}\nError Message: {error_msg}"

            if hasattr(e, "response"):
                try:
                    error_details += f"\nHTTP Status: {e.response.status_code}"
                    error_details += f"\nHTTP Response: {e.response.text}"
                except (AttributeError, TypeError):
                    pass

            if "timeout" in error_msg.lower():
                error_details += "\nThis appears to be a timeout error."
            if "rate" in error_msg.lower() or "429" in error_msg:
                error_details += "\nThis appears to be a rate limiting error."

            return LLMResult(
                response=f"Error: {error_details}", tool_calls=[], duration=time.time() - start_time
            )

    async def close(self):
        """Close connections."""
        await self.tool_discovery.close()
        if self.client:
            await self.client.close()


# ---------------------------------------------------------------------------
# Shared base class for SDK-backed LLM providers (Claude, Codex, Gemini, ...).
# ---------------------------------------------------------------------------


@dataclass
class SDKRunResult:
    """Intermediate result from a vendor SDK agent run.

    Subclasses of :class:`BaseSDKProvider` populate this in their ``_run_agent``
    implementation; the base class then normalises it into :class:`LLMResult`.

    The fields named in the harness contract MUST be populated correctly:

    - ``tool_results``: every native tool execution by the vendor SDK must be
      reflected here (paired with the corresponding ``tool_calls`` entry).
      If left empty when ``tool_calls`` is non-empty, ``test_runner.py`` will
      re-execute every call against MCP — catastrophic for state-mutating tools.
    - ``token_usage``: must use the repo-standard
      ``{"prompt", "completion", "total"}`` keys (other providers consume them).
    - ``cost``: only set when the SDK reports its own per-call price
      (Claude does, Codex/Gemini do not). When ``None`` the base estimates
      cost from the model registry's per-1M pricing.
    """

    response_text: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    tool_results: list[MCPToolResult] = field(default_factory=list)
    token_usage: dict[str, int] | None = None
    cost: float | None = None
    thinking: str | None = None
    raw_response: Any | None = None
    logs: list[str] = field(default_factory=list)


class BaseSDKProvider(LLMProvider, ABC):
    """Common base for SDK-backed providers (Claude, Codex, Gemini, ...).

    Centralises the parts of an SDK-backed provider that have repeatedly
    drifted between implementations and produced real correctness bugs:

    1. **tool_results contract** — when the vendor SDK executes MCP tools
       natively, :class:`LLMResult.tool_results` must be populated. Otherwise
       ``test_runner.py`` will re-execute each call against MCP, which is
       catastrophic for state-mutating tools (create/update/delete).
       ``generate_with_tools`` emits a loud warning when this is violated.
    2. **token_usage shape** — ``{"prompt", "completion", "total"}`` is the
       repo-wide convention; subclasses normalise vendor counts into this
       shape inside ``_run_agent``.
    3. **cost** — taken from the SDK when reported (Claude), otherwise
       estimated from :mod:`testmcpy.src.model_registry`. Subclasses must
       set ``SDKRunResult.cost`` only when the SDK reports it directly.
    4. **MCP cleanup** — each subclass closes its vendor MCP transport
       inside ``_run_agent`` (typically in a ``finally``); this base class
       does not own the transport handle.
    5. **Error scope** — :class:`asyncio.TimeoutError` and every type listed
       in ``_vendor_expected_errors()`` are converted to a clean error
       :class:`LLMResult`. Any other exception propagates so programming
       defects (bad SDK kwargs, AttributeError, etc.) surface as a real
       failure instead of being recorded as a silent 0-score result.
    6. **Auth / token resolution** — Bearer/JWT/OAuth/oauth_auto_discover
       is resolved here so a fix in one place covers every SDK provider
       (the previous hand-rolled cache paths in Codex/Gemini never matched
       what ``fastmcp.FileTokenStorage`` actually writes).
    """

    # Subclasses override (optional) — used as the logger suffix.
    LOGGER_NAME: str = ""

    def __init__(
        self,
        model: str,
        mcp_url: str | None = None,
        auth: dict[str, Any] | None = None,
    ):
        self.model = model
        config = get_config()
        if mcp_url is None:
            mcp_url = config.get_mcp_url()
        self.mcp_url = mcp_url
        if auth is None:
            default_mcp = config.get_default_mcp_server()
            if default_mcp and default_mcp.auth:
                auth = default_mcp.auth.to_dict()
        self.auth_config = auth
        self._mcp_headers: dict[str, str] = {}
        self._logger = logging.getLogger(__name__ + "." + (self.LOGGER_NAME or type(self).__name__))

    # ---- Hooks the subclass must implement --------------------------------

    @abstractmethod
    def _check_sdk_installed(self) -> None:
        """Raise :class:`ValueError` with an install hint if the vendor SDK
        package can't be imported. Called by :meth:`initialize` before
        credential checks."""

    @abstractmethod
    async def _validate_credentials(self) -> None:
        """Raise :class:`ValueError` if vendor credentials are missing or
        invalid. Providers that authenticate via subscription (e.g. Claude
        Code) may make this a no-op."""

    @abstractmethod
    async def _run_agent(
        self,
        prompt: str,
        timeout: float,
        messages: list[dict[str, Any]] | None,
    ) -> SDKRunResult:
        """Vendor-specific agent execution. Returns a normalised
        :class:`SDKRunResult` which the base class then converts to
        :class:`LLMResult`.

        Implementation contract:

        - **MUST** populate ``tool_results`` whenever the SDK executes tools
          natively (otherwise the harness will double-execute every call).
        - **MUST** normalise ``token_usage`` to the
          ``{"prompt", "completion", "total"}`` shape.
        - **MUST** clean up its own MCP transport (typically in a
          ``finally`` block inside this method).
        - **MAY** raise :class:`asyncio.TimeoutError` to signal a wall-clock
          timeout — the base wraps the call with :func:`asyncio.wait_for`.
        - **MAY** raise any error class declared in
          :meth:`_vendor_expected_errors`; everything else propagates.
        """

    @classmethod
    def _vendor_expected_errors(cls) -> tuple[type[BaseException], ...]:
        """Tuple of exception types treated as expected runtime failures by
        :meth:`generate_with_tools` — they convert to an error
        :class:`LLMResult`. Everything else (programming errors, unexpected
        states) propagates. Defaults to common network errors; subclasses
        extend with vendor-specific types (e.g. ``ProcessError``,
        ``openai.APIError``)."""
        return (ConnectionError, OSError)

    # ---- Template methods provided by the base ---------------------------

    async def initialize(self) -> None:
        """Validate the SDK is installed, validate credentials, and resolve
        the MCP Bearer token. Subclasses may extend (e.g. to additionally
        build a vendor-specific MCP config dict) but should call
        ``await super().initialize()``."""
        self._check_sdk_installed()
        await self._validate_credentials()
        token = await self._resolve_mcp_bearer_token()
        if token:
            self._mcp_headers = {"Authorization": f"Bearer {token}"}
            self._logger.info("MCP server configured with auth token")
        else:
            self._logger.info("MCP server configured without auth")
        self._logger.info("MCP server ready: %s", self.mcp_url)

    async def generate_with_tools(
        self,
        prompt: str,
        tools: list[dict[str, Any]],
        timeout: float = 120.0,
        messages: list[dict[str, Any]] | None = None,
    ) -> LLMResult:
        """Template method: dispatch to :meth:`_run_agent`, normalise the
        result, enforce the harness contract.

        Subclasses normally do **not** override this — implement
        :meth:`_run_agent` instead.
        """
        start_time = time.time()
        try:
            sdk_result = await asyncio.wait_for(
                self._run_agent(prompt, timeout, messages),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            self._logger.warning("SDK query timed out after %.0fs", timeout)
            return LLMResult(
                response=f"Error: SDK query timed out after {timeout}s",
                tool_calls=[],
                duration=time.time() - start_time,
            )
        except self._vendor_expected_errors() as e:
            self._logger.warning(
                "expected runtime error in _run_agent: %s: %s", type(e).__name__, e
            )
            return LLMResult(
                response=f"Error: {e}",
                tool_calls=[],
                duration=time.time() - start_time,
            )
        # Intentionally no broad `except Exception`: programming defects
        # (wrong vendor kwargs, AttributeError on event shape, etc.) MUST
        # propagate as real test failures rather than be recorded as a
        # silent 0-score LLMResult — see PR #82/#84 review comments.

        self._warn_if_tool_results_missing(sdk_result)

        cost = sdk_result.cost
        if not cost:  # None or 0.0 — estimate from registry
            cost = self._estimate_cost_from_registry(sdk_result.token_usage)

        duration = time.time() - start_time
        return LLMResult(
            response=sdk_result.response_text,
            tool_calls=sdk_result.tool_calls,
            tool_results=sdk_result.tool_results,
            thinking=sdk_result.thinking,
            token_usage=sdk_result.token_usage,
            cost=cost or 0.0,
            duration=duration,
            tti_ms=int(duration * 1000),
            raw_response=sdk_result.raw_response,
            logs=sdk_result.logs,
        )

    async def close(self) -> None:
        """No persistent connections — MCP session is per-request for SDK
        providers. Subclasses may override if they hold long-lived state."""

    # ---- Helpers used by the template method -----------------------------

    def _warn_if_tool_results_missing(self, sdk_result: SDKRunResult) -> None:
        """Loud warning when ``tool_calls`` is populated but ``tool_results``
        is empty — the harness will then re-execute every call against MCP
        (see ``test_runner.py:598``). This is catastrophic for state-mutating
        tools, so we surface it at WARNING level rather than letting it
        silently corrupt eval scores."""
        if sdk_result.tool_calls and not sdk_result.tool_results:
            self._logger.warning(
                "Contract violation: %d tool_calls but 0 tool_results — "
                "test_runner will RE-EXECUTE these calls against MCP, which "
                "is unsafe for state-mutating tools. %s._run_agent must "
                "populate tool_results when the SDK executes tools natively.",
                len(sdk_result.tool_calls),
                type(self).__name__,
            )

    def _estimate_cost_from_registry(self, token_usage: dict[str, int] | None) -> float:
        """Estimate USD cost from ``token_usage`` and ``model_registry``
        per-1M prices. Subclasses can store a friendly registry id
        (e.g. ``"codex-o3"``) in ``self._registry_model_id`` separate from
        the vendor-facing ``self.model`` (``"o3"``); both are tried.
        Unknown models cost 0.0 here; the non-SDK providers use module-level
        ``_estimate_cost_with_fallback`` to keep legacy estimates instead."""
        if not token_usage:
            return 0.0
        from .model_registry import get_model  # noqa: PLC0415

        registry_id = getattr(self, "_registry_model_id", None) or self.model
        model_info = get_model(registry_id) or get_model(self.model)
        if not model_info:
            return 0.0
        return (
            token_usage.get("prompt", 0) * model_info.input_price_per_1m / 1_000_000
            + token_usage.get("completion", 0) * model_info.output_price_per_1m / 1_000_000
        )

    # ---- Shared auth/token resolution ------------------------------------

    async def _resolve_mcp_bearer_token(self) -> str | None:
        """Dispatch by ``auth_config["type"]`` and return a Bearer token
        suitable for the ``Authorization`` header on MCP requests, or
        ``None`` when no auth is configured."""
        if not self.auth_config:
            return None
        auth_type = self.auth_config.get("type", "")
        if auth_type == "bearer":
            return self.auth_config.get("token", "") or None
        if auth_type == "jwt":
            return await self._fetch_jwt_token()
        if auth_type == "oauth":
            if self.auth_config.get("oauth_auto_discover"):
                token = await self._read_cached_oauth_token()
                if not token:
                    raise ValueError(
                        f"No usable cached OAuth token for {self.mcp_url}. "
                        "Authenticate the MCP profile first (open it on the "
                        "MCP Profiles page or run a smoke test to trigger "
                        "the OAuth flow), then re-run the test."
                    )
                return token
            return await self._fetch_oauth_token()
        return None

    async def _fetch_jwt_token(self) -> str | None:
        """Fetch a JWT bearer token from the configured API endpoint.

        Sends ``{"name": api_token, "secret": api_secret}`` (the Preset
        chatbot convention). Accepts both response shapes seen in the wild:
        ``{"payload": {"access_token": "..."}}`` (Preset chatbot) and a
        flat ``{"access_token": "..."}`` (generic). This unifies what was
        previously two divergent implementations across SDK providers.
        """
        if not self.auth_config:
            return None
        api_url = self.auth_config.get("api_url", "")
        api_token = self.auth_config.get("api_token", "")
        api_secret = self.auth_config.get("api_secret", "")
        if not all([api_url, api_token, api_secret]):
            self._logger.warning("JWT auth config incomplete")
            return None
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    api_url,
                    headers={
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                    },
                    json={"name": api_token, "secret": api_secret},
                    timeout=30.0,
                )
                resp.raise_for_status()
                data = resp.json()
                token = (
                    data.get("payload", {}).get("access_token")
                    or data.get("access_token")
                    or data.get("token")
                    or None
                )
                if token:
                    self._logger.info("JWT token fetched (length: %d)", len(token))
                return token
        except (httpx.HTTPStatusError, httpx.ConnectError, httpx.TimeoutException) as e:
            self._logger.warning("Failed to fetch JWT token: %s", e)
            return None

    async def _fetch_oauth_token(self) -> str | None:
        """Fetch an OAuth token via the ``client_credentials`` grant."""
        if not self.auth_config:
            return None
        token_url = self.auth_config.get("token_url", "")
        client_id = self.auth_config.get("client_id", "")
        client_secret = self.auth_config.get("client_secret", "")
        if not all([token_url, client_id, client_secret]):
            self._logger.warning("OAuth client_credentials config incomplete")
            return None
        scopes = self.auth_config.get("scopes", [])
        data: dict[str, Any] = {
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        }
        if scopes:
            data["scope"] = " ".join(scopes)
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(token_url, data=data, timeout=30.0)
                resp.raise_for_status()
                token = resp.json().get("access_token") or None
                if token:
                    self._logger.info("OAuth token fetched (length: %d)", len(token))
                return token
        except (httpx.HTTPStatusError, httpx.ConnectError, httpx.TimeoutException) as e:
            self._logger.warning("Failed to fetch OAuth token: %s", e)
            return None

    async def _read_cached_oauth_token(self) -> str | None:
        """Reuse the access token that fastmcp's OAuth flow already cached.

        Uses :class:`fastmcp.client.auth.oauth.FileTokenStorage` — the actual
        public API. The previous hand-rolled cache paths in CodexSDKProvider
        and GeminiSDKProvider (``~/.fastmcp/oauth-mcp-client-cache/{url-encoded
        mcp_url}.json``) did NOT match what fastmcp actually writes (it keys
        storage by server base URL via ``TokenStorageAdapter``). Centralising
        here fixes that latent bug for both.

        Returns ``None`` when there is no cached token or the cached payload
        is malformed/expired — callers expecting auth then surface a clear
        re-authentication error instead of silently going un-authenticated.
        """
        try:
            from urllib.parse import urlparse  # noqa: PLC0415

            from fastmcp.client.auth.oauth import FileTokenStorage  # noqa: PLC0415
        except ImportError as e:
            self._logger.warning("fastmcp not available for cached-token lookup: %s", e)
            return None
        parsed = urlparse(self.mcp_url)
        server_base_url = f"{parsed.scheme}://{parsed.netloc}"
        try:
            storage = FileTokenStorage(server_url=server_base_url)
            oauth_token = await storage.get_tokens()
        except (OSError, ValueError) as e:
            self._logger.warning("Failed to read cached OAuth token for %s: %s", server_base_url, e)
            return None
        if oauth_token is None:
            self._logger.warning(
                "No cached OAuth token for %s — authenticate the MCP profile "
                "(MCP Profiles page or smoke test) and re-run.",
                server_base_url,
            )
            return None
        access_token = getattr(oauth_token, "access_token", None)
        if not access_token:
            self._logger.warning(
                "Cached OAuth payload for %s is missing access_token — "
                "authenticate the MCP profile again to refresh it.",
                server_base_url,
            )
            return None
        self._logger.info(
            "Reusing cached OAuth token for %s (length: %d)",
            server_base_url,
            len(access_token),
        )
        return access_token


_claude_sdk_logger = logging.getLogger(__name__ + ".ClaudeSDKProvider")


# Substrings that strongly indicate a tool-result is an error, even when
# the SDK didn't flag is_error=True. Used by the retry-budget guard to
# detect cases like MCP-side validation errors that come back as "successful"
# tool results with error text in the body.
_ERROR_PAYLOAD_MARKERS = (
    "validation error",
    "Unexpected keyword argument",
    "Missing required argument",
    "missing_argument",
    "unexpected_keyword_argument",
    '"error":',
    "'error':",
    "Error:",
)


def _looks_like_error_payload(content: Any) -> bool:
    """Heuristic: does this tool-result content look like an error?"""
    text = str(content) if content is not None else ""
    if not text:
        return False
    return any(marker in text for marker in _ERROR_PAYLOAD_MARKERS)


def claude_cli_auth_env(token: str | None) -> dict[str, str]:
    """Map a UI-entered token to the env var the Claude CLI/Agent SDK expects.

    The Claude CLI (which the Agent SDK wraps) authenticates from its
    subprocess environment in two ways:

    - ``CLAUDE_CODE_OAUTH_TOKEN`` — a Pro/Max **subscription** token produced
      by ``claude setup-token`` (prefix ``sk-ant-oat``).
    - ``ANTHROPIC_API_KEY`` — a standard **API-credits** key.

    Auto-detect by prefix so users only paste one value. Returns ``{}`` for an
    empty/None token so callers can leave the environment untouched (preserving
    reliance on the host's ``claude`` login).
    """
    token = (token or "").strip()
    if not token:
        return {}
    if token.startswith("sk-ant-oat"):
        return {"CLAUDE_CODE_OAUTH_TOKEN": token}
    return {"ANTHROPIC_API_KEY": token}


# Provider type strings that map to the Claude Agent SDK (see create_llm_provider).
CLAUDE_SDK_PROVIDERS = ("claude-sdk", "claude-cli", "claude-code")


def resolve_claude_cli_token(
    model: str | None = None,
    llm_profile_id: str | None = None,
) -> str | None:
    """Look up a Claude Agent SDK auth token in the LLM profiles config.

    This lets every code path that builds a :class:`ClaudeSDKProvider` honor a
    token entered through the UI, even paths that have no request body to
    thread it through (CLI chat, docs optimizer, runner tools, websocket chat).

    Searches the named profile — or the default profile when
    ``llm_profile_id`` is None — for a provider config in the Claude family
    (:data:`CLAUDE_SDK_PROVIDERS`). Prefers one whose ``model`` matches, else
    the profile's default/first such provider. Returns the direct ``api_key``
    or the value of the named ``api_key_env``; ``None`` when nothing is
    configured (the caller then falls back to the host ``claude`` login).

    This is a best-effort fallback: a malformed/unreadable profile config
    degrades to ``None`` (host login) rather than breaking every
    ``ClaudeSDKProvider`` construction.
    """
    from testmcpy.llm_profiles import get_llm_profile_config

    try:
        profile = get_llm_profile_config().get_profile(llm_profile_id)
        if not profile:
            return None
        candidates = [p for p in profile.providers if p.provider in CLAUDE_SDK_PROVIDERS]
        if not candidates:
            return None
        chosen = None
        if model:
            chosen = next((p for p in candidates if p.model == model), None)
        if chosen is None:
            chosen = next((p for p in candidates if p.default), None) or candidates[0]
        if chosen.api_key:
            return chosen.api_key
        if chosen.api_key_env:
            return os.environ.get(chosen.api_key_env)
        return None
    except (OSError, ValueError, KeyError, AttributeError, TypeError) as e:
        _claude_sdk_logger.warning(
            "resolve_claude_cli_token: ignoring bad LLM profile config: %s", e
        )
        return None


def claude_provider_api_key_kwargs(
    provider: str,
    model: str | None = None,
    llm_profile_id: str | None = None,
) -> dict[str, str]:
    """``{"api_key": <token>}`` for create_llm_provider when ``provider`` is in
    the Claude family and a token is configured; otherwise ``{}``.

    Safe to splat into ``create_llm_provider(...)`` for any provider — returns
    empty for non-Claude providers so it never clobbers their credentials.
    """
    if provider not in CLAUDE_SDK_PROVIDERS:
        return {}
    token = resolve_claude_cli_token(model, llm_profile_id)
    return {"api_key": token} if token else {}


class ClaudeSDKProvider(BaseSDKProvider):
    """Claude Agent SDK provider with native MCP integration.

    Uses the claude-agent-sdk Python package (wraps Claude Code CLI internally).
    The SDK handles MCP tool discovery natively via McpHttpServerConfig —
    no need for our own ToolDiscoveryService.

    Supports JWT, OAuth, and Bearer auth for MCP servers via
    :class:`BaseSDKProvider`.

    Authentication for the model itself is optional: when ``api_key`` (or
    ``api_key_env``) supplies a token it is injected into the CLI subprocess
    env (see :func:`claude_cli_auth_env`). When none is supplied,
    ANTHROPIC_API_KEY is cleared so the CLI falls back to the host's Claude
    Code subscription login (the historical behavior).
    """

    LOGGER_NAME = "ClaudeSDKProvider"

    def __init__(
        self,
        model: str,
        mcp_url: str | None = None,
        auth: dict[str, Any] | None = None,
        log_callback=None,
        api_key: str | None = None,
        api_key_env: str | None = None,
    ):
        super().__init__(model=model, mcp_url=mcp_url, auth=auth)
        self.log_callback = log_callback
        # Optional model-auth token entered via the UI/profile. Precedence:
        # explicit api_key, then a named api_key_env, then a best-effort lookup
        # in the default LLM profile so code paths that can't thread a token
        # (CLI chat, docs optimizer, runner tools, websocket chat) still honor
        # a UI-entered token. None -> host ``claude`` login.
        self._cli_token = (
            api_key
            or (os.environ.get(api_key_env) if api_key_env else None)
            or resolve_claude_cli_token(model)
        )
        # The Claude SDK consumes an MCP server config dict shaped like
        # {"type": "http", "url": ..., "headers": {...}} — built in initialize().
        self._mcp_server_config: dict[str, Any] | None = None

    # ---- BaseSDKProvider hooks ------------------------------------------

    def _check_sdk_installed(self) -> None:
        try:
            from claude_agent_sdk import CLINotFoundError  # noqa: F401
        except ImportError:
            raise ValueError(
                "claude-agent-sdk package not installed. Install with: pip install claude-agent-sdk"
            )

    async def _validate_credentials(self) -> None:
        # ClaudeSDKProvider uses the Claude Code subscription (and explicitly
        # clears ANTHROPIC_API_KEY in _run_agent's env), so no upfront API
        # credentials are required here.
        return None

    @classmethod
    def _vendor_expected_errors(cls) -> tuple[type[BaseException], ...]:
        # claude-agent-sdk's own CLI/process/connection errors plus the
        # serialization-quirk errors that the previous implementation caught
        # at the generate_with_tools boundary. Preserves observable behavior.
        # Imports are deferred so the module loads without the SDK installed.
        try:
            from claude_agent_sdk import (  # noqa: PLC0415
                CLIConnectionError,
                CLINotFoundError,
                ProcessError,
            )
        except ImportError:
            return (
                ConnectionError,
                OSError,
                KeyError,
                ValueError,
                TypeError,
                json.JSONDecodeError,
            )
        return (
            CLINotFoundError,
            ProcessError,
            CLIConnectionError,
            ConnectionError,
            OSError,
            KeyError,
            ValueError,
            TypeError,
            json.JSONDecodeError,
        )

    async def initialize(self) -> None:
        """Extend :meth:`BaseSDKProvider.initialize` to also build the SDK's
        ``McpHttpServerConfig`` dict shaped like
        ``{"type": "http", "url": ..., "headers": {...}}``."""
        await super().initialize()

        from claude_agent_sdk.types import McpHttpServerConfig  # noqa: PLC0415

        server_config: McpHttpServerConfig = {"type": "http", "url": self.mcp_url}
        if self._mcp_headers:
            server_config["headers"] = dict(self._mcp_headers)
        self._mcp_server_config = server_config

    @staticmethod
    def _build_clean_env(
        source_env: dict[str, str] | None = None,
        cli_token: str | None = None,
    ) -> dict[str, str]:
        """Build the subprocess env handed to the Claude CLI.

        Inherits the current process env but:
        - Strips Claude Code session vars that would prevent nested CLI spawning.
        - When ``cli_token`` is supplied, injects it as the appropriate auth
          var (see :func:`claude_cli_auth_env`) and drops the conflicting one
          so only the chosen credential is present. When it is not supplied,
          clears ``ANTHROPIC_API_KEY`` so the CLI uses the host's Claude Code
          subscription login instead of API credits (historical behavior).
        - Sets ``IS_SANDBOX=1`` so ``--dangerously-skip-permissions`` (driven
          by ``permission_mode="bypassPermissions"``) is honored when
          testmcpy runs as root in a container. Recent Claude CLI versions
          refuse that flag under root/sudo without this opt-in. Harmless
          when not running as root.
        """
        if source_env is None:
            source_env = dict(os.environ)
        clean_env = {
            k: v
            for k, v in source_env.items()
            if not k.startswith("CLAUDE_CODE") and k != "CLAUDECODE"
        }
        auth_env = claude_cli_auth_env(cli_token)
        if auth_env:
            # Keep only the chosen credential so the two never conflict.
            clean_env.pop("ANTHROPIC_API_KEY", None)
            clean_env.pop("CLAUDE_CODE_OAUTH_TOKEN", None)
            clean_env.update(auth_env)
        else:
            clean_env["ANTHROPIC_API_KEY"] = ""  # Force subscription usage, not API credits
        clean_env["IS_SANDBOX"] = "1"
        return clean_env

    async def _run_agent(
        self,
        prompt: str,
        timeout: float,
        messages: list[dict[str, Any]] | None,
    ) -> SDKRunResult:
        """Execute the Claude Agent SDK query loop and return a normalised
        :class:`SDKRunResult` for :class:`BaseSDKProvider` to convert into
        :class:`LLMResult`."""
        logs: list[str] = []

        def log(msg: str):
            """Log to module logger, logs list, and optionally stream via callback."""
            _claude_sdk_logger.info(msg)
            logs.append(msg)
            if self.log_callback:
                if asyncio.iscoroutinefunction(self.log_callback):
                    try:
                        asyncio.get_event_loop().call_soon(
                            lambda m=msg: asyncio.ensure_future(self.log_callback(m))
                        )
                    except RuntimeError:
                        pass
                else:
                    self.log_callback(msg)

        try:
            from claude_agent_sdk import (
                AssistantMessage,
                ClaudeAgentOptions,
                ClaudeSDKError,
                CLIConnectionError,
                CLINotFoundError,
                ProcessError,
                RateLimitEvent,
                ResultMessage,
                SystemMessage,
                TextBlock,
                ThinkingBlock,
                ToolUseBlock,
                UserMessage,
                query,
            )
            from claude_agent_sdk.types import ToolResultBlock

            # Build SDK options
            mcp_servers = {}
            if self._mcp_server_config:
                mcp_servers["mcp-service"] = self._mcp_server_config
                log(f"[ClaudeSDK] MCP server configured: {self._mcp_server_config.get('url', '?')}")
            else:
                log("[ClaudeSDK] No MCP server config — SDK will have no MCP tools")

            # Build a clean env (see _build_clean_env for what gets stripped/added,
            # including the IS_SANDBOX=1 opt-in required when running as root).
            clean_env = self._build_clean_env(cli_token=self._cli_token)

            # Capture the CLI's stderr so failures (e.g. the root +
            # --dangerously-skip-permissions refusal) surface in the error
            # message instead of being swallowed by the previous
            # debug_stderr=None behavior. We keep a bounded buffer so a
            # noisy CLI can't blow up memory.
            stderr_capture: list[str] = []
            _max_stderr_lines = 200

            def _capture_stderr(line: str) -> None:
                if len(stderr_capture) < _max_stderr_lines:
                    stderr_capture.append(line)

            # Disable Claude Code's built-in tools (Bash, Read, Edit, Grep, etc.)
            # so the LLM only uses the MCP server's tools.
            # This prevents the LLM from calling ToolSearch or other internal tools
            # instead of the MCP gateway tools.
            _builtin_tools_to_block = [
                "Bash",
                "Read",
                "Edit",
                "Write",
                "Grep",
                "Glob",
                "ToolSearch",
                "Skill",
                "TodoWrite",
                "Agent",
                "WebFetch",
                "WebSearch",
                "NotebookEdit",
                "EnterWorktree",
                "ExitWorktree",
            ]

            # System prompt to focus the LLM on MCP tools exclusively
            system_prompt = (
                "You are a test executor. Your ONLY job is to call the MCP tools provided "
                "to fulfill the user's request, then report the results.\n\n"
                "IMPORTANT RULES:\n"
                "1. Use ONLY the MCP server tools provided to you. Do NOT use any Claude Code "
                "built-in tools and do NOT call tools from any other MCP server.\n"
                "2. Some MCP servers use a gateway pattern where tools are invoked via a meta-tool "
                "(e.g., call_tool(name='tool_name', arguments={...})). Use whatever interface the server provides.\n"
                "3. Do NOT call any tool discovery or search tools — the tool name is always specified "
                "in the request. Proceed directly to the requested tool without prior discovery.\n"
                "4. Do NOT call any authentication, login, or credential tool (e.g. 'authenticate'). "
                "Skip it and proceed directly to the requested tool.\n"
                "5. Always include the actual data from tool results in your response.\n"
                "6. Be concise and factual — include key data points from the tool output."
            )

            # Run the subprocess from a temp directory so it doesn't inherit
            # any project-level MCP config files from the working directory.
            # The only MCP server available to the subprocess is the one we
            # pass explicitly via mcp_servers above.
            _sdk_tmpdir = tempfile.mkdtemp(prefix="testmcpy_sdk_")

            options = ClaudeAgentOptions(
                model=self.model,
                permission_mode="bypassPermissions",
                mcp_servers=mcp_servers,
                max_turns=25,
                env=clean_env,
                cwd=_sdk_tmpdir,
                disallowed_tools=_builtin_tools_to_block,
                system_prompt=system_prompt,
                debug_stderr=None,  # Don't dump CLI debug to host stderr
                stderr=_capture_stderr,  # Capture lines for failure diagnostics
                # --strict-mcp-config tells the CLI to honour ONLY the MCP
                # servers we pass explicitly via mcp_servers above, ignoring
                # any servers in ~/.claude/settings.json, .mcp.json, or
                # user-installed plugins (e.g. Playwright). Without this flag
                # those global servers leak into the subprocess and the model
                # reaches for them (e.g. browser_navigate to read a tool-result
                # file) producing spurious tool-call errors in eval results.
                #
                # NOTE: setting_sources=[] looks like it should disable config
                # loading but the SDK only passes --setting-sources when the
                # list is truthy, so [] is silently a no-op. Use extra_args
                # to pass the flag directly instead.
                extra_args={"strict-mcp-config": None},
            )

            # Execute query with timeout
            response_text = ""
            thinking_text = ""
            tool_calls = []
            tool_results_map: dict[str, dict[str, Any]] = {}
            token_usage = None
            cost = 0.0
            raw_events = []

            # Retry budget: if the model keeps calling the SAME tool with the
            # SAME arguments and getting the SAME error, abort the query
            # rather than letting it spin until the wall-clock timeout fires.
            # Counts how many times each (tool_name, args, error) signature
            # has been seen; we abort when any signature crosses the
            # threshold below.
            error_signature_counts: dict[tuple[str, str, str], int] = {}
            max_repeats_per_signature = 3
            retry_budget_aborted = False

            log(f"[ClaudeSDK] Starting query (model={self.model}, timeout={timeout}s)...")

            async def execute_query():
                nonlocal response_text, thinking_text, token_usage, cost
                nonlocal retry_budget_aborted
                message_count = 0
                # Track all text blocks per AssistantMessage so we can
                # identify the FINAL text response (after all tool calls)
                all_text_segments: list[str] = []
                current_turn_text = ""
                try:
                    async for message in query(prompt=prompt, options=options):
                        message_count += 1
                        msg_type = type(message).__name__

                        if isinstance(message, SystemMessage):
                            raw_events.append(
                                {"type": msg_type, "subtype": message.subtype, "data": message.data}
                            )
                            log(f"[ClaudeSDK] System ({message.subtype})")
                            continue

                        raw_events.append({"type": msg_type})
                        # Suppress the generic header for known content-bearing types that
                        # already log their own descriptive lines (Text:, Tool Call:, etc.).
                        # Keep it as a fallback for any unknown/future SDK message types so
                        # they remain visible in verbose output rather than silently dropping.
                        if not isinstance(message, (AssistantMessage, UserMessage)):
                            log(f"[ClaudeSDK] Message #{message_count}: {msg_type}")

                        if isinstance(message, RateLimitEvent):
                            # Rate limit info from subscription — log but continue
                            info = message.rate_limit_info
                            log(
                                f"[ClaudeSDK] Rate limit: status={info.status}, "
                                f"utilization={info.utilization}"
                            )
                            continue

                        if isinstance(message, AssistantMessage):
                            # Start a new turn's text accumulator
                            current_turn_text = ""
                            for block in message.content:
                                if isinstance(block, TextBlock):
                                    current_turn_text += block.text
                                    preview = block.text[:80].replace("\n", " ")
                                    log(f"[ClaudeSDK] Text: {preview}...")
                                elif isinstance(block, ThinkingBlock):
                                    thinking_text += block.thinking
                                    truncated = len(block.thinking) > 100
                                    preview = repr(block.thinking[:100])
                                    suffix = "..." if truncated else ""
                                    log(
                                        f"[ClaudeSDK] Thinking: {preview}{suffix}"
                                        f" ({len(block.thinking)} chars)"
                                    )
                                elif isinstance(block, ToolUseBlock):
                                    tool_call = {
                                        "id": block.id,
                                        "name": block.name,
                                        "arguments": block.input,
                                    }
                                    tool_calls.append(tool_call)
                                    args_str = json.dumps(block.input)
                                    if len(args_str) > 200:
                                        args_str = args_str[:200] + "..."
                                    log(f"[ClaudeSDK] Tool Call: {block.name} | Args: {args_str}")

                            # Save this turn's text
                            if current_turn_text:
                                all_text_segments.append(current_turn_text)

                        elif isinstance(message, UserMessage):
                            # Tool results come back as UserMessage content
                            if isinstance(message.content, list):
                                for block in message.content:
                                    if isinstance(block, ToolResultBlock):
                                        tool_use_id = block.tool_use_id
                                        is_error = block.is_error or False
                                        # Serialize content to a plain string
                                        raw_content = block.content or ""
                                        if isinstance(raw_content, list):
                                            parts = []
                                            for item in raw_content:
                                                if hasattr(item, "text"):
                                                    parts.append(item.text)
                                                else:
                                                    parts.append(str(item))
                                            content = "\n".join(parts)
                                        elif hasattr(raw_content, "text"):
                                            content = raw_content.text
                                        elif not isinstance(raw_content, str):
                                            content = str(raw_content)
                                        else:
                                            content = raw_content
                                        tool_results_map[tool_use_id] = {
                                            "content": content,
                                            "is_error": is_error,
                                        }
                                        status = "Error" if is_error else "Success"
                                        content_preview = str(content)[:200]
                                        log(
                                            f"[ClaudeSDK] Tool Result ({status}): {content_preview}"
                                        )

                                        # Retry-budget enforcement: if the model
                                        # keeps making the same call with the
                                        # same args and getting the same error,
                                        # abort to break out of the loop.
                                        if is_error or _looks_like_error_payload(content):
                                            matching_call = next(
                                                (
                                                    tc
                                                    for tc in tool_calls
                                                    if tc.get("id") == tool_use_id
                                                ),
                                                None,
                                            )
                                            if matching_call:
                                                sig_args = json.dumps(
                                                    matching_call.get("arguments", {}),
                                                    sort_keys=True,
                                                    default=str,
                                                )[:200]
                                                # Use a normalized prefix of the
                                                # error text — exact byte match
                                                # would be too brittle.
                                                sig_err = str(content)[:120]
                                                sig = (
                                                    matching_call.get("name", ""),
                                                    sig_args,
                                                    sig_err,
                                                )
                                                error_signature_counts[sig] = (
                                                    error_signature_counts.get(sig, 0) + 1
                                                )
                                                if (
                                                    error_signature_counts[sig]
                                                    >= max_repeats_per_signature
                                                ):
                                                    log(
                                                        f"[ClaudeSDK] Retry budget exhausted: "
                                                        f"same call+error repeated "
                                                        f"{max_repeats_per_signature}× — aborting "
                                                        f"(tool={sig[0]}, error={sig_err[:80]!r})"
                                                    )
                                                    retry_budget_aborted = True
                                                    return

                        elif isinstance(message, ResultMessage):
                            if message.usage:
                                usage = message.usage
                                token_usage = {
                                    "prompt": (
                                        usage.get("input_tokens", 0)
                                        + usage.get("cache_read_input_tokens", 0)
                                        + usage.get("cache_creation_input_tokens", 0)
                                    ),
                                    "completion": usage.get("output_tokens", 0),
                                    "total": (
                                        usage.get("input_tokens", 0)
                                        + usage.get("cache_read_input_tokens", 0)
                                        + usage.get("cache_creation_input_tokens", 0)
                                        + usage.get("output_tokens", 0)
                                    ),
                                    "cache_creation": usage.get("cache_creation_input_tokens", 0),
                                    "cache_read": usage.get("cache_read_input_tokens", 0),
                                }
                            if message.total_cost_usd is not None:
                                cost = message.total_cost_usd
                            duration_ms = getattr(message, "duration_ms", 0)
                            log(
                                f"[ClaudeSDK] Result: {message.num_turns} turns, "
                                f"{duration_ms}ms, ${cost:.4f}"
                            )
                except ClaudeSDKError as e:
                    # SDK may throw on unknown message types (e.g. rate_limit_event).
                    # If we already collected any response or tool calls, treat as complete.
                    log(f"[ClaudeSDK] SDK error during iteration: {e}")
                    if not all_text_segments and not tool_calls:
                        raise

                # Use the FINAL text segment as the response. In a multi-turn
                # agentic loop (search → call → synthesize), intermediate text
                # is often "I'll check..." while the last segment contains the
                # actual answer with tool results incorporated.
                if all_text_segments:
                    response_text = all_text_segments[-1]
                    if len(all_text_segments) > 1:
                        log(
                            f"[ClaudeSDK] {len(all_text_segments)} text segments; "
                            f"using final segment ({len(response_text)} chars)"
                        )

                log(f"[ClaudeSDK] Completed: {message_count} messages, {len(response_text)} chars")

            # The base wraps _run_agent in asyncio.wait_for; we still run our
            # OWN wait_for here because we want to translate a wall-clock
            # timeout into a clean Error response that includes the partial
            # logs (the base swallows logs on timeout because it has no
            # SDKRunResult yet).
            try:
                await asyncio.wait_for(execute_query(), timeout=timeout)
            except asyncio.TimeoutError:
                log(f"[ClaudeSDK] TIMEOUT after {timeout}s")
                return SDKRunResult(
                    response_text=f"Error: SDK query timed out after {timeout}s",
                    logs=logs,
                )
            finally:
                shutil.rmtree(_sdk_tmpdir, ignore_errors=True)

            # Attach tool results to tool calls and build MCPToolResult objects
            mcp_tool_results = []
            for tc in tool_calls:
                tc_id = tc.get("id", "")
                if tc_id in tool_results_map:
                    tc["result"] = tool_results_map[tc_id]
                    result_data = tool_results_map[tc_id]
                    mcp_result = MCPToolResult(
                        tool_call_id=tc_id,
                        tool_name=tc.get("name"),
                        content=result_data.get("content", ""),
                        is_error=result_data.get("is_error", False),
                        error_message=str(result_data.get("content", ""))
                        if result_data.get("is_error")
                        else None,
                    )
                    mcp_tool_results.append(mcp_result)

            # If we aborted via the retry budget, surface that in the
            # response so evaluators see a clear, actionable error
            # rather than an empty / partial response.
            if retry_budget_aborted and not response_text:
                response_text = (
                    f"Error: aborted after the model repeated the same tool call "
                    f"and got the same error {max_repeats_per_signature}× in a row. "
                    f"This usually means the prompt is priming the model toward a "
                    f"wrong parameter name, the tool's schema mismatches the model's "
                    f"expectation, or the resource being queried doesn't exist. See "
                    f"the log lines marked '[ClaudeSDK] Tool Result (Error)' for the "
                    f"specific error pattern."
                )

            log(
                f"[ClaudeSDK] Done: {len(response_text)} chars, "
                f"{len(tool_calls)} tool calls, {len(mcp_tool_results)} results"
                + (" [retry budget aborted]" if retry_budget_aborted else "")
            )

            return SDKRunResult(
                response_text=response_text,
                tool_calls=tool_calls,
                tool_results=mcp_tool_results,
                thinking=thinking_text if thinking_text else None,
                token_usage=token_usage,
                cost=cost if cost else None,  # base estimates from registry if None/0
                raw_response={"events": raw_events} if raw_events else None,
                logs=logs,
            )

        except CLINotFoundError:
            log("[ClaudeSDK] Claude CLI not found — install @anthropic-ai/claude-code")
            return SDKRunResult(
                response_text=(
                    "Error: Claude CLI not found. "
                    "Install with: npm install -g @anthropic-ai/claude-code"
                ),
                logs=logs,
            )
        except ProcessError as e:
            # Surface the real CLI stderr (e.g. the root + bypassPermissions
            # refusal) instead of just "exit code 1". Prefer the stderr the
            # SDK already attached to ProcessError; fall back to our own
            # callback-captured buffer. Truncate to keep error payloads sane.
            sdk_stderr = (getattr(e, "stderr", None) or "").strip()
            captured = "\n".join(stderr_capture).strip()
            stderr_text = sdk_stderr or captured
            max_chars = 2000
            if len(stderr_text) > max_chars:
                stderr_text = stderr_text[-max_chars:]
            if stderr_text:
                log(f"[ClaudeSDK] CLI stderr (captured): {stderr_text}")
            log(f"[ClaudeSDK] Process error: {e}")
            response_msg = f"Error: Claude CLI process failed: {e}"
            if stderr_text and stderr_text not in str(e):
                response_msg = f"{response_msg}\nCLI stderr:\n{stderr_text}"
            return SDKRunResult(
                response_text=response_msg,
                logs=logs,
            )
        except CLIConnectionError as e:
            log(f"[ClaudeSDK] Connection error: {e}")
            return SDKRunResult(
                response_text=f"Error: Claude CLI connection failed: {e}",
                logs=logs,
            )
        except (KeyError, ValueError, TypeError, json.JSONDecodeError) as e:
            log(f"[ClaudeSDK] Unexpected error: {type(e).__name__}: {e}")
            return SDKRunResult(
                response_text=f"Error: {type(e).__name__}: {e}",
                logs=logs,
            )


_assistant_logger = logging.getLogger(__name__ + ".AssistantProvider")


def _format_seconds(seconds: float) -> str:
    """Format a duration so sub-second values aren't rounded to ``0s``.

    The SSE idle threshold is configurable down to fractions of a second
    (the unit tests override it to 0.3s). Using ``f"{x:.0f}s"`` would
    produce a misleading ``0s`` in those messages — switch to ms below
    1s, decimals below 10s, and integer seconds otherwise.
    """
    if seconds < 1.0:
        return f"{seconds * 1000:.0f}ms"
    if seconds < 10.0:
        return f"{seconds:.1f}s"
    return f"{seconds:.0f}s"


@dataclass
class _SSEStreamState:
    """Mutable state accumulated as we parse a chatbot SSE response."""

    response_text: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    tool_results: list[Any] = field(default_factory=list)
    token_usage: dict[str, int] | None = None
    got_final: bool = False
    got_error: bool = False
    error_message: str = ""
    tti_ms: int | None = None
    token_event_count: int = 0


class AssistantProvider(LLMProvider):
    """Generic LLM provider for chatbot/assistant HTTP endpoints.

    The chatbot endpoint owns the LLM and any tool-calling integration
    server-side; testmcpy just POSTs the prompt and reads back a
    streaming response. testmcpy does not list tools, mint conversations
    locally, or call MCP itself when this provider is in use.

    Protocol contract this provider expects:

    1. **Auth**: POST ``api_url`` with body
       ``{"name": api_token, "secret": api_secret}``; the response JSON
       has ``payload.access_token`` (a Bearer JWT).
    2. **Conversation**: POST ``{base_url}{conversations_path}`` with
       body ``{"conversation_starter": []}`` (Bearer-authenticated);
       the response JSON has ``id`` (the conversation id).
    3. **Completions**: POST ``{base_url}{completions_path}`` with
       body ``{"conversation_id", "messages": [{"role", "content"}],
       "model_override"?}`` and consume a ``text/event-stream`` of
       ``event:`` / ``data:`` pairs.

    Recognized SSE events (any others are ignored):

    - ``token``: ``{"chunk": "<text>"}`` — appended to the running
      response text. The first ``token`` event records TTI.
    - ``tool_call``: ``{"tool_call_id", "tool_name", "input"}`` — the
      backend invoked a tool.
    - ``tool_result``: ``{"tool_call_id", "tool_name?", "result",
      "is_error?", "duration_ms?"}`` — wrapped in :class:`MCPToolResult`
      so evaluators see the same shape across providers.
    - ``usage``: ``{"input_tokens", "output_tokens", "total_tokens"}``.
    - ``final``: end-of-response sentinel; may carry an ``answer`` /
      ``message`` field used as fallback when no ``token`` events came.
    - ``error``: ``{"error" | "message"}``.

    To target a vendor that diverges from this contract, subclass and
    override the relevant hook (``_authenticate``, ``_open_conversation``,
    ``_build_headers``, ``_build_completions_payload``,
    ``_handle_sse_event``).
    """

    # No hardcoded default paths — every deployment may differ.
    # Paths MUST be provided via .llm_providers.yaml or the
    # --assistant-conversations-path / --assistant-completions-path CLI flags.
    _DEFAULT_CONVERSATIONS_PATH: str | None = None
    _DEFAULT_COMPLETIONS_PATH: str | None = None

    # If the SSE stream emits no recognized event for this many seconds,
    # abort the stream. Defends against a chatbot backend that keeps the
    # connection open (preventing httpx's per-event read timeout from
    # firing) but stops emitting real progress. Observed in c29
    # (SC-105915). Class-level so subclasses / tests can override.
    SSE_IDLE_ABORT_SECONDS: float = 90.0

    # Hard ceiling on the entire SSE consumption — kicks in even when
    # bytes ARE flowing (just slowly) so the agor parallel-cycle harness
    # never sees a child stay alive past this. Distinct from the idle
    # abort: idle = "no progress at all"; per-call wall-clock = "any
    # progress, but too slow overall". Observed in c28-c32 against the
    # staging chatbot (SC-106138). Class-level so callers can override.
    PER_CALL_WALL_CLOCK_SECONDS: float = 180.0

    # Emit a structured heartbeat log line every N seconds while the SSE
    # stream is open. Lets a parent harness distinguish "child is still
    # streaming" from "child is wedged" without parsing every event.
    HEARTBEAT_SECONDS: float = 10.0

    # Max number of completion POSTs per generate_with_tools invocation.
    # The Preset chatbot backend executes tools server-side in a first
    # SSE stream that emits tool_call + tool_result events and then closes
    # WITHOUT a final / token event — the generated answer arrives only on
    # a SECOND POST against the same conversation_id. Cap protects against
    # a backend that keeps reporting tool calls without ever returning text.
    #
    # Raised from 3 → 8: multi-step chatbot prompts legitimately walk through
    # several info-gathering tool calls across multiple turns before the
    # chatbot is ready to produce a final answer. The cap was clipping the
    # synthesis turn off.
    # Idle (SSE_IDLE_ABORT_SECONDS, default 90s) and per-call wall-clock
    # (PER_CALL_WALL_CLOCK_SECONDS, default 180s) still bound runaway
    # streams independently of this cap.
    MAX_COMPLETION_TURNS: int = 8

    # Optional process-wide cap on concurrent SSE streams. Set via
    # ``--max-concurrent-streams`` on ``testmcpy run``. ``None`` =
    # unbounded. Stored as a class attribute (not instance) so multiple
    # AssistantProvider instances inside the same process share it.
    #
    # The Semaphore itself is lazily allocated inside the event loop on
    # first use — `asyncio.Semaphore` binds to the running loop, so
    # creating it at sync configuration time would either fail or bind
    # to the wrong loop.
    _max_concurrent_streams: int | None = None
    _stream_semaphore: asyncio.Semaphore | None = None
    _stream_semaphore_loop: object | None = None  # the loop the sem was bound to

    @classmethod
    def configure_concurrency_limit(cls, max_streams: int | None) -> None:
        """Set the process-wide cap on concurrent SSE streams.

        ``None`` (or 0) → unbounded. Positive int → cap. Negative
        values raise ``ValueError`` (a Semaphore with a negative
        capacity would crash at acquire time, so reject up front).
        The class-level ``asyncio.Semaphore`` is created lazily on
        first use and shared across all AssistantProvider instances
        in the process. Safe to call multiple times — the semaphore
        is re-created lazily next time ``_get_stream_semaphore`` is
        called.
        """
        if max_streams is not None and max_streams < 0:
            raise ValueError(
                f"max_streams must be a non-negative int or None, "
                f"got {max_streams!r}. Use 0 or None for unbounded."
            )
        if not max_streams:
            cls._max_concurrent_streams = None
        else:
            cls._max_concurrent_streams = max_streams
        # Drop any existing semaphore so the next acquire rebuilds with
        # the new limit (and rebinds to the current event loop).
        cls._stream_semaphore = None
        cls._stream_semaphore_loop = None

    @classmethod
    def _get_stream_semaphore(cls) -> asyncio.Semaphore | None:
        """Return the (lazily-created) class-level Semaphore, or None
        if no concurrency limit is configured. Rebinds to the running
        loop if the previously-bound loop is gone (test isolation)."""
        if not cls._max_concurrent_streams:
            return None
        running_loop = asyncio.get_running_loop()
        if cls._stream_semaphore is None or cls._stream_semaphore_loop is not running_loop:
            cls._stream_semaphore = asyncio.Semaphore(cls._max_concurrent_streams)
            cls._stream_semaphore_loop = running_loop
        return cls._stream_semaphore

    def __init__(
        self,
        model: str = "default",
        workspace_hash: str | None = None,
        domain: str | None = None,
        environment: str | None = None,
        api_token: str | None = None,
        api_secret: str | None = None,
        api_url: str | None = None,
        model_override: str | None = None,
        conversations_path: str | None = None,
        completions_path: str | None = None,
        **kwargs,
    ):
        self.model = model
        self.model_override = model_override
        self.conversations_path = conversations_path or self._DEFAULT_CONVERSATIONS_PATH
        self.completions_path = completions_path or self._DEFAULT_COMPLETIONS_PATH

        if not self.conversations_path:
            raise ValueError(
                "AssistantProvider: conversations_path is required. "
                "Set it in .llm_providers.yaml (conversations_path key under the provider) "
                "or pass --assistant-conversations-path on the CLI."
            )
        if not self.completions_path:
            raise ValueError(
                "AssistantProvider: completions_path is required. "
                "Set it in .llm_providers.yaml (completions_path key under the provider) "
                "or pass --assistant-completions-path on the CLI."
            )

        # Auth must come from .llm_providers.yaml or explicit CLI flags.
        # No fallback to MCP config — assistant and MCP are separate concerns.
        self.workspace_hash = workspace_hash or ""
        self.domain = domain or ""
        self.environment = environment or "staging"
        self.api_token = api_token or ""
        self.api_secret = api_secret or ""
        self.api_url = api_url or ""

        # Derive base workspace URL. Both workspace_hash and domain are
        # required — environment alone isn't enough since we don't ship
        # any environment→domain mapping in code.
        if self.workspace_hash and self.domain:
            self.base_url = f"https://{self.workspace_hash}.{self.domain}"
        else:
            self.base_url = ""

        # Session state populated by initialize()
        self._session_token: str | None = None
        self._csrf_token: str = str(uuid.uuid4())
        self._conversation_id: str | None = None
        self._client: httpx.AsyncClient | None = None

    # --- Public API -------------------------------------------------

    @property
    def completions_url(self) -> str:
        """Full URL of the chatbot completions endpoint, for display in verbose output."""
        return f"{self.base_url}{self.completions_path}"

    async def initialize(self):
        """Validate config, create an HTTP client, authenticate.

        NOTE: conversation creation moved into ``generate_with_tools`` so each
        test gets a fresh conversation. Reusing a single conversation across
        a multi-test suite let the backend's per-conversation history grow
        unbounded — later tests in C01-exploration silently returned empty
        SSE streams (zero tool_calls, zero text, no error) once the
        conversation hit its server-side context limit. SC-108179.
        """
        cls_name = type(self).__name__
        if not self.base_url:
            raise ValueError(
                f"{cls_name} requires workspace_hash AND domain. "
                "Pass them via the `--workspace-hash` and `--domain` CLI flags "
                f"on `testmcpy run`, or as kwargs to {cls_name}()."
            )
        if not self.api_token or not self.api_secret:
            raise ValueError(
                f"{cls_name} requires api_token and api_secret for auth. "
                "Pass them via the `--assistant-api-token` / `--assistant-api-secret` "
                "CLI flags (or `--jwt-token` / `--jwt-secret` if MCP and the "
                "assistant share creds), or configure them in the MCP profile "
                "auth block."
            )
        if not self.api_url or not str(self.api_url).strip():
            raise ValueError(
                f"{cls_name} requires a non-empty api_url. "
                "Pass it via the `--assistant-api-url` CLI flag (or `--jwt-url` "
                "if MCP and the assistant share auth), or configure api_url in "
                "the MCP profile."
            )

        self._client = httpx.AsyncClient(timeout=60.0)
        await self._authenticate()

    async def close(self):
        """Close the httpx client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def generate_with_tools(
        self,
        prompt: str,
        tools: list[dict[str, Any]] | None = None,
        timeout: float = 120.0,
        messages: list[dict[str, Any]] | None = None,
        **kwargs,
    ) -> LLMResult:
        """POST the prompt and stream the SSE response.

        Tool schemas are ignored — the chatbot endpoint owns its tool
        registry server-side.
        """
        start_time = time.time()
        logs: list[str] = []

        def log(msg: str):
            _assistant_logger.info(msg)
            logs.append(msg)

        if not self._client or not self._session_token:
            return LLMResult(
                response=(
                    f"Error: {type(self).__name__} not initialized. Call initialize() first."
                ),
                tool_calls=[],
                duration=time.time() - start_time,
                logs=logs,
            )

        # Open a fresh conversation for every call. Reusing the same
        # conversation_id across a multi-test suite let the backend's
        # per-conversation history grow unbounded — later tests silently
        # returned empty SSE streams (zero tool_calls, zero text, no
        # error) once the conversation hit its context limit (SC-108179).
        # Failures here surface as an LLMResult-with-error so the test
        # runner gets a real result object back, not an exception.
        try:
            await self._open_conversation()
        except (RuntimeError, httpx.HTTPError, ValueError) as e:
            log(f"[Assistant] Conversation creation failed: {e}")
            return LLMResult(
                response=f"Error: failed to create conversation: {e}",
                tool_calls=[],
                duration=time.time() - start_time,
                logs=logs,
            )
        log(f"[Assistant] Fresh conversation: {self._conversation_id}")

        payload = self._build_completions_payload(prompt)
        completions_url = f"{self.base_url}{self.completions_path}"
        headers = {**self._build_headers(), "Accept": "text/event-stream"}

        # Three layers of timeout protection on the SSE consumption:
        #   1. SSE_IDLE_ABORT_SECONDS  — fires when no recognized event
        #      arrives for N seconds (server still sending keepalives
        #      but no real progress). c29 (SC-105915).
        #   2. PER_CALL_WALL_CLOCK_SECONDS — fires when total time on
        #      THIS call exceeds the budget, regardless of progress.
        #      Catches the slow-but-not-stuck case the agor harness
        #      hits in c28-c32 (SC-106138) where bytes keep flowing
        #      but the call takes 5+ minutes.
        #   3. HEARTBEAT_SECONDS — non-fatal: emits a "still streaming"
        #      log line every N seconds so a parent harness can tell
        #      a slow stream from a wedged one.
        sse_idle_abort_seconds = self.SSE_IDLE_ABORT_SECONDS
        per_call_wall_clock_seconds = self.PER_CALL_WALL_CLOCK_SECONDS
        heartbeat_seconds = self.HEARTBEAT_SECONDS
        max_turns = self.MAX_COMPLETION_TURNS
        idle_aborted = False
        wall_clock_aborted = False

        state = _SSEStreamState()
        # Optional process-wide concurrency cap. When unset the semaphore
        # is None and acquisition is a no-op. Held for the entire SSE
        # consumption (across follow-up turns too) so the cap really does
        # limit parallel logical requests, not parallel POSTs.
        sem = type(self)._get_stream_semaphore()
        sem_held = False
        if sem is not None:
            sem_wait_start = time.time()
            await sem.acquire()
            sem_held = True
            sem_wait = time.time() - sem_wait_start
            if sem_wait > 0.5:
                log(
                    f"[Assistant] Waited {sem_wait:.1f}s for concurrency-limit "
                    f"semaphore (max={type(self)._max_concurrent_streams})"
                )

        def _release_sem():
            nonlocal sem_held
            if sem is not None and sem_held:
                sem.release()
                sem_held = False

        # Multi-turn loop. The Preset chatbot backend executes tools
        # server-side and emits tool_call + tool_result events on the
        # FIRST POST but then closes the stream WITHOUT emitting a
        # final/token event — the generated answer arrives on a SECOND
        # POST that reuses the same conversation_id. Loop continues
        # until we get text, a final marker, an error, or hit the cap.
        # See SC-108177.
        total_event_count = 0
        turn_idx = 0
        try:
            for turn_idx in range(max_turns):
                if turn_idx == 0:
                    log(
                        f"[Assistant] POST {completions_url} (conversation={self._conversation_id})"
                    )
                else:
                    log(
                        f"[Assistant] Follow-up POST {turn_idx + 1}/{max_turns} "
                        f"(server-side tools executed but no answer text yet — "
                        f"reissuing same prompt on conversation={self._conversation_id})"
                    )
                # Per-turn timing. Wall-clock + idle budgets apply per turn,
                # not across the whole multi-turn loop, because a follow-up
                # POST is a separate SSE stream from the backend's POV.
                stream_start_time = time.time()
                last_event_at = stream_start_time
                last_heartbeat_at = stream_start_time
                event_count = 0
                pre_turn_response_len = len(state.response_text)
                pre_turn_tool_results = len(state.tool_results)
                async with self._client.stream(
                    "POST", completions_url, headers=headers, json=payload, timeout=timeout
                ) as resp:
                    if resp.status_code != 200:
                        body = await resp.aread()
                        raise RuntimeError(
                            f"Assistant API error: HTTP {resp.status_code} - "
                            f"{body.decode('utf-8', errors='replace')}"
                        )

                    current_event: str | None = None
                    # Drive the line iterator manually so we can wrap each
                    # await in asyncio.wait_for(...). httpx's aiter_lines()
                    # blocks inside __anext__ when no bytes arrive — a plain
                    # `async for` would be suspended forever. The wait_for
                    # catches the case where the SSE connection stays open
                    # but never sends another byte (real-world c29 hang).
                    line_iter = resp.aiter_lines().__aiter__()
                    idle_budget_str = _format_seconds(sse_idle_abort_seconds)
                    wall_clock_budget_str = _format_seconds(per_call_wall_clock_seconds)
                    while True:
                        now = time.time()
                        # Per-call wall-clock check: total time spent on the
                        # SSE stream itself (NOT counting time waiting for
                        # the concurrency-limit semaphore) exceeded budget.
                        total_elapsed = now - stream_start_time
                        if total_elapsed >= per_call_wall_clock_seconds:
                            log(
                                f"[Assistant] SSE wall-clock abort: per-call budget "
                                f"{wall_clock_budget_str} exceeded "
                                f"({total_elapsed:.0f}s, {event_count} events) — "
                                "closing stream"
                            )
                            wall_clock_aborted = True
                            break
                        # Idle check: no recognized event for too long.
                        elapsed_since_event = now - last_event_at
                        idle_remaining = sse_idle_abort_seconds - elapsed_since_event
                        if idle_remaining <= 0:
                            log(
                                f"[Assistant] SSE idle abort: no recognized event for "
                                f"{idle_budget_str} — closing stream"
                            )
                            idle_aborted = True
                            break
                        # Heartbeat: non-fatal "still alive" log.
                        if now - last_heartbeat_at >= heartbeat_seconds:
                            log(
                                f"[Assistant] still streaming … "
                                f"{total_elapsed:.0f}s elapsed, "
                                f"{event_count} events, "
                                f"{elapsed_since_event:.0f}s since last event"
                            )
                            last_heartbeat_at = now
                        # Per-line read budget = min(idle_remaining, time-to-next-heartbeat,
                        # wall-clock-remaining). Smaller waits let the heartbeat /
                        # wall-clock checks fire on schedule even when no bytes arrive.
                        wall_clock_remaining = per_call_wall_clock_seconds - total_elapsed
                        next_heartbeat_in = heartbeat_seconds - (now - last_heartbeat_at)
                        read_timeout = max(
                            0.05,
                            min(idle_remaining, wall_clock_remaining, next_heartbeat_in),
                        )
                        try:
                            raw_line = await asyncio.wait_for(
                                line_iter.__anext__(), timeout=read_timeout
                            )
                        except StopAsyncIteration:
                            break
                        except asyncio.TimeoutError:
                            # Read deadline expired — loop top will re-check
                            # idle / wall-clock / heartbeat. Most likely the
                            # heartbeat tick.
                            continue

                        line = raw_line.strip()
                        if not line:
                            current_event = None
                            continue
                        if line.startswith("event:"):
                            current_event = line[6:].strip()
                            continue
                        if not line.startswith("data:") or current_event is None:
                            continue

                        json_str = line[5:].strip()
                        if not json_str:
                            continue

                        if state.tti_ms is None and current_event == self._first_token_event():
                            state.tti_ms = int((time.time() - start_time) * 1000)

                        try:
                            data = json.loads(json_str)
                        except json.JSONDecodeError:
                            log(f"[Assistant] Failed to parse SSE data: {json_str[:100]}")
                            continue

                        self._handle_sse_event(current_event, data, state, log)
                        # A real event arrived — reset the idle timer.
                        last_event_at = time.time()
                        event_count += 1

                total_event_count += event_count

                # Decide whether to do a follow-up POST. Several subtle
                # interactions to keep straight:
                #
                # - The backend may interleave transitional text with tool
                #   calls in the same SSE turn — a naïve "any text → stop"
                #   would surface the fragment as the answer prematurely.
                # - The backend may also send `final` in the SAME turn as
                #   tool calls (tool ran, `final` arrived, but the actual
                #   synthesized answer came on a follow-up POST). Treating
                #   `final` as unconditional "we're done" drops that synthesis.
                #
                # Stop on ANY of:
                #   1. backend signaled an error — terminal regardless.
                #   2. backend signaled `final` AND no new tool_results
                #      this turn — backend has nothing left to synthesize.
                #   3. one of the streaming safety guards fired.
                #   4. text grew AND no new tool_results — we got a
                #      synthesized answer with no outstanding server-side
                #      work.
                #   5. nothing happened this turn (no text, no tools) —
                #      a follow-up would just be a no-op POST.
                if state.got_error:
                    break
                new_tool_results_this_turn = len(state.tool_results) > pre_turn_tool_results
                if state.got_final and not new_tool_results_this_turn:
                    break
                if idle_aborted or wall_clock_aborted:
                    break
                text_grew = len(state.response_text) > pre_turn_response_len
                if text_grew and not new_tool_results_this_turn:
                    break
                if not text_grew and not new_tool_results_this_turn:
                    log(
                        "[Assistant] No new tool_results and no answer text — "
                        "stopping multi-turn loop (would be a no-op POST)"
                    )
                    break
        except httpx.TimeoutException:
            duration = time.time() - start_time
            log(f"[Assistant] TIMEOUT after {duration:.1f}s (turn {turn_idx + 1})")
            _release_sem()
            return LLMResult(
                response=f"Error: Assistant request timed out after {timeout}s",
                tool_calls=state.tool_calls,
                tool_results=state.tool_results,
                duration=duration,
                logs=logs,
            )
        except (httpx.HTTPStatusError, httpx.ConnectError, RuntimeError) as e:
            duration = time.time() - start_time
            log(f"[Assistant] Request failed (turn {turn_idx + 1}): {e}")
            _release_sem()
            return LLMResult(
                response=f"Error: {e}",
                tool_calls=state.tool_calls,
                tool_results=state.tool_results,
                duration=duration,
                logs=logs,
            )
        finally:
            # Always release on the success path. ``_release_sem`` is
            # idempotent (sem_held flag) so it's safe to also call on
            # the except branches above.
            _release_sem()

        # For logging / accounting downstream.
        event_count = total_event_count
        # Final per-call wall clock for the abort message uses the LAST
        # turn's stream_start_time (set at the top of every turn).
        duration = time.time() - start_time
        if state.got_error and not state.response_text:
            state.response_text = f"Error: {state.error_message}"
        elif wall_clock_aborted and not state.response_text:
            # Surface the wall-clock abort with the same shape as the
            # idle abort so evaluators see a clean error string. Uses
            # stream_elapsed (NOT total duration) so the reported time
            # matches the actual budget — total `duration` would
            # include semaphore-wait time which by design isn't
            # charged against the wall-clock budget.
            stream_elapsed = time.time() - stream_start_time
            state.response_text = (
                f"Error: SSE stream exceeded the per-call wall-clock budget of "
                f"{_format_seconds(per_call_wall_clock_seconds)} "
                f"({stream_elapsed:.0f}s elapsed, {event_count} events). "
                "The stream was making progress but too slowly. Aborted to "
                "free the runner (SC-106138)."
            )
        elif idle_aborted and not state.response_text:
            # Surface the idle abort cleanly so evaluators don't see an
            # empty response with no explanation.
            state.response_text = (
                f"Error: SSE stream went idle for "
                f"{_format_seconds(sse_idle_abort_seconds)} without sending a "
                "final / error event. The chatbot backend kept the connection "
                "open but stopped emitting progress. Aborted to free the runner."
            )

        abort_marker = ""
        if idle_aborted:
            abort_marker = " [SSE idle aborted]"
        elif wall_clock_aborted:
            abort_marker = " [SSE wall-clock aborted]"
        log(
            f"[Assistant] Done: {len(state.response_text)} chars, "
            f"{len(state.tool_calls)} tool calls, "
            f"{len(state.tool_results)} tool results, "
            f"{state.token_event_count} tokens, "
            f"turns={turn_idx + 1}/{max_turns}, "
            f"final={'yes' if state.got_final else 'no'}, "
            f"error={'yes' if state.got_error else 'no'}, "
            f"{duration:.2f}s" + abort_marker
        )

        return LLMResult(
            response=state.response_text,
            tool_calls=state.tool_calls,
            tool_results=state.tool_results,
            token_usage=state.token_usage,
            cost=0.0,
            duration=duration,
            tti_ms=state.tti_ms,
            logs=logs,
        )

    # --- Hooks (override to target a different vendor) -------------

    async def _authenticate(self) -> None:
        """Exchange (api_token, api_secret) for a Bearer session token."""
        assert self._client is not None
        _assistant_logger.info("[Assistant] Authenticating at: %s", self.api_url)
        try:
            resp = await self._client.post(
                self.api_url,
                headers={"Content-Type": "application/json", "Accept": "application/json"},
                json={"name": self.api_token, "secret": self.api_secret},
                timeout=30.0,
            )
            resp.raise_for_status()
            data = resp.json()
            self._session_token = data.get("payload", {}).get("access_token", "")
            if not self._session_token:
                raise ValueError(f"No access_token in auth response: {data}")
            _assistant_logger.info(
                "[Assistant] Session token obtained (length: %d)", len(self._session_token)
            )
        except httpx.HTTPStatusError as e:
            raise RuntimeError(
                f"Auth failed: HTTP {e.response.status_code} - {e.response.text}"
            ) from e
        except httpx.ConnectError as e:
            raise RuntimeError(f"Auth connection failed: {e}") from e

    async def _open_conversation(self) -> None:
        """POST to ``conversations_path`` to start a session."""
        assert self._client is not None
        conv_url = f"{self.base_url}{self.conversations_path}"
        _assistant_logger.info("[Assistant] Creating conversation at: %s", conv_url)
        try:
            resp = await self._client.post(
                conv_url,
                headers=self._build_headers(),
                json={"conversation_starter": []},
                timeout=30.0,
            )
            resp.raise_for_status()
            conv_data = resp.json()
            self._conversation_id = conv_data.get("id")
            if not self._conversation_id:
                raise ValueError(f"No conversation ID in response: {conv_data}")
            _assistant_logger.info("[Assistant] Conversation created: %s", self._conversation_id)
        except httpx.HTTPStatusError as e:
            raise RuntimeError(
                f"Conversation creation failed: HTTP {e.response.status_code} - {e.response.text}"
            ) from e

    def _build_headers(self) -> dict[str, str]:
        """Auth headers for the conversation + completions calls.

        Bearer + cookie + CSRF, since some chatbot backends are served
        from the same web app as a UI and require the CSRF guard.
        """
        return {
            "Authorization": f"Bearer {self._session_token}",
            "Cookie": f"__s__={self._session_token}; csrf_access_token={self._csrf_token}",
            "X-CSRFToken": self._csrf_token,
            "Content-Type": "application/json",
            "Referer": f"{self.base_url}/",
        }

    def _build_completions_payload(self, prompt: str) -> dict[str, Any]:
        """Body for the streaming POST.

        Default: ``{conversation_id, messages, model_override?}``.
        """
        payload: dict[str, Any] = {
            "conversation_id": self._conversation_id,
            "messages": [{"role": "user", "content": prompt}],
        }
        if self.model_override or (self.model and self.model != "default"):
            payload["model_override"] = self.model_override or self.model
        return payload

    def _first_token_event(self) -> str:
        """Name of the SSE event that signals the first content token.

        Used to record TTI (time-to-first-token).
        """
        return "token"

    def _handle_sse_event(
        self, event: str, data: dict[str, Any], state: _SSEStreamState, log
    ) -> None:
        """Process a single SSE event and mutate ``state``."""
        from testmcpy.src.mcp_client import MCPToolResult

        if event == "token":
            chunk = data.get("chunk", "")
            state.response_text += chunk
            state.token_event_count += 1
        elif event == "tool_call":
            # Different chatbot backends use different field names — try all known variants.
            fn_dict = data.get("function") if isinstance(data.get("function"), dict) else {}
            tool_name = (
                data.get("tool_name")
                or data.get("name")
                or data.get("function_name")
                # Nested dict: {"function": {"name": ...}}
                or fn_dict.get("name")
                # Flattened dotted key: {"function.name": ...}
                or data.get("function.name")
                or ""
            )
            raw_args = (
                data.get("input")
                or data.get("arguments")
                or data.get("parameters")
                or fn_dict.get("arguments")
                # Flattened dotted key
                or data.get("function.arguments")
                or {}
            )
            # Some backends serialise arguments as a JSON string rather than a dict.
            if isinstance(raw_args, str):
                try:
                    raw_args = json.loads(raw_args)
                except (json.JSONDecodeError, ValueError):
                    raw_args = {}
            tool_args: dict = raw_args if isinstance(raw_args, dict) else {}
            tool_id = data.get("tool_call_id") or data.get("id", "")
            tc = {"id": tool_id, "name": tool_name, "arguments": tool_args}
            state.tool_calls.append(tc)
            args_preview = json.dumps(tool_args)[:100] if tool_args else "{}"
            log(f"[Assistant] Tool call: {tool_name}({args_preview}) id={tool_id}")
        elif event == "tool_result":
            result_payload = data.get("result")
            is_error = bool(data.get("is_error", False))
            if not is_error and isinstance(result_payload, dict):
                if result_payload.get("isError") or result_payload.get("is_error"):
                    is_error = True

            tool_call_id = data.get("tool_call_id") or data.get("id", "")
            tool_name = (
                data.get("tool_name")
                or data.get("name")
                or data.get("function_name")
                or next(
                    (tc.get("name") for tc in state.tool_calls if tc.get("id") == tool_call_id),
                    None,
                )
            )

            tr = MCPToolResult(
                tool_call_id=tool_call_id,
                tool_name=tool_name,
                content=result_payload,
                is_error=is_error,
                error_message=str(result_payload) if is_error else None,
            )
            state.tool_results.append(tr)
            log(
                f"[Assistant] Tool result: id={tool_call_id}, "
                f"tool={tool_name}, duration={data.get('duration_ms')}ms"
            )
        elif event == "usage":
            state.token_usage = {
                "prompt": data.get("input_tokens", 0),
                "completion": data.get("output_tokens", 0),
                "total": data.get("total_tokens", 0),
            }
            log(f"[Assistant] Usage: {state.token_usage}")
        elif event == "final":
            state.got_final = True
            final_answer = data.get("answer", "") or data.get("message", "")
            if final_answer and not state.response_text:
                state.response_text = final_answer
            log(f"[Assistant] Final event received ({len(state.response_text)} chars)")
        elif event == "error":
            state.got_error = True
            state.error_message = data.get("error", "") or data.get("message", "unknown error")
            log(f"[Assistant] Error event: {state.error_message}")


class GeminiProvider(LLMProvider):
    """Google Gemini API provider with tool calling support."""

    def __init__(
        self,
        model: str,
        api_key: str | None = None,
        mcp_url: str | None = None,
    ):
        self.model = model
        config = get_config()
        self.api_key = api_key or ""
        self.base_url = "https://generativelanguage.googleapis.com/v1beta"
        self.client = httpx.AsyncClient(timeout=60.0)
        # Use MCP_URL and auth from default profile if not provided
        if mcp_url is None:
            mcp_url = config.get_mcp_url()
        # Get auth from default MCP server
        auth = None
        default_mcp = config.get_default_mcp_server()
        if default_mcp and default_mcp.auth:
            auth = default_mcp.auth.to_dict()
        self.tool_discovery = ToolDiscoveryService(mcp_url, auth=auth)

    async def initialize(self):
        """Initialize Gemini provider."""
        if not self.api_key:
            raise ValueError(
                "Google API key not provided. Supply api_key in the LLM profile (.llm_providers.yaml)."
            )

        # Try to pre-discover tools
        try:
            await self.tool_discovery.discover_tools()
            print(f"✅ Successfully connected to MCP service at {self.tool_discovery.mcp_url}")
        except Exception as e:
            print(f"⚠️  Warning: Failed to initialize MCP tools: {e}")
            print("   The provider will work without MCP tools")

    async def generate_with_tools(
        self,
        prompt: str,
        tools: list[dict[str, Any]],
        timeout: float = 30.0,
        messages: list[dict[str, Any]] | None = None,
    ) -> LLMResult:
        """Generate response with Gemini's function calling."""
        start_time = time.time()

        try:
            # CRITICAL: Validate NO MCP URLs in request
            if not MCPURLFilter.validate_request_data({"prompt": prompt, "tools": tools}):
                raise Exception("SECURITY VIOLATION: MCP URLs detected in request data")

            # Convert tools to Gemini format
            gemini_tools = []
            function_declarations = []

            for tool in tools:
                if "function" in tool:
                    func = tool["function"]
                else:
                    func = tool

                # Sanitize tool schema
                sanitized = MCPURLFilter.sanitize_tool_schema(func)

                # Get parameters schema
                params = sanitized.get("parameters", sanitized.get("inputSchema", {}))
                if "type" not in params:
                    params["type"] = "object"

                function_declarations.append(
                    {
                        "name": sanitized.get("name", ""),
                        "description": sanitized.get("description", ""),
                        "parameters": params,
                    }
                )

            if function_declarations:
                gemini_tools = [{"function_declarations": function_declarations}]

            # Build request
            contents = []

            # Add message history if provided
            if messages:
                for msg in messages:
                    if msg.get("content"):
                        role = "user" if msg.get("role") == "user" else "model"
                        contents.append({"role": role, "parts": [{"text": msg["content"]}]})

            # Add current prompt
            contents.append({"role": "user", "parts": [{"text": prompt}]})

            request_data = {
                "contents": contents,
                "generationConfig": {
                    "temperature": 0.1,
                    "maxOutputTokens": 2048,
                },
            }

            if gemini_tools:
                request_data["tools"] = gemini_tools

            # Final security check
            if not MCPURLFilter.validate_request_data(request_data):
                raise Exception("SECURITY VIOLATION: MCP URLs in final API request")

            # Make API call
            url = f"{self.base_url}/models/{self.model}:generateContent?key={self.api_key}"
            response = await self.client.post(url, json=request_data, timeout=timeout)

            if response.status_code != 200:
                raise Exception(f"Gemini API error: {response.status_code} - {response.text}")

            result = response.json()

            # Extract response
            response_text = ""
            tool_calls = []

            candidates = result.get("candidates", [])
            if candidates:
                content = candidates[0].get("content", {})
                parts = content.get("parts", [])

                for part in parts:
                    if "text" in part:
                        response_text += part["text"]
                    elif "functionCall" in part:
                        fc = part["functionCall"]
                        tool_calls.append(
                            {
                                "name": fc.get("name", ""),
                                "arguments": fc.get("args", {}),
                            }
                        )

            # Execute tool calls locally
            for tool_call in tool_calls:
                try:
                    await self.tool_discovery.execute_tool_call(tool_call)
                except (MCPError, KeyError) as e:
                    _logger.warning(
                        "Tool call %s failed locally: %s", tool_call.get("name", "?"), e
                    )

            # Extract usage metadata
            usage_metadata = result.get("usageMetadata", {})
            token_usage = {
                "prompt": usage_metadata.get("promptTokenCount", 0),
                "completion": usage_metadata.get("candidatesTokenCount", 0),
                "total": usage_metadata.get("totalTokenCount", 0),
            }

            cost = _estimate_cost_with_fallback(
                self.model,
                token_usage["prompt"],
                token_usage["completion"],
                fallback_input_per_1m=0.25,
                fallback_output_per_1m=0.50,
            )

            duration = time.time() - start_time
            tti_ms = int(duration * 1000)  # Non-streaming: TTI = total duration

            return LLMResult(
                response=response_text,
                tool_calls=tool_calls,
                token_usage=token_usage,
                cost=cost,
                duration=duration,
                tti_ms=tti_ms,
                raw_response=result,
            )

        except Exception as e:
            duration = time.time() - start_time
            error_details = f"Error Type: {type(e).__name__}\nError Message: {str(e)}"
            return LLMResult(
                response=f"Error: {error_details}",
                tool_calls=[],
                duration=duration,
                tti_ms=int(duration * 1000),
            )

    async def close(self):
        """Close connections."""
        await self.tool_discovery.close()
        await self.client.aclose()


# Factory function to create providers


class CodexCLIProvider(LLMProvider):
    """OpenAI Codex CLI provider via subprocess (similar to Claude Code).

    Deprecated in favour of CodexSDKProvider — kept for backward compatibility.
    """

    def __init__(
        self,
        model: str,
        codex_cli_path: str | None = None,
        mcp_url: str | None = None,
        auth: dict[str, Any] | None = None,
    ):
        if not re.match(r"^[a-zA-Z0-9._/-]+$", model):
            raise ValueError(f"Invalid model identifier: {model}")
        self.model = model
        self.codex_cli_path = codex_cli_path or self._find_codex_cli()
        # Use MCP_URL and auth from default profile if not provided
        config = get_config()
        if mcp_url is None:
            mcp_url = config.get_mcp_url()
        if auth is None:
            # Get auth from default MCP server
            default_mcp = config.get_default_mcp_server()
            if default_mcp and default_mcp.auth:
                auth = default_mcp.auth.to_dict()
        self.tool_discovery = ToolDiscoveryService(mcp_url, auth=auth)

    def _find_codex_cli(self) -> str:
        """Find Codex CLI in PATH or common locations."""
        # Check environment variable first
        cli_path = os.environ.get("CODEX_CLI_PATH")
        if cli_path and os.path.exists(cli_path):
            return cli_path

        # Check common locations
        common_paths = [
            "/usr/local/bin/codex",
            "/opt/homebrew/bin/codex",
            os.path.expanduser("~/.local/bin/codex"),
            os.path.expanduser("~/.npm-global/bin/codex"),
            "codex",  # In PATH
        ]

        for path in common_paths:
            try:
                result = subprocess.run([path, "--version"], capture_output=True, timeout=5)
                if result.returncode == 0:
                    return path
            except (subprocess.TimeoutExpired, FileNotFoundError):
                continue

        raise Exception(
            "Codex CLI not found. Install via: npm i -g @openai/codex or brew install --cask codex"
        )

    async def initialize(self):
        """Initialize Codex CLI provider."""
        # Verify Codex CLI is working
        try:
            result = subprocess.run(
                [self.codex_cli_path, "--version"], capture_output=True, timeout=10, text=True
            )
            if result.returncode != 0:
                raise Exception(f"Codex CLI error: {result.stderr}")
        except subprocess.TimeoutExpired:
            raise Exception("Codex CLI timeout during initialization")

        # Try to pre-discover tools, but don't fail if MCP service is unavailable
        try:
            await self.tool_discovery.discover_tools()
            print(f"✅ Successfully connected to MCP service at {self.tool_discovery.mcp_url}")
        except (ConnectionError, TimeoutError, OSError, ValueError) as e:
            print(f"⚠️  Warning: Failed to initialize MCP tools: {e}")
            print(f"   MCP URL: {self.tool_discovery.mcp_url}")
            print("   The provider will work without MCP tools (direct API calls only)")

    async def generate_with_tools(
        self,
        prompt: str,
        tools: list[dict[str, Any]],
        timeout: float = 120.0,
        messages: list[dict[str, Any]] | None = None,
    ) -> LLMResult:
        """Generate response using Codex CLI."""
        start_time = time.time()

        try:
            # Create tool-aware prompt template
            enhanced_prompt = self._create_tool_prompt(prompt, tools)

            # Run codex CLI with prompt
            # Codex CLI uses stdin for prompts similar to Claude
            cmd = [
                self.codex_cli_path,
                "--print",  # Print response only, no interactive mode
                "--model",
                self.model,
                "--dangerously-skip-permissions",  # Skip permission prompts for automation
            ]

            # Run as subprocess
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            # Send prompt and wait for response
            stdout, stderr = await asyncio.wait_for(
                process.communicate(input=enhanced_prompt.encode()), timeout=timeout
            )

            response_text = stdout.decode("utf-8").strip()

            if process.returncode != 0:
                error_text = stderr.decode("utf-8").strip()
                return LLMResult(
                    response=f"Codex CLI error: {error_text}",
                    tool_calls=[],
                    duration=time.time() - start_time,
                )

            # Parse tool calls from CLI output
            tool_calls = self._parse_tool_calls(response_text)

            # Execute tool calls locally
            for tool_call in tool_calls:
                try:
                    await self.tool_discovery.execute_tool_call(tool_call)
                except (MCPError, KeyError) as e:
                    _logger.warning(
                        "Tool call %s failed locally: %s", tool_call.get("name", "?"), e
                    )

            return LLMResult(
                response=response_text,
                tool_calls=tool_calls,
                token_usage=None,  # CLI doesn't provide token counts
                cost=0.0,  # CLI usage varies by subscription
                duration=time.time() - start_time,
                raw_response={"stdout": response_text},
            )

        except asyncio.TimeoutError:
            return LLMResult(
                response=f"Error: Codex CLI timed out after {timeout}s",
                tool_calls=[],
                duration=time.time() - start_time,
            )
        except (subprocess.SubprocessError, OSError, ValueError) as e:
            return LLMResult(
                response=f"Error: {str(e)}", tool_calls=[], duration=time.time() - start_time
            )

    def _create_tool_prompt(self, prompt: str, tools: list[dict[str, Any]]) -> str:
        """Create enhanced prompt with tool descriptions."""
        if not tools:
            return prompt

        tool_descriptions = []
        for tool in tools:
            name = tool.get("name", "unknown")
            desc = tool.get("description", "")
            params = tool.get("inputSchema", tool.get("parameters", {}))

            tool_desc = f"**{name}**: {desc}"
            if params.get("properties"):
                param_list = ", ".join(params["properties"].keys())
                tool_desc += f" (parameters: {param_list})"

            tool_descriptions.append(tool_desc)

        return f"""You have access to the following tools:

{chr(10).join(tool_descriptions)}

When you need to use a tool, format your response like this:
TOOL_CALL: {{"name": "tool_name", "arguments": {{"param": "value"}}}}

User request: {prompt}"""

    def _parse_tool_calls(self, response: str) -> list[dict[str, Any]]:
        """Parse tool calls from Codex CLI response."""
        tool_calls = []

        # Look for TOOL_CALL: patterns
        tool_call_pattern = r"TOOL_CALL:\s*(\{[^}]+\}|\{[^}]*\{[^}]*\}[^}]*\})"
        matches = re.findall(tool_call_pattern, response)

        for match in matches:
            try:
                call_data = json.loads(match)
                if "name" in call_data:
                    tool_calls.append(
                        {"name": call_data["name"], "arguments": call_data.get("arguments", {})}
                    )
            except json.JSONDecodeError:
                continue

        return tool_calls

    async def close(self):
        """Close connections."""
        await self.tool_discovery.close()


# ---------------------------------------------------------------------------
# Codex SDK Provider (openai-agents with native MCP)
# ---------------------------------------------------------------------------

_codex_sdk_logger = logging.getLogger(__name__ + ".CodexSDKProvider")

# Maps testmcpy model IDs to real OpenAI model identifiers.
_CODEX_MODEL_MAP: dict[str, str] = {
    # Friendly registry IDs → real OpenAI model identifiers
    "codex": "o4-mini",
    "codex-latest": "o4-mini",
    "codex-sdk": "o4-mini",
    "codex-o4-mini": "o4-mini",
    "codex-o4mini": "o4-mini",
    "codex-mini": "o4-mini",
    "codex-o3": "o3",
    "codex-o3-full": "o3",
    "codex-o3-mini": "o3-mini",
    "codex-o3mini": "o3-mini",
    "codex-gpt-4o": "gpt-4o",
    "codex-4o": "gpt-4o",
}

_CODEX_SYSTEM_PROMPT = (
    "You are a test executor. Your ONLY job is to call the MCP tools provided "
    "to fulfil the user's request, then report the results.\n\n"
    "IMPORTANT RULES:\n"
    "1. Use ONLY the MCP server tools provided. Do NOT use any other tools or built-ins.\n"
    "2. Some MCP servers use a gateway pattern where tools are invoked via a meta-tool "
    "(e.g., call_tool(name='tool_name', arguments={...})). Use whatever interface the server provides.\n"
    "3. Do NOT call any tool discovery or search tools — the tool name is always specified "
    "in the request. Proceed directly to the requested tool without prior discovery.\n"
    "4. Do NOT call any authentication, login, or credential tool. "
    "Skip it and proceed directly to the requested tool.\n"
    "5. Always include the actual data from tool results in your response.\n"
    "6. Be concise and factual — include key data points from the tool output."
)


class CodexSDKProvider(BaseSDKProvider):
    """OpenAI Agents SDK provider with native MCP integration.

    Uses the openai-agents Python package (analogous to ClaudeSDKProvider).
    Handles MCP tool discovery natively via MCPServerStreamableHttp — no manual
    tool schema injection required.

    ``openai_api_key`` must be supplied via the constructor (resolved from the
    LLM profile in ``.llm_providers.yaml``) or left None to fall back to the
    stored Codex CLI API key (``OPENAI_API_KEY`` field in ``~/.codex/auth.json``).

    MCP server auth (bearer / jwt / oauth) is resolved by
    :class:`BaseSDKProvider` — including ``oauth_auto_discover`` via the
    proper :class:`fastmcp.client.auth.oauth.FileTokenStorage` API.
    """

    LOGGER_NAME = "CodexSDKProvider"

    def __init__(
        self,
        model: str,
        mcp_url: str | None = None,
        auth: dict[str, Any] | None = None,
        openai_api_key: str | None = None,
    ):
        # Keep the unmapped id (e.g. "codex-o3") for model_registry cost
        # estimation; pass the vendor id (e.g. "o3") to the base for self.model.
        self._registry_model_id = model
        super().__init__(
            model=_CODEX_MODEL_MAP.get(model, model),
            mcp_url=mcp_url,
            auth=auth,
        )
        self.openai_api_key = openai_api_key or ""

    # ---- BaseSDKProvider hooks ------------------------------------------

    def _check_sdk_installed(self) -> None:
        try:
            from agents import Agent, Runner  # noqa: F401, PLC0415
        except ImportError:
            raise ValueError(
                "openai-agents package not installed. Install with: pip install openai-agents"
            )

    async def _validate_credentials(self) -> None:
        # Constructor arg → cached Codex CLI key in ~/.codex/auth.json.
        if not self.openai_api_key:
            self.openai_api_key = self._read_cached_codex_token() or ""
        if not self.openai_api_key:
            raise ValueError(
                "No OpenAI api_key. Supply api_key in the LLM profile "
                "(.llm_providers.yaml) or configure the Codex CLI with an "
                "API key so it is stored in ~/.codex/auth.json."
            )

    @classmethod
    def _vendor_expected_errors(cls) -> tuple[type[BaseException], ...]:
        return (
            ConnectionError,
            OSError,
            TimeoutError,
            httpx.HTTPError,
        )

    def _read_cached_codex_token(self) -> str | None:
        """Read the stored OpenAI API key from ``~/.codex/auth.json``.

        The Codex CLI persists credentials as
        ``{"OPENAI_API_KEY": "sk-...", "tokens": {"access_token": "...", ...}}``.
        The top-level ``OPENAI_API_KEY`` is an OpenAI Platform key usable with
        api.openai.com; the nested OAuth ``access_token`` is a ChatGPT-backend
        token and does NOT work with the Platform API — don't read it here.
        Returns ``None`` when the key is absent or null (e.g. after a pure
        OAuth login where no API key was configured).
        """
        auth_path = Path.home() / ".codex" / "auth.json"
        if not auth_path.exists():
            return None
        try:
            data = json.loads(auth_path.read_text())
            api_key = data.get("OPENAI_API_KEY")
            return api_key if isinstance(api_key, str) and api_key else None
        except (json.JSONDecodeError, OSError) as e:
            self._logger.warning("Could not read %s: %s", auth_path, e)
            return None

    async def _run_agent(
        self,
        prompt: str,
        timeout: float,
        messages: list[dict[str, Any]] | None,
    ) -> SDKRunResult:
        # openai-agents is an optional dependency; initialize() has already
        # validated it is installed, so these deferred imports are safe.
        from agents import Agent, Runner  # noqa: PLC0415
        from agents.items import ToolCallItem, ToolCallOutputItem  # noqa: PLC0415
        from agents.mcp import MCPServerStreamableHttp  # noqa: PLC0415
        from agents.models.openai_provider import OpenAIProvider as OAIProvider  # noqa: PLC0415
        from agents.run_config import RunConfig  # noqa: PLC0415

        params: dict[str, Any] = {"url": self.mcp_url}
        if self._mcp_headers:
            params["headers"] = self._mcp_headers

        async with MCPServerStreamableHttp(
            params=params,
            cache_tools_list=True,
            name="testmcpy-mcp",
        ) as mcp_server:
            agent = Agent(
                name="testmcpy-codex-agent",
                model=self.model,
                instructions=_CODEX_SYSTEM_PROMPT,
                mcp_servers=[mcp_server],
            )
            run_config = RunConfig(
                model_provider=OAIProvider(api_key=self.openai_api_key),
            )
            # Note: the base wraps this _run_agent in asyncio.wait_for, so
            # we do NOT additionally wrap Runner.run with wait_for. (Doubling
            # up was the source of asyncio.timeout 3.10-incompat bugs in
            # earlier revisions.)
            result = await Runner.run(agent, prompt, run_config=run_config, max_turns=25)

        response_text = str(result.final_output) if result.final_output is not None else ""

        # Extract tool calls AND tool results from the run's item trace.
        # ToolCallItem.arguments lives on raw_item; ToolCallOutputItem.output
        # is the executed result. Correlate by call_id so test_runner.py
        # does NOT re-execute these calls. (Drift fix flagged in PR #84 review.)
        tool_calls: list[dict[str, Any]] = []
        tool_outputs_by_call_id: dict[str, ToolCallOutputItem] = {}
        for item in result.new_items:
            if isinstance(item, ToolCallItem) and item.tool_name:
                raw = item.raw_item
                raw_args = (
                    raw.get("arguments")
                    if isinstance(raw, dict)
                    else getattr(raw, "arguments", None)
                ) or "{}"
                try:
                    args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                except json.JSONDecodeError:
                    args = {}
                tool_calls.append(
                    {
                        "id": item.call_id or "",
                        "name": item.tool_name,
                        "arguments": args,
                    }
                )
            elif isinstance(item, ToolCallOutputItem):
                call_id = item.call_id
                if call_id:
                    tool_outputs_by_call_id[call_id] = item

        # Build MCPToolResult objects matching the call ids; harness keys on
        # llm_result.tool_results to skip re-execution.
        mcp_tool_results: list[MCPToolResult] = []
        for tc in tool_calls:
            output_item = tool_outputs_by_call_id.get(tc["id"])
            if output_item is not None:
                mcp_tool_results.append(
                    MCPToolResult(
                        tool_call_id=tc["id"],
                        tool_name=tc["name"],
                        content=output_item.output,
                        is_error=False,
                    )
                )

        # Normalise token usage to {prompt, completion, total}.
        usage = getattr(getattr(result, "context_wrapper", None), "usage", None)
        input_tokens = getattr(usage, "input_tokens", None)
        output_tokens = getattr(usage, "output_tokens", None)
        token_usage = (
            {
                "prompt": input_tokens or 0,
                "completion": output_tokens or 0,
                "total": (input_tokens or 0) + (output_tokens or 0),
            }
            if input_tokens is not None
            else None
        )

        return SDKRunResult(
            response_text=response_text,
            tool_calls=tool_calls,
            tool_results=mcp_tool_results,
            token_usage=token_usage,
            cost=None,  # let the base estimate from registry pricing
            raw_response={"final_output": response_text},
        )


class GeminiCLIProvider(LLMProvider):
    """Google Gemini CLI provider via subprocess.

    Wraps the Gemini CLI tool (installed via ``npm i -g @google/gemini-cli``
    or the official Gemini CLI package).  Follows the same pattern as
    ``CodexCLIProvider`` — the CLI handles authentication, tool discovery, and
    model routing; we just pipe a prompt in and parse what comes back.
    """

    def __init__(
        self,
        model: str,
        gemini_cli_path: str | None = None,
        mcp_url: str | None = None,
        auth: dict[str, Any] | None = None,
    ):
        if not re.match(r"^[a-zA-Z0-9._-]+$", model):
            raise ValueError(f"Invalid model identifier: {model}")
        self.model = model
        self.gemini_cli_path = gemini_cli_path or self._find_gemini_cli()
        # Use MCP_URL and auth from default profile if not provided
        config = get_config()
        if mcp_url is None:
            mcp_url = config.get_mcp_url()
        if auth is None:
            default_mcp = config.get_default_mcp_server()
            if default_mcp and default_mcp.auth:
                auth = default_mcp.auth.to_dict()
        self.tool_discovery = ToolDiscoveryService(mcp_url, auth=auth)

    def _find_gemini_cli(self) -> str:
        """Find Gemini CLI in PATH or common locations."""
        # Check environment variable first
        cli_path = os.environ.get("GEMINI_CLI_PATH")
        if cli_path and os.path.exists(cli_path):
            return cli_path

        # Check common locations
        common_paths = [
            "/usr/local/bin/gemini",
            "/opt/homebrew/bin/gemini",
            os.path.expanduser("~/.local/bin/gemini"),
            os.path.expanduser("~/.npm-global/bin/gemini"),
            "gemini",  # In PATH
        ]

        for path in common_paths:
            try:
                result = subprocess.run([path, "--version"], capture_output=True, timeout=5)
                if result.returncode == 0:
                    return path
            except (subprocess.TimeoutExpired, FileNotFoundError):
                continue

        raise FileNotFoundError(
            "Gemini CLI not found. Install via: npm i -g @anthropic-ai/gemini-cli"
        )

    async def initialize(self):
        """Initialize Gemini CLI provider."""
        # Verify Gemini CLI is working
        try:
            result = subprocess.run(
                [self.gemini_cli_path, "--version"], capture_output=True, timeout=10, text=True
            )
            if result.returncode != 0:
                raise RuntimeError(f"Gemini CLI error: {result.stderr}")
        except subprocess.TimeoutExpired as e:
            raise RuntimeError("Gemini CLI timeout during initialization") from e

        # Try to pre-discover tools, but don't fail if MCP service is unavailable
        try:
            await self.tool_discovery.discover_tools()
            print(f"✅ Successfully connected to MCP service at {self.tool_discovery.mcp_url}")
        except (ConnectionError, TimeoutError, OSError, ValueError) as e:
            print(f"⚠️  Warning: Failed to initialize MCP tools: {e}")
            print(f"   MCP URL: {self.tool_discovery.mcp_url}")
            print("   The provider will work without MCP tools (direct CLI calls only)")

    async def generate_with_tools(
        self,
        prompt: str,
        tools: list[dict[str, Any]],
        timeout: float = 120.0,
        messages: list[dict[str, Any]] | None = None,
    ) -> LLMResult:
        """Generate response using Gemini CLI."""
        start_time = time.time()

        try:
            # Create tool-aware prompt template
            enhanced_prompt = self._create_tool_prompt(prompt, tools)

            # Build command — Gemini CLI accepts a prompt via stdin
            cmd = [
                self.gemini_cli_path,
                "--print",  # Print response only, no interactive mode
                "--model",
                self.model,
            ]

            # Run as subprocess
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(input=enhanced_prompt.encode()), timeout=timeout
            )

            response_text = stdout.decode("utf-8").strip()

            if process.returncode != 0:
                error_text = stderr.decode("utf-8").strip()
                return LLMResult(
                    response=f"Gemini CLI error: {error_text}",
                    tool_calls=[],
                    duration=time.time() - start_time,
                )

            # Parse tool calls from CLI output
            tool_calls = self._parse_tool_calls(response_text)

            # Execute tool calls locally
            for tool_call in tool_calls:
                try:
                    await self.tool_discovery.execute_tool_call(tool_call)
                except (ConnectionError, TimeoutError, OSError, ValueError, RuntimeError) as e:
                    logging.warning("Gemini CLI tool call failed: %s", e)

            return LLMResult(
                response=response_text,
                tool_calls=tool_calls,
                token_usage=None,  # CLI doesn't provide token counts
                cost=0.0,  # CLI usage varies by subscription
                duration=time.time() - start_time,
                raw_response={"stdout": response_text},
            )

        except asyncio.TimeoutError:
            return LLMResult(
                response=f"Error: Gemini CLI timed out after {timeout}s",
                tool_calls=[],
                duration=time.time() - start_time,
            )
        except (FileNotFoundError, OSError) as e:
            return LLMResult(
                response=f"Error: {str(e)}", tool_calls=[], duration=time.time() - start_time
            )

    def _create_tool_prompt(self, prompt: str, tools: list[dict[str, Any]]) -> str:
        """Create enhanced prompt with tool descriptions."""
        if not tools:
            return prompt

        tool_descriptions = []
        for tool in tools:
            name = tool.get("name", "unknown")
            desc = tool.get("description", "")
            params = tool.get("inputSchema", tool.get("parameters", {}))

            tool_desc = f"**{name}**: {desc}"
            if params.get("properties"):
                param_list = ", ".join(params["properties"].keys())
                tool_desc += f" (parameters: {param_list})"

            tool_descriptions.append(tool_desc)

        return f"""You have access to the following tools:

{chr(10).join(tool_descriptions)}

When you need to use a tool, format your response like this:
TOOL_CALL: {{"name": "tool_name", "arguments": {{"param": "value"}}}}

User request: {prompt}"""

    def _parse_tool_calls(self, response: str) -> list[dict[str, Any]]:
        """Parse tool calls from Gemini CLI response."""
        tool_calls = []

        # Look for TOOL_CALL: patterns — try nested braces first so the
        # regex engine does not short-circuit on the flat alternative.
        tool_call_pattern = r"TOOL_CALL:\s*(\{[^}]*\{[^}]*\}[^}]*\}|\{[^}]+\})"
        matches = re.findall(tool_call_pattern, response)

        for match in matches:
            try:
                call_data = json.loads(match)
                if "name" in call_data:
                    tool_calls.append(
                        {"name": call_data["name"], "arguments": call_data.get("arguments", {})}
                    )
            except json.JSONDecodeError:
                continue

        return tool_calls

    async def close(self):
        """Close connections."""
        await self.tool_discovery.close()


# ---------------------------------------------------------------------------
# Gemini SDK Provider (google-adk with native MCP)
# ---------------------------------------------------------------------------

_gemini_sdk_logger = logging.getLogger(__name__ + ".GeminiSDKProvider")

# Maps testmcpy model IDs to real Gemini model identifiers.
_GEMINI_SDK_MODEL_MAP: dict[str, str] = {
    "gemini-sdk": "gemini-2.5-flash",
    "gemini-sdk-flash": "gemini-2.5-flash",
    "gemini-sdk-pro": "gemini-2.5-pro",
}

_GEMINI_SDK_SYSTEM_PROMPT = (
    "You are a test executor. Your ONLY job is to call the MCP tools provided "
    "to fulfil the user's request, then report the results.\n\n"
    "IMPORTANT RULES:\n"
    "1. Use ONLY the MCP server tools provided. Do NOT use any other tools or built-ins.\n"
    "2. Some MCP servers use a gateway pattern where tools are invoked via a meta-tool "
    "(e.g., call_tool(name='tool_name', arguments={...})). Use whatever interface the server provides.\n"
    "3. Do NOT call any tool discovery or search tools — the tool name is always specified in the request.\n"
    "4. Do NOT call any authentication, login, or credential tool.\n"
    "5. Always include the actual data from tool results in your response.\n"
    "6. Be concise and factual — include key data points from the tool output."
)


class GeminiSDKProvider(BaseSDKProvider):
    """Google ADK provider with native MCP integration.

    Uses the google-adk Python package (analogous to ClaudeSDKProvider/
    CodexSDKProvider). ``api_key`` must be supplied via the constructor
    (resolved from ``.llm_providers.yaml``).

    MCP server auth (bearer / jwt / oauth) is resolved by
    :class:`BaseSDKProvider` — including ``oauth_auto_discover`` via the
    proper :class:`fastmcp.client.auth.oauth.FileTokenStorage` API.
    """

    LOGGER_NAME = "GeminiSDKProvider"

    def __init__(
        self,
        model: str,
        mcp_url: str | None = None,
        auth: dict[str, Any] | None = None,
        api_key: str | None = None,
    ):
        # Keep the unmapped id (e.g. "gemini-sdk-flash") for model_registry
        # cost estimation; pass the vendor id (e.g. "gemini-2.5-flash") to
        # the base for self.model.
        self._registry_model_id = model
        super().__init__(
            model=_GEMINI_SDK_MODEL_MAP.get(model, model),
            mcp_url=mcp_url,
            auth=auth,
        )
        self.api_key = api_key or ""

    # ---- BaseSDKProvider hooks ------------------------------------------

    def _check_sdk_installed(self) -> None:
        # Import the root package only — the deeper imports in _run_agent
        # are guarded by initialize() having completed first. Importing only
        # the root also keeps unit-test fixtures simple (a single
        # ``sys.modules["google.adk"]`` stub is enough).
        try:
            import google.adk  # noqa: F401, PLC0415
        except ImportError:
            raise ValueError(
                "google-adk package not installed. Install with: pip install google-adk"
            )

    async def _validate_credentials(self) -> None:
        if not self.api_key:
            raise ValueError(
                "No Google api_key. Supply api_key in the LLM profile (.llm_providers.yaml)."
            )

    @classmethod
    def _vendor_expected_errors(cls) -> tuple[type[BaseException], ...]:
        return (
            ConnectionError,
            OSError,
            TimeoutError,
            httpx.HTTPError,
        )

    async def _run_agent(
        self,
        prompt: str,
        timeout: float,
        messages: list[dict[str, Any]] | None,
    ) -> SDKRunResult:
        # google-adk is an optional dependency; initialize() has already
        # validated it is installed, so these deferred imports are safe.
        # NOTE: we import LlmAgent (the underlying class) rather than the
        # ``Agent`` re-export from ``google.adk`` so unit tests can patch
        # this name reliably (the re-export captures the original class at
        # google.adk import time and is not affected by patches on the
        # source module).
        from google.adk.agents.llm_agent import LlmAgent  # noqa: PLC0415
        from google.adk.models.google_llm import Gemini  # noqa: PLC0415
        from google.adk.runners import Runner  # noqa: PLC0415
        from google.adk.sessions.in_memory_session_service import (  # noqa: PLC0415
            InMemorySessionService,
        )
        from google.adk.tools.mcp_tool.mcp_session_manager import (  # noqa: PLC0415
            StreamableHTTPConnectionParams,
        )
        from google.adk.tools.mcp_tool.mcp_toolset import McpToolset  # noqa: PLC0415
        from google.genai import types as genai_types  # noqa: PLC0415

        # Subclass Gemini to inject our explicit API key — the documented ADK
        # pattern (see google_llm.Gemini.api_client docstring: "subclass Gemini
        # and override the api_client property"). functools.cached_property
        # avoids re-instantiating the genai.Client on every attribute access.
        api_key_capture = self.api_key

        class _GeminiWithKey(Gemini):
            # Tracks google_llm.Gemini.api_client (cached_property on base).
            @functools.cached_property  # type: ignore[misc]
            def api_client(self):
                from google.genai import Client  # noqa: PLC0415

                return Client(api_key=api_key_capture)

        params: dict[str, Any] = {"url": self.mcp_url}
        if self._mcp_headers:
            params["headers"] = self._mcp_headers

        mcp_toolset = McpToolset(connection_params=StreamableHTTPConnectionParams(**params))
        try:
            agent = LlmAgent(
                name="testmcpy-gemini-agent",
                model=_GeminiWithKey(model=self.model),
                instruction=_GEMINI_SDK_SYSTEM_PROMPT,
                tools=[mcp_toolset],
            )
            session_service = InMemorySessionService()
            # InMemorySessionService does not auto-create on first run_async,
            # so we create the session explicitly first.
            session = await session_service.create_session(
                app_name="testmcpy",
                user_id="testmcpy",
                session_id=uuid.uuid4().hex,
            )
            runner = Runner(
                agent=agent,
                app_name="testmcpy",
                session_service=session_service,
            )
            new_message = genai_types.Content(
                role="user",
                parts=[genai_types.Part(text=prompt)],
            )

            tool_calls: list[dict[str, Any]] = []
            # Indexed by function name for response correlation.
            func_responses_by_name: dict[str, Any] = {}
            response_parts: list[str] = []
            # Accumulate usage across all model-response events (each tool
            # round-trip can produce one; the final synthesis produces
            # another).
            total_prompt_tokens = 0
            total_completion_tokens = 0
            total_tokens = 0
            has_usage = False

            async for event in runner.run_async(
                user_id="testmcpy",
                session_id=session.id,
                new_message=new_message,
            ):
                # Collect function calls made by the model.
                for fc in event.get_function_calls():
                    tool_calls.append(
                        {
                            "name": fc.name,
                            "arguments": dict(fc.args) if fc.args else {},
                        }
                    )
                # Collect function responses (already executed by McpToolset)
                # so test_runner.py does not re-execute them.
                for fr in event.get_function_responses():
                    func_responses_by_name[fr.name] = fr
                # Collect final response text.
                if event.is_final_response() and event.content:
                    for part in event.content.parts or []:
                        if getattr(part, "text", None):
                            response_parts.append(part.text)
                # Sum usage across every model-response event.
                if event.usage_metadata is not None:
                    has_usage = True
                    total_prompt_tokens += (
                        getattr(event.usage_metadata, "prompt_token_count", 0) or 0
                    )
                    total_completion_tokens += (
                        getattr(event.usage_metadata, "candidates_token_count", 0) or 0
                    )
                    total_tokens += getattr(event.usage_metadata, "total_token_count", 0) or 0

            # Build MCPToolResult objects from ADK function responses so
            # test_runner knows these calls are already executed.
            mcp_tool_results: list[MCPToolResult] = []
            for tc in tool_calls:
                fr = func_responses_by_name.get(tc["name"])
                if fr is not None:
                    mcp_tool_results.append(
                        MCPToolResult(
                            tool_call_id=getattr(fr, "id", tc["name"]),
                            tool_name=tc["name"],
                            content=getattr(fr, "response", {}),
                            is_error=False,
                        )
                    )

            token_usage = (
                {
                    "prompt": total_prompt_tokens,
                    "completion": total_completion_tokens,
                    "total": total_tokens or total_prompt_tokens + total_completion_tokens,
                }
                if has_usage
                else None
            )

            return SDKRunResult(
                response_text=" ".join(response_parts),
                tool_calls=tool_calls,
                tool_results=mcp_tool_results,
                token_usage=token_usage,
                cost=None,  # let the base estimate from registry pricing
                raw_response={"parts": response_parts},
            )
        finally:
            # Guard cleanup separately so a close() error does not suppress
            # the SDKRunResult / exception already in flight.
            try:
                await mcp_toolset.close()
            except Exception:
                self._logger.debug("mcp_toolset.close() raised", exc_info=True)


def create_llm_provider(provider: str, model: str, **kwargs) -> LLMProvider:
    """
    Create an LLM provider instance.

    Args:
        provider: Provider name (ollama, openai, openrouter, local, anthropic, bedrock,
                  claude-sdk, claude-cli, claude-code, assistant, chatbot,
                  codex-sdk, codex-cli, codex, gemini-cli, xai, grok)
        model: Model name/path
        **kwargs: Additional provider-specific arguments

    Returns:
        LLMProvider instance
    """
    providers = {
        "ollama": OllamaProvider,
        "openai": OpenAIProvider,
        "openrouter": OpenRouterProvider,
        "local": LocalModelProvider,
        "anthropic": AnthropicProvider,
        "bedrock": BedrockProvider,
        "aws-bedrock": BedrockProvider,  # Alias
        "gemini": GeminiProvider,
        "google": GeminiProvider,  # Alias
        "claude-sdk": ClaudeSDKProvider,  # Claude Agent SDK (uses Claude CLI)
        "claude-cli": ClaudeSDKProvider,  # Alias → claude-sdk
        "claude-code": ClaudeSDKProvider,  # Alias → claude-sdk
        "assistant": AssistantProvider,
        "chatbot": AssistantProvider,
        "codex-sdk": CodexSDKProvider,  # OpenAI Agents SDK with native MCP
        "codex-cli": CodexSDKProvider,  # Alias → codex-sdk
        "codex": CodexSDKProvider,  # Alias → codex-sdk
        "gemini-cli": GeminiCLIProvider,
        "gemini-sdk": GeminiSDKProvider,  # Google ADK with native MCP
        "xai": XAIProvider,  # xAI (Grok models)
        "grok": XAIProvider,  # Alias → xai
    }

    if provider not in providers:
        raise ValueError(f"Unknown provider: {provider}. Available: {list(providers.keys())}")

    provider_class = providers[provider]

    # Filter kwargs to only include parameters the provider accepts
    import inspect

    sig = inspect.signature(provider_class.__init__)
    valid_params = set(sig.parameters.keys()) - {"self"}
    filtered_kwargs = {k: v for k, v in kwargs.items() if k in valid_params}

    return provider_class(model=model, **filtered_kwargs)
