"""
API routes for test results history and comparison.

All data is stored in and read from the SQLite database via TestStorage.
"""

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from testmcpy.storage import get_storage

router = APIRouter(prefix="/api/results", tags=["results"])


class TestRunMetadata(BaseModel):
    """Metadata for a test run."""

    run_id: str
    test_file: str
    test_file_path: str
    timestamp: str
    provider: str
    model: str
    mcp_profile: str | None = None
    version: str = "1.0"
    total_tests: int = 0
    passed: int = 0
    failed: int = 0
    total_cost: float = 0.0
    total_tokens: int = 0
    total_duration: float = 0.0


class TestRunResult(BaseModel):
    """Full test run result with all details."""

    metadata: TestRunMetadata
    results: list[dict[str, Any]]
    summary: dict[str, Any]


def save_test_run_to_file(data: dict[str, Any]) -> dict[str, Any]:
    """
    Save a test run result to the database.

    Kept as `save_test_run_to_file` for backward compatibility with callers,
    but now writes to DB instead of JSON files.

    Expected data format:
    {
        "test_file": "health_check/test.yaml",
        "test_file_path": "/full/path/to/test.yaml",
        "provider": "claude-cli",
        "model": "claude-sonnet-4-20250514",
        "mcp_profile": "my-profile",
        "results": [...],
        "summary": {...}
    }
    """
    storage = get_storage()
    run_id = str(uuid.uuid4())[:8] + "_" + datetime.now().strftime("%Y%m%d_%H%M%S")

    results = data.get("results", [])

    test_file = data.get("test_file", "unknown")
    provider = data.get("provider", "unknown")
    model = data.get("model", "unknown")

    # Ensure suite exists
    storage.save_suite(
        suite_id=test_file,
        name=test_file,
        questions=[],  # We don't have the questions here, just the results
    )

    # Save the run
    started_at = datetime.now().isoformat()
    storage.save_run(
        run_id=run_id,
        test_id=test_file,
        test_version=1,
        model=model,
        provider=provider,
        started_at=started_at,
        mcp_profile_id=data.get("mcp_profile"),
    )

    # Save individual question results
    for r in results:
        storage.save_question_result(
            run_id=run_id,
            question_id=r.get("test_name", r.get("question_id", "unknown")),
            passed=r.get("passed", False),
            score=r.get("score", 0.0),
            answer=r.get("response", r.get("answer")),
            tool_uses=r.get("tool_calls", r.get("tool_uses")),
            tool_results=r.get("tool_results"),
            tokens_input=(r.get("token_usage") or {}).get("input", 0),
            tokens_output=(r.get("token_usage") or {}).get("output", 0),
            duration_ms=int(r.get("duration", 0) * 1000),
            evaluations=r.get("evaluations"),
            error=r.get("error"),
        )

    # Complete the run
    storage.complete_run(run_id, datetime.now().isoformat())

    return {"run_id": run_id, "saved": True, "path": f"db://test_runs/{run_id}"}


@router.post("/save")
async def save_test_run(data: dict[str, Any]) -> dict[str, Any]:
    """HTTP endpoint to save a test run result."""
    return save_test_run_to_file(data)


@router.get("/list")
async def list_test_runs(test_file: str | None = None, limit: int = 50) -> dict[str, Any]:
    """
    List all test runs, optionally filtered by test file.
    Returns metadata only (not full results).
    """
    storage = get_storage()
    runs_data = storage.list_runs(test_id=test_file, limit=limit)

    runs = []
    for run in runs_data:
        runs.append(
            {
                "run_id": run["run_id"],
                "test_file": run["test_id"],
                "test_file_path": "",
                "timestamp": run["started_at"],
                "provider": run["provider"],
                "model": run["model"],
                "mcp_profile": None,
                "version": str(run["test_version"]),
                "total_tests": run["total_questions"],
                "passed": run["passed_questions"],
                "failed": run["total_questions"] - run["passed_questions"],
                "total_cost": 0.0,
                "total_tokens": 0,
                "total_duration": 0.0,
            }
        )

    return {"runs": runs, "total": len(runs)}


@router.get("/run/{run_id}")
async def get_test_run(run_id: str) -> dict[str, Any]:
    """Get full details of a specific test run."""
    storage = get_storage()
    run = storage.get_run(run_id)

    if not run:
        raise HTTPException(status_code=404, detail=f"Test run {run_id} not found")

    # Transform to the expected response shape
    metadata = {
        "run_id": run["run_id"],
        "test_file": run["test_id"],
        "test_file_path": "",
        "timestamp": run["started_at"],
        "provider": run["provider"],
        "model": run["model"],
        "mcp_profile": run.get("metadata", {}).get("mcp_profile"),
        "version": str(run["test_version"]),
        "total_tests": run["summary"]["total"],
        "passed": run["summary"]["passed"],
        "failed": run["summary"]["failed"],
        "total_cost": 0.0,
        "total_tokens": run["summary"]["total_tokens"],
        "total_duration": run["summary"]["total_duration_ms"] / 1000.0,
    }

    # Transform question results to legacy result format
    results = []
    for qr in run["question_results"]:
        results.append(
            {
                "test_name": qr["question_id"],
                "passed": qr["passed"],
                "score": qr["score"],
                "duration": qr["duration_ms"] / 1000.0,
                "cost": 0.0,
                "response": qr["answer"],
                "tool_calls": qr["tool_uses"],
                "tool_results": qr["tool_results"],
                "token_usage": {
                    "input": qr["tokens_input"],
                    "output": qr["tokens_output"],
                    "total": qr["tokens_input"] + qr["tokens_output"],
                },
                "evaluations": qr["evaluations"],
                "error": qr["error"],
            }
        )

    return {
        "metadata": metadata,
        "results": results,
        "summary": run["summary"],
    }


@router.get("/history/{test_file:path}")
async def get_test_history(test_file: str, limit: int = 20) -> dict[str, Any]:
    """
    Get history of runs for a specific test file.
    Returns data suitable for timeline/comparison charts.
    """
    storage = get_storage()
    runs_data = storage.list_runs(test_id=test_file, limit=limit)

    history = []
    for run_meta in runs_data:
        # Get full run details for per-test scores
        full_run = storage.get_run(run_meta["run_id"])
        test_scores = {}
        if full_run:
            for qr in full_run.get("question_results", []):
                test_scores[qr["question_id"]] = {
                    "passed": qr["passed"],
                    "score": qr["score"],
                    "duration": qr["duration_ms"] / 1000.0,
                    "cost": 0.0,
                }

        total = run_meta["total_questions"]
        passed = run_meta["passed_questions"]

        history.append(
            {
                "run_id": run_meta["run_id"],
                "timestamp": run_meta["started_at"],
                "provider": run_meta["provider"],
                "model": run_meta["model"],
                "passed": passed,
                "failed": total - passed,
                "total": total,
                "pass_rate": (passed / total) if total > 0 else 0,
                "total_cost": 0.0,
                "total_duration": 0.0,
                "test_scores": test_scores,
            }
        )

    return {"test_file": test_file, "history": history, "total": len(history)}


@router.get("/compare")
async def compare_runs(run_ids: str) -> dict[str, Any]:
    """
    Compare multiple test runs side by side.
    run_ids: comma-separated list of run IDs
    """
    ids = [r.strip() for r in run_ids.split(",") if r.strip()]

    if len(ids) < 2:
        raise HTTPException(status_code=400, detail="At least 2 run IDs required for comparison")

    storage = get_storage()
    runs = []
    for run_id in ids:
        run = storage.get_run(run_id)
        if run:
            runs.append(run)

    if len(runs) < 2:
        raise HTTPException(status_code=404, detail="Not enough valid runs found for comparison")

    comparison: dict[str, Any] = {"runs": [], "tests": {}}

    for run in runs:
        total = run["summary"]["total"]
        passed = run["summary"]["passed"]
        comparison["runs"].append(
            {
                "run_id": run["run_id"],
                "timestamp": run["started_at"],
                "provider": run["provider"],
                "model": run["model"],
                "pass_rate": (passed / total) if total > 0 else 0,
            }
        )

        for qr in run["question_results"]:
            test_name = qr["question_id"]
            if test_name not in comparison["tests"]:
                comparison["tests"][test_name] = {}

            comparison["tests"][test_name][run["run_id"]] = {
                "passed": qr["passed"],
                "score": qr["score"],
                "duration": qr["duration_ms"] / 1000.0,
                "cost": 0.0,
            }

    return comparison


@router.delete("/run/{run_id}")
async def delete_test_run(run_id: str) -> dict[str, Any]:
    """Delete a test run result."""
    storage = get_storage()

    # Check it exists first
    run = storage.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Test run {run_id} not found")

    # Delete from DB using a direct session
    from testmcpy.models import QuestionResultModel, TestRunModel

    session = storage._session()
    try:
        session.query(QuestionResultModel).filter_by(run_id=run_id).delete()
        session.query(TestRunModel).filter_by(run_id=run_id).delete()
        session.commit()
    finally:
        session.close()

    return {"deleted": True, "run_id": run_id}


@router.get("/export/{run_id}")
async def export_test_run_json(run_id: str) -> dict[str, Any]:
    """Export a test run as JSON (replacement for direct file access)."""
    storage = get_storage()
    run = storage.get_run(run_id)

    if not run:
        raise HTTPException(status_code=404, detail=f"Test run {run_id} not found")

    return run


@router.get("/run/{run_id}/traces")
async def get_run_traces(run_id: str) -> dict[str, Any]:
    """
    Get tool call timing data for a test run (trace waterfall view).

    Extracts timing from stored question results to build
    a timeline of tool calls within each test.
    """
    storage = get_storage()
    run = storage.get_run(run_id)

    if not run:
        raise HTTPException(status_code=404, detail=f"Test run {run_id} not found")

    traces = []
    for qr in run.get("question_results", []):
        question_trace = {
            "question_id": qr["question_id"],
            "passed": qr["passed"],
            "total_duration_ms": qr["duration_ms"],
            "tool_calls": [],
        }

        tool_uses = qr.get("tool_uses") or []
        tool_results = qr.get("tool_results") or []

        # Build timeline from tool_uses and tool_results
        cumulative_ms = 0
        for i, tool_use in enumerate(tool_uses):
            tool_name = tool_use.get("name", tool_use.get("tool_name", f"tool_{i}"))
            arguments = tool_use.get("arguments", tool_use.get("input", {}))

            # Try to get corresponding result
            result_data = None
            is_error = False
            if i < len(tool_results):
                result_data = tool_results[i]
                is_error = bool(result_data.get("is_error") or result_data.get("error"))

            # Estimate duration: if we have individual timing, use it;
            # otherwise distribute evenly across tool calls
            call_duration_ms = 0
            if isinstance(tool_use, dict) and "duration_ms" in tool_use:
                call_duration_ms = tool_use["duration_ms"]
            elif isinstance(result_data, dict) and "duration_ms" in (result_data or {}):
                call_duration_ms = result_data["duration_ms"]
            elif tool_uses:
                # Distribute total duration evenly as estimate
                call_duration_ms = qr["duration_ms"] / len(tool_uses)

            start_ms = cumulative_ms
            cumulative_ms += call_duration_ms

            question_trace["tool_calls"].append(
                {
                    "index": i,
                    "name": tool_name,
                    "arguments": arguments,
                    "result": result_data,
                    "is_error": is_error,
                    "start_ms": round(start_ms),
                    "duration_ms": round(call_duration_ms),
                    "status": "error" if is_error else "success",
                }
            )

        traces.append(question_trace)

    return {
        "run_id": run_id,
        "model": run["model"],
        "provider": run["provider"],
        "started_at": run["started_at"],
        "traces": traces,
    }
