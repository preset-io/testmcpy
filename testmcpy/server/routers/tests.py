"""
Test management API router with streaming support.
"""

import asyncio
import json
from pathlib import Path
from typing import Any, AsyncGenerator

import yaml
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from testmcpy.server.models import TestRunRequest
from testmcpy.server.state import TimeoutConfig, config
from testmcpy.src.test_runner import TestCase, TestRunner

router = APIRouter(prefix="/api", tags=["tests"])


async def get_or_create_mcp_client(profile_selection: str):
    """Get or create MCP client for the selected profile."""
    from testmcpy.server.state import get_mcp_client_for_server, get_mcp_clients_for_profile

    if ":" in profile_selection:
        profile_id, mcp_name = profile_selection.split(":", 1)
        return await get_mcp_client_for_server(profile_id, mcp_name)
    else:
        clients = await get_mcp_clients_for_profile(profile_selection)
        return clients[0][1] if clients else None


async def stream_test_output(
    test_cases: list[TestCase],
    model: str,
    provider: str,
    mcp_client: Any | None,
) -> AsyncGenerator[str, None]:
    """
    Stream test execution output using Server-Sent Events.

    Yields SSE-formatted events:
    - event: start - Test run starting with metadata
    - event: test_start - Individual test starting
    - event: test_progress - Progress update during test
    - event: test_complete - Individual test completed
    - event: done - All tests complete with summary
    - event: error - Error occurred
    """
    total_tests = len(test_cases)

    # Emit start event
    yield f"event: start\ndata: {json.dumps({'total': total_tests, 'model': model, 'provider': provider})}\n\n"

    results = []
    try:
        # Create test runner
        runner = TestRunner(
            model=model,
            provider=provider,
            mcp_url=config.get_mcp_url(),
            mcp_client=mcp_client,
            verbose=False,
            hide_tool_output=True,
        )

        for idx, test_case in enumerate(test_cases):
            # Emit test start event
            yield f"event: test_start\ndata: {json.dumps({'index': idx, 'name': test_case.name, 'total': total_tests})}\n\n"

            try:
                # Run individual test
                test_results = await runner.run_tests([test_case])
                result = test_results[0] if test_results else None

                if result:
                    result_dict = result.to_dict()
                    results.append(result)

                    # Emit test complete event
                    yield f"event: test_complete\ndata: {json.dumps({'index': idx, 'name': test_case.name, 'passed': result.passed, 'duration': result.duration, 'cost': result.cost, 'result': result_dict})}\n\n"
                else:
                    yield f"event: test_complete\ndata: {json.dumps({'index': idx, 'name': test_case.name, 'passed': False, 'error': 'No result returned'})}\n\n"

            except Exception as e:
                yield f"event: test_complete\ndata: {json.dumps({'index': idx, 'name': test_case.name, 'passed': False, 'error': str(e)})}\n\n"

            # Small delay between tests
            await asyncio.sleep(0.1)

        # Emit done event with summary
        summary = {
            "total": len(results),
            "passed": sum(1 for r in results if r.passed),
            "failed": sum(1 for r in results if not r.passed),
            "total_cost": sum(r.cost for r in results),
            "total_tokens": sum(r.token_usage.get("total", 0) for r in results if r.token_usage),
        }
        yield f"event: done\ndata: {json.dumps({'summary': summary})}\n\n"

    except Exception as e:
        yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"


@router.post("/tests/run")
async def run_tests(request: TestRunRequest):
    """
    Run test cases from a file.

    If stream=true, returns a streaming response with Server-Sent Events
    for live test output. Otherwise, returns a standard JSON response.
    """
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

        # Filter to specific test if test_name is provided
        if request.test_name:
            test_cases = [tc for tc in test_cases if tc.name == request.test_name]
            if not test_cases:
                raise HTTPException(
                    status_code=404,
                    detail=f"Test '{request.test_name}' not found in test file",
                )

        # Get MCP client for the selected profile
        mcp_client = None
        if request.profile:
            mcp_client = await get_or_create_mcp_client(request.profile)

        # Handle streaming response
        if request.stream:
            return StreamingResponse(
                stream_test_output(test_cases, model, provider, mcp_client),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                },
            )

        # Non-streaming response (original behavior)
        runner = TestRunner(
            model=model,
            provider=provider,
            mcp_url=config.get_mcp_url(),
            mcp_client=mcp_client,
            verbose=False,
            hide_tool_output=True,
        )

        results = await runner.run_tests(test_cases)

        return {
            "summary": {
                "total": len(results),
                "passed": sum(1 for r in results if r.passed),
                "failed": sum(1 for r in results if not r.passed),
                "total_cost": sum(r.cost for r in results),
                "total_tokens": sum(
                    r.token_usage.get("total", 0) for r in results if r.token_usage
                ),
            },
            "results": [r.to_dict() for r in results],
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tests/run-stream")
async def run_tests_stream(request: TestRunRequest):
    """
    Run test cases with streaming output (explicit streaming endpoint).
    Returns Server-Sent Events for live test progress.
    """
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

        # Filter to specific test if test_name is provided
        if request.test_name:
            test_cases = [tc for tc in test_cases if tc.name == request.test_name]
            if not test_cases:
                raise HTTPException(
                    status_code=404,
                    detail=f"Test '{request.test_name}' not found in test file",
                )

        # Get MCP client for the selected profile
        mcp_client = None
        if request.profile:
            mcp_client = await get_or_create_mcp_client(request.profile)

        return StreamingResponse(
            stream_test_output(test_cases, model, provider, mcp_client),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
