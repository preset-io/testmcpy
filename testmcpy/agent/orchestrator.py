"""
Test Execution Agent orchestrator.

Main entry point for creating and running the agent. Wires together
tools, hooks, prompts, and the Claude Agent SDK.
"""

import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any

from testmcpy.agent.hooks import create_hooks
from testmcpy.agent.models import AgentRunReport, AgentSession
from testmcpy.agent.prompts import build_context_prompt
from testmcpy.agent.tools import ALL_TOOLS, set_tool_context

try:
    from claude_agent_sdk import (
        AssistantMessage,
        ClaudeAgentOptions,
        ClaudeSDKClient,
        ResultMessage,
        TextBlock,
        create_sdk_mcp_server,
        query,
    )

    _HAS_SDK = True
except ImportError:
    _HAS_SDK = False


class TestExecutionAgent:
    """Intelligent test execution agent powered by Claude Agent SDK.

    Orchestrates testmcpy infrastructure through custom @tool functions,
    providing reasoning, adaptability, and natural language interaction.
    """

    def __init__(
        self,
        mcp_profile: str | None = None,
        mcp_url: str | None = None,
        auth_config: dict[str, Any] | None = None,
        models: list[str] | None = None,
        storage_path: str | None = None,
        max_turns: int = 50,
        agent_model: str | None = None,
    ):
        """Initialize the agent.

        Args:
            mcp_profile: MCP service profile name
            mcp_url: Direct MCP service URL (overrides profile)
            auth_config: Authentication config dict
            models: List of model names available for testing
            storage_path: Path to SQLite storage database
            max_turns: Maximum agent turns (default 50)
            agent_model: Model for the agent itself (default: SDK default)
        """
        if not _HAS_SDK:
            raise ImportError(
                "claude_agent_sdk is required for the Test Execution Agent. "
                "Install with: pip install testmcpy[sdk]"
            )

        self.mcp_profile = mcp_profile
        self.mcp_url = mcp_url
        self.auth_config = auth_config
        self.models = models or []
        self.storage_path = storage_path
        self.max_turns = max_turns
        self.agent_model = agent_model

        # Configure shared tool context
        set_tool_context(
            mcp_profile=mcp_profile,
            mcp_url=mcp_url,
            auth_config=auth_config,
            storage_path=storage_path,
        )

    def _build_options(self, session: AgentSession) -> ClaudeAgentOptions:
        """Build ClaudeAgentOptions with tools, hooks, and configuration."""
        # Create in-process MCP server with our custom tools
        mcp_server = create_sdk_mcp_server(
            name="testmcpy-agent-tools",
            version="1.0.0",
            tools=ALL_TOOLS,
        )

        # Build system prompt with context
        system_prompt = build_context_prompt(
            mcp_profile=self.mcp_profile,
            models=self.models,
        )

        # Create hooks wired to the session
        hooks = create_hooks(session)

        options = ClaudeAgentOptions(
            system_prompt=system_prompt,
            permission_mode="bypassPermissions",
            max_turns=self.max_turns,
            mcp_servers={"testmcpy-agent-tools": mcp_server},
            hooks=hooks,
        )

        if self.agent_model:
            options.model = self.agent_model

        return options

    async def run(self, prompt: str) -> AgentRunReport:
        """Execute a one-shot agent run.

        The agent processes the prompt, uses tools as needed, and returns
        a structured report of what it did.

        Args:
            prompt: Natural language instruction (e.g., "Run all tests in tests/example.yaml")

        Returns:
            AgentRunReport with test results, costs, and analysis
        """
        run_id = (
            f"agent_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
        )
        session = AgentSession()
        options = self._build_options(session)

        # Collect the agent's text output for analysis
        analysis_parts = []
        num_turns = 0

        async for message in query(prompt=prompt, options=options):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        analysis_parts.append(block.text)

            if isinstance(message, ResultMessage):
                num_turns = message.num_turns
                # Extract cost info from result
                if message.total_cost_usd is not None:
                    session.orchestrator_cost_usd = max(
                        0.0,
                        message.total_cost_usd - session.test_execution_cost_usd,
                    )
                if message.usage:
                    session.orchestrator_tokens_input = message.usage.get("input_tokens", 0)
                    session.orchestrator_tokens_output = message.usage.get("output_tokens", 0)

        # Build report
        report = AgentRunReport.from_session(session, run_id=run_id)
        report.analysis = "\n".join(analysis_parts)
        report.num_turns = num_turns

        return report

    async def chat(self, prompt: str) -> AsyncIterator[dict[str, Any]]:
        """Start an interactive chat session.

        Yields message dicts as they arrive from the agent.
        Suitable for streaming to a web UI or CLI.

        Args:
            prompt: Initial prompt to start the conversation

        Yields:
            Dicts with keys: type (text|tool_use|tool_result|result), content
        """
        session = AgentSession()
        options = self._build_options(session)

        async with ClaudeSDKClient(options=options) as client:
            await client.query(prompt)

            async for message in client.receive_response():
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            yield {"type": "text", "content": block.text}

                elif isinstance(message, ResultMessage):
                    report = AgentRunReport.from_session(session)
                    report.num_turns = message.num_turns
                    if message.total_cost_usd is not None:
                        report.orchestrator_cost_usd = max(
                            0.0,
                            message.total_cost_usd - session.test_execution_cost_usd,
                        )
                        report.total_cost_usd = message.total_cost_usd
                    yield {"type": "result", "content": report.to_dict()}
