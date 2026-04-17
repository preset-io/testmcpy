"""
API routes for side-by-side comparison of test runs.

Returns per-test pass/fail matrix for comparing runs across models.
"""

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from testmcpy.storage import get_storage

router = APIRouter(prefix="/api/compare", tags=["compare"])


class CompareRequest(BaseModel):
    """Request body for comparing multiple test runs."""

    run_ids: list[str]


@router.post("")
async def compare_runs(request: CompareRequest) -> dict[str, Any]:
    """
    Compare multiple test runs side by side.

    Takes an array of run_ids and returns a per-test pass/fail matrix.
    Each cell contains: pass/fail status, score, response time, and answer snippet.
    """
    if len(request.run_ids) < 2:
        raise HTTPException(status_code=400, detail="At least 2 run IDs required for comparison")

    storage = get_storage()

    # Load all runs
    runs_data = []
    for run_id in request.run_ids:
        run = storage.get_run(run_id)
        if not run:
            raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
        runs_data.append(run)

    # Build column metadata (one per run)
    columns = []
    for run in runs_data:
        total = run["summary"]["total"]
        passed = run["summary"]["passed"]
        columns.append(
            {
                "run_id": run["run_id"],
                "test_id": run["test_id"],
                "model": run["model"],
                "provider": run["provider"],
                "started_at": run["started_at"],
                "total": total,
                "passed": passed,
                "failed": total - passed,
                "pass_rate": round((passed / total * 100) if total > 0 else 0, 1),
            }
        )

    # Build per-test matrix
    # Collect all unique question IDs across all runs
    all_question_ids: list[str] = []
    seen: set[str] = set()
    for run in runs_data:
        for qr in run.get("question_results", []):
            qid = qr["question_id"]
            if qid not in seen:
                all_question_ids.append(qid)
                seen.add(qid)

    # Build rows: one per question
    rows = []
    for qid in all_question_ids:
        cells = {}
        for run in runs_data:
            # Find this question in the run
            match = None
            for qr in run.get("question_results", []):
                if qr["question_id"] == qid:
                    match = qr
                    break

            if match:
                answer_snippet = (match.get("answer") or "")[:200]
                cells[run["run_id"]] = {
                    "status": "pass" if match["passed"] else "fail",
                    "passed": match["passed"],
                    "score": match["score"],
                    "duration_ms": match["duration_ms"],
                    "error": match.get("error"),
                    "answer_snippet": answer_snippet,
                    "tokens_input": match.get("tokens_input", 0),
                    "tokens_output": match.get("tokens_output", 0),
                }
            else:
                cells[run["run_id"]] = {
                    "status": "missing",
                    "passed": None,
                    "score": None,
                    "duration_ms": None,
                    "error": None,
                    "answer_snippet": None,
                    "tokens_input": 0,
                    "tokens_output": 0,
                }

        # Detect regressions/improvements between consecutive runs
        run_ids_ordered = [r["run_id"] for r in runs_data]
        for i in range(1, len(run_ids_ordered)):
            prev_id = run_ids_ordered[i - 1]
            curr_id = run_ids_ordered[i]
            prev_cell = cells.get(prev_id, {})
            curr_cell = cells.get(curr_id, {})

            if prev_cell.get("passed") and not curr_cell.get("passed"):
                curr_cell["change"] = "regression"
            elif not prev_cell.get("passed") and curr_cell.get("passed"):
                curr_cell["change"] = "improvement"
            elif prev_cell.get("status") == "missing" or curr_cell.get("status") == "missing":
                curr_cell["change"] = "new"
            else:
                curr_cell["change"] = "same"

        rows.append(
            {
                "question_id": qid,
                "cells": cells,
            }
        )

    return {
        "columns": columns,
        "rows": rows,
        "total_questions": len(rows),
    }
