"""API routes for test-performance analytics.

Thin HTTP layer over testmcpy.analytics — the same aggregation
functions back the matrix/leaderboard/flaky CLI commands, so the UI
and CI report identical numbers.
"""

from typing import Any

from fastapi import APIRouter, HTTPException

from testmcpy import analytics
from testmcpy.storage import get_storage

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/matrix")
async def get_matrix(
    suite_id: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    min_runs: int = 1,
    include_profile: bool = True,
    include_effort: bool = False,
    include_suite: bool = False,
) -> dict[str, Any]:
    """Per-question × per-config performance matrix."""
    storage = get_storage()
    with storage.session() as session:
        return analytics.test_matrix(
            session,
            suite_id=suite_id,
            date_from=date_from,
            date_to=date_to,
            min_runs=min_runs,
            include_profile=include_profile,
            include_effort=include_effort,
            include_suite=include_suite,
        )


@router.get("/leaderboard")
async def get_leaderboard(
    suite_id: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    include_profile: bool = True,
    include_effort: bool = False,
    include_suite: bool = False,
) -> dict[str, Any]:
    """Configs ranked by pass rate with cost-per-pass and latency.

    ``include_effort`` splits configs by reasoning-effort level (accuracy-vs-cost
    effort curve); ``include_suite`` splits by test suite (per-suite facets).
    """
    storage = get_storage()
    with storage.session() as session:
        ranked = analytics.leaderboard(
            session,
            suite_id=suite_id,
            date_from=date_from,
            date_to=date_to,
            include_profile=include_profile,
            include_effort=include_effort,
            include_suite=include_suite,
        )
    return {"configs": ranked, "total": len(ranked)}


@router.get("/flaky")
async def get_flaky(
    suite_id: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    min_runs: int = analytics.FLAKY_MIN_RUNS,
) -> dict[str, Any]:
    """Flaky question × config cells, most intermittent first."""
    storage = get_storage()
    with storage.session() as session:
        flaky = analytics.flaky_tests(
            session,
            suite_id=suite_id,
            date_from=date_from,
            date_to=date_to,
            min_runs=min_runs,
        )
    return {"flaky": flaky, "total": len(flaky)}


@router.get("/question-history")
async def get_question_history(
    question_id: str,
    suite_id: str | None = None,
    model: str | None = None,
    provider: str | None = None,
    mcp_profile: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """Chronological per-run points for one question (drill-down)."""
    if not question_id:
        raise HTTPException(status_code=422, detail="question_id is required")
    storage = get_storage()
    with storage.session() as session:
        points = analytics.question_history(
            session,
            question_id,
            suite_id=suite_id,
            model=model,
            provider=provider,
            mcp_profile=mcp_profile,
            limit=limit,
        )
    return {"question_id": question_id, "points": points, "total": len(points)}
