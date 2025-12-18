"""
WebSocket support for streaming chat responses and test execution.
"""

import asyncio
import time
from pathlib import Path

import yaml
from fastapi import WebSocket, WebSocketDisconnect

from testmcpy.config import get_config
from testmcpy.server.state import get_or_create_mcp_client
from testmcpy.src.llm_integration import create_llm_provider
from testmcpy.src.mcp_client import MCPClient, MCPToolCall
from testmcpy.src.test_runner import TestCase, TestRunner


def strip_mcp_prefix(tool_name: str) -> str:
    """Strip MCP namespace prefix from tool name.

    LLM providers may return tool names like 'mcp__testmcpy__list_charts'
    but the MCP server expects just 'list_charts'.
    """
    if "__" in tool_name:
        # Get the last part after the final __
        return tool_name.rsplit("__", 1)[-1]
    return tool_name


class ConnectionManager:
    """Manage WebSocket connections."""

    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def send_message(self, message: dict, websocket: WebSocket):
        await websocket.send_json(message)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            await connection.send_json(message)


manager = ConnectionManager()


async def handle_chat_websocket(websocket: WebSocket, mcp_client: MCPClient):
    """
    Handle WebSocket chat connections with streaming responses.

    Message format from client:
    {
        "type": "chat",
        "message": "user message",
        "model": "claude-haiku-4-5",
        "provider": "anthropic"
    }

    Message format to client:
    {
        "type": "start" | "token" | "tool_call" | "tool_result" | "complete" | "error",
        "content": "...",
        "tool_name": "...",  # for tool_call
        "tool_args": {...},  # for tool_call
        "tool_result": {...},  # for tool_result
        "token_usage": {...},  # for complete
        "cost": 0.0,  # for complete
        "duration": 0.0  # for complete
    }
    """
    await manager.connect(websocket)
    config = get_config()

    try:
        while True:
            # Receive message from client
            data = await websocket.receive_json()

            if data.get("type") == "chat":
                message = data.get("message", "")
                model = data.get("model") or config.default_model
                provider = data.get("provider") or config.default_provider

                # Send start message
                await manager.send_message(
                    {"type": "start", "content": "Processing your request..."}, websocket
                )

                try:
                    # Get available tools
                    tools = await mcp_client.list_tools()
                    formatted_tools = [
                        {
                            "type": "function",
                            "function": {
                                "name": tool.name,
                                "description": tool.description,
                                "parameters": tool.input_schema,
                            },
                        }
                        for tool in tools
                    ]

                    # Initialize LLM provider
                    llm_provider = create_llm_provider(provider, model)
                    await llm_provider.initialize()

                    # Generate response
                    result = await llm_provider.generate_with_tools(
                        prompt=message, tools=formatted_tools, timeout=30.0
                    )

                    # Stream the response text token by token for better UX
                    response_text = result.response
                    chunk_size = 50  # Characters per chunk
                    for i in range(0, len(response_text), chunk_size):
                        chunk = response_text[i : i + chunk_size]
                        await manager.send_message({"type": "token", "content": chunk}, websocket)
                        await asyncio.sleep(0.05)  # Small delay for streaming effect

                    # Execute tool calls if any
                    if result.tool_calls:
                        for tool_call in result.tool_calls:
                            # Send tool call notification
                            await manager.send_message(
                                {
                                    "type": "tool_call",
                                    "tool_name": tool_call["name"],
                                    "tool_args": tool_call.get("arguments", {}),
                                },
                                websocket,
                            )

                            # Execute tool - strip MCP prefix if present
                            actual_tool_name = strip_mcp_prefix(tool_call["name"])
                            mcp_tool_call = MCPToolCall(
                                name=actual_tool_name,
                                arguments=tool_call.get("arguments", {}),
                                id=tool_call.get("id", "unknown"),
                            )
                            tool_result = await mcp_client.call_tool(mcp_tool_call)

                            # Send tool result
                            await manager.send_message(
                                {
                                    "type": "tool_result",
                                    "tool_name": tool_call["name"],
                                    "tool_result": {
                                        "content": tool_result.content,
                                        "is_error": tool_result.is_error,
                                        "error_message": tool_result.error_message,
                                    },
                                },
                                websocket,
                            )

                    # Send completion message
                    await manager.send_message(
                        {
                            "type": "complete",
                            "token_usage": result.token_usage,
                            "cost": result.cost,
                            "duration": result.duration,
                        },
                        websocket,
                    )

                    await llm_provider.close()

                except Exception as e:
                    await manager.send_message({"type": "error", "content": str(e)}, websocket)

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        print(f"WebSocket error: {e}")
        manager.disconnect(websocket)


async def handle_test_websocket(websocket: WebSocket):
    """
    Handle WebSocket for streaming test execution with real-time logs.

    Message format from client:
    {
        "type": "run_test",
        "test_path": "/path/to/test.yaml",
        "test_name": "optional_specific_test",
        "model": "claude-sonnet-4-20250514",
        "provider": "claude-cli",
        "profile": "mcp_profile_id"
    }

    Message format to client:
    {
        "type": "log" | "test_start" | "test_complete" | "all_complete" | "error",
        "message": "...",
        "test_name": "...",
        "result": {...}
    }
    """
    await manager.connect(websocket)
    config = get_config()

    async def send_log(msg: str):
        """Send a log message to the client."""
        await manager.send_message({"type": "log", "message": msg}, websocket)

    try:
        while True:
            data = await websocket.receive_json()

            if data.get("type") == "run_test":
                test_path = Path(data.get("test_path", ""))
                test_name = data.get("test_name")
                model = data.get("model") or config.default_model
                provider = data.get("provider") or config.default_provider
                profile = data.get("profile")

                if not test_path.exists():
                    await manager.send_message(
                        {"type": "error", "message": f"Test file not found: {test_path}"},
                        websocket,
                    )
                    continue

                await send_log(f"📁 Loading test file: {test_path}")

                try:
                    # Load test cases
                    with open(test_path) as f:
                        file_data = yaml.safe_load(f)

                    test_cases = []
                    if "tests" in file_data:
                        for test_data in file_data["tests"]:
                            test_cases.append(TestCase.from_dict(test_data))
                    else:
                        test_cases.append(TestCase.from_dict(file_data))

                    # Filter to specific test if requested
                    if test_name:
                        test_cases = [tc for tc in test_cases if tc.name == test_name]
                        if not test_cases:
                            await manager.send_message(
                                {"type": "error", "message": f"Test '{test_name}' not found"},
                                websocket,
                            )
                            continue

                    await send_log(f"📋 Found {len(test_cases)} test(s) to run")
                    await send_log(f"🤖 Provider: {provider}, Model: {model}")

                    # Get MCP client - use profile or default
                    mcp_client = None
                    effective_profile = profile
                    if not effective_profile:
                        # Try to get default profile from config
                        from testmcpy.server.helpers.mcp_config import load_mcp_yaml

                        mcp_config = load_mcp_yaml()
                        effective_profile = mcp_config.get("default")
                        if effective_profile:
                            await send_log(f"🔌 Using default MCP profile: {effective_profile}")

                    if effective_profile:
                        await send_log(f"🔌 Loading MCP profile: {effective_profile}")
                        mcp_client = await get_or_create_mcp_client(effective_profile)

                    # Create runner with streaming log callback
                    runner = TestRunner(
                        model=model,
                        provider=provider,
                        mcp_url=config.get_mcp_url(),
                        mcp_client=mcp_client,
                        verbose=True,
                        hide_tool_output=False,
                        log_callback=send_log,
                    )

                    await send_log("⚙️ Initializing test runner...")
                    await runner.initialize()
                    await send_log("✅ Test runner ready")

                    # Run each test one at a time
                    all_results = []
                    for i, tc in enumerate(test_cases):
                        await manager.send_message(
                            {
                                "type": "test_start",
                                "test_name": tc.name,
                                "index": i,
                                "total": len(test_cases),
                            },
                            websocket,
                        )

                        await send_log(f"\n{'=' * 50}")
                        await send_log(f"🧪 Running test {i + 1}/{len(test_cases)}: {tc.name}")
                        await send_log(f"📝 Prompt: {tc.prompt[:100]}...")
                        await send_log(f"⏱️ Timeout: {tc.timeout}s")

                        start_time = time.time()
                        result = await runner.run_test(tc)
                        elapsed = time.time() - start_time

                        # Send logs from the result
                        if hasattr(result, "logs") and result.logs:
                            for log_line in result.logs:
                                await send_log(log_line)

                        # Send test result
                        status = "✅ PASSED" if result.passed else "❌ FAILED"
                        await send_log(f"{status} in {elapsed:.2f}s")

                        if result.tool_calls:
                            await send_log(f"🔧 Tool calls: {len(result.tool_calls)}")
                            for tc_call in result.tool_calls:
                                await send_log(f"   - {tc_call.get('name', 'unknown')}")

                        if result.error:
                            await send_log(f"⚠️ Error: {result.error}")

                        await manager.send_message(
                            {
                                "type": "test_complete",
                                "test_name": tc.name,
                                "result": result.to_dict(),
                            },
                            websocket,
                        )

                        all_results.append(result)

                    # Send final summary
                    passed = sum(1 for r in all_results if r.passed)
                    failed = len(all_results) - passed
                    total_cost = sum(r.cost for r in all_results)

                    await send_log(f"\n{'=' * 50}")
                    await send_log(f"📊 SUMMARY: {passed} passed, {failed} failed")
                    if total_cost > 0:
                        await send_log(f"💰 Total cost: ${total_cost:.4f}")

                    results_list = [r.to_dict() for r in all_results]
                    summary = {
                        "total": len(all_results),
                        "passed": passed,
                        "failed": failed,
                        "total_cost": total_cost,
                    }

                    # Save results to history
                    try:
                        from testmcpy.server.routers.results import save_test_run_to_file

                        # Get relative path from tests directory if possible
                        tests_dir = Path.cwd() / "tests"
                        if test_path.is_relative_to(tests_dir):
                            test_file_name = str(test_path.relative_to(tests_dir))
                        else:
                            test_file_name = test_path.name

                        save_data = {
                            "test_file": test_file_name,
                            "test_file_path": str(test_path),
                            "provider": provider,
                            "model": model,
                            "mcp_profile": effective_profile,
                            "results": results_list,
                            "summary": summary,
                        }
                        save_result = save_test_run_to_file(save_data)
                        await send_log(f"💾 Results saved: {save_result.get('run_id')}")
                    except Exception as save_err:
                        await send_log(f"⚠️ Failed to save results: {save_err}")

                    await manager.send_message(
                        {
                            "type": "all_complete",
                            "summary": summary,
                            "results": results_list,
                        },
                        websocket,
                    )

                except Exception as e:
                    import traceback

                    tb = traceback.format_exc()
                    await send_log(f"❌ Error: {str(e)}")
                    await send_log(f"Traceback:\n{tb}")
                    await manager.send_message(
                        {"type": "error", "message": str(e), "traceback": tb},
                        websocket,
                    )

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        print(f"Test WebSocket error: {e}")
        manager.disconnect(websocket)
