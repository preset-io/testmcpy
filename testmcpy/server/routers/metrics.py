"""
Metrics and versioning API router.
"""

from fastapi import APIRouter, HTTPException, Query

from testmcpy.storage import get_storage

router = APIRouter(prefix="/api/metrics", tags=["metrics"])


# ==================== Metrics Endpoints ====================


@router.get("/summary")
async def get_metrics_summary(
    test_path: str | None = Query(None, description="Filter by test file path"),
    model: str | None = Query(None, description="Filter by model"),
    days: int = Query(30, description="Number of days to analyze"),
):
    """Get overall metrics summary."""
    try:
        storage = get_storage()
        return storage.get_pass_rate(test_path=test_path, model=model, days=days)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get metrics: {str(e)}")


@router.get("/trends")
async def get_metrics_trends(
    test_path: str | None = Query(None, description="Filter by test file path"),
    model: str | None = Query(None, description="Filter by model"),
    days: int = Query(30, description="Number of days to analyze"),
    group_by: str = Query("day", description="Group by: day, week, hour"),
):
    """Get historical trends."""
    try:
        storage = get_storage()
        return storage.get_trends(test_path=test_path, model=model, days=days, group_by=group_by)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get trends: {str(e)}")


@router.get("/models")
async def get_model_comparison(
    days: int = Query(30, description="Number of days to analyze"),
):
    """Compare performance across models."""
    try:
        storage = get_storage()
        return storage.get_model_comparison(days=days)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get model comparison: {str(e)}")


@router.get("/failing")
async def get_failing_tests(
    days: int = Query(7, description="Number of days to analyze"),
    min_failures: int = Query(2, description="Minimum failures to include"),
):
    """Get frequently failing tests."""
    try:
        storage = get_storage()
        return storage.get_failing_tests(days=days, min_failures=min_failures)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get failing tests: {str(e)}")


@router.get("/results")
async def get_test_results(
    test_path: str | None = Query(None, description="Filter by test file path"),
    test_name: str | None = Query(None, description="Filter by test name"),
    model: str | None = Query(None, description="Filter by model"),
    limit: int = Query(100, description="Maximum results"),
    since: str | None = Query(None, description="ISO timestamp to filter after"),
):
    """Query test results."""
    try:
        storage = get_storage()
        results = storage.get_results(
            test_path=test_path,
            test_name=test_name,
            model=model,
            limit=limit,
            since=since,
        )
        return [r.to_dict() for r in results]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get results: {str(e)}")


# ==================== Version Endpoints ====================


@router.get("/versions/{test_path:path}")
async def get_test_versions(
    test_path: str,
    limit: int = Query(50, description="Maximum versions to return"),
):
    """Get version history for a test file."""
    try:
        storage = get_storage()
        versions = storage.get_versions(test_path, limit=limit)
        return [v.to_dict() for v in versions]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get versions: {str(e)}")


@router.get("/versions/{test_path:path}/{version}")
async def get_test_version(test_path: str, version: int):
    """Get a specific version of a test file."""
    try:
        storage = get_storage()
        v = storage.get_version(test_path, version)
        if not v:
            raise HTTPException(
                status_code=404, detail=f"Version {version} not found for {test_path}"
            )
        return v.to_dict()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get version: {str(e)}")


@router.get("/versions/{test_path:path}/diff")
async def diff_test_versions(
    test_path: str,
    v1: int = Query(..., description="First version number"),
    v2: int = Query(..., description="Second version number"),
):
    """Compare two versions of a test file."""
    try:
        storage = get_storage()
        return storage.diff_versions(test_path, v1, v2)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to diff versions: {str(e)}")
