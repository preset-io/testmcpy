"""
Test Execution Agent using Claude Agent SDK.

Provides an intelligent orchestrator that wraps testmcpy infrastructure
with reasoning, adaptability, and natural language interaction.

Note: Requires `claude-agent-sdk` package. Imports are lazy to avoid
crashing when the SDK is not installed.
"""

from testmcpy.agent.models import AgentRunReport, AgentSession, ToolInvocation


def __getattr__(name):
    if name == "TestExecutionAgent":
        from testmcpy.agent.orchestrator import TestExecutionAgent

        return TestExecutionAgent
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "TestExecutionAgent",
    "AgentRunReport",
    "AgentSession",
    "ToolInvocation",
]
