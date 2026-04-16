"""
API routes for smoke test reports history.

All data is stored in and read from the SQLite database via TestStorage.
"""

from typing import Any

from fastapi import APIRouter, HTTPException

from testmcpy.storage import get_storage

router = APIRouter(prefix="/api/smoke-reports", tags=["smoke-reports"])


def save_smoke_report(report_data: dict[str, Any]) -> str:
    """Save a smoke test report and return the report ID."""
    storage = get_storage()
    return storage.save_smoke_report(report_data)


@router.post("/save")
async def save_smoke_report_endpoint(report_data: dict[str, Any]) -> dict[str, Any]:
    """HTTP endpoint to save a smoke test report (used by testmcpy push)."""
    report_id = save_smoke_report(report_data)
    return {"saved": True, "report_id": report_id}


@router.get("/list")
async def list_smoke_reports(
    server_url: str | None = None, profile_id: str | None = None, limit: int = 50
) -> dict[str, Any]:
    """
    List all smoke test reports, optionally filtered by server URL or profile.
    Returns metadata only (not full results).
    """
    storage = get_storage()
    reports = storage.list_smoke_reports(server_url=server_url, profile_id=profile_id, limit=limit)
    return {"reports": reports, "total": len(reports)}


@router.get("/report/{report_id}")
async def get_smoke_report(report_id: str) -> dict[str, Any]:
    """Get full details of a specific smoke test report."""
    storage = get_storage()
    report = storage.get_smoke_report(report_id)

    if not report:
        raise HTTPException(status_code=404, detail=f"Smoke test report {report_id} not found")

    return report


@router.delete("/report/{report_id}")
async def delete_smoke_report(report_id: str) -> dict[str, Any]:
    """Delete a smoke test report."""
    storage = get_storage()
    deleted = storage.delete_smoke_report(report_id)

    if not deleted:
        raise HTTPException(status_code=404, detail=f"Smoke test report {report_id} not found")

    return {"deleted": True, "report_id": report_id}


@router.delete("/clear")
async def clear_all_smoke_reports() -> dict[str, Any]:
    """Delete all smoke test reports."""
    storage = get_storage()
    count = storage.clear_smoke_reports()
    return {"deleted": count}
