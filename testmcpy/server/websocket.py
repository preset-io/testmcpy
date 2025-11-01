"""
WebSocket support for streaming chat responses.
"""

import asyncio

from fastapi import WebSocket, WebSocketDisconnect

from testmcpy.config import get_config
from testmcpy.src.llm_integration import create_llm_provider
from testmcpy.src.mcp_client import MCPClient, MCPToolCall


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

                            # Execute tool
                            mcp_tool_call = MCPToolCall(
                                name=tool_call["name"],
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
