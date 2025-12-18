"""Core business logic modules shared between CLI, TUI, and web UI."""

from testmcpy.core.chat_session import ChatMessage, ChatSession, ToolCallExecution
from testmcpy.core.docs_optimizer import DocsOptimizer, OptimizationResult
from testmcpy.core.mcp_manager import ConnectionStatus, MCPManager
from testmcpy.core.tool_discovery import Prompt, Resource, Tool, ToolDiscovery

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
