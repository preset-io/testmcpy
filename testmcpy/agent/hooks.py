"""
Agent hooks for monitoring and controlling the Test Execution Agent.

Uses the Claude Agent SDK hook system (PreToolUse, PostToolUse, Stop)
to track tool calls, detect loops, measure costs, and generate reports.
"""

import time
from typing import Any

from testmcpy.agent.models import AgentSession, ToolInvocation

try:
    from claude_agent_sdk import HookContext
except ImportError:
    HookContext = Any  # type: ignore[assignment,misc]

# Maximum identical consecutive tool calls before blocking
MAX_IDENTICAL_CALLS = 3


def create_hooks(session: AgentSession) -> dict[str, list[dict[str, Any]]]:
    """Create all hooks wired to a shared AgentSession.

    Returns a hooks dict in the format expected by ClaudeAgentOptions:
        {
            "PreToolUse": [{"matcher": None, "hooks": [callback]}],
            "PostToolUse": [{"matcher": None, "hooks": [callback]}],
            "Stop": [{"matcher": None, "hooks": [callback]}],
        }
    """
    # Mutable state shared between hooks (not in session to keep session clean)
    _hook_state: dict[str, Any] = {
        "last_tool_name": None,
        "last_tool_args": None,
        "consecutive_identical": 0,
        "pending_start_times": {},  # tool_use_id -> start_time
    }

    async def pre_tool_use(
        input_data: dict[str, Any],
        tool_use_id: str | None,
        context: HookContext,
    ) -> dict[str, Any]:
        """Hook called before each tool use.

        - Detects loops (3+ identical consecutive calls)
        - Records start time for duration tracking
        """
        tool_name = input_data.get("name", "")
        tool_args = input_data.get("input", {})

        # Loop detection: track consecutive identical calls
        if (
            tool_name == _hook_state["last_tool_name"]
            and tool_args == _hook_state["last_tool_args"]
        ):
            _hook_state["consecutive_identical"] += 1
        else:
            _hook_state["consecutive_identical"] = 1

        _hook_state["last_tool_name"] = tool_name
        _hook_state["last_tool_args"] = tool_args

        # Block if too many identical calls in a row
        if _hook_state["consecutive_identical"] >= MAX_IDENTICAL_CALLS:
            session.record_error(
                f"Loop detected: {tool_name} called {MAX_IDENTICAL_CALLS}+ times "
                f"with identical arguments"
            )
            return {
                "decision": "block",
                "systemMessage": (
                    f"BLOCKED: You have called {tool_name} {MAX_IDENTICAL_CALLS} times "
                    f"in a row with identical arguments. This looks like a loop. "
                    f"Try a different approach or different arguments."
                ),
            }

        # Record start time for this tool use
        if tool_use_id:
            _hook_state["pending_start_times"][tool_use_id] = time.time()

        return {}

    async def post_tool_use(
        input_data: dict[str, Any],
        tool_use_id: str | None,
        context: HookContext,
    ) -> dict[str, Any]:
        """Hook called after each tool use.

        - Records tool invocation with timing
        - Tracks test results for execute_test_case
        - Accumulates costs and tokens
        """
        tool_name = input_data.get("name", "")
        tool_input = input_data.get("input", {})
        tool_result = input_data.get("result", "")

        # Calculate duration
        duration_ms = 0.0
        if tool_use_id and tool_use_id in _hook_state["pending_start_times"]:
            start = _hook_state["pending_start_times"].pop(tool_use_id)
            duration_ms = (time.time() - start) * 1000

        # Determine if there was an error
        is_error = False
        result_summary = ""
        if isinstance(tool_result, str):
            result_summary = tool_result[:200]
            is_error = tool_result.startswith("Error:")
        elif isinstance(tool_result, dict):
            is_error = tool_result.get("is_error", False)
            content = tool_result.get("content", [])
            if content and isinstance(content, list) and len(content) > 0:
                first = content[0]
                if isinstance(first, dict):
                    result_summary = first.get("text", "")[:200]

        # Record the invocation
        invocation = ToolInvocation(
            tool_name=tool_name,
            arguments=tool_input,
            result_summary=result_summary,
            is_error=is_error,
            duration_ms=duration_ms,
        )
        session.record_tool_call(invocation)

        # Track test results if this was execute_test_case
        if tool_name == "execute_test_case" and not is_error:
            try:
                import json

                # Parse the result to extract pass/fail
                if isinstance(tool_result, str) and not tool_result.startswith("Error:"):
                    parsed = json.loads(tool_result)
                    if "passed" in parsed:
                        session.record_test_result(parsed["passed"])
                        # Track test execution cost separately
                        if "cost" in parsed:
                            session.test_execution_cost_usd += parsed.get("cost", 0.0)
                        if "token_usage" in parsed and parsed["token_usage"]:
                            tokens = parsed["token_usage"]
                            session.test_execution_tokens += tokens.get("total", 0)
            except (json.JSONDecodeError, KeyError, TypeError):
                pass

        if is_error:
            session.record_error(f"Tool {tool_name} returned error: {result_summary}")

        return {}

    async def stop_hook(
        input_data: dict[str, Any],
        tool_use_id: str | None,
        context: HookContext,
    ) -> dict[str, Any]:
        """Hook called when the agent stops.

        Finalizes the session and generates the run report.
        """
        session.complete()

        # Extract orchestrator cost from the result message if available
        result = input_data.get("result", {})
        if isinstance(result, dict):
            total_cost = result.get("total_cost_usd", 0.0)
            if total_cost:
                session.orchestrator_cost_usd = total_cost - session.test_execution_cost_usd

            usage = result.get("usage", {})
            if usage:
                session.orchestrator_tokens_input = usage.get("input_tokens", 0)
                session.orchestrator_tokens_output = usage.get("output_tokens", 0)

        return {}

    return {
        "PreToolUse": [{"matcher": None, "hooks": [pre_tool_use]}],
        "PostToolUse": [{"matcher": None, "hooks": [post_tool_use]}],
        "Stop": [{"matcher": None, "hooks": [stop_hook]}],
    }
