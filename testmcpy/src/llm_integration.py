"""
LLM integration module for supporting multiple model providers.
"""

import asyncio
import json
import logging
import os
import re
import subprocess
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import httpx

# Import MCP components (we'll handle the import error gracefully)
try:
    from ..config import get_config
    from .mcp_client import MCPClient, MCPTool, MCPToolCall, MCPToolResult
except ImportError:
    # Fallback for when running as script
    import os
    import sys

    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    from mcp_client import MCPClient, MCPTool, MCPToolCall, MCPToolResult

    # Config will fall back to environment variables
    def get_config():
        class FallbackConfig:
            def get(self, key, default=None):
                return os.getenv(key, default)

        return FallbackConfig()


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

            # Estimate cost (GPT-4 pricing as example)
            cost = (token_usage["prompt"] * 0.03 + token_usage["completion"] * 0.06) / 1000

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
        resolved_key = api_key or os.environ.get("OPENROUTER_API_KEY", "")
        super().__init__(
            model=model,
            api_key=resolved_key,
            base_url="https://openrouter.ai/api/v1",
        )

    async def initialize(self):
        """Validate that an API key is available."""
        if not self.api_key:
            config = get_config()
            self.api_key = config.get("OPENROUTER_API_KEY", "")
        if not self.api_key:
            raise ValueError(
                "OpenRouter API key not provided. "
                "Set OPENROUTER_API_KEY in ~/.testmcpy or environment."
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
                # Fallback estimate
                cost = (token_usage["prompt"] * 0.03 + token_usage["completion"] * 0.06) / 1000

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
            raise Exception(f"Failed to discover MCP tools: {e}")

    async def execute_tool_call(self, tool_call: dict[str, Any]) -> MCPToolResult:
        """Execute tool call via local MCP client."""
        if not self._mcp_client:
            raise Exception("MCP client not initialized")

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
        # Get auth from default MCP server
        auth = None
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
            for tool_call in tool_calls:
                try:
                    await self.tool_discovery.execute_tool_call(tool_call)
                    # Tool results are returned separately, not appended to response text
                except Exception:
                    pass  # Errors are handled by the tool execution

            # Calculate usage and cost
            usage = result.get("usage", {})
            token_usage = {
                "prompt": usage.get("input_tokens", 0),
                "completion": usage.get("output_tokens", 0),
                "total": usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
                "cache_creation": usage.get("cache_creation_input_tokens", 0),
                "cache_read": usage.get("cache_read_input_tokens", 0),
            }

            # Estimate cost (Claude pricing)
            cost = (token_usage["prompt"] * 0.003 + token_usage["completion"] * 0.015) / 1000

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


_claude_sdk_logger = logging.getLogger(__name__ + ".ClaudeSDKProvider")


class ClaudeSDKProvider(LLMProvider):
    """Claude Agent SDK provider with native MCP integration.

    Uses the claude-agent-sdk Python package (wraps Claude Code CLI internally).
    The SDK handles MCP tool discovery natively via McpHttpServerConfig —
    no need for our own ToolDiscoveryService.

    Supports JWT, OAuth, and Bearer auth for MCP servers.
    Uses Claude Code subscription (no API credits) by clearing ANTHROPIC_API_KEY from env.
    """

    def __init__(
        self,
        model: str,
        mcp_url: str | None = None,
        auth: dict[str, Any] | None = None,
        log_callback=None,
    ):
        self.model = model
        self.log_callback = log_callback
        config = get_config()

        # Use MCP_URL and auth from default profile if not provided
        if mcp_url is None:
            mcp_url = config.get_mcp_url()
        self.mcp_url = mcp_url

        if auth is None:
            default_mcp = config.get_default_mcp_server()
            if default_mcp and default_mcp.auth:
                auth = default_mcp.auth.to_dict()
        self.auth_config = auth

        self._mcp_server_config: dict[str, Any] | None = None

    async def initialize(self):
        """Initialize Claude SDK provider — build MCP server config with auth."""
        try:
            from claude_agent_sdk import CLINotFoundError  # noqa: F401
        except ImportError:
            raise ValueError(
                "claude-agent-sdk package not installed. Install with: pip install claude-agent-sdk"
            )

        # Configure HTTP MCP server
        from claude_agent_sdk.types import McpHttpServerConfig

        server_config: McpHttpServerConfig = {"type": "http", "url": self.mcp_url}

        # Fetch auth token based on auth config type
        token = None
        if self.auth_config:
            auth_type = self.auth_config.get("type", "")
            if auth_type == "jwt":
                token = await self._fetch_jwt_token()
            elif auth_type == "bearer":
                token = self.auth_config.get("token", "")
            elif auth_type == "oauth":
                token = await self._fetch_oauth_token()

        if token:
            server_config["headers"] = {"Authorization": f"Bearer {token}"}
            _claude_sdk_logger.info("[ClaudeSDK] MCP server configured with auth token")
        else:
            _claude_sdk_logger.info("[ClaudeSDK] MCP server configured without auth")

        self._mcp_server_config = server_config
        _claude_sdk_logger.info("[ClaudeSDK] MCP server ready: %s", self.mcp_url)

    async def _fetch_jwt_token(self) -> str | None:
        """Fetch JWT token from API."""
        if not self.auth_config:
            return None

        api_url = self.auth_config.get("api_url", "")
        api_token = self.auth_config.get("api_token", "")
        api_secret = self.auth_config.get("api_secret", "")

        if not all([api_url, api_token, api_secret]):
            _claude_sdk_logger.warning("[ClaudeSDK] JWT auth config incomplete")
            return None

        _claude_sdk_logger.info("[ClaudeSDK] Fetching JWT token from: %s", api_url)
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    api_url,
                    headers={
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                    },
                    json={"name": api_token, "secret": api_secret},
                    timeout=30.0,
                )
                response.raise_for_status()
                data = response.json()
                token = data.get("payload", {}).get("access_token", "")
                if token:
                    _claude_sdk_logger.info(
                        "[ClaudeSDK] JWT token fetched (length: %d)", len(token)
                    )
                return token
            except (httpx.HTTPStatusError, httpx.ConnectError, httpx.TimeoutException) as e:
                _claude_sdk_logger.warning("[ClaudeSDK] Failed to fetch JWT token: %s", e)
                return None

    async def _fetch_oauth_token(self) -> str | None:
        """Fetch OAuth token using client credentials."""
        if not self.auth_config:
            return None

        token_url = self.auth_config.get("token_url", "")
        client_id = self.auth_config.get("client_id", "")
        client_secret = self.auth_config.get("client_secret", "")

        if not all([token_url, client_id, client_secret]):
            _claude_sdk_logger.warning("[ClaudeSDK] OAuth auth config incomplete")
            return None

        _claude_sdk_logger.info("[ClaudeSDK] Fetching OAuth token from: %s", token_url)
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    token_url,
                    data={
                        "grant_type": "client_credentials",
                        "client_id": client_id,
                        "client_secret": client_secret,
                    },
                    timeout=30.0,
                )
                response.raise_for_status()
                data = response.json()
                token = data.get("access_token", "")
                if token:
                    _claude_sdk_logger.info(
                        "[ClaudeSDK] OAuth token fetched (length: %d)", len(token)
                    )
                return token
            except (httpx.HTTPStatusError, httpx.ConnectError, httpx.TimeoutException) as e:
                _claude_sdk_logger.warning("[ClaudeSDK] Failed to fetch OAuth token: %s", e)
                return None

    async def generate_with_tools(
        self,
        prompt: str,
        tools: list[dict[str, Any]],
        timeout: float = 120.0,
        messages: list[dict[str, Any]] | None = None,
    ) -> LLMResult:
        """Generate response using Claude Agent SDK."""
        start_time = time.time()
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

            # Build a clean env: inherit current env but remove Claude Code
            # session vars that prevent nested CLI spawning
            clean_env = {
                k: v
                for k, v in os.environ.items()
                if not k.startswith("CLAUDE_CODE") and k != "CLAUDECODE"
            }
            clean_env["ANTHROPIC_API_KEY"] = ""  # Force subscription usage, not API credits

            # Disable Claude Code's built-in tools (Bash, Read, Edit, Grep, etc.)
            # so the LLM only uses the MCP server's tools (call_tool, search_tools, etc.).
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
                "1. Use ONLY the MCP server tools (call_tool, search_tools, health_check, "
                "get_instance_info). Do NOT use any Claude Code built-in tools.\n"
                "2. The MCP server uses a gateway pattern: real tools like list_dashboards, "
                "get_chart_info, etc. are accessed via call_tool(name='tool_name', arguments={...}).\n"
                "3. For simple tools like health_check and get_instance_info, call them directly.\n"
                "4. Complete the FULL agentic loop: search/discover tools if needed, call the tool, "
                "then summarize the results in your final response.\n"
                "5. Always include the actual data from tool results in your response.\n"
                "6. Be concise and factual — include key data points from the tool output."
            )

            options = ClaudeAgentOptions(
                model=self.model,
                permission_mode="bypassPermissions",
                mcp_servers=mcp_servers,
                max_turns=25,
                env=clean_env,
                disallowed_tools=_builtin_tools_to_block,
                system_prompt=system_prompt,
                debug_stderr=None,  # Suppress CLI debug output
            )

            # Execute query with timeout
            response_text = ""
            thinking_text = ""
            tool_calls = []
            tool_results_map: dict[str, dict[str, Any]] = {}
            token_usage = None
            cost = 0.0
            raw_events = []

            log(f"[ClaudeSDK] Starting query (model={self.model}, timeout={timeout}s)...")

            async def execute_query():
                nonlocal response_text, thinking_text, token_usage, cost
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
                                    log(f"[ClaudeSDK] Thinking ({len(block.thinking)} chars)")
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

            try:
                await asyncio.wait_for(execute_query(), timeout=timeout)
            except asyncio.TimeoutError:
                log(f"[ClaudeSDK] TIMEOUT after {timeout}s")
                return LLMResult(
                    response=f"Error: SDK query timed out after {timeout}s",
                    tool_calls=[],
                    duration=time.time() - start_time,
                    logs=logs,
                )

            # Attach tool results to tool calls and build MCPToolResult objects
            mcp_tool_results = []
            for tc in tool_calls:
                tc_id = tc.get("id", "")
                if tc_id in tool_results_map:
                    tc["result"] = tool_results_map[tc_id]
                    result_data = tool_results_map[tc_id]
                    mcp_result = MCPToolResult(
                        tool_call_id=tc_id,
                        content=result_data.get("content", ""),
                        is_error=result_data.get("is_error", False),
                        error_message=str(result_data.get("content", ""))
                        if result_data.get("is_error")
                        else None,
                    )
                    mcp_tool_results.append(mcp_result)

            duration = time.time() - start_time
            log(
                f"[ClaudeSDK] Done: {len(response_text)} chars, "
                f"{len(tool_calls)} tool calls, {len(mcp_tool_results)} results"
            )

            return LLMResult(
                response=response_text,
                tool_calls=tool_calls,
                tool_results=mcp_tool_results,
                thinking=thinking_text if thinking_text else None,
                token_usage=token_usage,
                cost=cost,
                duration=duration,
                tti_ms=int(duration * 1000),
                raw_response={"events": raw_events} if raw_events else None,
                logs=logs,
            )

        except CLINotFoundError:
            log("[ClaudeSDK] Claude CLI not found — install @anthropic-ai/claude-code")
            return LLMResult(
                response="Error: Claude CLI not found. Install with: npm install -g @anthropic-ai/claude-code",
                tool_calls=[],
                duration=time.time() - start_time,
                logs=logs,
            )
        except ProcessError as e:
            log(f"[ClaudeSDK] Process error: {e}")
            return LLMResult(
                response=f"Error: Claude CLI process failed: {e}",
                tool_calls=[],
                duration=time.time() - start_time,
                logs=logs,
            )
        except CLIConnectionError as e:
            log(f"[ClaudeSDK] Connection error: {e}")
            return LLMResult(
                response=f"Error: Claude CLI connection failed: {e}",
                tool_calls=[],
                duration=time.time() - start_time,
                logs=logs,
            )
        except (KeyError, ValueError, TypeError, json.JSONDecodeError) as e:
            log(f"[ClaudeSDK] Unexpected error: {type(e).__name__}: {e}")
            return LLMResult(
                response=f"Error: {type(e).__name__}: {e}",
                tool_calls=[],
                duration=time.time() - start_time,
                logs=logs,
            )

    async def close(self):
        """No-op — SDK manages its own cleanup."""
        pass


_assistant_logger = logging.getLogger(__name__ + ".AssistantProvider")


class AssistantProvider(LLMProvider):
    """LLM provider that sends prompts to the AI assistant conversation endpoint.

    Uses the same auth flow as MCP JWT auth to obtain a JWT token, then
    creates a assistant conversation and streams SSE completions via httpx.

    Config is resolved from kwargs, then env vars, then the default MCP
    profile auth settings (in that order).
    """

    # Default environments map to manager API URLs
    _ENV_API_URLS: dict[str, str] = {
        "staging": "https://manage.app.staging.preset.zone/api/v1/auth/",
        "production": "https://manage.app.preset.io/api/v1/auth/",
        "local": "http://manager.local.preset.zone/api/v1/auth/",
    }

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
        conversations_path: str = "/api/v1/copilot/conversations",
        completions_path: str = "/api/v1/copilot/completions",
        **kwargs,
    ):
        self.model = model
        self.model_override = model_override
        self.conversations_path = conversations_path
        self.completions_path = completions_path

        # Resolve config: kwargs > env vars > MCP profile auth
        config = get_config()
        default_mcp = config.get_default_mcp_server()
        auth_cfg = {}
        if default_mcp and default_mcp.auth:
            auth_cfg = default_mcp.auth.to_dict()

        self.workspace_hash = (
            workspace_hash
            or os.environ.get("ASSISTANT_WORKSPACE_HASH")
            or os.environ.get("PRESET_WORKSPACE_HASH", "")
        )
        self.domain = (
            domain or os.environ.get("ASSISTANT_DOMAIN") or os.environ.get("PRESET_DOMAIN", "")
        )
        self.environment = (
            environment
            or os.environ.get("ASSISTANT_ENVIRONMENT")
            or os.environ.get("PRESET_ENVIRONMENT", "staging")
        )
        self.api_token = (
            api_token
            or os.environ.get("ASSISTANT_API_TOKEN")
            or os.environ.get("PRESET_API_TOKEN")
            or auth_cfg.get("api_token", "")
        )
        self.api_secret = (
            api_secret
            or os.environ.get("ASSISTANT_API_SECRET")
            or os.environ.get("PRESET_API_SECRET")
            or auth_cfg.get("api_secret", "")
        )
        self.api_url = (
            api_url
            or os.environ.get("ASSISTANT_API_URL")
            or os.environ.get("PRESET_API_URL")
            or auth_cfg.get("api_url", "")
            or self._ENV_API_URLS.get(self.environment, "")
        )

        # Derive base workspace URL if domain is set
        if self.workspace_hash and self.domain:
            self.base_url = f"https://{self.workspace_hash}.{self.domain}"
        elif self.workspace_hash and self.environment:
            # Derive domain from environment
            env_domains = {
                "staging": "app.staging.preset.zone",
                "production": "app.preset.io",
                "local": "local.preset.zone",
            }
            d = env_domains.get(self.environment, "app.staging.preset.zone")
            self.base_url = f"https://{self.workspace_hash}.{d}"
        else:
            self.base_url = ""

        self._jwt_token: str | None = None
        self._csrf_token: str = str(uuid.uuid4())
        self._conversation_id: str | None = None
        self._client: httpx.AsyncClient | None = None

    async def initialize(self):
        """Fetch JWT token and create a assistant conversation."""
        if not self.base_url:
            raise ValueError(
                "AssistantProvider requires workspace_hash + domain (or environment). "
                "Set ASSISTANT_WORKSPACE_HASH and ASSISTANT_DOMAIN env vars, or pass them as kwargs."
            )
        if not self.api_token or not self.api_secret:
            raise ValueError(
                "AssistantProvider requires api_token and api_secret for JWT auth. "
                "Set ASSISTANT_API_TOKEN / ASSISTANT_API_SECRET env vars, or configure MCP profile auth."
            )

        self._client = httpx.AsyncClient(timeout=60.0)

        # --- Fetch JWT ---
        _assistant_logger.info("[Assistant] Fetching JWT from: %s", self.api_url)
        try:
            resp = await self._client.post(
                self.api_url,
                headers={"Content-Type": "application/json", "Accept": "application/json"},
                json={"name": self.api_token, "secret": self.api_secret},
                timeout=30.0,
            )
            resp.raise_for_status()
            data = resp.json()
            self._jwt_token = data.get("payload", {}).get("access_token", "")
            if not self._jwt_token:
                raise ValueError(f"No access_token in auth response: {data}")
            _assistant_logger.info("[Assistant] JWT obtained (length: %d)", len(self._jwt_token))
        except httpx.HTTPStatusError as e:
            raise RuntimeError(
                f"JWT auth failed: HTTP {e.response.status_code} - {e.response.text}"
            ) from e
        except httpx.ConnectError as e:
            raise RuntimeError(f"JWT auth connection failed: {e}") from e

        # --- Create conversation ---
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
        """Build auth headers with JWT, CSRF cookie, and referer."""
        return {
            "Authorization": f"Bearer {self._jwt_token}",
            "Cookie": f"__s__={self._jwt_token}; csrf_access_token={self._csrf_token}",
            "X-CSRFToken": self._csrf_token,
            "Content-Type": "application/json",
            "Referer": f"{self.base_url}/",
        }

    async def generate_with_tools(
        self,
        prompt: str,
        tools: list[dict[str, Any]] | None = None,
        timeout: float = 120.0,
        messages: list[dict[str, Any]] | None = None,
        **kwargs,
    ) -> LLMResult:
        """Send prompt to assistant completions endpoint and stream SSE response.

        The assistant endpoint handles tool calling internally (server-side),
        so we do not send tool schemas. Instead we parse SSE events for
        tool_call / tool_result events emitted by the assistant backend.
        """
        start_time = time.time()
        logs: list[str] = []

        def log(msg: str):
            _assistant_logger.info(msg)
            logs.append(msg)

        if not self._client or not self._jwt_token or not self._conversation_id:
            return LLMResult(
                response="Error: AssistantProvider not initialized. Call initialize() first.",
                tool_calls=[],
                duration=time.time() - start_time,
                logs=logs,
            )

        # Build completions payload
        payload: dict[str, Any] = {
            "conversation_id": self._conversation_id,
            "messages": [{"role": "user", "content": prompt}],
        }
        if self.model_override or (self.model and self.model != "default"):
            payload["model_override"] = self.model_override or self.model

        completions_url = f"{self.base_url}{self.completions_path}"
        headers = {**self._build_headers(), "Accept": "text/event-stream"}

        log(f"[Assistant] POST {completions_url} (conversation={self._conversation_id})")

        response_text = ""
        tool_calls: list[dict[str, Any]] = []
        tool_results: list[dict[str, Any]] = []
        token_usage: dict[str, int] | None = None
        got_final = False
        got_error = False
        error_message = ""
        tti_ms: int | None = None
        token_event_count = 0

        try:
            async with self._client.stream(
                "POST",
                completions_url,
                headers=headers,
                json=payload,
                timeout=timeout,
            ) as resp:
                if resp.status_code != 200:
                    body = await resp.aread()
                    raise RuntimeError(
                        f"Assistant API error: HTTP {resp.status_code} - {body.decode('utf-8', errors='replace')}"
                    )

                current_event: str | None = None

                async for raw_line in resp.aiter_lines():
                    line = raw_line.strip()
                    if not line:
                        current_event = None
                        continue

                    if line.startswith("event:"):
                        current_event = line[6:].strip()
                        continue

                    if not line.startswith("data:"):
                        continue

                    json_str = line[5:].strip()
                    if not json_str:
                        continue

                    # Track time to first token
                    if current_event == "token" and tti_ms is None:
                        tti_ms = int((time.time() - start_time) * 1000)

                    try:
                        data = json.loads(json_str)
                    except json.JSONDecodeError:
                        log(f"[Assistant] Failed to parse SSE data: {json_str[:100]}")
                        continue

                    if current_event == "token":
                        chunk = data.get("chunk", "")
                        response_text += chunk
                        token_event_count += 1

                    elif current_event == "tool_call":
                        tc = {
                            "id": data.get("tool_call_id", ""),
                            "name": data.get("tool_name", ""),
                            "arguments": data.get("input", {}),
                        }
                        tool_calls.append(tc)
                        log(f"[Assistant] Tool call: {tc['name']} (id={tc['id']})")

                    elif current_event == "tool_result":
                        tr = {
                            "tool_call_id": data.get("tool_call_id", ""),
                            "result": data.get("result"),
                            "duration_ms": data.get("duration_ms"),
                        }
                        tool_results.append(tr)
                        log(
                            f"[Assistant] Tool result: id={tr['tool_call_id']}, duration={tr['duration_ms']}ms"
                        )

                    elif current_event == "usage":
                        token_usage = {
                            "prompt": data.get("input_tokens", 0),
                            "completion": data.get("output_tokens", 0),
                            "total": data.get("total_tokens", 0),
                        }
                        log(f"[Assistant] Usage: {token_usage}")

                    elif current_event == "final":
                        got_final = True
                        # The final event may contain the full answer
                        final_answer = data.get("answer", "") or data.get("message", "")
                        if final_answer and not response_text:
                            response_text = final_answer
                        log(f"[Assistant] Final event received ({len(response_text)} chars)")

                    elif current_event == "error":
                        got_error = True
                        error_message = data.get("error", "") or data.get(
                            "message", "unknown error"
                        )
                        log(f"[Assistant] Error event: {error_message}")

        except httpx.TimeoutException:
            duration = time.time() - start_time
            log(f"[Assistant] TIMEOUT after {duration:.1f}s")
            return LLMResult(
                response=f"Error: Assistant request timed out after {timeout}s",
                tool_calls=tool_calls,
                duration=duration,
                logs=logs,
            )
        except (httpx.HTTPStatusError, httpx.ConnectError, RuntimeError) as e:
            duration = time.time() - start_time
            log(f"[Assistant] Request failed: {e}")
            return LLMResult(
                response=f"Error: {e}",
                tool_calls=tool_calls,
                duration=duration,
                logs=logs,
            )

        duration = time.time() - start_time

        if got_error and not response_text:
            response_text = f"Error: {error_message}"

        log(
            f"[Assistant] Done: {len(response_text)} chars, "
            f"{len(tool_calls)} tool calls, {token_event_count} tokens, "
            f"final={'yes' if got_final else 'no'}, error={'yes' if got_error else 'no'}, "
            f"{duration:.2f}s"
        )

        return LLMResult(
            response=response_text,
            tool_calls=tool_calls,
            tool_results=tool_results,
            token_usage=token_usage,
            cost=0.0,  # Assistant usage is bundled with workspace subscription
            duration=duration,
            tti_ms=tti_ms,
            logs=logs,
        )

    async def close(self):
        """Close the httpx client."""
        if self._client:
            await self._client.aclose()
            self._client = None


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
        self.api_key = (
            api_key or config.get("GOOGLE_API_KEY", "") or config.get("GEMINI_API_KEY", "")
        )
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
                "Google API key not provided. Set GOOGLE_API_KEY or GEMINI_API_KEY in ~/.testmcpy, .env, or environment."
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
                except Exception:
                    pass

            # Extract usage metadata
            usage_metadata = result.get("usageMetadata", {})
            token_usage = {
                "prompt": usage_metadata.get("promptTokenCount", 0),
                "completion": usage_metadata.get("candidatesTokenCount", 0),
                "total": usage_metadata.get("totalTokenCount", 0),
            }

            # Estimate cost (Gemini Pro pricing)
            cost = (token_usage["prompt"] * 0.00025 + token_usage["completion"] * 0.0005) / 1000

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
    """OpenAI Codex CLI provider via subprocess (similar to Claude Code)."""

    def __init__(
        self,
        model: str,
        codex_cli_path: str | None = None,
        mcp_url: str | None = None,
        auth: dict[str, Any] | None = None,
    ):
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
        except Exception as e:
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
                except Exception:
                    pass  # Errors are handled by the tool execution

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
        except Exception as e:
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


def create_llm_provider(provider: str, model: str, **kwargs) -> LLMProvider:
    """
    Create an LLM provider instance.

    Args:
        provider: Provider name (ollama, openai, openrouter, local, anthropic, claude-sdk, claude-cli, claude-code, assistant, chatbot, codex-cli, gemini-cli)
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
        "gemini": GeminiProvider,
        "google": GeminiProvider,  # Alias
        "claude-sdk": ClaudeSDKProvider,  # Claude Agent SDK (uses Claude CLI)
        "claude-cli": ClaudeSDKProvider,  # Alias → claude-sdk
        "claude-code": ClaudeSDKProvider,  # Alias → claude-sdk
        "assistant": AssistantProvider,  # AI assistant conversation endpoint
        "chatbot": AssistantProvider,  # Alias → assistant
        "codex-cli": CodexCLIProvider,
        "codex": CodexCLIProvider,  # Alias
        "gemini-cli": GeminiCLIProvider,
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
