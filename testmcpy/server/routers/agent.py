"""
API routes for the Test Execution Agent.
"""

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/agent", tags=["agent"])


# ---------------------------------------------------------------------------
# Request / Response Models
# ---------------------------------------------------------------------------


class AgentRunRequest(BaseModel):
    """Request to start an agent run."""

    prompt: str = Field(..., min_length=1, description="Natural language instruction")
    test_path: str | None = Field(None, description="Path to test file or directory")
    mcp_profile: str | None = Field(None, description="MCP service profile ID")
    mcp_url: str | None = Field(None, description="Direct MCP service URL")
    models: list[str] = Field(default_factory=list, description="Models to test")
    max_turns: int = Field(50, ge=1, le=200, description="Maximum agent turns")
    agent_model: str | None = Field(None, description="Model for the agent itself")


class AgentRunResponse(BaseModel):
    """Response from an agent run."""

    run_id: str
    status: str
    report: dict[str, Any] | None = None
    error: str | None = None


# ---------------------------------------------------------------------------
# Storage for agent reports
# ---------------------------------------------------------------------------


def _get_reports_dir() -> Path:
    """Get or create the agent reports directory."""
    reports_dir = Path.cwd() / "tests" / ".agent_reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    return reports_dir


def _save_report(run_id: str, report: dict[str, Any]) -> Path:
    """Save an agent report to disk."""
    reports_dir = _get_reports_dir()
    report_file = reports_dir / f"{run_id}.json"
    report_file.write_text(json.dumps(report, indent=2, default=str))
    return report_file


def _load_report(run_id: str) -> dict[str, Any] | None:
    """Load an agent report from disk."""
    reports_dir = _get_reports_dir()
    report_file = reports_dir / f"{run_id}.json"
    if report_file.exists():
        return json.loads(report_file.read_text())
    return None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/run", response_model=AgentRunResponse)
async def run_agent(request: AgentRunRequest):
    """Start an agent run and return the report.

    The agent processes the prompt synchronously and returns results.
    """
    try:
        from testmcpy.agent.orchestrator import TestExecutionAgent
    except ImportError:
        raise HTTPException(
            status_code=501,
            detail="Claude Agent SDK not installed. Install with: pip install testmcpy[sdk]",
        )

    # Build effective prompt
    effective_prompt = request.prompt
    if request.test_path:
        effective_prompt += f"\n\nTest files are at: {request.test_path}"

    # Resolve MCP profile if not provided
    mcp_profile = request.mcp_profile
    if not mcp_profile and not request.mcp_url:
        try:
            from testmcpy.server.helpers.mcp_config import load_mcp_yaml

            mcp_config = load_mcp_yaml()
            mcp_profile = mcp_config.get("default")
        except (FileNotFoundError, KeyError):
            pass

    try:
        agent = TestExecutionAgent(
            mcp_profile=mcp_profile,
            mcp_url=request.mcp_url,
            models=request.models,
            max_turns=request.max_turns,
            agent_model=request.agent_model,
        )

        report = await agent.run(effective_prompt)
        report_dict = report.to_dict()

        # Save report to disk
        _save_report(report.run_id, report_dict)

        return AgentRunResponse(
            run_id=report.run_id,
            status="completed",
            report=report_dict,
        )

    except (ConnectionError, TimeoutError, OSError) as e:
        return AgentRunResponse(
            run_id="",
            status="error",
            error=f"Connection error: {e}",
        )
    except ValueError as e:
        return AgentRunResponse(
            run_id="",
            status="error",
            error=f"Configuration error: {e}",
        )


@router.get("/report/{run_id}")
async def get_agent_report(run_id: str):
    """Get an agent run report by ID."""
    report = _load_report(run_id)
    if report is None:
        raise HTTPException(status_code=404, detail=f"Report not found: {run_id}")
    return report


@router.get("/reports")
async def list_agent_reports(limit: int = 20):
    """List recent agent run reports."""
    reports_dir = _get_reports_dir()
    report_files = sorted(reports_dir.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)

    reports = []
    for report_file in report_files[:limit]:
        try:
            data = json.loads(report_file.read_text())
            reports.append(
                {
                    "run_id": data.get("run_id", report_file.stem),
                    "started_at": data.get("started_at"),
                    "tests_run": data.get("tests_run", 0),
                    "tests_passed": data.get("tests_passed", 0),
                    "tests_failed": data.get("tests_failed", 0),
                    "total_cost_usd": data.get("total_cost_usd", 0.0),
                    "num_turns": data.get("num_turns", 0),
                }
            )
        except (json.JSONDecodeError, KeyError):
            continue

    return {"reports": reports, "total": len(reports)}
