"""
Chat API router with streaming support.
"""

import asyncio
import json
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from testmcpy.server.models import ChatRequest, ChatResponse
from testmcpy.server.state import (
    TimeoutConfig,
    config,
    get_mcp_client_for_server,
    get_mcp_clients_for_profile,
)
from testmcpy.src.llm_integration import create_llm_provider
from testmcpy.src.mcp_client import MCPToolCall

router = APIRouter(prefix="/api", tags=["chat"])


async def stream_chat_response(
    request: ChatRequest,
    model: str,
    provider: str,
) -> AsyncGenerator[str, None]:
    """
    Stream chat responses using Server-Sent Events.

    Yields SSE-formatted events:
    - event: token - Individual tokens from LLM
    - event: tool_call - Tool call initiated
    - event: tool_result - Tool call completed
    - event: done - Stream complete with final metadata
    - event: error - Error occurred
    """
    try:
        # Determine which MCP clients to use
        clients_to_use = []
        if request.profiles:
            for server_id in request.profiles:
                if ":" in server_id:
                    profile_id, mcp_name = server_id.split(":", 1)
                    client = await get_mcp_client_for_server(profile_id, mcp_name)
                    if client:
                        clients_to_use.append((profile_id, mcp_name, client))
                else:
                    profile_clients = await get_mcp_clients_for_profile(server_id)
                    for mcp_name, client in profile_clients:
                        clients_to_use.append((server_id, mcp_name, client))

        # Gather tools from all clients
        all_tools = []
        tool_to_client = {}

        for profile_id, mcp_name, client in clients_to_use:
            tools = await client.list_tools()
            for tool in tools:
                tool_to_client[tool.name] = (client, profile_id, mcp_name)
                all_tools.append(
                    {
                        "type": "function",
                        "function": {
                            "name": tool.name,
                            "description": tool.description,
                            "parameters": tool.input_schema,
                        },
                    }
                )

        # Initialize LLM provider
        llm_provider = create_llm_provider(provider, model)
        await llm_provider.initialize()

        # Emit start event
        yield f"event: start\ndata: {json.dumps({'model': model, 'provider': provider})}\n\n"

        # Generate response with streaming if supported
        # For now, we'll simulate streaming by yielding the full response
        # TODO: Implement actual token-by-token streaming when LLM providers support it
        result = await llm_provider.generate_with_tools(
            prompt=request.message,
            tools=all_tools,
            timeout=TimeoutConfig.LLM_REQUEST,
            messages=request.history,
        )

        # Stream response text in chunks
        response_text = result.response
        chunk_size = 20  # Characters per chunk for smoother streaming
        for i in range(0, len(response_text), chunk_size):
            chunk = response_text[i : i + chunk_size]
            yield f"event: token\ndata: {json.dumps({'content': chunk})}\n\n"
            await asyncio.sleep(0.01)  # Small delay for smoother streaming

        # Execute tool calls if any
        tool_calls_with_results = []
        if result.tool_calls:
            for tool_call in result.tool_calls:
                # Emit tool call event
                yield f"event: tool_call\ndata: {json.dumps({'name': tool_call['name'], 'arguments': tool_call.get('arguments', {})})}\n\n"

                mcp_tool_call = MCPToolCall(
                    name=tool_call["name"],
                    arguments=tool_call.get("arguments", {}),
                    id=tool_call.get("id", "unknown"),
                )

                tool_info = tool_to_client.get(tool_call["name"])
                if not tool_info:
                    tool_call_with_result = {
                        "name": tool_call["name"],
                        "arguments": tool_call.get("arguments", {}),
                        "id": tool_call.get("id", "unknown"),
                        "result": None,
                        "error": f"Tool '{tool_call['name']}' not found in any MCP profile",
                        "is_error": True,
                    }
                    yield f"event: tool_result\ndata: {json.dumps(tool_call_with_result)}\n\n"
                    tool_calls_with_results.append(tool_call_with_result)
                    continue

                client_for_tool, profile_id, mcp_name = tool_info
                tool_result = await client_for_tool.call_tool(mcp_tool_call)

                tool_call_with_result = {
                    "name": tool_call["name"],
                    "arguments": tool_call.get("arguments", {}),
                    "id": tool_call.get("id", "unknown"),
                    "result": tool_result.content if not tool_result.is_error else None,
                    "error": tool_result.error_message if tool_result.is_error else None,
                    "is_error": tool_result.is_error,
                }
                yield f"event: tool_result\ndata: {json.dumps(tool_call_with_result)}\n\n"
                tool_calls_with_results.append(tool_call_with_result)

        await llm_provider.close()

        # Emit done event with metadata
        done_data = {
            "token_usage": result.token_usage,
            "cost": result.cost,
            "duration": result.duration,
            "tool_calls": tool_calls_with_results,
        }
        yield f"event: done\ndata: {json.dumps(done_data)}\n\n"

    except Exception as e:
        yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"


@router.post("/chat")
async def chat(request: ChatRequest):
    """
    Send a message to the LLM with MCP tools.

    If stream=true, returns a streaming response with Server-Sent Events.
    Otherwise, returns a standard JSON response.
    """
    # Get model and provider from LLM profile if specified
    if request.llm_profile:
        from testmcpy.llm_profiles import load_llm_profile

        llm_profile = load_llm_profile(request.llm_profile)
        if llm_profile:
            default_provider_config = llm_profile.get_default_provider()
            if default_provider_config:
                model = request.model or default_provider_config.model
                provider = request.provider or default_provider_config.provider
            else:
                model = request.model or config.default_model
                provider = request.provider or config.default_provider
        else:
            model = request.model or config.default_model
            provider = request.provider or config.default_provider
    else:
        model = request.model or config.default_model
        provider = request.provider or config.default_provider

    if not model or not provider:
        raise HTTPException(
            status_code=400,
            detail="Model and provider must be specified or configured in LLM profile",
        )

    # Handle streaming response
    if request.stream:
        return StreamingResponse(
            stream_chat_response(request, model, provider),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # Disable nginx buffering
            },
        )

    # Non-streaming response (original behavior)
    try:
        clients_to_use = []
        if request.profiles:
            for server_id in request.profiles:
                if ":" in server_id:
                    profile_id, mcp_name = server_id.split(":", 1)
                    client = await get_mcp_client_for_server(profile_id, mcp_name)
                    if client:
                        clients_to_use.append((profile_id, mcp_name, client))
                else:
                    profile_clients = await get_mcp_clients_for_profile(server_id)
                    for mcp_name, client in profile_clients:
                        clients_to_use.append((server_id, mcp_name, client))

        all_tools = []
        tool_to_client = {}

        for profile_id, mcp_name, client in clients_to_use:
            tools = await client.list_tools()
            for tool in tools:
                tool_to_client[tool.name] = (client, profile_id, mcp_name)
                all_tools.append(
                    {
                        "type": "function",
                        "function": {
                            "name": tool.name,
                            "description": tool.description,
                            "parameters": tool.input_schema,
                        },
                    }
                )

        llm_provider = create_llm_provider(provider, model)
        await llm_provider.initialize()

        result = await llm_provider.generate_with_tools(
            prompt=request.message,
            tools=all_tools,
            timeout=TimeoutConfig.LLM_REQUEST,
            messages=request.history,
        )

        tool_calls_with_results = []
        if result.tool_calls:
            for tool_call in result.tool_calls:
                mcp_tool_call = MCPToolCall(
                    name=tool_call["name"],
                    arguments=tool_call.get("arguments", {}),
                    id=tool_call.get("id", "unknown"),
                )

                tool_info = tool_to_client.get(tool_call["name"])
                if not tool_info:
                    tool_call_with_result = {
                        "name": tool_call["name"],
                        "arguments": tool_call.get("arguments", {}),
                        "id": tool_call.get("id", "unknown"),
                        "result": None,
                        "error": f"Tool '{tool_call['name']}' not found in any MCP profile",
                        "is_error": True,
                    }
                    tool_calls_with_results.append(tool_call_with_result)
                    continue

                client_for_tool, profile_id, mcp_name = tool_info
                tool_result = await client_for_tool.call_tool(mcp_tool_call)

                tool_call_with_result = {
                    "name": tool_call["name"],
                    "arguments": tool_call.get("arguments", {}),
                    "id": tool_call.get("id", "unknown"),
                    "result": tool_result.content if not tool_result.is_error else None,
                    "error": tool_result.error_message if tool_result.is_error else None,
                    "is_error": tool_result.is_error,
                }
                tool_calls_with_results.append(tool_call_with_result)

        await llm_provider.close()

        # Clean up response
        clean_response = result.response
        if tool_calls_with_results:
            lines = clean_response.split("\n")
            filtered_lines = []
            skip_next = False
            for line in lines:
                if line.strip().startswith("Tool ") and (
                    " executed successfully" in line or " failed" in line
                ):
                    skip_next = True
                    continue
                if skip_next and (line.strip().startswith("[") or line.strip().startswith("{")):
                    skip_next = False
                    continue
                skip_next = False
                filtered_lines.append(line)
            clean_response = "\n".join(filtered_lines).strip()

        return ChatResponse(
            response=clean_response,
            tool_calls=tool_calls_with_results,
            token_usage=result.token_usage,
            cost=result.cost,
            duration=result.duration,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
