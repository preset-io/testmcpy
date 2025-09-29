"""
LLM integration module for supporting multiple model providers.
"""

import json
import asyncio
import time
import re
import os
import subprocess
from typing import Dict, List, Any, Optional, Union
from dataclasses import dataclass, field
from abc import ABC, abstractmethod
import httpx
from urllib.parse import urlparse

# Import MCP components (we'll handle the import error gracefully)
try:
    from .mcp_client import MCPClient, MCPTool, MCPToolCall, MCPToolResult
except ImportError:
    # Fallback for when running as script
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    from mcp_client import MCPClient, MCPTool, MCPToolCall, MCPToolResult


@dataclass
class LLMResult:
    """Result from LLM generation."""
    response: str
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    token_usage: Optional[Dict[str, int]] = None
    cost: float = 0.0
    duration: float = 0.0
    raw_response: Optional[Any] = None


@dataclass
class ToolSchema:
    """Sanitized tool schema without internal URLs."""
    name: str
    description: str
    parameters: Dict[str, Any]

    @classmethod
    def from_mcp_tool(cls, tool: MCPTool) -> "ToolSchema":
        """Create sanitized tool schema from MCP tool."""
        return cls(
            name=tool.name,
            description=tool.description,
            parameters=tool.input_schema
        )


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
        tools: List[Dict[str, Any]],
        timeout: float = 30.0
    ) -> LLMResult:
        """Generate response with tool calling capability."""
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
                timeout=600.0  # 10 minutes for large models
            )
            if response.status_code != 200:
                raise Exception(f"Failed to pull model: {response.text}")
        except Exception as e:
            raise Exception(f"Failed to pull model {self.model}: {e}")

    async def generate_with_tools(
        self,
        prompt: str,
        tools: List[Dict[str, Any]],
        timeout: float = 30.0
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
                }
            }

            response = await self.client.post(
                f"{self.base_url}/api/generate",
                json=request_data,
                timeout=timeout
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
                "total": result.get("prompt_eval_count", 0) + result.get("eval_count", 0)
            }

            return LLMResult(
                response=response_text,
                tool_calls=tool_calls,
                token_usage=token_usage,
                cost=0.0,  # Local models have no API cost
                duration=time.time() - start_time,
                raw_response=result
            )

        except Exception as e:
            return LLMResult(
                response=f"Error: {str(e)}",
                tool_calls=[],
                duration=time.time() - start_time
            )

    def _format_prompt_with_tools(self, prompt: str, tools: List[Dict[str, Any]]) -> str:
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

    def _parse_tool_calls(self, response: str, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Parse tool calls from Ollama response."""
        tool_calls = []

        try:
            # Try to parse as JSON
            data = json.loads(response)

            # Check common patterns
            if "tool" in data and "arguments" in data:
                tool_calls.append({
                    "name": data["tool"],
                    "arguments": data["arguments"]
                })
            elif "function" in data and "arguments" in data:
                tool_calls.append({
                    "name": data["function"],
                    "arguments": data["arguments"]
                })
            elif "name" in data and ("arguments" in data or "parameters" in data):
                tool_calls.append({
                    "name": data["name"],
                    "arguments": data.get("arguments", data.get("parameters", {}))
                })

        except json.JSONDecodeError:
            # Try to extract JSON from the response
            import re
            json_pattern = r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
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
        self,
        model: str,
        api_key: Optional[str] = None,
        base_url: str = "https://api.openai.com/v1"
    ):
        self.model = model
        self.api_key = api_key or ""
        self.base_url = base_url
        self.client = httpx.AsyncClient(timeout=60.0)

    async def initialize(self):
        """Initialize OpenAI provider."""
        if not self.api_key and self.base_url == "https://api.openai.com/v1":
            import os
            self.api_key = os.environ.get("OPENAI_API_KEY", "")
            if not self.api_key:
                raise ValueError("OpenAI API key not provided")

    async def generate_with_tools(
        self,
        prompt: str,
        tools: List[Dict[str, Any]],
        timeout: float = 30.0
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
            messages = [
                {"role": "user", "content": prompt}
            ]

            request_data = {
                "model": self.model,
                "messages": messages,
                "tools": tools,
                "tool_choice": "auto",
                "temperature": 0.1,
                "max_tokens": 1000
            }

            response = await self.client.post(
                f"{self.base_url}/chat/completions",
                json=request_data,
                headers=headers,
                timeout=timeout
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
                    tool_calls.append({
                        "name": tc["function"]["name"],
                        "arguments": json.loads(tc["function"]["arguments"])
                    })

            # Token usage
            usage = result.get("usage", {})
            token_usage = {
                "prompt": usage.get("prompt_tokens", 0),
                "completion": usage.get("completion_tokens", 0),
                "total": usage.get("total_tokens", 0)
            }

            # Estimate cost (GPT-4 pricing as example)
            cost = (token_usage["prompt"] * 0.03 + token_usage["completion"] * 0.06) / 1000

            return LLMResult(
                response=message.get("content", ""),
                tool_calls=tool_calls,
                token_usage=token_usage,
                cost=cost,
                duration=time.time() - start_time,
                raw_response=result
            )

        except Exception as e:
            return LLMResult(
                response=f"Error: {str(e)}",
                tool_calls=[],
                duration=time.time() - start_time
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
                "text-generation",
                model=self.model,
                device=self.device,
                max_new_tokens=1000
            )
        except ImportError:
            raise ImportError("transformers library required for local models")
        except Exception as e:
            raise Exception(f"Failed to load local model {self.model}: {e}")

    async def generate_with_tools(
        self,
        prompt: str,
        tools: List[Dict[str, Any]],
        timeout: float = 30.0
    ) -> LLMResult:
        """Generate with local model."""
        start_time = time.time()

        # Format prompt with tools
        formatted_prompt = self._format_prompt_with_tools(prompt, tools)

        try:
            # Run generation in executor to avoid blocking
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                self.pipeline,
                formatted_prompt
            )

            response_text = result[0]["generated_text"]
            # Remove the prompt from response
            if response_text.startswith(formatted_prompt):
                response_text = response_text[len(formatted_prompt):].strip()

            # Parse tool calls
            tool_calls = self._parse_tool_calls(response_text)

            return LLMResult(
                response=response_text,
                tool_calls=tool_calls,
                duration=time.time() - start_time
            )

        except Exception as e:
            return LLMResult(
                response=f"Error: {str(e)}",
                tool_calls=[],
                duration=time.time() - start_time
            )

    def _format_prompt_with_tools(self, prompt: str, tools: List[Dict[str, Any]]) -> str:
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

    def _parse_tool_calls(self, response: str) -> List[Dict[str, Any]]:
        """Parse tool calls from response."""
        tool_calls = []
        try:
            import re
            json_pattern = r'\{[^{}]*\}'
            matches = re.findall(json_pattern, response)
            for match in matches:
                data = json.loads(match)
                if "tool" in data:
                    tool_calls.append({
                        "name": data["tool"],
                        "arguments": data.get("arguments", {})
                    })
        except:
            pass
        return tool_calls

    async def close(self):
        """Clean up resources."""
        self.pipeline = None


class MCPURLFilter:
    """Security class to prevent MCP URLs from reaching external APIs."""

    MCP_URL_PATTERNS = [
        r'http://localhost:\d+/mcp',
        r'https://localhost:\d+/mcp',
        r'http://127\.0\.0\.1:\d+/mcp',
        r'https://127\.0\.0\.1:\d+/mcp',
        r'http://0\.0\.0\.0:\d+/mcp',
        r'https://0\.0\.0\.0:\d+/mcp',
        r'mcp://',
        r'localhost:\d+/mcp',
        r'127\.0\.0\.1:\d+/mcp',
        r'0\.0\.0\.0:\d+/mcp'
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
    def sanitize_tool_schema(cls, tool_schema: Dict[str, Any]) -> Dict[str, Any]:
        """Remove any URLs from tool schema."""
        def _sanitize_recursive(obj):
            if isinstance(obj, str):
                # Remove URLs but keep the rest of the text
                for pattern in cls.MCP_URL_PATTERNS:
                    obj = re.sub(pattern, '[REDACTED]', obj, flags=re.IGNORECASE)
                return obj
            elif isinstance(obj, dict):
                return {k: _sanitize_recursive(v) for k, v in obj.items()
                       if k not in ['url', 'endpoint', 'base_url']}
            elif isinstance(obj, list):
                return [_sanitize_recursive(item) for item in obj]
            return obj

        return _sanitize_recursive(tool_schema)


class ToolDiscoveryService:
    """Discovers MCP tools locally and creates sanitized schemas."""

    def __init__(self, mcp_url: str):
        self.mcp_url = mcp_url
        self._tools_cache: Optional[List[ToolSchema]] = None
        self._mcp_client: Optional[MCPClient] = None

    async def discover_tools(self, force_refresh: bool = False) -> List[ToolSchema]:
        """Connect to MCP service and extract tool schemas only."""
        if not force_refresh and self._tools_cache is not None:
            return self._tools_cache

        if not self._mcp_client:
            self._mcp_client = MCPClient(self.mcp_url)
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

    async def execute_tool_call(self, tool_call: Dict[str, Any]) -> MCPToolResult:
        """Execute tool call via local MCP client."""
        if not self._mcp_client:
            raise Exception("MCP client not initialized")

        mcp_call = MCPToolCall(
            name=tool_call["name"],
            arguments=tool_call.get("arguments", {}),
            id=tool_call.get("id", "unknown")
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
        api_key: Optional[str] = None,
        base_url: str = "https://api.anthropic.com",
        mcp_url: str = "http://localhost:5008/mcp"
    ):
        self.model = model
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self.base_url = base_url
        self.client = httpx.AsyncClient(timeout=60.0)
        self.tool_discovery = ToolDiscoveryService(mcp_url)

    async def initialize(self):
        """Initialize Anthropic provider."""
        if not self.api_key:
            raise ValueError("Anthropic API key not provided. Set ANTHROPIC_API_KEY environment variable.")

        # Pre-discover tools
        await self.tool_discovery.discover_tools()

    async def generate_with_tools(
        self,
        prompt: str,
        tools: List[Dict[str, Any]],
        timeout: float = 30.0
    ) -> LLMResult:
        """Generate response with tool calling capability."""
        start_time = time.time()

        try:
            # CRITICAL: Validate NO MCP URLs in request
            request_data = {
                "prompt": prompt,
                "tools": tools
            }

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
                        "parameters": func.get("parameters", {})
                    }
                else:
                    # Direct tool schema format
                    tool_dict = tool

                # Sanitize tool schema
                sanitized_tool = MCPURLFilter.sanitize_tool_schema(tool_dict)

                input_schema = sanitized_tool.get("inputSchema", sanitized_tool.get("parameters", {}))
                # Ensure input_schema has required type field
                if "type" not in input_schema:
                    input_schema["type"] = "object"

                anthropic_tools.append({
                    "name": sanitized_tool.get("name", ""),
                    "description": sanitized_tool.get("description", ""),
                    "input_schema": input_schema
                })

            # Prepare Anthropic API request
            headers = {
                "Content-Type": "application/json",
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01"
            }

            messages = [
                {"role": "user", "content": prompt}
            ]

            api_request = {
                "model": self.model,
                "max_tokens": 1000,
                "messages": messages
            }

            if anthropic_tools:
                api_request["tools"] = anthropic_tools
                api_request["tool_choice"] = {"type": "auto"}

            # Final security check
            if not MCPURLFilter.validate_request_data(api_request):
                raise Exception("SECURITY VIOLATION: MCP URLs in final API request")

            # Make API call
            response = await self.client.post(
                f"{self.base_url}/v1/messages",
                json=api_request,
                headers=headers,
                timeout=timeout
            )

            if response.status_code != 200:
                raise Exception(f"Anthropic API error: {response.status_code} - {response.text}")

            result = response.json()

            # Extract response
            content = result.get("content", [])
            response_text = ""
            tool_calls = []

            for item in content:
                if item.get("type") == "text":
                    response_text += item.get("text", "")
                elif item.get("type") == "tool_use":
                    tool_calls.append({
                        "id": item.get("id", ""),
                        "name": item.get("name", ""),
                        "arguments": item.get("input", {})
                    })

            # Execute tool calls locally
            for tool_call in tool_calls:
                try:
                    tool_result = await self.tool_discovery.execute_tool_call(tool_call)
                    if not tool_result.is_error:
                        response_text += f"\n\nTool {tool_call['name']} executed successfully: {tool_result.content}"
                    else:
                        response_text += f"\n\nTool {tool_call['name']} failed: {tool_result.error_message}"
                except Exception as e:
                    response_text += f"\n\nTool {tool_call['name']} execution error: {e}"

            # Calculate usage and cost
            usage = result.get("usage", {})
            token_usage = {
                "prompt": usage.get("input_tokens", 0),
                "completion": usage.get("output_tokens", 0),
                "total": usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
            }

            # Estimate cost (Claude pricing)
            cost = (token_usage["prompt"] * 0.003 + token_usage["completion"] * 0.015) / 1000

            return LLMResult(
                response=response_text,
                tool_calls=tool_calls,
                token_usage=token_usage,
                cost=cost,
                duration=time.time() - start_time,
                raw_response=result
            )

        except Exception as e:
            return LLMResult(
                response=f"Error: {str(e)}",
                tool_calls=[],
                duration=time.time() - start_time
            )

    async def close(self):
        """Close connections."""
        await self.tool_discovery.close()
        await self.client.aclose()


class ClaudeCodeProvider(LLMProvider):
    """Claude Code CLI provider via subprocess."""

    def __init__(
        self,
        model: str,
        claude_cli_path: Optional[str] = None,
        mcp_url: str = "http://localhost:5008/mcp"
    ):
        self.model = model
        self.claude_cli_path = claude_cli_path or self._find_claude_cli()
        self.tool_discovery = ToolDiscoveryService(mcp_url)

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
            "claude"  # In PATH
        ]

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
                [self.claude_cli_path, "--version"],
                capture_output=True,
                timeout=10,
                text=True
            )
            if result.returncode != 0:
                raise Exception(f"Claude CLI error: {result.stderr}")
        except subprocess.TimeoutExpired:
            raise Exception("Claude CLI timeout during initialization")

        # Pre-discover tools
        await self.tool_discovery.discover_tools()

    async def generate_with_tools(
        self,
        prompt: str,
        tools: List[Dict[str, Any]],
        timeout: float = 30.0
    ) -> LLMResult:
        """Generate response using Claude Code CLI."""
        start_time = time.time()

        try:
            # Create tool-aware prompt template
            enhanced_prompt = self._create_tool_prompt(prompt, tools)

            # Execute Claude CLI
            process = await asyncio.create_subprocess_exec(
                self.claude_cli_path,
                "-p", enhanced_prompt,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                raise Exception(f"Claude CLI timeout after {timeout}s")

            if process.returncode != 0:
                raise Exception(f"Claude CLI error: {stderr.decode()}")

            response_text = stdout.decode().strip()

            # Parse tool calls from CLI output
            tool_calls = self._parse_tool_calls(response_text)

            # Execute tool calls locally
            for tool_call in tool_calls:
                try:
                    result = await self.tool_discovery.execute_tool_call(tool_call)
                    if not result.is_error:
                        response_text += f"\n\nTool {tool_call['name']} executed: {result.content}"
                    else:
                        response_text += f"\n\nTool {tool_call['name']} failed: {result.error_message}"
                except Exception as e:
                    response_text += f"\n\nTool execution error: {e}"

            return LLMResult(
                response=response_text,
                tool_calls=tool_calls,
                token_usage=None,  # CLI doesn't provide token counts
                cost=0.0,  # CLI usage varies by subscription
                duration=time.time() - start_time,
                raw_response={"stdout": response_text}
            )

        except Exception as e:
            return LLMResult(
                response=f"Error: {str(e)}",
                tool_calls=[],
                duration=time.time() - start_time
            )

    def _create_tool_prompt(self, prompt: str, tools: List[Dict[str, Any]]) -> str:
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

    def _parse_tool_calls(self, response: str) -> List[Dict[str, Any]]:
        """Parse tool calls from Claude CLI response."""
        tool_calls = []

        # Look for TOOL_CALL: patterns
        tool_call_pattern = r'TOOL_CALL:\s*(\{[^}]+\}|\{[^}]*\{[^}]*\}[^}]*\})'
        matches = re.findall(tool_call_pattern, response)

        for match in matches:
            try:
                call_data = json.loads(match)
                if "name" in call_data:
                    tool_calls.append({
                        "name": call_data["name"],
                        "arguments": call_data.get("arguments", {})
                    })
            except json.JSONDecodeError:
                continue

        return tool_calls

    async def close(self):
        """Close connections."""
        await self.tool_discovery.close()


# Factory function to create providers

def create_llm_provider(
    provider: str,
    model: str,
    **kwargs
) -> LLMProvider:
    """
    Create an LLM provider instance.

    Args:
        provider: Provider name (ollama, openai, local, anthropic, claude-cli)
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
        "claude-cli": ClaudeCodeProvider,
    }

    if provider not in providers:
        raise ValueError(f"Unknown provider: {provider}. Available: {list(providers.keys())}")

    provider_class = providers[provider]
    return provider_class(model=model, **kwargs)