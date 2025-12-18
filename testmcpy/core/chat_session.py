"""
Chat Session Management.

Handles chat interactions with LLMs including tool calling, history management,
and test generation. Provides core business logic independent of UI layer.
"""

import time
from dataclasses import dataclass, field
from typing import Any

from testmcpy.config import get_config
from testmcpy.src.llm_integration import LLMProvider, LLMResult, create_llm_provider
from testmcpy.src.mcp_client import MCPClient, MCPToolCall


@dataclass
class ToolCallExecution:
    """Represents a single tool call execution."""

    tool_name: str
    arguments: dict[str, Any]
    start_time: float
    end_time: float | None = None
    success: bool = False
    result: Any = None
    error: str | None = None

    @property
    def duration(self) -> float:
        """Get execution duration in seconds."""
        if self.end_time is None:
            return time.time() - self.start_time
        return self.end_time - self.start_time

    @property
    def status_emoji(self) -> str:
        """Get status emoji for display."""
        if self.end_time is None:
            return "⏳"
        return "✓" if self.success else "✗"


@dataclass
class ChatMessage:
    """Represents a single message in the chat."""

    role: str  # "user", "assistant", "system"
    content: str
    timestamp: float = field(default_factory=time.time)
    tool_calls: list[ToolCallExecution] = field(default_factory=list)
    cost: float = 0.0
    token_usage: dict[str, int] | None = None


class ChatSession:
    """
    Manages an interactive chat session with LLM and MCP tools.

    This class handles:
    - Message history
    - LLM provider integration
    - MCP tool execution
    - Cost tracking
    - Session state
    """

    def __init__(
        self,
        profile: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        mcp_url: str | None = None,
    ):
        """
        Initialize chat session.

        Args:
            profile: MCP profile ID (optional)
            provider: LLM provider (anthropic, openai, ollama, etc.)
            model: Model name
            mcp_url: MCP service URL
        """
        self.config = get_config()
        self.profile = profile
        self.messages: list[ChatMessage] = []
        self.total_cost = 0.0
        self.total_tokens = 0

        # LLM provider setup
        self.provider_name = provider or self.config.default_provider or "anthropic"
        self.model = model or self.config.default_model or "claude-haiku-4-5"
        # Get MCP URL from profile if available
        if not mcp_url:
            default_mcp = self.config.get_default_mcp_server()
            if default_mcp:
                mcp_url = default_mcp.mcp_url
        self.mcp_url = mcp_url

        # Initialize clients (will be done in async initialize)
        self.llm_provider: LLMProvider | None = None
        self.mcp_client: MCPClient | None = None
        self._tools: list[dict[str, Any]] = []
        self._initialized = False

    async def initialize(self):
        """Initialize LLM provider and MCP client."""
        if self._initialized:
            return

        # Initialize LLM provider
        self.llm_provider = create_llm_provider(
            self.provider_name, self.model, mcp_url=self.mcp_url
        )
        await self.llm_provider.initialize()

        # Initialize MCP client
        self.mcp_client = MCPClient(self.mcp_url)
        await self.mcp_client.initialize()

        # Discover available tools
        mcp_tools = await self.mcp_client.list_tools()

        # Convert to LLM tool format
        self._tools = []
        for tool in mcp_tools:
            self._tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.input_schema,
                    },
                }
            )

        self._initialized = True

    async def send_message(self, message: str) -> ChatMessage:
        """
        Send a message and get response from LLM.

        Args:
            message: User message text

        Returns:
            Assistant's response message with tool calls
        """
        if not self._initialized:
            await self.initialize()

        # Add user message to history
        user_msg = ChatMessage(role="user", content=message)
        self.messages.append(user_msg)

        # Prepare message history for LLM (exclude tool calls for simplicity)
        message_history = [
            {"role": msg.role, "content": msg.content}
            for msg in self.messages
            if msg.content  # Filter out empty messages
        ]

        # Get LLM response with tool calling
        result: LLMResult = await self.llm_provider.generate_with_tools(
            prompt=message, tools=self._tools, messages=message_history, timeout=60.0
        )

        # Process tool calls if any
        tool_executions = []
        if result.tool_calls:
            for tool_call in result.tool_calls:
                execution = await self._execute_tool_call(tool_call)
                tool_executions.append(execution)

        # Create assistant message
        assistant_msg = ChatMessage(
            role="assistant",
            content=result.response,
            tool_calls=tool_executions,
            cost=result.cost,
            token_usage=result.token_usage,
        )
        self.messages.append(assistant_msg)

        # Update session totals
        self.total_cost += result.cost
        if result.token_usage:
            self.total_tokens += result.token_usage.get("total", 0)

        return assistant_msg

    async def _execute_tool_call(self, tool_call: dict[str, Any]) -> ToolCallExecution:
        """Execute a tool call via MCP client."""
        execution = ToolCallExecution(
            tool_name=tool_call["name"],
            arguments=tool_call.get("arguments", {}),
            start_time=time.time(),
        )

        try:
            # Execute via MCP
            mcp_call = MCPToolCall(
                name=tool_call["name"],
                arguments=tool_call.get("arguments", {}),
                id=tool_call.get("id", f"call_{int(time.time())}"),
            )

            result = await self.mcp_client.call_tool(mcp_call)

            execution.end_time = time.time()
            execution.success = not result.is_error
            execution.result = result.content
            execution.error = result.error_message if result.is_error else None

        except Exception as e:
            execution.end_time = time.time()
            execution.success = False
            execution.error = str(e)

        return execution

    async def evaluate_conversation(self, evaluators: list[str] | None = None) -> dict[str, Any]:
        """
        Evaluate the conversation using specified evaluators.

        Args:
            evaluators: List of evaluator names to run (default: all)

        Returns:
            Dictionary with evaluation results
        """
        # This would integrate with the existing evaluator system
        # For now, return a placeholder
        results = {
            "passed": [],
            "failed": [],
            "scores": {},
            "details": {},
        }

        # TODO: Integrate with testmcpy.evals.base_evaluators
        # For each evaluator:
        #   - Check if tool calls match expected patterns
        #   - Validate responses
        #   - Calculate scores

        return results

    async def save_as_test(self, filepath: str, test_name: str | None = None) -> str:
        """
        Save the conversation as a test file.

        Args:
            filepath: Path to save test file
            test_name: Optional test name (default: derived from first message)

        Returns:
            Path to created test file
        """
        from pathlib import Path

        import yaml

        if not self.messages:
            raise ValueError("No messages to save")

        # Get first user message as prompt
        user_messages = [msg for msg in self.messages if msg.role == "user"]
        if not user_messages:
            raise ValueError("No user messages found")

        prompt = user_messages[0].content

        # Extract tool calls
        all_tool_calls = []
        for msg in self.messages:
            if msg.role == "assistant" and msg.tool_calls:
                for tc in msg.tool_calls:
                    all_tool_calls.append(
                        {
                            "tool": tc.tool_name,
                            "arguments": tc.arguments,
                            "success": tc.success,
                        }
                    )

        # Build test YAML
        test_data = {
            "name": test_name or f"test_{int(time.time())}",
            "prompt": prompt,
            "model": self.model,
            "provider": self.provider_name,
            "expected_tool_calls": [
                {"tool": tc["tool"], "arguments": tc["arguments"]} for tc in all_tool_calls
            ],
            "evaluators": [
                {"type": "was_mcp_tool_called", "params": {}},
                {"type": "execution_successful", "params": {}},
            ],
            "metadata": {
                "created_from_chat": True,
                "timestamp": time.time(),
                "total_cost": self.total_cost,
                "message_count": len(self.messages),
            },
        }

        # Write to file
        filepath_obj = Path(filepath)
        filepath_obj.parent.mkdir(parents=True, exist_ok=True)

        with open(filepath_obj, "w") as f:
            yaml.dump(test_data, f, default_flow_style=False, sort_keys=False)

        return str(filepath_obj)

    async def close(self):
        """Clean up resources."""
        if self.llm_provider:
            await self.llm_provider.close()
        if self.mcp_client:
            await self.mcp_client.close()

    def get_message_count(self) -> int:
        """Get total message count."""
        return len(self.messages)

    def get_user_message_count(self) -> int:
        """Get user message count."""
        return len([msg for msg in self.messages if msg.role == "user"])

    def get_assistant_message_count(self) -> int:
        """Get assistant message count."""
        return len([msg for msg in self.messages if msg.role == "assistant"])

    def get_tool_call_count(self) -> int:
        """Get total tool call count."""
        return sum(len(msg.tool_calls) for msg in self.messages if msg.role == "assistant")

    def clear_history(self):
        """Clear message history and reset session."""
        self.messages.clear()
        self.total_cost = 0.0
        self.total_tokens = 0

    def export_conversation(self, format: str = "json") -> str:
        """
        Export conversation to string format.

        Args:
            format: Output format (json or yaml)

        Returns:
            Serialized conversation
        """
        import json

        import yaml

        data = {
            "profile": self.profile,
            "provider": self.provider_name,
            "model": self.model,
            "total_cost": self.total_cost,
            "total_tokens": self.total_tokens,
            "messages": [
                {
                    "role": msg.role,
                    "content": msg.content,
                    "timestamp": msg.timestamp,
                    "tool_calls": [
                        {
                            "tool_name": tc.tool_name,
                            "arguments": tc.arguments,
                            "duration": tc.duration,
                            "success": tc.success,
                            "result": tc.result,
                            "error": tc.error,
                        }
                        for tc in msg.tool_calls
                    ],
                    "cost": msg.cost,
                    "token_usage": msg.token_usage,
                }
                for msg in self.messages
            ],
        }

        if format == "yaml":
            return yaml.dump(data, default_flow_style=False, sort_keys=False)
        else:
            return json.dumps(data, indent=2)
