"""
API routes for test generation logs history.

All data is stored in and read from the SQLite database via TestStorage.
"""

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from testmcpy.storage import get_storage

router = APIRouter(prefix="/api/generation-logs", tags=["generation-logs"])


class LLMCall(BaseModel):
    """A single LLM call during test generation."""

    step: str  # "analysis" or "generation"
    prompt: str
    response: str
    cost: float = 0.0
    tokens: int = 0
    duration: float = 0.0
    timestamp: str


class GenerationLogMetadata(BaseModel):
    """Metadata for a test generation run."""

    log_id: str
    tool_name: str
    tool_description: str
    coverage_level: str
    provider: str
    model: str
    timestamp: str
    success: bool = False
    test_count: int = 0
    total_cost: float = 0.0
    output_file: str | None = None
    error: str | None = None


class GenerationLog(BaseModel):
    """Full generation log with all details."""

    metadata: GenerationLogMetadata
    tool_schema: dict[str, Any]
    llm_calls: list[LLMCall]
    logs: list[str]  # Streaming log messages
    analysis: dict[str, Any] | None = None
    generated_yaml: str | None = None


def save_generation_log(log_data: dict[str, Any]) -> str:
    """Save a generation log and return the log ID."""
    storage = get_storage()
    return storage.save_generation_log(log_data)


@router.post("/save")
async def save_generation_log_endpoint(log_data: dict[str, Any]) -> dict[str, Any]:
    """HTTP endpoint to save a generation log (used by testmcpy push)."""
    log_id = save_generation_log(log_data)
    return {"saved": True, "log_id": log_id}


@router.get("/list")
async def list_generation_logs(tool_name: str | None = None, limit: int = 50) -> dict[str, Any]:
    """
    List all generation logs, optionally filtered by tool name.
    Returns metadata only (not full logs).
    """
    storage = get_storage()
    logs = storage.list_generation_logs(tool_name=tool_name, limit=limit)
    return {"logs": logs, "total": len(logs)}


@router.get("/log/{log_id}")
async def get_generation_log(log_id: str) -> dict[str, Any]:
    """Get full details of a specific generation log."""
    storage = get_storage()
    log = storage.get_generation_log(log_id)

    if not log:
        raise HTTPException(status_code=404, detail=f"Generation log {log_id} not found")

    return log


@router.get("/tools")
async def list_generated_tools() -> dict[str, Any]:
    """Get list of unique tools that have had tests generated."""
    storage = get_storage()
    tools = storage.list_generated_tools()
    return {"tools": tools, "total": len(tools)}


@router.delete("/log/{log_id}")
async def delete_generation_log(log_id: str) -> dict[str, Any]:
    """Delete a generation log."""
    storage = get_storage()
    deleted = storage.delete_generation_log(log_id)

    if not deleted:
        raise HTTPException(status_code=404, detail=f"Generation log {log_id} not found")

    return {"deleted": True, "log_id": log_id}


@router.delete("/clear")
async def clear_all_logs() -> dict[str, Any]:
    """Delete all generation logs."""
    storage = get_storage()
    count = storage.clear_generation_logs()
    return {"deleted": count}
