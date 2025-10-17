"""
FastAPI server for testmcpy web UI.
"""

import asyncio
import json
import os
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
import yaml

from testmcpy.src.mcp_client import MCPClient, MCPToolCall
from testmcpy.src.llm_integration import create_llm_provider
from testmcpy.src.test_runner import TestRunner, TestCase
from testmcpy.config import get_config
from testmcpy.evals.base_evaluators import create_evaluator


# Pydantic models for request/response
class ChatRequest(BaseModel):
    message: str
    model: Optional[str] = None
    provider: Optional[str] = None


class ChatResponse(BaseModel):
    response: str
    tool_calls: List[Dict[str, Any]] = []
    token_usage: Optional[Dict[str, int]] = None
    cost: float = 0.0
    duration: float = 0.0


class TestFileCreate(BaseModel):
    filename: str
    content: str


class TestFileUpdate(BaseModel):
    content: str


class TestRunRequest(BaseModel):
    test_path: str
    model: Optional[str] = None
    provider: Optional[str] = None


class EvalRunRequest(BaseModel):
    prompt: str
    response: str
    tool_calls: List[Dict[str, Any]] = []
    model: Optional[str] = None
    provider: Optional[str] = None


# Initialize FastAPI app
app = FastAPI(
    title="testmcpy Web UI",
    description="Web interface for testing MCP services with LLMs",
    version="1.0.0"
)

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify exact origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global state
config = get_config()
mcp_client: Optional[MCPClient] = None
active_websockets: List[WebSocket] = []


@app.on_event("startup")
async def startup_event():
    """Initialize MCP client on startup."""
    global mcp_client
    try:
        mcp_client = MCPClient(config.mcp_url)
        await mcp_client.initialize()
        print(f"MCP client initialized at {config.mcp_url}")
    except Exception as e:
        print(f"Warning: Failed to initialize MCP client: {e}")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    global mcp_client
    if mcp_client:
        await mcp_client.close()


# API Routes

@app.get("/")
async def root():
    """Root endpoint - serves the React app."""
    ui_dir = Path(__file__).parent.parent / "ui" / "dist"
    index_file = ui_dir / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {"message": "testmcpy Web UI - Build the React app first"}


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "mcp_connected": mcp_client is not None,
        "timestamp": datetime.now().isoformat()
    }


@app.get("/api/config")
async def get_configuration():
    """Get current configuration."""
    all_config = config.get_all_with_sources()

    # Mask sensitive values
    masked_config = {}
    for key, (value, source) in all_config.items():
        if "API_KEY" in key or "TOKEN" in key or "SECRET" in key:
            if value:
                masked_value = f"{value[:8]}...{value[-4:]}" if len(value) > 12 else "***"
            else:
                masked_value = None
        else:
            masked_value = value

        masked_config[key] = {
            "value": masked_value,
            "source": source
        }

    return masked_config


@app.get("/api/models")
async def list_models():
    """List available models for each provider."""
    return {
        "anthropic": [
            {"id": "claude-sonnet-4-5", "name": "Claude Sonnet 4.5", "description": "Latest Sonnet 4.5 (most capable)"},
            {"id": "claude-haiku-4-5", "name": "Claude Haiku 4.5", "description": "Latest Haiku 4.5 (fast & efficient)"},
            {"id": "claude-opus-4-1", "name": "Claude Opus 4.1", "description": "Latest Opus 4.1 (most powerful)"},
            {"id": "claude-haiku-4-5", "name": "Claude 3.5 Haiku", "description": "Legacy Haiku 3.5"}
        ],
        "ollama": [
            {"id": "llama3.1:8b", "name": "Llama 3.1 8B", "description": "Meta's Llama 3.1 8B (good balance)"},
            {"id": "llama3.1:70b", "name": "Llama 3.1 70B", "description": "Meta's Llama 3.1 70B (more capable)"},
            {"id": "qwen2.5:14b", "name": "Qwen 2.5 14B", "description": "Alibaba's Qwen 2.5 14B (strong coding)"},
            {"id": "mistral:7b", "name": "Mistral 7B", "description": "Mistral 7B (efficient)"}
        ],
        "openai": [
            {"id": "gpt-4o", "name": "GPT-4 Optimized", "description": "GPT-4 Optimized (recommended)"},
            {"id": "gpt-4-turbo", "name": "GPT-4 Turbo", "description": "GPT-4 Turbo"},
            {"id": "gpt-4", "name": "GPT-4", "description": "GPT-4 (original)"},
            {"id": "gpt-3.5-turbo", "name": "GPT-3.5 Turbo", "description": "GPT-3.5 Turbo (faster, cheaper)"}
        ]
    }


# MCP Tools, Resources, Prompts

@app.get("/api/mcp/tools")
async def list_mcp_tools():
    """List all MCP tools with their schemas."""
    if not mcp_client:
        raise HTTPException(status_code=503, detail="MCP client not initialized")

    try:
        tools = await mcp_client.list_tools()
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.input_schema
            }
            for tool in tools
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/mcp/resources")
async def list_mcp_resources():
    """List all MCP resources."""
    if not mcp_client:
        raise HTTPException(status_code=503, detail="MCP client not initialized")

    try:
        resources = await mcp_client.list_resources()
        return resources
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/mcp/prompts")
async def list_mcp_prompts():
    """List all MCP prompts."""
    if not mcp_client:
        raise HTTPException(status_code=503, detail="MCP client not initialized")

    try:
        prompts = await mcp_client.list_prompts()
        return prompts
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Chat endpoint

@app.post("/api/chat")
async def chat(request: ChatRequest) -> ChatResponse:
    """Send a message to the LLM with MCP tools."""
    if not mcp_client:
        raise HTTPException(status_code=503, detail="MCP client not initialized")

    model = request.model or config.default_model
    provider = request.provider or config.default_provider

    try:
        # Get available tools
        tools = await mcp_client.list_tools()
        formatted_tools = [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.input_schema
                }
            }
            for tool in tools
        ]

        # Initialize LLM provider
        llm_provider = create_llm_provider(provider, model)
        await llm_provider.initialize()

        # Generate response
        result = await llm_provider.generate_with_tools(
            prompt=request.message,
            tools=formatted_tools,
            timeout=30.0
        )

        # Execute tool calls if any
        tool_calls_with_results = []
        if result.tool_calls:
            for tool_call in result.tool_calls:
                mcp_tool_call = MCPToolCall(
                    name=tool_call["name"],
                    arguments=tool_call.get("arguments", {}),
                    id=tool_call.get("id", "unknown")
                )
                tool_result = await mcp_client.call_tool(mcp_tool_call)

                # Add result to tool call
                tool_call_with_result = {
                    "name": tool_call["name"],
                    "arguments": tool_call.get("arguments", {}),
                    "id": tool_call.get("id", "unknown"),
                    "result": tool_result.content if not tool_result.is_error else None,
                    "error": tool_result.error_message if tool_result.is_error else None,
                    "is_error": tool_result.is_error
                }
                tool_calls_with_results.append(tool_call_with_result)

        await llm_provider.close()

        # Clean up response - remove tool execution messages since we show them separately
        clean_response = result.response
        if tool_calls_with_results:
            # Remove lines that start with "Tool <name> executed" or "Tool <name> failed"
            lines = clean_response.split('\n')
            filtered_lines = []
            skip_next = False
            for line in lines:
                # Skip tool execution status lines
                if line.strip().startswith('Tool ') and (' executed successfully' in line or ' failed' in line):
                    skip_next = True
                    continue
                # Skip the raw content line after tool execution
                if skip_next and (line.strip().startswith('[') or line.strip().startswith('{')):
                    skip_next = False
                    continue
                skip_next = False
                filtered_lines.append(line)

            clean_response = '\n'.join(filtered_lines).strip()

        return ChatResponse(
            response=clean_response,
            tool_calls=tool_calls_with_results,
            token_usage=result.token_usage,
            cost=result.cost,
            duration=result.duration
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Test file management

@app.get("/api/tests")
async def list_tests():
    """List all test files in the tests directory."""
    tests_dir = Path.cwd() / "tests"
    if not tests_dir.exists():
        return []

    test_files = []
    for file in tests_dir.glob("*.yaml"):
        try:
            with open(file) as f:
                content = f.read()
                data = yaml.safe_load(content)

                # Count tests
                test_count = len(data.get("tests", [])) if "tests" in data else 1

                test_files.append({
                    "filename": file.name,
                    "path": str(file),
                    "test_count": test_count,
                    "size": file.stat().st_size,
                    "modified": file.stat().st_mtime
                })
        except Exception as e:
            print(f"Error reading {file}: {e}")

    return sorted(test_files, key=lambda x: x["modified"], reverse=True)


@app.get("/api/tests/{filename}")
async def get_test_file(filename: str):
    """Get content of a specific test file."""
    tests_dir = Path.cwd() / "tests"
    file_path = tests_dir / filename

    if not file_path.exists() or not file_path.is_relative_to(tests_dir):
        raise HTTPException(status_code=404, detail="Test file not found")

    try:
        with open(file_path) as f:
            content = f.read()

        return {
            "filename": filename,
            "content": content,
            "path": str(file_path)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/tests")
async def create_test_file(request: TestFileCreate):
    """Create a new test file."""
    tests_dir = Path.cwd() / "tests"
    tests_dir.mkdir(exist_ok=True)

    file_path = tests_dir / request.filename

    if file_path.exists():
        raise HTTPException(status_code=400, detail="File already exists")

    # Validate YAML
    try:
        yaml.safe_load(request.content)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid YAML: {str(e)}")

    try:
        with open(file_path, 'w') as f:
            f.write(request.content)

        return {
            "message": "Test file created successfully",
            "filename": request.filename,
            "path": str(file_path)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/tests/{filename}")
async def update_test_file(filename: str, request: TestFileUpdate):
    """Update an existing test file."""
    tests_dir = Path.cwd() / "tests"
    file_path = tests_dir / filename

    if not file_path.exists() or not file_path.is_relative_to(tests_dir):
        raise HTTPException(status_code=404, detail="Test file not found")

    # Validate YAML
    try:
        yaml.safe_load(request.content)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid YAML: {str(e)}")

    try:
        with open(file_path, 'w') as f:
            f.write(request.content)

        return {
            "message": "Test file updated successfully",
            "filename": filename,
            "path": str(file_path)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/tests/{filename}")
async def delete_test_file(filename: str):
    """Delete a test file."""
    tests_dir = Path.cwd() / "tests"
    file_path = tests_dir / filename

    if not file_path.exists() or not file_path.is_relative_to(tests_dir):
        raise HTTPException(status_code=404, detail="Test file not found")

    try:
        file_path.unlink()
        return {
            "message": "Test file deleted successfully",
            "filename": filename
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Test execution

@app.post("/api/tests/run")
async def run_tests(request: TestRunRequest):
    """Run test cases from a file."""
    test_path = Path(request.test_path)

    if not test_path.exists():
        raise HTTPException(status_code=404, detail="Test file not found")

    model = request.model or config.default_model
    provider = request.provider or config.default_provider

    try:
        # Load test cases
        with open(test_path) as f:
            if test_path.suffix == ".json":
                data = json.load(f)
            else:
                data = yaml.safe_load(f)

        test_cases = []
        if "tests" in data:
            for test_data in data["tests"]:
                test_cases.append(TestCase.from_dict(test_data))
        else:
            test_cases.append(TestCase.from_dict(data))

        # Run tests
        runner = TestRunner(
            model=model,
            provider=provider,
            mcp_url=config.mcp_url,
            verbose=False,
            hide_tool_output=True
        )

        results = await runner.run_tests(test_cases)

        # Format results
        return {
            "summary": {
                "total": len(results),
                "passed": sum(1 for r in results if r.passed),
                "failed": sum(1 for r in results if not r.passed),
                "total_cost": sum(r.cost for r in results),
                "total_tokens": sum(r.token_usage.get("total", 0) for r in results if r.token_usage)
            },
            "results": [r.to_dict() for r in results]
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Eval endpoints

@app.post("/api/eval/run")
async def run_eval(request: EvalRunRequest):
    """Run evaluators on a prompt/response pair from chat."""
    try:
        # Extract tool results from tool_calls (chat embeds results in tool_calls)
        from testmcpy.src.mcp_client import MCPToolResult

        print(f"[EVAL DEBUG] Received tool_calls: {request.tool_calls}")

        tool_results = []
        for tool_call in request.tool_calls:
            print(f"[EVAL DEBUG] Processing tool_call: {tool_call.get('name')}")
            print(f"[EVAL DEBUG] - has 'result' key: {'result' in tool_call}")
            print(f"[EVAL DEBUG] - result value: {tool_call.get('result')}")
            print(f"[EVAL DEBUG] - is_error: {tool_call.get('is_error', False)}")

            # Create MCPToolResult from embedded result data
            tool_results.append(MCPToolResult(
                tool_call_id=tool_call.get("id", "unknown"),
                content=tool_call.get("result"),
                is_error=tool_call.get("is_error", False),
                error_message=tool_call.get("error")
            ))

        print(f"[EVAL DEBUG] Created {len(tool_results)} tool_results")

        # Create a context for evaluators
        context = {
            "prompt": request.prompt,
            "response": request.response,
            "tool_calls": request.tool_calls,
            "tool_results": tool_results,
            "metadata": {
                "model": request.model or config.default_model,
                "provider": request.provider or config.default_provider,
            }
        }

        # Default evaluators to run for chat interactions
        default_evaluators = [
            {"name": "execution_successful"},
            {"name": "was_mcp_tool_called"},
        ]

        # Run evaluators
        evaluations = []
        all_passed = True
        total_score = 0.0

        for eval_config in default_evaluators:
            try:
                evaluator = create_evaluator(eval_config["name"], **eval_config.get("args", {}))
                eval_result = evaluator.evaluate(context)

                evaluations.append({
                    "evaluator": evaluator.name,
                    "passed": eval_result.passed,
                    "score": eval_result.score,
                    "reason": eval_result.reason,
                    "details": eval_result.details
                })

                if not eval_result.passed:
                    all_passed = False
                total_score += eval_result.score
            except Exception as e:
                # If evaluator fails, mark it as failed but continue
                evaluations.append({
                    "evaluator": eval_config["name"],
                    "passed": False,
                    "score": 0.0,
                    "reason": f"Evaluator error: {str(e)}",
                    "details": None
                })
                all_passed = False

        avg_score = total_score / len(default_evaluators) if default_evaluators else 0.0

        return {
            "passed": all_passed,
            "score": avg_score,
            "reason": "All evaluators passed" if all_passed else "Some evaluators failed",
            "evaluations": evaluations
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Catch-all route for React Router (must be before static files)
@app.get("/{full_path:path}")
async def serve_react_app(full_path: str):
    """Serve React app for all non-API routes (SPA support)."""
    # Don't intercept API routes
    if full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="API endpoint not found")

    # Serve index.html for all other routes (client-side routing)
    ui_dir = Path(__file__).parent.parent / "ui" / "dist"
    index_file = ui_dir / "index.html"

    # Check if it's a static file request
    static_file = ui_dir / full_path
    if static_file.exists() and static_file.is_file():
        return FileResponse(static_file)

    # Otherwise serve index.html for React Router
    if index_file.exists():
        return FileResponse(index_file)

    return {"message": "testmcpy Web UI - Build the React app first"}
