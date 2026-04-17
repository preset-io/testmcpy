"""
API routes for analytics metrics dashboard.

Aggregates cost, latency, pass rate, and token usage from test runs
and question results over configurable time ranges.
"""

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Query
from sqlalchemy import func

from testmcpy.db import get_session_factory, init_db
from testmcpy.models import QuestionResultModel, TestRunModel

router = APIRouter(prefix="/api/metrics", tags=["metrics"])


def _get_session():
    """Get a database session."""
    init_db()
    session_factory = get_session_factory()
    return session_factory()


def _parse_date(date_str: str | None) -> datetime | None:
    """Parse an ISO date string to datetime."""
    if not date_str:
        return None
    try:
        return datetime.fromisoformat(date_str)
    except ValueError:
        return None


@router.get("")
async def get_metrics(
    date_from: str | None = Query(None, description="Start date (ISO format)"),
    date_to: str | None = Query(None, description="End date (ISO format)"),
    mcp_profile: str | None = Query(None, description="Filter by MCP profile ID"),
    llm_provider: str | None = Query(None, description="Filter by LLM provider"),
    model: str | None = Query(None, description="Filter by model name"),
    granularity: str = Query("daily", description="Time grouping: daily or weekly"),
) -> dict[str, Any]:
    """
    Get aggregate metrics over time.

    Returns summary totals and time series data for charts.
    """
    session = _get_session()
    try:
        # Default date range: last 30 days
        now = datetime.now(timezone.utc)
        dt_from = _parse_date(date_from) or (now - timedelta(days=30))
        dt_to = _parse_date(date_to) or now

        # Convert to ISO strings for comparison with started_at (stored as string)
        from_str = dt_from.isoformat()
        to_str = dt_to.isoformat()

        # Base query filters
        def apply_filters(query):
            query = query.filter(TestRunModel.started_at >= from_str)
            query = query.filter(TestRunModel.started_at <= to_str)
            query = query.filter(TestRunModel.status == "completed")
            if mcp_profile:
                query = query.filter(TestRunModel.mcp_profile_id == mcp_profile)
            if llm_provider:
                query = query.filter(TestRunModel.provider == llm_provider)
            if model:
                query = query.filter(TestRunModel.model == model)
            return query

        # --- Summary totals ---
        run_query = apply_filters(session.query(TestRunModel))
        runs = run_query.all()
        run_ids = [r.run_id for r in runs]

        total_runs = len(runs)
        total_cost = sum(r.total_cost or 0 for r in runs)
        total_tokens = sum(r.total_tokens or 0 for r in runs)

        # Get question-level stats
        total_questions = 0
        total_passed = 0
        total_duration_ms = 0

        if run_ids:
            q_stats = (
                session.query(
                    func.count(QuestionResultModel.id).label("total"),
                    func.sum(func.iif(QuestionResultModel.passed, 1, 0)).label("passed"),
                    func.sum(QuestionResultModel.duration_ms).label("total_duration"),
                )
                .filter(QuestionResultModel.run_id.in_(run_ids))
                .one()
            )
            total_questions = q_stats.total or 0
            total_passed = q_stats.passed or 0
            total_duration_ms = q_stats.total_duration or 0

        pass_rate = (total_passed / total_questions * 100) if total_questions > 0 else 0
        avg_latency_ms = (total_duration_ms / total_questions) if total_questions > 0 else 0
        avg_cost = (total_cost / total_runs) if total_runs > 0 else 0

        summary = {
            "total_runs": total_runs,
            "total_questions": total_questions,
            "total_passed": total_passed,
            "total_failed": total_questions - total_passed,
            "pass_rate": round(pass_rate, 1),
            "total_cost": round(total_cost, 4),
            "avg_cost_per_run": round(avg_cost, 4),
            "total_tokens": total_tokens,
            "avg_latency_ms": round(avg_latency_ms, 0),
            "date_from": from_str,
            "date_to": to_str,
        }

        # --- Time series ---
        if granularity == "weekly":
            date_expr = func.strftime("%Y-W%W", TestRunModel.started_at)
        else:
            date_expr = func.date(TestRunModel.started_at)

        # Build time series from runs joined with question results
        time_series = []

        if run_ids:
            ts_query = (
                session.query(
                    date_expr.label("period"),
                    func.count(func.distinct(TestRunModel.run_id)).label("runs"),
                    func.count(QuestionResultModel.id).label("questions"),
                    func.sum(func.iif(QuestionResultModel.passed, 1, 0)).label("passed"),
                    func.sum(QuestionResultModel.duration_ms).label("total_duration"),
                    func.sum(TestRunModel.total_cost).label("cost"),
                    func.sum(TestRunModel.total_tokens).label("tokens"),
                )
                .join(
                    QuestionResultModel,
                    TestRunModel.run_id == QuestionResultModel.run_id,
                )
                .filter(TestRunModel.run_id.in_(run_ids))
                .group_by("period")
                .order_by("period")
            )

            for row in ts_query.all():
                questions = row.questions or 0
                passed = row.passed or 0
                time_series.append(
                    {
                        "period": row.period,
                        "runs": row.runs or 0,
                        "questions": questions,
                        "passed": passed,
                        "failed": questions - passed,
                        "pass_rate": round((passed / questions * 100) if questions > 0 else 0, 1),
                        "avg_latency_ms": round(
                            (row.total_duration or 0) / questions if questions > 0 else 0,
                            0,
                        ),
                        "cost": round(row.cost or 0, 4),
                        "tokens": row.tokens or 0,
                    }
                )

        # --- Model breakdown ---
        model_breakdown = []
        if run_ids:
            mb_query = (
                session.query(
                    TestRunModel.model,
                    TestRunModel.provider,
                    func.count(func.distinct(TestRunModel.run_id)).label("runs"),
                    func.count(QuestionResultModel.id).label("questions"),
                    func.sum(func.iif(QuestionResultModel.passed, 1, 0)).label("passed"),
                    func.avg(QuestionResultModel.duration_ms).label("avg_latency"),
                    func.sum(TestRunModel.total_cost).label("cost"),
                )
                .join(
                    QuestionResultModel,
                    TestRunModel.run_id == QuestionResultModel.run_id,
                )
                .filter(TestRunModel.run_id.in_(run_ids))
                .group_by(TestRunModel.model, TestRunModel.provider)
                .order_by(func.count(func.distinct(TestRunModel.run_id)).desc())
            )

            for row in mb_query.all():
                questions = row.questions or 0
                passed = row.passed or 0
                model_breakdown.append(
                    {
                        "model": row.model,
                        "provider": row.provider,
                        "runs": row.runs or 0,
                        "questions": questions,
                        "passed": passed,
                        "pass_rate": round((passed / questions * 100) if questions > 0 else 0, 1),
                        "avg_latency_ms": round(row.avg_latency or 0, 0),
                        "cost": round(row.cost or 0, 4),
                    }
                )

        return {
            "summary": summary,
            "time_series": time_series,
            "model_breakdown": model_breakdown,
        }
    finally:
        session.close()
