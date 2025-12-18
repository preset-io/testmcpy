"""Core business logic modules shared between CLI, TUI, and web UI."""

from testmcpy.core.mcp_manager import MCPManager, ConnectionStatus
from testmcpy.core.tool_discovery import ToolDiscovery, Tool, Resource, Prompt
from testmcpy.core.chat_session import ChatSession, ChatMessage, ToolCallExecution
from testmcpy.core.docs_optimizer import DocsOptimizer, OptimizationResult

__all__ = [
    "MCPManager",
    "ConnectionStatus",
    "ToolDiscovery",
    "Tool",
    "Resource",
    "Prompt",
    "ChatSession",
    "ChatMessage",
    "ToolCallExecution",
    "DocsOptimizer",
    "OptimizationResult",
]
