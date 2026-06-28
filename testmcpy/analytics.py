"""Aggregation core for test-performance analytics.

Answers "which tests perform better than others given the model /
routing config": per-question × per-config pass rates, scores, costs,
latency, flakiness, and day-bucketed trends.

Pure query/aggregation functions over a SQLAlchemy session, shared by
the /api/analytics router and the `testmcpy matrix | leaderboard |
flaky` CLI commands so both surfaces report identical numbers.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from testmcpy.models import QuestionResultModel, TestRunModel

# A cell needs at least this many runs before an intermittent result is
# called "flaky" rather than noise.
FLAKY_MIN_RUNS = 3

# Number of day buckets in a cell's trend sparkline.
TREND_BUCKETS = 7


def config_key(model: str, provider: str, mcp_profile_id: str | None = None) -> str:
    """Canonical label for a model/provider/profile combination."""
    key = f"{provider}/{model}"
    if mcp_profile_id:
        key = f"{key} @ {mcp_profile_id}"
    return key


def _pass_rate_expr() -> Any:
    """Portable AVG over a boolean column (0.0–1.0)."""
    return func.avg(case((QuestionResultModel.passed.is_(True), 1.0), else_=0.0))


def _apply_run_filters(
    query,
    suite_id: str | None,
    date_from: str | None,
    date_to: str | None,
):
    query = query.filter(TestRunModel.status == "completed")
    if suite_id:
        query = query.filter(TestRunModel.suite_id == suite_id)
    if date_from:
        query = query.filter(TestRunModel.started_at >= date_from)
    if date_to:
        query = query.filter(TestRunModel.started_at <= date_to)
    return query


def test_matrix(
    session: Session,
    suite_id: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    min_runs: int = 1,
    include_profile: bool = True,
    trend_buckets: int = TREND_BUCKETS,
) -> dict[str, Any]:
    """Per-question × per-config aggregation.

    Returns ``{"configs": [...], "rows": [...], "warnings": [...]}`` where
    each row carries one cell per config with n, pass_rate, flaky flag,
    avg score/cost/latency, and a day-bucketed pass-rate trend.
    """
    config_cols: list[Any] = [TestRunModel.model, TestRunModel.provider]
    if include_profile:
        config_cols.append(TestRunModel.mcp_profile_id)

    def cell_key(row) -> str:
        profile = row.mcp_profile_id if include_profile else None
        return config_key(row.model, row.provider, profile)

    group_cols = [QuestionResultModel.question_id, *config_cols]
    cells_query = _apply_run_filters(
        session.query(
            *group_cols,
            func.count(QuestionResultModel.id).label("n"),
            _pass_rate_expr().label("pass_rate"),
            func.avg(QuestionResultModel.score).label("avg_score"),
            func.avg(func.coalesce(QuestionResultModel.false_positive_rate, 0.0)).label(
                "avg_false_positive_rate"
            ),
            func.avg(func.coalesce(QuestionResultModel.cost_usd, 0.0)).label("avg_cost"),
            func.avg(func.coalesce(QuestionResultModel.duration_ms, 0)).label("avg_duration_ms"),
            func.max(TestRunModel.started_at).label("last_run_at"),
        ).join(TestRunModel, TestRunModel.run_id == QuestionResultModel.run_id),
        suite_id,
        date_from,
        date_to,
    ).group_by(*group_cols)

    # Day-bucketed pass rates for trend sparklines. started_at is an ISO
    # string, so the first 10 chars are the date — portable across
    # SQLite and Postgres.
    day_expr = func.substr(TestRunModel.started_at, 1, 10)
    trend_query = _apply_run_filters(
        session.query(
            *group_cols,
            day_expr.label("day"),
            _pass_rate_expr().label("pass_rate"),
        ).join(TestRunModel, TestRunModel.run_id == QuestionResultModel.run_id),
        suite_id,
        date_from,
        date_to,
    ).group_by(*group_cols, day_expr)

    trends: dict[tuple[str, str], list[tuple[str, float]]] = {}
    for row in trend_query:
        trends.setdefault((row.question_id, cell_key(row)), []).append(
            (row.day, round(row.pass_rate or 0.0, 4))
        )

    rows: dict[str, dict[str, Any]] = {}
    config_totals: dict[str, dict[str, Any]] = {}
    single_run_cells = 0

    for row in cells_query:
        key = cell_key(row)
        n = int(row.n or 0)
        if n < min_runs:
            continue
        pass_rate = round(row.pass_rate or 0.0, 4)
        flaky = 0.0 < pass_rate < 1.0 and n >= FLAKY_MIN_RUNS
        if n == 1:
            single_run_cells += 1

        trend_points = sorted(trends.get((row.question_id, key), []))[-trend_buckets:]
        rows.setdefault(row.question_id, {"question_id": row.question_id, "cells": {}})["cells"][
            key
        ] = {
            "n": n,
            "pass_rate": pass_rate,
            "flaky": flaky,
            "avg_score": round(row.avg_score or 0.0, 4),
            "avg_false_positive_rate": round(row.avg_false_positive_rate or 0.0, 4),
            "avg_cost": round(row.avg_cost or 0.0, 6),
            "avg_duration_ms": round(row.avg_duration_ms or 0.0, 1),
            "last_run_at": row.last_run_at,
            "trend": [rate for _, rate in trend_points],
        }

        totals = config_totals.setdefault(
            key,
            {
                "key": key,
                "model": row.model,
                "provider": row.provider,
                "mcp_profile": row.mcp_profile_id if include_profile else None,
                "n": 0,
                "passed_weight": 0.0,
                "score_weight": 0.0,
                "fp_weight": 0.0,
                "total_cost": 0.0,
                "flaky_cells": 0,
            },
        )
        totals["n"] += n
        totals["passed_weight"] += pass_rate * n
        totals["score_weight"] += (row.avg_score or 0.0) * n
        totals["fp_weight"] += (row.avg_false_positive_rate or 0.0) * n
        totals["total_cost"] += (row.avg_cost or 0.0) * n
        totals["flaky_cells"] += 1 if flaky else 0

    # Distinct completed-run counts per config (cells count question
    # results; the leaderboard wants whole runs).
    runs_query = _apply_run_filters(
        session.query(
            *config_cols,
            func.count(TestRunModel.run_id).label("n_runs"),
        ),
        suite_id,
        date_from,
        date_to,
    ).group_by(*config_cols)
    run_counts = {cell_key(row): int(row.n_runs or 0) for row in runs_query}

    configs = []
    for key, totals in sorted(config_totals.items()):
        n = totals["n"]
        configs.append(
            {
                "key": key,
                "model": totals["model"],
                "provider": totals["provider"],
                "mcp_profile": totals["mcp_profile"],
                "n_runs": run_counts.get(key, 0),
                "n_results": n,
                "pass_rate": round(totals["passed_weight"] / n, 4) if n else 0.0,
                "avg_score": round(totals["score_weight"] / n, 4) if n else 0.0,
                "avg_false_positive_rate": round(totals["fp_weight"] / n, 4) if n else 0.0,
                "total_cost": round(totals["total_cost"], 6),
                "flaky_cells": totals["flaky_cells"],
            }
        )

    warnings = []
    if single_run_cells:
        warnings.append(
            f"{single_run_cells} cell(s) have n=1 — single runs are noise, "
            f"re-run with `testmcpy bench --repeat {FLAKY_MIN_RUNS}` for signal"
        )

    return {
        "configs": configs,
        "rows": sorted(rows.values(), key=lambda r: r["question_id"]),
        "warnings": warnings,
    }


def leaderboard(
    session: Session,
    suite_id: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    include_profile: bool = True,
) -> list[dict[str, Any]]:
    """Configs ranked by pass rate, with cost-per-pass and latency."""
    matrix = test_matrix(
        session,
        suite_id=suite_id,
        date_from=date_from,
        date_to=date_to,
        include_profile=include_profile,
    )

    # Aggregate latency per config from the row cells.
    latency: dict[str, list[tuple[float, int]]] = {}
    passes: dict[str, float] = {}
    for row in matrix["rows"]:
        for key, cell in row["cells"].items():
            latency.setdefault(key, []).append((cell["avg_duration_ms"], cell["n"]))
            passes[key] = passes.get(key, 0.0) + cell["pass_rate"] * cell["n"]

    ranked = []
    for config in matrix["configs"]:
        key = config["key"]
        weighted = latency.get(key, [])
        total_n = sum(n for _, n in weighted)
        avg_duration = sum(duration * n for duration, n in weighted) / total_n if total_n else 0.0
        passed = passes.get(key, 0.0)
        ranked.append(
            {
                **config,
                "avg_duration_ms": round(avg_duration, 1),
                "cost_per_pass": round(config["total_cost"] / passed, 6) if passed else None,
            }
        )

    ranked.sort(key=lambda c: (-c["pass_rate"], c["cost_per_pass"] or float("inf")))
    return ranked


def question_history(
    session: Session,
    question_id: str,
    suite_id: str | None = None,
    model: str | None = None,
    provider: str | None = None,
    mcp_profile: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Chronological per-run points for one question (drill-down view)."""
    query = _apply_run_filters(
        session.query(
            QuestionResultModel.run_id,
            QuestionResultModel.passed,
            QuestionResultModel.score,
            QuestionResultModel.false_positive_rate,
            QuestionResultModel.cost_usd,
            QuestionResultModel.duration_ms,
            QuestionResultModel.error,
            TestRunModel.model,
            TestRunModel.provider,
            TestRunModel.mcp_profile_id,
            TestRunModel.started_at,
        )
        .join(TestRunModel, TestRunModel.run_id == QuestionResultModel.run_id)
        .filter(QuestionResultModel.question_id == question_id),
        suite_id,
        None,
        None,
    )
    if model:
        query = query.filter(TestRunModel.model == model)
    if provider:
        query = query.filter(TestRunModel.provider == provider)
    if mcp_profile:
        query = query.filter(TestRunModel.mcp_profile_id == mcp_profile)

    rows = query.order_by(TestRunModel.started_at.desc()).limit(limit).all()
    points = [
        {
            "run_id": row.run_id,
            "started_at": row.started_at,
            "passed": bool(row.passed),
            "score": round(row.score or 0.0, 4),
            "false_positive_rate": round(row.false_positive_rate or 0.0, 4),
            "cost_usd": round(row.cost_usd or 0.0, 6),
            "duration_ms": row.duration_ms or 0,
            "error": row.error,
            "model": row.model,
            "provider": row.provider,
            "mcp_profile": row.mcp_profile_id,
            "config": config_key(row.model, row.provider, row.mcp_profile_id),
        }
        for row in rows
    ]
    points.reverse()  # chronological
    return points


def flaky_tests(
    session: Session,
    suite_id: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    min_runs: int = FLAKY_MIN_RUNS,
) -> list[dict[str, Any]]:
    """Flaky question × config cells, sorted by how intermittent they are."""
    matrix = test_matrix(
        session,
        suite_id=suite_id,
        date_from=date_from,
        date_to=date_to,
        min_runs=min_runs,
    )
    flaky = []
    for row in matrix["rows"]:
        for key, cell in row["cells"].items():
            if cell["flaky"]:
                flaky.append(
                    {
                        "question_id": row["question_id"],
                        "config": key,
                        "n": cell["n"],
                        "pass_rate": cell["pass_rate"],
                        "last_run_at": cell["last_run_at"],
                    }
                )
    # Most intermittent first: pass rates near 0.5 are the flakiest.
    flaky.sort(key=lambda f: abs(f["pass_rate"] - 0.5))
    return flaky
