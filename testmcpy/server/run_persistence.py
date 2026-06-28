"""Incremental DB persistence for in-flight test runs.

Historically the WebSocket runner saved a run to the database only once,
at the very end (``save_test_run_to_file``) — a server crash at test 29/30
lost everything. ``RunRecord`` makes the DB the source of truth for
partial progress instead:

- ``begin()``   — creates the suite + a ``test_runs`` row (status=running)
  as soon as the run starts executing.
- ``append()``  — writes one ``question_results`` row per completed test.
- ``finish()``  — stamps the terminal status (completed/error/stopped) and
  the denormalized totals. Idempotent.

DB errors are swallowed (logged through the run's own log stream): a
persistence hiccup must degrade history, never kill a live run.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.exc import SQLAlchemyError

from testmcpy.storage import get_storage


def mint_run_id() -> str:
    """Legacy ``<8-hex>_<timestamp>`` run-id shape shared with the run
    registry and ``save_test_run_to_file`` so every code path mints
    correlatable identifiers."""
    return f"{uuid.uuid4().hex[:8]}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


def question_result_kwargs(r: dict[str, Any]) -> dict[str, Any]:
    """Map a TestResult.to_dict() shape onto ``save_question_result``
    kwargs. Single source of truth for the mapping — used by both the
    end-of-run ``save_test_run_to_file`` and the incremental ``RunRecord``.
    """
    # LLM providers report token_usage as {prompt, completion, total}
    # (see llm_integration.py); the old mapping read input/output and
    # silently stored 0 for every UI-triggered run. Keep input/output as
    # a fallback for callers of POST /api/results/save that adopted the
    # old keys.
    usage = r.get("token_usage") or {}
    return {
        "question_id": r.get("test_name", r.get("question_id", "unknown")),
        "passed": r.get("passed", False),
        "score": r.get("score", 0.0),
        # Pre-penalty mean so storage re-derives the final score without
        # double-penalising (falls back to ``score`` when absent).
        "base_score": r.get("base_score"),
        "answer": r.get("response", r.get("answer")),
        "tool_uses": r.get("tool_calls", r.get("tool_uses")),
        "tool_results": r.get("tool_results"),
        "tokens_input": usage.get("prompt", usage.get("input", 0)),
        "tokens_output": usage.get("completion", usage.get("output", 0)),
        "duration_ms": int(r.get("duration", 0) * 1000),
        "evaluations": r.get("evaluations"),
        "error": r.get("error"),
        "cost_usd": r.get("cost", r.get("cost_usd", 0.0)),
    }


def ui_result_from_question_result(q: dict[str, Any]) -> dict[str, Any]:
    """Inverse of ``question_result_kwargs``: map a stored question_results
    row (as returned by ``storage.get_run``) back onto the TestResult
    wire shape the UI's test_complete / all_complete handlers expect —
    including the live {prompt, completion, total} token_usage keys the
    client sums (TestRunContext reads token_usage.total)."""
    tokens_in = q.get("tokens_input", 0) or 0
    tokens_out = q.get("tokens_output", 0) or 0
    return {
        "test_name": q.get("question_id"),
        "passed": bool(q.get("passed")),
        "score": q.get("score", 0.0),
        "response": q.get("answer"),
        "tool_calls": q.get("tool_uses") or [],
        "tool_results": q.get("tool_results") or [],
        "token_usage": {
            "prompt": tokens_in,
            "completion": tokens_out,
            "total": tokens_in + tokens_out,
        },
        "duration": (q.get("duration_ms") or 0) / 1000,
        "evaluations": q.get("evaluations") or [],
        "error": q.get("error"),
        "cost": q.get("cost_usd", 0.0) or 0.0,
    }


# DB statuses that map straight onto the wire's terminal statuses. A DB
# row still 'running' (or already 'interrupted') with no registry handle
# means the server died mid-run — report it as interrupted.
_TERMINAL_WIRE_STATUS = {"completed": "completed", "stopped": "stopped", "error": "error"}


def wire_status_for_db_status(db_status: str | None) -> str:
    """Map a test_runs.status onto the WebSocket/REST wire status for a
    run that is NOT in the in-memory registry: terminal statuses pass
    through, anything else (running / interrupted / NULL / unknown) means
    the owning process died mid-run — interrupted."""
    return _TERMINAL_WIRE_STATUS.get(db_status or "", "interrupted")


def history_replay_messages(record: dict[str, Any]) -> list[dict[str, Any]]:
    """Synthesize the WebSocket message sequence for attaching to a run
    that's no longer in the in-memory registry (GC'd after CLEANUP_TTL,
    or lost to a server restart) but lives in the results DB: a
    ``run_started`` marker, one ``test_complete`` per stored result (so
    the UI rebuilds its per-test panels), and a terminal ``all_complete``
    carrying the run's real status — including ``interrupted`` with
    partial results for runs that died mid-flight."""
    status = wire_status_for_db_status(record.get("status"))
    results = [ui_result_from_question_result(q) for q in record.get("question_results", [])]
    passed = sum(1 for r in results if r["passed"])
    summary = {
        "total": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "total_cost": sum(r["cost"] for r in results),
        "status": status,
    }
    return [
        {
            "type": "run_started",
            "run_id": record.get("run_id"),
            "kind": "single",
            "reattached": True,
            "status": status,
            "source": "history",
        },
        *({"type": "test_complete", "test_name": r["test_name"], "result": r} for r in results),
        {"type": "all_complete", "status": status, "summary": summary, "results": results},
    ]


class RunRecord:
    """Write-through record of one run (one YAML file) in the results DB.

    All writes are best-effort: a failure marks the record broken and is
    reported once through ``log``, after which subsequent calls no-op so
    a flaky DB doesn't spam the run log or slow the run down.
    """

    def __init__(self, run_id: str | None = None, log: Callable[[str], None] | None = None):
        self.run_id = run_id or mint_run_id()
        self._log = log or (lambda msg: None)
        self._began = False
        self._finished = False
        self._broken = False

    def _report_db_error(self, op: str, exc: SQLAlchemyError) -> None:
        self._broken = True
        self._log(f"⚠️ Results DB unavailable ({op}): {exc} — run continues without history")

    def begin(
        self,
        *,
        test_file: str,
        model: str,
        provider: str,
        mcp_profile: str | None = None,
        llm_profile: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Create the suite + the run row (status=running) up front."""
        if self._began or self._broken:
            return
        try:
            storage = get_storage()
            storage.save_suite(suite_id=test_file, name=test_file, questions=[])
            storage.save_run(
                run_id=self.run_id,
                test_id=test_file,
                test_version=1,
                model=model,
                provider=provider,
                started_at=datetime.now(timezone.utc).isoformat(),
                mcp_profile_id=mcp_profile,
                llm_profile_id=llm_profile,
                metadata=metadata,
            )
            self._began = True
        except SQLAlchemyError as exc:
            self._report_db_error("begin", exc)

    def append(self, result: dict[str, Any]) -> None:
        """Persist one completed test immediately (crash-safe progress)."""
        if not self._began or self._finished or self._broken:
            return
        try:
            get_storage().save_question_result(run_id=self.run_id, **question_result_kwargs(result))
        except SQLAlchemyError as exc:
            self._report_db_error("append", exc)

    def finish(self, status: str) -> None:
        """Stamp the terminal status + denormalized totals. Idempotent —
        the first terminal status wins (e.g. ``stopped`` from the cancel
        path must not be overwritten by a later generic finalizer)."""
        if not self._began or self._finished or self._broken:
            return
        try:
            get_storage().finish_run(
                self.run_id, status=status, completed_at=datetime.now(timezone.utc).isoformat()
            )
            self._finished = True
        except SQLAlchemyError as exc:
            self._report_db_error("finish", exc)
