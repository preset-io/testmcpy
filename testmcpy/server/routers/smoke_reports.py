"""
API routes for smoke test reports history.
Stores smoke test results with detailed tool input/output information.
"""

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/smoke-reports", tags=["smoke-reports"])


def get_smoke_reports_dir() -> Path:
    """Get or create the smoke test reports directory."""
    reports_dir = Path.cwd() / "tests" / ".smoke_reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    return reports_dir


def get_report_file(report_id: str) -> Path:
    """Get path to a report file."""
    return get_smoke_reports_dir() / f"{report_id}.json"


def save_smoke_report(report_data: dict[str, Any]) -> str:
    """Save a smoke test report and return the report ID."""
    report_id = str(uuid.uuid4())[:8] + "_" + datetime.now().strftime("%Y%m%d_%H%M%S")

    # Add report_id to the data
    report_data["report_id"] = report_id
    report_data["saved_at"] = datetime.now().isoformat()

    report_file = get_report_file(report_id)
    with open(report_file, "w") as f:
        json.dump(report_data, f, indent=2, default=str)

    return report_id


@router.get("/list")
async def list_smoke_reports(
    server_url: str | None = None, profile_id: str | None = None, limit: int = 50
) -> dict[str, Any]:
    """
    List all smoke test reports, optionally filtered by server URL or profile.
    Returns metadata only (not full results).
    """
    reports_dir = get_smoke_reports_dir()
    reports = []

    for report_file in sorted(reports_dir.glob("*.json"), reverse=True):
        try:
            with open(report_file) as f:
                data = json.load(f)

                # Filter by server_url if specified
                if server_url and data.get("server_url") != server_url:
                    continue

                # Filter by profile_id if specified
                if profile_id and data.get("profile_id") != profile_id:
                    continue

                # Return summary metadata
                reports.append(
                    {
                        "report_id": data.get("report_id"),
                        "server_url": data.get("server_url"),
                        "profile_id": data.get("profile_id"),
                        "profile_name": data.get("profile_name"),
                        "timestamp": data.get("timestamp"),
                        "saved_at": data.get("saved_at"),
                        "total_tests": data.get("total_tests", 0),
                        "passed": data.get("passed", 0),
                        "failed": data.get("failed", 0),
                        "success_rate": data.get("success_rate", 0),
                        "duration_ms": data.get("duration_ms", 0),
                    }
                )

                if len(reports) >= limit:
                    break
        except Exception:
            continue

    return {"reports": reports, "total": len(reports)}


@router.get("/report/{report_id}")
async def get_smoke_report(report_id: str) -> dict[str, Any]:
    """Get full details of a specific smoke test report."""
    report_file = get_report_file(report_id)

    if not report_file.exists():
        raise HTTPException(status_code=404, detail=f"Smoke test report {report_id} not found")

    with open(report_file) as f:
        return json.load(f)


@router.delete("/report/{report_id}")
async def delete_smoke_report(report_id: str) -> dict[str, Any]:
    """Delete a smoke test report."""
    report_file = get_report_file(report_id)

    if not report_file.exists():
        raise HTTPException(status_code=404, detail=f"Smoke test report {report_id} not found")

    report_file.unlink()
    return {"deleted": True, "report_id": report_id}


@router.delete("/clear")
async def clear_all_smoke_reports() -> dict[str, Any]:
    """Delete all smoke test reports."""
    reports_dir = get_smoke_reports_dir()
    count = 0

    for report_file in reports_dir.glob("*.json"):
        try:
            report_file.unlink()
            count += 1
        except Exception:
            continue

    return {"deleted": count}
