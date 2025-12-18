"""
API routes for test results history and comparison.
"""

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

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


def get_results_dir() -> Path:
    """Get or create the results directory."""
    results_dir = Path.cwd() / "tests" / ".results"
    results_dir.mkdir(parents=True, exist_ok=True)
    return results_dir


def get_result_file(run_id: str) -> Path:
    """Get path to a result file."""
    return get_results_dir() / f"{run_id}.json"


def save_test_run_to_file(data: dict[str, Any]) -> dict[str, Any]:
    """
    Save a test run result to file.
    This function can be called directly (not as an HTTP endpoint).

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
    run_id = str(uuid.uuid4())[:8] + "_" + datetime.now().strftime("%Y%m%d_%H%M%S")

    results = data.get("results", [])
    summary = data.get("summary", {})

    # Calculate totals from results
    total_cost = sum(r.get("cost", 0) for r in results)
    total_tokens = sum(r.get("token_usage", {}).get("total", 0) for r in results)
    total_duration = sum(r.get("duration", 0) for r in results)

    metadata = TestRunMetadata(
        run_id=run_id,
        test_file=data.get("test_file", "unknown"),
        test_file_path=data.get("test_file_path", ""),
        timestamp=datetime.now().isoformat(),
        provider=data.get("provider", "unknown"),
        model=data.get("model", "unknown"),
        mcp_profile=data.get("mcp_profile"),
        total_tests=len(results),
        passed=summary.get("passed", 0),
        failed=summary.get("failed", 0),
        total_cost=total_cost,
        total_tokens=total_tokens,
        total_duration=total_duration,
    )

    run_result = TestRunResult(metadata=metadata, results=results, summary=summary)

    # Save to file
    result_file = get_result_file(run_id)
    with open(result_file, "w") as f:
        json.dump(run_result.model_dump(), f, indent=2, default=str)

    return {"run_id": run_id, "saved": True, "path": str(result_file)}


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
    results_dir = get_results_dir()
    runs = []

    for result_file in sorted(results_dir.glob("*.json"), reverse=True):
        try:
            with open(result_file) as f:
                data = json.load(f)
                metadata = data.get("metadata", {})

                # Filter by test file if specified
                if test_file and metadata.get("test_file") != test_file:
                    continue

                runs.append(metadata)

                if len(runs) >= limit:
                    break
        except Exception:
            continue

    return {"runs": runs, "total": len(runs)}


@router.get("/run/{run_id}")
async def get_test_run(run_id: str) -> dict[str, Any]:
    """Get full details of a specific test run."""
    result_file = get_result_file(run_id)

    if not result_file.exists():
        raise HTTPException(status_code=404, detail=f"Test run {run_id} not found")

    with open(result_file) as f:
        return json.load(f)


@router.get("/history/{test_file:path}")
async def get_test_history(test_file: str, limit: int = 20) -> dict[str, Any]:
    """
    Get history of runs for a specific test file.
    Returns data suitable for timeline/comparison charts.
    """
    results_dir = get_results_dir()
    history = []

    for result_file in sorted(results_dir.glob("*.json"), reverse=True):
        try:
            with open(result_file) as f:
                data = json.load(f)
                metadata = data.get("metadata", {})

                if metadata.get("test_file") != test_file:
                    continue

                # Extract per-test scores for comparison
                test_scores = {}
                for result in data.get("results", []):
                    test_name = result.get("test_name", "unknown")
                    test_scores[test_name] = {
                        "passed": result.get("passed", False),
                        "score": result.get("score", 0),
                        "duration": result.get("duration", 0),
                        "cost": result.get("cost", 0),
                    }

                history.append(
                    {
                        "run_id": metadata.get("run_id"),
                        "timestamp": metadata.get("timestamp"),
                        "provider": metadata.get("provider"),
                        "model": metadata.get("model"),
                        "passed": metadata.get("passed", 0),
                        "failed": metadata.get("failed", 0),
                        "total": metadata.get("total_tests", 0),
                        "pass_rate": (
                            metadata.get("passed", 0) / metadata.get("total_tests", 1)
                            if metadata.get("total_tests", 0) > 0
                            else 0
                        ),
                        "total_cost": metadata.get("total_cost", 0),
                        "total_duration": metadata.get("total_duration", 0),
                        "test_scores": test_scores,
                    }
                )

                if len(history) >= limit:
                    break
        except Exception:
            continue

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

    runs = []
    for run_id in ids:
        result_file = get_result_file(run_id)
        if result_file.exists():
            with open(result_file) as f:
                runs.append(json.load(f))

    if len(runs) < 2:
        raise HTTPException(status_code=404, detail="Not enough valid runs found for comparison")

    # Build comparison data
    comparison = {"runs": [], "tests": {}}

    for run_data in runs:
        metadata = run_data.get("metadata", {})
        comparison["runs"].append(
            {
                "run_id": metadata.get("run_id"),
                "timestamp": metadata.get("timestamp"),
                "provider": metadata.get("provider"),
                "model": metadata.get("model"),
                "pass_rate": (
                    metadata.get("passed", 0) / metadata.get("total_tests", 1)
                    if metadata.get("total_tests", 0) > 0
                    else 0
                ),
            }
        )

        # Collect per-test results
        for result in run_data.get("results", []):
            test_name = result.get("test_name", "unknown")
            if test_name not in comparison["tests"]:
                comparison["tests"][test_name] = {}

            comparison["tests"][test_name][metadata.get("run_id")] = {
                "passed": result.get("passed", False),
                "score": result.get("score", 0),
                "duration": result.get("duration", 0),
                "cost": result.get("cost", 0),
            }

    return comparison


@router.delete("/run/{run_id}")
async def delete_test_run(run_id: str) -> dict[str, Any]:
    """Delete a test run result."""
    result_file = get_result_file(run_id)

    if not result_file.exists():
        raise HTTPException(status_code=404, detail=f"Test run {run_id} not found")

    result_file.unlink()
    return {"deleted": True, "run_id": run_id}
