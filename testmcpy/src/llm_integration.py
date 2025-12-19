"""
LLM integration module for supporting multiple model providers.
"""

import asyncio
import json
import os
import re
import subprocess
import time
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
                except:
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
        except:
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
                except:
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


class ClaudeSDKProvider(LLMProvider):
    """Claude Agent SDK provider with MCP integration."""

    def __init__(self, model: str, api_key: str | None = None, mcp_url: str | None = None):
        self.model = model
        # Use config system for API key
        config = get_config()
        self.api_key = api_key or config.get("ANTHROPIC_API_KEY", "")
        # Use MCP_URL and auth from default profile if not provided
        if mcp_url is None:
            mcp_url = config.get_mcp_url()
        self.mcp_url = mcp_url
        # Get auth from default MCP server
        auth = None
        default_mcp = config.get_default_mcp_server()
        if default_mcp and default_mcp.auth:
            auth = default_mcp.auth.to_dict()
        self.auth_config = auth  # Store auth config for initialize
        self.tool_discovery = ToolDiscoveryService(mcp_url, auth=auth)
        self._sdk_tools: list[Any] = []
        self._mcp_server_config: dict[str, Any] | None = None

    async def initialize(self):
        """Initialize Claude SDK provider."""
        if not self.api_key:
            raise ValueError(
                "Anthropic API key not provided. Set ANTHROPIC_API_KEY in ~/.testmcpy, .env, or environment."
            )

        # Configure HTTP MCP server
        try:
            from claude_agent_sdk.types import McpHttpServerConfig

            # Build HTTP server config
            server_config: McpHttpServerConfig = {"type": "http", "url": self.mcp_url}

            # Fetch auth token based on auth config type
            token = None
            if self.auth_config:
                auth_type = self.auth_config.get("type", "")
                if auth_type == "jwt":
                    # Fetch JWT token dynamically
                    token = await self._fetch_jwt_token()
                elif auth_type == "bearer":
                    token = self.auth_config.get("token", "")
                elif auth_type == "oauth":
                    # Fetch OAuth token dynamically
                    token = await self._fetch_oauth_token()

            if token:
                server_config["headers"] = {"Authorization": f"Bearer {token}"}
                print("[SDK] Configured MCP HTTP server with auth token")
            else:
                print("[SDK] Configured MCP HTTP server without auth")

            self._mcp_server_config = server_config
            print(f"[SDK] ✓ MCP Server configured: {self.mcp_url}")

        except Exception as e:
            print(f"[SDK] ❌ Failed to configure MCP server: {e}")
            self._mcp_server_config = None

    async def _fetch_jwt_token(self) -> str | None:
        """Fetch JWT token from API."""
        if not self.auth_config:
            return None

        api_url = self.auth_config.get("api_url", "")
        api_token = self.auth_config.get("api_token", "")
        api_secret = self.auth_config.get("api_secret", "")

        if not all([api_url, api_token, api_secret]):
            print("[SDK] JWT auth config incomplete")
            return None

        try:
            import httpx

            print(f"[SDK] Fetching JWT token from: {api_url}")
            async with httpx.AsyncClient() as client:
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
                    print(f"[SDK] JWT token fetched successfully (length: {len(token)})")
                return token
        except Exception as e:
            print(f"[SDK] Failed to fetch JWT token: {e}")
            return None

    async def _fetch_oauth_token(self) -> str | None:
        """Fetch OAuth token using client credentials."""
        if not self.auth_config:
            return None

        token_url = self.auth_config.get("token_url", "")
        client_id = self.auth_config.get("client_id", "")
        client_secret = self.auth_config.get("client_secret", "")

        if not all([token_url, client_id, client_secret]):
            print("[SDK] OAuth auth config incomplete")
            return None

        try:
            import httpx

            print(f"[SDK] Fetching OAuth token from: {token_url}")
            async with httpx.AsyncClient() as client:
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
                    print(f"[SDK] OAuth token fetched successfully (length: {len(token)})")
                return token
        except Exception as e:
            print(f"[SDK] Failed to fetch OAuth token: {e}")
            return None

    def _create_sdk_tool(self, tool_schema: ToolSchema):
        """Create an SDK tool wrapper for an MCP tool."""
        from claude_agent_sdk import tool

        # Create a closure that captures the tool schema
        tool_name = tool_schema.name
        tool_description = tool_schema.description
        tool_params = tool_schema.parameters

        # Convert parameters to SDK format (simplified schema)
        # SDK expects {param_name: type} format, but we have JSON Schema
        # We'll use the JSON Schema directly since SDK supports that too
        input_schema = tool_params

        # Create the async function that will execute the tool
        async def tool_executor(args):
            """Execute the tool via our MCP service."""
            try:
                tool_call = {
                    "name": tool_name,
                    "arguments": args,
                    "id": f"tool_{tool_name}_{time.time()}",
                }

                result = await self.tool_discovery.execute_tool_call(tool_call)

                if result.is_error:
                    return {
                        "content": [{"type": "text", "text": f"Error: {result.error_message}"}],
                        "is_error": True,
                    }
                else:
                    # Format result content
                    content = []
                    if isinstance(result.content, str):
                        content.append({"type": "text", "text": result.content})
                    elif isinstance(result.content, list):
                        content = result.content
                    else:
                        content.append({"type": "text", "text": str(result.content)})

                    return {"content": content}

            except Exception as e:
                return {
                    "content": [{"type": "text", "text": f"Tool execution error: {str(e)}"}],
                    "is_error": True,
                }

        # Apply the tool decorator
        sdk_tool = tool(tool_name, tool_description, input_schema)(tool_executor)
        return sdk_tool

    async def generate_with_tools(
        self,
        prompt: str,
        tools: list[dict[str, Any]],
        timeout: float = 30.0,
        messages: list[dict[str, Any]] | None = None,
    ) -> LLMResult:
        """Generate response using Claude Agent SDK."""
        start_time = time.time()

        try:
            from claude_agent_sdk import ClaudeAgentOptions, query

            # Create options for the SDK
            options = ClaudeAgentOptions(
                model=self.model,
                permission_mode="bypassPermissions",  # Skip permission prompts for automation
                mcp_servers={},
            )

            # Add our MCP server if we have config
            if self._mcp_server_config:
                options.mcp_servers["superset"] = self._mcp_server_config
                # Mask token for logging
                masked_config = dict(self._mcp_server_config)
                if "headers" in masked_config and "Authorization" in masked_config["headers"]:
                    token = masked_config["headers"]["Authorization"].replace("Bearer ", "")
                    if len(token) > 30:
                        masked_token = f"{token[:20]}...{token[-8:]}"
                        masked_config["headers"]["Authorization"] = f"Bearer {masked_token}"
                print("[SDK] Added MCP server 'superset' to SDK options")
                print(f"[SDK] URL: {masked_config.get('url')}")
                print(f"[SDK] Auth: {'Yes (token masked)' if 'headers' in masked_config else 'No'}")
            else:
                print("[SDK] Warning: No MCP server config available - SDK will not have MCP tools")

            # Execute query with timeout wrapper
            response_text = ""
            tool_calls = []
            token_usage = None
            cost = 0.0

            print(f"[SDK] Starting query (timeout={timeout}s)...")

            # Wrap the query in a timeout
            async def execute_query():
                nonlocal response_text, token_usage, cost
                message_count = 0
                async for message in query(prompt=prompt, options=options):
                    message_count += 1
                    msg_type = type(message).__name__
                    print(f"[SDK] Message #{message_count}: {msg_type}")

                    # Extract text from AssistantMessage
                    if hasattr(message, "content"):
                        for block in message.content:
                            if hasattr(block, "text"):
                                response_text += block.text
                                preview = block.text[:80].replace("\n", " ")
                                print(f"[SDK]   └─ Text: {preview}...")
                            elif hasattr(block, "type") and block.type == "tool_use":
                                # Log tool calls
                                tool_name = getattr(block, "name", "unknown")
                                tool_input = getattr(block, "input", {})
                                print(f"[SDK]   └─ 🔧 Tool Call: {tool_name}")
                                # Show abbreviated input
                                if tool_input:
                                    import json

                                    input_str = json.dumps(tool_input, indent=2)
                                    if len(input_str) > 200:
                                        input_str = input_str[:200] + "..."
                                    print(f"[SDK]      Input: {input_str}")

                    # Log tool results from UserMessage (SDK sends tool results as user messages)
                    if msg_type == "UserMessage" and hasattr(message, "content"):
                        for block in message.content:
                            if hasattr(block, "type") and block.type == "tool_result":
                                tool_id = getattr(block, "tool_use_id", "unknown")
                                is_error = getattr(block, "is_error", False)
                                print(f"[SDK]   └─ ✅ Tool Result (id={tool_id}, error={is_error})")

                    # Extract usage from ResultMessage
                    if hasattr(message, "usage"):
                        usage = message.usage
                        token_usage = {
                            "prompt": usage.get("input_tokens", 0)
                            + usage.get("cache_read_input_tokens", 0)
                            + usage.get("cache_creation_input_tokens", 0),
                            "completion": usage.get("output_tokens", 0),
                            "total": (
                                usage.get("input_tokens", 0)
                                + usage.get("cache_read_input_tokens", 0)
                                + usage.get("cache_creation_input_tokens", 0)
                                + usage.get("output_tokens", 0)
                            ),
                        }
                        print(
                            f"[SDK] Token usage: {token_usage['total']:,} tokens (prompt: {token_usage['prompt']:,}, completion: {token_usage['completion']:,})"
                        )

                        # Get cost from SDK result
                        if hasattr(message, "total_cost_usd"):
                            cost = message.total_cost_usd
                            print(f"[SDK] Cost: ${cost:.4f}")

                print(
                    f"[SDK] Query completed: {message_count} messages, {len(response_text)} chars"
                )

            # Execute with timeout
            try:
                await asyncio.wait_for(execute_query(), timeout=timeout)
            except asyncio.TimeoutError:
                raise Exception(f"SDK query timed out after {timeout}s")

            return LLMResult(
                response=response_text,
                tool_calls=tool_calls,
                token_usage=token_usage,
                cost=cost,
                duration=time.time() - start_time,
                raw_response=None,
            )

        except Exception as e:
            print(f"[SDK] ❌ Error: {type(e).__name__}: {str(e)}")
            return LLMResult(
                response=f"Error: {str(e)}", tool_calls=[], duration=time.time() - start_time
            )

    async def close(self):
        """Close connections."""
        await self.tool_discovery.close()


class ClaudeCodeProvider(LLMProvider):
    """Claude Code CLI provider via subprocess with JSON output support.

    This provider uses Claude Code's subscription (no API credits required).
    It supports:
    - Structured JSON output with tool calls, thinking, and usage stats
    - Direct MCP server integration via Claude Code's native MCP support
    - Extended thinking capture when available
    """

    def __init__(
        self,
        model: str,
        claude_cli_path: str | None = None,
        mcp_url: str | None = None,
        auth: dict[str, Any] | None = None,
        output_format: str = "json",  # 'json' for structured, 'text' for plain
        log_callback=None,
    ):
        self.model = model
        self.claude_cli_path = claude_cli_path or self._find_claude_cli()
        self.output_format = output_format
        self.log_callback = log_callback  # Real-time log streaming callback
        # Use MCP_URL and auth from default profile if not provided
        config = get_config()
        if mcp_url is None:
            mcp_url = config.get_mcp_url()
        self.mcp_url = mcp_url
        if auth is None:
            # Get auth from default MCP server
            default_mcp = config.get_default_mcp_server()
            if default_mcp and default_mcp.auth:
                auth = default_mcp.auth.to_dict()
        self.auth_config = auth
        self.tool_discovery = ToolDiscoveryService(mcp_url, auth=auth)

    def _find_claude_cli(self) -> str:
        """Find Claude CLI in PATH or common locations."""
        # Check environment variable first
        cli_path = os.environ.get("CLAUDE_CLI_PATH")
        if cli_path and os.path.exists(cli_path):
            return cli_path

        # Check common locations
        common_paths = [
            "/usr/local/bin/claude",
            "/opt/homebrew/bin/claude",
            os.path.expanduser("~/.local/bin/claude"),
        ]

        # Add nvm paths - check all installed node versions
        nvm_dir = os.path.expanduser("~/.nvm/versions/node")
        if os.path.isdir(nvm_dir):
            for version_dir in os.listdir(nvm_dir):
                nvm_claude = os.path.join(nvm_dir, version_dir, "bin", "claude")
                if os.path.exists(nvm_claude):
                    common_paths.insert(0, nvm_claude)  # Prioritize nvm paths

        # Also try shutil.which which respects PATH
        import shutil

        which_result = shutil.which("claude")
        if which_result:
            common_paths.insert(0, which_result)

        # Finally add "claude" for PATH lookup
        common_paths.append("claude")

        for path in common_paths:
            try:
                result = subprocess.run([path, "--version"], capture_output=True, timeout=5)
                if result.returncode == 0:
                    return path
            except (subprocess.TimeoutExpired, FileNotFoundError):
                continue

        raise Exception("Claude CLI not found. Please install Claude Code or set CLAUDE_CLI_PATH")

    async def initialize(self):
        """Initialize Claude Code provider."""
        # Verify Claude CLI is working
        try:
            result = subprocess.run(
                [self.claude_cli_path, "--version"], capture_output=True, timeout=10, text=True
            )
            if result.returncode != 0:
                raise Exception(f"Claude CLI error: {result.stderr}")
            version = result.stdout.strip()
            print(f"[ClaudeCode] CLI version: {version}")
        except subprocess.TimeoutExpired:
            raise Exception("Claude CLI timeout during initialization")

        # Try to pre-discover tools for tool schema info
        try:
            await self.tool_discovery.discover_tools()
            print(f"[ClaudeCode] ✅ MCP service available at {self.tool_discovery.mcp_url}")
        except Exception as e:
            print(f"[ClaudeCode] ⚠️  MCP tools not available: {e}")

    async def _fetch_jwt_token(self) -> str | None:
        """Fetch JWT token from API."""
        if not self.auth_config:
            return None

        api_url = self.auth_config.get("api_url", "")
        api_token = self.auth_config.get("api_token", "")
        api_secret = self.auth_config.get("api_secret", "")

        if not all([api_url, api_token, api_secret]):
            print("[ClaudeCode] JWT auth config incomplete")
            return None

        try:
            import httpx

            print(f"[ClaudeCode] Fetching JWT token from: {api_url}")
            async with httpx.AsyncClient() as client:
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
                    print(f"[ClaudeCode] JWT token fetched successfully (length: {len(token)})")
                return token
        except Exception as e:
            print(f"[ClaudeCode] Failed to fetch JWT token: {e}")
            return None

    async def generate_with_tools(
        self,
        prompt: str,
        tools: list[dict[str, Any]],
        timeout: float = 120.0,
        messages: list[dict[str, Any]] | None = None,
    ) -> LLMResult:
        """Generate response using Claude Code CLI with JSON output."""
        start_time = time.time()
        logs = []  # Capture logs for UI display

        def log(msg: str):
            """Log a message to console, logs list, and optionally via callback."""
            print(msg)
            logs.append(msg)
            # Stream to callback if available (for real-time UI updates)
            if self.log_callback:
                import asyncio

                if asyncio.iscoroutinefunction(self.log_callback):
                    try:
                        loop = asyncio.get_event_loop()
                        if loop.is_running():
                            asyncio.create_task(self.log_callback(msg))
                        else:
                            loop.run_until_complete(self.log_callback(msg))
                    except RuntimeError:
                        # No event loop, skip callback
                        pass
                else:
                    self.log_callback(msg)

        try:
            log(f"[ClaudeCode] Running with timeout={timeout}s, output_format=stream-json")

            # Build command with stream-json output for structured responses with tool calls
            # Note: -p/--print enables non-interactive mode, prompt is positional arg
            # stream-json + verbose exposes tool_use and tool_result events
            cmd = [
                self.claude_cli_path,
                "-p",  # --print mode (non-interactive)
                "--output-format",
                "stream-json",  # Use stream-json to get tool call details
                "--verbose",  # Required for stream-json in print mode
                "--dangerously-skip-permissions",
            ]

            # Add model if specified
            if self.model:
                cmd.extend(["--model", self.model])

            # Add MCP server config if we have one AND tools are expected - write to temp file
            # Only add MCP config when tools are provided (otherwise it's just text generation)
            mcp_config_file = None
            if self.mcp_url and tools:
                import tempfile

                # Build MCP config JSON for the server
                mcp_config = {
                    "mcpServers": {
                        "testmcpy": {
                            "type": "http",
                            "url": self.mcp_url,
                        }
                    }
                }
                # Add auth header based on auth config type
                auth_token = None
                if self.auth_config:
                    auth_type = self.auth_config.get("type", "")
                    if auth_type == "jwt":
                        # Fetch JWT token dynamically
                        auth_token = await self._fetch_jwt_token()
                        log(
                            f"[ClaudeCode] Fetched JWT token (length: {len(auth_token) if auth_token else 0})"
                        )
                    elif auth_type == "bearer":
                        auth_token = self.auth_config.get("token", "")
                    elif self.auth_config.get("token"):
                        # Legacy: direct token
                        auth_token = self.auth_config.get("token")

                if auth_token:
                    mcp_config["mcpServers"]["testmcpy"]["headers"] = {
                        "Authorization": f"Bearer {auth_token}"
                    }

                # Write config to temp file
                mcp_config_file = tempfile.NamedTemporaryFile(
                    mode="w", suffix=".json", delete=False
                )
                json.dump(mcp_config, mcp_config_file)
                mcp_config_file.close()
                cmd.extend(["--mcp-config", mcp_config_file.name])
                log(f"[ClaudeCode] MCP config file: {mcp_config_file.name}")
                log(f"[ClaudeCode] MCP URL: {self.mcp_url}")
            elif not tools:
                log("[ClaudeCode] No tools - skipping MCP config (text generation mode)")

            # Use -- to separate options from positional argument (needed for --mcp-config)
            cmd.append("--")
            cmd.append(prompt)

            # Print full command for debugging (mask prompt)
            cmd_debug = cmd[:-1] + ["<prompt>"]  # Replace actual prompt with placeholder
            log(f"[ClaudeCode] Full command: {' '.join(cmd_debug)}")

            # Show prompt details
            prompt_preview = prompt[:500] + "..." if len(prompt) > 500 else prompt
            log(f"[ClaudeCode] Prompt ({len(prompt)} chars):\n{prompt_preview}")
            log(f"[ClaudeCode] Tools provided: {len(tools)}")
            if tools:
                tool_names = [t.get("function", {}).get("name", "unknown") for t in tools[:10]]
                log(f"[ClaudeCode] Tool names (first 10): {tool_names}")

            # Execute Claude CLI
            # IMPORTANT: Clear ANTHROPIC_API_KEY from env so CLI uses subscription, not API credits
            cli_env = os.environ.copy()
            cli_env.pop("ANTHROPIC_API_KEY", None)  # Remove API key if present

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=cli_env,
            )

            try:
                log("[ClaudeCode] Waiting for response...")
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
                elapsed = time.time() - start_time
                log(
                    f"[ClaudeCode] Got response after {elapsed:.1f}s, returncode={process.returncode}"
                )
            except asyncio.TimeoutError:
                log(f"[ClaudeCode] TIMEOUT after {timeout}s - killing process")
                process.kill()
                await process.wait()
                raise Exception(f"Claude CLI timeout after {timeout}s")

            stdout_text = stdout.decode().strip()
            stderr_text = stderr.decode().strip()

            log(f"[ClaudeCode] Response size: {len(stdout_text)} chars")
            if stderr_text:
                log(f"[ClaudeCode] stderr: {stderr_text[:500]}...")

            # Show raw response preview
            if stdout_text:
                response_preview = (
                    stdout_text[:1000] + "..." if len(stdout_text) > 1000 else stdout_text
                )
                log(f"[ClaudeCode] Raw response:\n{response_preview}")

            # Parse stream-json output (multiple JSON lines)
            return self._parse_stream_json_response(stdout_text, start_time, logs)

        except Exception as e:
            duration = time.time() - start_time
            log(f"[ClaudeCode] ❌ Error: {type(e).__name__}: {str(e)}")
            return LLMResult(
                response=f"Error: {str(e)}",
                tool_calls=[],
                duration=duration,
                logs=logs,
            )
        finally:
            # Clean up temp MCP config file
            if mcp_config_file and os.path.exists(mcp_config_file.name):
                try:
                    os.unlink(mcp_config_file.name)
                except Exception:
                    pass

    def _parse_stream_json_response(
        self, output: str, start_time: float, logs: list[str] | None = None
    ) -> LLMResult:
        """Parse stream-json output from Claude CLI.

        Stream-json format outputs multiple JSON lines with different event types:
        - {"type":"assistant","message":{"content":[{"type":"text","text":"..."},{"type":"tool_use",...}]}}
        - {"type":"user","message":{"content":[{"type":"tool_result","tool_use_id":"...","content":"..."}]}}
        - {"type":"result","duration_ms":...,"usage":{...},"cost_usd":...}
        """
        logs = logs or []
        response_text = ""
        thinking_text = ""
        tool_calls = []
        tool_results = {}  # Map tool_use_id to result
        token_usage = None
        cost = 0.0
        raw_events = []

        try:
            # Parse each line as a separate JSON event
            lines = output.strip().split("\n")
            logs.append(f"[ClaudeCode] Parsing {len(lines)} stream-json lines")
            print(f"[ClaudeCode] Parsing {len(lines)} stream-json lines")

            for line_num, line in enumerate(lines):
                line = line.strip()
                if not line:
                    continue

                try:
                    event = json.loads(line)
                    raw_events.append(event)
                    event_type = event.get("type", "")

                    if event_type == "assistant":
                        # Assistant message with text and/or tool_use blocks
                        message = event.get("message", {})
                        content = message.get("content", [])

                        for block in content:
                            block_type = block.get("type", "")

                            if block_type == "text":
                                text = block.get("text", "")
                                response_text += text
                                logs.append(f"[ClaudeCode] 📝 Text ({len(text)} chars)")
                                print(f"[ClaudeCode] 📝 Text ({len(text)} chars)")

                            elif block_type == "thinking":
                                thinking = block.get("thinking", "")
                                thinking_text += thinking
                                logs.append(f"[ClaudeCode] 🧠 Thinking ({len(thinking)} chars)")
                                print(f"[ClaudeCode] 🧠 Thinking ({len(thinking)} chars)")

                            elif block_type == "tool_use":
                                tool_call = {
                                    "id": block.get("id", ""),
                                    "name": block.get("name", ""),
                                    "arguments": block.get("input", {}),
                                }
                                tool_calls.append(tool_call)
                                logs.append(
                                    f"[ClaudeCode] 🔧 Tool Call: {tool_call['name']} (id={tool_call['id'][:20]}...)"
                                )
                                print(
                                    f"[ClaudeCode] 🔧 Tool Call: {tool_call['name']} (id={tool_call['id'][:20]}...)"
                                )
                                # Log arguments preview
                                args_str = json.dumps(tool_call["arguments"])
                                if len(args_str) > 200:
                                    args_str = args_str[:200] + "..."
                                logs.append(f"[ClaudeCode]    Args: {args_str}")
                                print(f"[ClaudeCode]    Args: {args_str}")

                    elif event_type == "user":
                        # User message containing tool_result blocks
                        message = event.get("message", {})
                        content = message.get("content", [])

                        for block in content:
                            if block.get("type") == "tool_result":
                                tool_use_id = block.get("tool_use_id", "")
                                is_error = block.get("is_error", False)
                                result_content = block.get("content", "")

                                # Store the result
                                tool_results[tool_use_id] = {
                                    "content": result_content,
                                    "is_error": is_error,
                                }

                                # Log result preview
                                content_preview = (
                                    str(result_content)[:200] + "..."
                                    if len(str(result_content)) > 200
                                    else str(result_content)
                                )
                                status = "❌ Error" if is_error else "✅ Success"
                                logs.append(
                                    f"[ClaudeCode] {status} Tool Result (id={tool_use_id[:20]}...)"
                                )
                                logs.append(f"[ClaudeCode]    Content: {content_preview}")
                                print(
                                    f"[ClaudeCode] {status} Tool Result (id={tool_use_id[:20]}...)"
                                )
                                print(f"[ClaudeCode]    Content: {content_preview}")

                    elif event_type == "result":
                        # Final result with usage and cost
                        usage = event.get("usage", {})
                        token_usage = {
                            "prompt": usage.get("input_tokens", 0),
                            "completion": usage.get("output_tokens", 0),
                            "total": usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
                            "cache_creation": usage.get("cache_creation_input_tokens", 0),
                            "cache_read": usage.get("cache_read_input_tokens", 0),
                        }

                        cost = event.get("cost_usd", 0.0)

                        logs.append(
                            f"[ClaudeCode] 📊 Result: {token_usage['total']} tokens, ${cost:.4f}"
                        )
                        print(f"[ClaudeCode] 📊 Result: {token_usage['total']} tokens, ${cost:.4f}")

                    elif event_type == "system":
                        # System messages (usually init info)
                        system_msg = event.get("message", "")
                        if system_msg:
                            logs.append(f"[ClaudeCode] ℹ️ System: {str(system_msg)[:100]}")
                            print(f"[ClaudeCode] ℹ️ System: {str(system_msg)[:100]}")

                except json.JSONDecodeError:
                    # Not valid JSON - might be plain text output
                    logs.append(f"[ClaudeCode] ⚠️ Non-JSON line {line_num + 1}: {line[:50]}...")
                    print(f"[ClaudeCode] ⚠️ Non-JSON line {line_num + 1}: {line[:50]}...")
                    # Append to response if we haven't parsed any JSON yet
                    if not raw_events:
                        response_text += line + "\n"

            # Attach tool results to tool calls for completeness
            # Also create MCPToolResult objects for evaluators
            mcp_tool_results = []
            for tc in tool_calls:
                tc_id = tc.get("id", "")
                if tc_id in tool_results:
                    tc["result"] = tool_results[tc_id]
                    # Create MCPToolResult for evaluators
                    result_data = tool_results[tc_id]
                    mcp_result = MCPToolResult(
                        tool_call_id=tc_id,
                        content=result_data.get("content", ""),
                        is_error=result_data.get("is_error", False),
                        error_message=str(result_data.get("content", ""))
                        if result_data.get("is_error")
                        else None,
                    )
                    mcp_tool_results.append(mcp_result)

            # Summary
            logs.append(
                f"[ClaudeCode] ✓ Parsed: {len(response_text)} chars response, "
                f"{len(tool_calls)} tool calls, {len(mcp_tool_results)} tool results, "
                f"{len(thinking_text)} chars thinking"
            )
            print(
                f"[ClaudeCode] ✓ Parsed: {len(response_text)} chars response, "
                f"{len(tool_calls)} tool calls, {len(mcp_tool_results)} tool results, "
                f"{len(thinking_text)} chars thinking"
            )

        except Exception as e:
            logs.append(f"[ClaudeCode] ❌ Parse error: {e}")
            print(f"[ClaudeCode] ❌ Parse error: {e}")
            # Fallback to raw output
            response_text = output
            mcp_tool_results = []

        duration = time.time() - start_time
        return LLMResult(
            response=response_text,
            tool_calls=tool_calls,
            tool_results=mcp_tool_results,
            thinking=thinking_text if thinking_text else None,
            token_usage=token_usage,
            cost=cost,
            duration=duration,
            tti_ms=int(duration * 1000),
            raw_response={"events": raw_events} if raw_events else {"stdout": output},
            logs=logs,
        )

    def _parse_json_response(
        self, output: str, start_time: float, logs: list[str] | None = None
    ) -> LLMResult:
        """Parse structured JSON output from Claude CLI."""
        logs = logs or []
        response_text = ""
        thinking_text = ""
        tool_calls = []
        token_usage = None
        cost = 0.0
        raw_data = None

        try:
            # Claude CLI JSON output is a single JSON object or stream of JSON lines
            # Try parsing as single JSON first
            try:
                data = json.loads(output)
                raw_data = data
            except json.JSONDecodeError:
                # Try parsing as JSON lines (stream format)
                lines = output.strip().split("\n")
                data = None
                for line in lines:
                    if line.strip():
                        try:
                            data = json.loads(line)
                        except json.JSONDecodeError:
                            continue

            if data:
                # Extract response text
                if isinstance(data, dict):
                    # Handle different JSON output formats from Claude CLI
                    if "result" in data:
                        response_text = data.get("result", "")
                    elif "response" in data:
                        response_text = data.get("response", "")
                    elif "content" in data:
                        content = data.get("content", [])
                        if isinstance(content, list):
                            for block in content:
                                if isinstance(block, dict):
                                    if block.get("type") == "text":
                                        response_text += block.get("text", "")
                                    elif block.get("type") == "thinking":
                                        thinking_text += block.get("thinking", "")
                                    elif block.get("type") == "tool_use":
                                        tool_calls.append(
                                            {
                                                "id": block.get("id", ""),
                                                "name": block.get("name", ""),
                                                "arguments": block.get("input", {}),
                                            }
                                        )
                        elif isinstance(content, str):
                            response_text = content
                    elif "message" in data:
                        response_text = data.get("message", "")
                    elif "text" in data:
                        response_text = data.get("text", "")

                    # Extract tool calls if present
                    if "tool_calls" in data:
                        for tc in data.get("tool_calls", []):
                            tool_calls.append(
                                {
                                    "id": tc.get("id", ""),
                                    "name": tc.get("name", ""),
                                    "arguments": tc.get("arguments", tc.get("input", {})),
                                }
                            )

                    # Extract usage stats if available
                    if "usage" in data:
                        usage = data.get("usage", {})
                        token_usage = {
                            "prompt": usage.get("input_tokens", 0),
                            "completion": usage.get("output_tokens", 0),
                            "total": usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
                        }

                    # Extract cost if available
                    if "cost" in data:
                        cost = data.get("cost", 0.0)
                    elif "total_cost" in data:
                        cost = data.get("total_cost", 0.0)

                    # Extract thinking if available
                    if "thinking" in data and not thinking_text:
                        thinking_text = data.get("thinking", "")

            # Fallback if no structured data found
            if not response_text and not tool_calls:
                response_text = output

            logs.append(
                f"[ClaudeCode] Parsed: {len(response_text)} chars, {len(tool_calls)} tool calls"
            )
            print(f"[ClaudeCode] Parsed: {len(response_text)} chars, {len(tool_calls)} tool calls")
            if tool_calls:
                logs.append("[ClaudeCode] Tool calls:")
                print("[ClaudeCode] Tool calls:")
                for i, tc in enumerate(tool_calls):
                    tool_log = f"[ClaudeCode]   {i + 1}. {tc.get('name', 'unknown')}({json.dumps(tc.get('arguments', {}), indent=2)[:200]})"
                    logs.append(tool_log)
                    print(tool_log)
            if response_text:
                response_preview = (
                    response_text[:300] + "..." if len(response_text) > 300 else response_text
                )
                logs.append(f"[ClaudeCode] Response text: {response_preview}")
                print(f"[ClaudeCode] Response text: {response_preview}")
            if thinking_text:
                logs.append(f"[ClaudeCode] Thinking: {len(thinking_text)} chars")
                print(f"[ClaudeCode] Thinking: {len(thinking_text)} chars")
            if token_usage:
                logs.append(f"[ClaudeCode] Tokens: {token_usage.get('total', 0)}")
                print(f"[ClaudeCode] Tokens: {token_usage.get('total', 0)}")

        except Exception as e:
            logs.append(f"[ClaudeCode] JSON parse error: {e}")
            print(f"[ClaudeCode] JSON parse error: {e}")
            response_text = output

        duration = time.time() - start_time
        return LLMResult(
            response=response_text,
            tool_calls=tool_calls,
            thinking=thinking_text if thinking_text else None,
            token_usage=token_usage,
            cost=cost,
            duration=duration,
            tti_ms=int(duration * 1000),
            raw_response=raw_data or {"stdout": output},
            logs=logs,
        )

    def _parse_text_response(
        self, output: str, start_time: float, logs: list[str] | None = None
    ) -> LLMResult:
        """Parse plain text output from Claude CLI."""
        logs = logs or []
        # Parse tool calls from text output (legacy format)
        tool_calls = []
        tool_call_pattern = r"TOOL_CALL:\s*(\{[^}]+\}|\{[^}]*\{[^}]*\}[^}]*\})"
        matches = re.findall(tool_call_pattern, output)

        for match in matches:
            try:
                call_data = json.loads(match)
                if "name" in call_data:
                    tool_calls.append(
                        {
                            "name": call_data["name"],
                            "arguments": call_data.get("arguments", {}),
                        }
                    )
            except json.JSONDecodeError:
                continue

        duration = time.time() - start_time
        return LLMResult(
            response=output,
            tool_calls=tool_calls,
            token_usage=None,
            cost=0.0,
            duration=duration,
            raw_response={"stdout": output},
            logs=logs,
        )

    async def close(self):
        """Close connections."""
        await self.tool_discovery.close()


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


def create_llm_provider(provider: str, model: str, **kwargs) -> LLMProvider:
    """
    Create an LLM provider instance.

    Args:
        provider: Provider name (ollama, openai, local, anthropic, claude-cli, codex-cli)
        model: Model name/path
        **kwargs: Additional provider-specific arguments

    Returns:
        LLMProvider instance
    """
    providers = {
        "ollama": OllamaProvider,
        "openai": OpenAIProvider,
        "local": LocalModelProvider,
        "anthropic": AnthropicProvider,
        "gemini": GeminiProvider,
        "google": GeminiProvider,  # Alias
        "claude-sdk": ClaudeSDKProvider,
        "claude-cli": ClaudeCodeProvider,
        "claude-code": ClaudeCodeProvider,  # Alias for claude-cli
        "codex-cli": CodexCLIProvider,
        "codex": CodexCLIProvider,  # Alias
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
