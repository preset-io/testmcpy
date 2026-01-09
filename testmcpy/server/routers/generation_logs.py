"""
API routes for test generation logs history.
Stores all LLM calls, prompts, responses, and metadata from test generation runs.
"""

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

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


def get_logs_dir() -> Path:
    """Get or create the generation logs directory."""
    logs_dir = Path.cwd() / "tests" / ".generation_logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    return logs_dir


def get_log_file(log_id: str) -> Path:
    """Get path to a log file."""
    return get_logs_dir() / f"{log_id}.json"


def save_generation_log(log_data: dict[str, Any]) -> str:
    """Save a generation log and return the log ID."""
    log_id = str(uuid.uuid4())[:8] + "_" + datetime.now().strftime("%Y%m%d_%H%M%S")

    # Add log_id to metadata
    if "metadata" in log_data:
        log_data["metadata"]["log_id"] = log_id
    else:
        log_data["log_id"] = log_id

    log_file = get_log_file(log_id)
    with open(log_file, "w") as f:
        json.dump(log_data, f, indent=2, default=str)

    return log_id


@router.get("/list")
async def list_generation_logs(tool_name: str | None = None, limit: int = 50) -> dict[str, Any]:
    """
    List all generation logs, optionally filtered by tool name.
    Returns metadata only (not full logs).
    """
    logs_dir = get_logs_dir()
    logs = []

    for log_file in sorted(logs_dir.glob("*.json"), reverse=True):
        try:
            with open(log_file) as f:
                data = json.load(f)
                metadata = data.get("metadata", {})

                # Filter by tool name if specified
                if tool_name and metadata.get("tool_name") != tool_name:
                    continue

                logs.append(metadata)

                if len(logs) >= limit:
                    break
        except Exception:
            continue

    return {"logs": logs, "total": len(logs)}


@router.get("/log/{log_id}")
async def get_generation_log(log_id: str) -> dict[str, Any]:
    """Get full details of a specific generation log."""
    log_file = get_log_file(log_id)

    if not log_file.exists():
        raise HTTPException(status_code=404, detail=f"Generation log {log_id} not found")

    with open(log_file) as f:
        return json.load(f)


@router.get("/tools")
async def list_generated_tools() -> dict[str, Any]:
    """Get list of unique tools that have had tests generated."""
    logs_dir = get_logs_dir()
    tools = {}

    for log_file in sorted(logs_dir.glob("*.json"), reverse=True):
        try:
            with open(log_file) as f:
                data = json.load(f)
                metadata = data.get("metadata", {})
                tool_name = metadata.get("tool_name")

                if tool_name:
                    if tool_name not in tools:
                        tools[tool_name] = {
                            "name": tool_name,
                            "description": metadata.get("tool_description", "")[:100],
                            "generation_count": 0,
                            "last_generated": metadata.get("timestamp"),
                            "success_count": 0,
                        }

                    tools[tool_name]["generation_count"] += 1
                    if metadata.get("success"):
                        tools[tool_name]["success_count"] += 1
        except Exception:
            continue

    return {"tools": list(tools.values()), "total": len(tools)}


@router.delete("/log/{log_id}")
async def delete_generation_log(log_id: str) -> dict[str, Any]:
    """Delete a generation log."""
    log_file = get_log_file(log_id)

    if not log_file.exists():
        raise HTTPException(status_code=404, detail=f"Generation log {log_id} not found")

    log_file.unlink()
    return {"deleted": True, "log_id": log_id}


@router.delete("/clear")
async def clear_all_logs() -> dict[str, Any]:
    """Delete all generation logs."""
    logs_dir = get_logs_dir()
    count = 0

    for log_file in logs_dir.glob("*.json"):
        try:
            log_file.unlink()
            count += 1
        except Exception:
            continue

    return {"deleted": count}
