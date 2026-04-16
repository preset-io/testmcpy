"""
SQLAlchemy-based storage for testmcpy.

Provides:
- Test file version tracking (legacy)
- Test result history (legacy)
- Test suite and run management
- Smoke report storage
- Generation log storage
- Metrics aggregation and trends
"""

import hashlib
import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, func, text
from sqlalchemy.orm import Session, sessionmaker

from testmcpy.models import (
    Base,
    GenerationLLMCallModel,
    GenerationLogModel,
    QuestionResultModel,
    SmokeReportModel,
    SmokeReportResultModel,
    TestResultModel,
    TestRunModel,
    TestSuiteModel,
    TestVersionModel,
)


# Legacy dataclasses kept for backward compatibility with callers
@dataclass
class TestVersion:
    """A version of a test file."""

    id: int | None
    test_path: str
    version: int
    content_hash: str
    content: str
    created_at: str
    message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TestResult:
    """A test execution result."""

    id: int | None
    test_path: str
    test_name: str
    version_id: int | None
    passed: bool
    score: float
    duration: float
    cost: float
    tokens_used: int
    model: str
    provider: str
    error: str | None
    evaluations: str  # JSON string
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["evaluations"] = json.loads(d["evaluations"]) if d["evaluations"] else []
        return d


class TestStorage:
    """SQLAlchemy-based storage for test versioning, results, and metrics."""

    def __init__(self, db_path: str | Path | None = None):
        if db_path is None:
            db_path = os.environ.get("TESTMCPY_DB_PATH")
        if db_path is None:
            db_dir = Path.cwd() / ".testmcpy"
            db_dir.mkdir(exist_ok=True)
            db_path = db_dir / "storage.db"

        self.db_path = Path(db_path)
        url = f"sqlite:///{self.db_path}"
        self._engine = create_engine(
            url,
            connect_args={"check_same_thread": False},
            echo=False,
        )
        self._SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self._engine)
        # Ensure all tables exist (safe for existing DBs)
        Base.metadata.create_all(bind=self._engine)

    def _session(self) -> Session:
        return self._SessionLocal()

    def _hash_content(self, content: str) -> str:
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    # ==================== Version Management (legacy) ====================

    def save_version(self, test_path: str, content: str, message: str | None = None) -> TestVersion:
        """Save a new version of a test file. Only creates if content changed."""
        content_hash = self._hash_content(content)

        with self._session() as session:
            # Check if this exact content already exists
            existing = (
                session.query(TestVersionModel)
                .filter_by(test_path=test_path, content_hash=content_hash)
                .order_by(TestVersionModel.version.desc())
                .first()
            )

            if existing:
                return TestVersion(
                    id=existing.id,
                    test_path=existing.test_path,
                    version=existing.version,
                    content_hash=existing.content_hash,
                    content=existing.content,
                    created_at=existing.created_at,
                    message=existing.message,
                )

            # Get next version number
            max_version = (
                session.query(func.max(TestVersionModel.version))
                .filter_by(test_path=test_path)
                .scalar()
            )
            next_version = (max_version or 0) + 1
            now = datetime.now(timezone.utc).isoformat()

            model = TestVersionModel(
                test_path=test_path,
                version=next_version,
                content_hash=content_hash,
                content=content,
                message=message,
                created_at=now,
            )
            session.add(model)
            session.commit()
            session.refresh(model)

            return TestVersion(
                id=model.id,
                test_path=test_path,
                version=next_version,
                content_hash=content_hash,
                content=content,
                created_at=now,
                message=message,
            )

    def get_versions(self, test_path: str, limit: int = 50) -> list[TestVersion]:
        with self._session() as session:
            rows = (
                session.query(TestVersionModel)
                .filter_by(test_path=test_path)
                .order_by(TestVersionModel.version.desc())
                .limit(limit)
                .all()
            )
            return [
                TestVersion(
                    id=r.id,
                    test_path=r.test_path,
                    version=r.version,
                    content_hash=r.content_hash,
                    content=r.content,
                    created_at=r.created_at,
                    message=r.message,
                )
                for r in rows
            ]

    def get_version(self, test_path: str, version: int) -> TestVersion | None:
        with self._session() as session:
            r = (
                session.query(TestVersionModel)
                .filter_by(test_path=test_path, version=version)
                .first()
            )
            if not r:
                return None
            return TestVersion(
                id=r.id,
                test_path=r.test_path,
                version=r.version,
                content_hash=r.content_hash,
                content=r.content,
                created_at=r.created_at,
                message=r.message,
            )

    def get_latest_version(self, test_path: str) -> TestVersion | None:
        versions = self.get_versions(test_path, limit=1)
        return versions[0] if versions else None

    def diff_versions(self, test_path: str, version1: int, version2: int) -> dict[str, Any]:
        import difflib

        v1 = self.get_version(test_path, version1)
        v2 = self.get_version(test_path, version2)

        if not v1 or not v2:
            return {"error": "Version not found"}

        diff = list(
            difflib.unified_diff(
                v1.content.splitlines(keepends=True),
                v2.content.splitlines(keepends=True),
                fromfile=f"v{version1}",
                tofile=f"v{version2}",
            )
        )

        return {
            "version1": version1,
            "version2": version2,
            "diff": "".join(diff),
            "v1_hash": v1.content_hash,
            "v2_hash": v2.content_hash,
        }

    # ==================== Result Storage (legacy) ====================

    def save_result(
        self,
        test_path: str,
        test_name: str,
        passed: bool,
        duration: float = 0.0,
        cost: float = 0.0,
        tokens_used: int = 0,
        model: str = "",
        provider: str = "",
        error: str | None = None,
        evaluations: list[dict] | None = None,
        score: float = 0.0,
        version_id: int | None = None,
    ) -> TestResult:
        now = datetime.now(timezone.utc).isoformat()
        evaluations_json = json.dumps(evaluations or [])

        with self._session() as session:
            model_obj = TestResultModel(
                test_path=test_path,
                test_name=test_name,
                version_id=version_id,
                passed=passed,
                score=score,
                duration=duration,
                cost=cost,
                tokens_used=tokens_used,
                model=model,
                provider=provider,
                error=error,
                evaluations=evaluations_json,
                created_at=now,
            )
            session.add(model_obj)
            session.commit()
            session.refresh(model_obj)

            return TestResult(
                id=model_obj.id,
                test_path=test_path,
                test_name=test_name,
                version_id=version_id,
                passed=passed,
                score=score,
                duration=duration,
                cost=cost,
                tokens_used=tokens_used,
                model=model,
                provider=provider,
                error=error,
                evaluations=evaluations_json,
                created_at=now,
            )

    def get_results(
        self,
        test_path: str | None = None,
        test_name: str | None = None,
        model: str | None = None,
        limit: int = 100,
        since: str | None = None,
    ) -> list[TestResult]:
        with self._session() as session:
            query = session.query(TestResultModel)

            if test_path:
                query = query.filter(TestResultModel.test_path == test_path)
            if test_name:
                query = query.filter(TestResultModel.test_name == test_name)
            if model:
                query = query.filter(TestResultModel.model == model)
            if since:
                query = query.filter(TestResultModel.created_at >= since)

            rows = query.order_by(TestResultModel.created_at.desc()).limit(limit).all()

            return [
                TestResult(
                    id=r.id,
                    test_path=r.test_path,
                    test_name=r.test_name,
                    version_id=r.version_id,
                    passed=bool(r.passed),
                    score=r.score,
                    duration=r.duration,
                    cost=r.cost,
                    tokens_used=r.tokens_used,
                    model=r.model,
                    provider=r.provider,
                    error=r.error,
                    evaluations=r.evaluations,
                    created_at=r.created_at,
                )
                for r in rows
            ]

    # ==================== Metrics & Analytics ====================

    def get_pass_rate(
        self,
        test_path: str | None = None,
        model: str | None = None,
        days: int = 30,
    ) -> dict[str, Any]:
        since = (
            datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
            - timedelta(days=days)
        ).isoformat()

        with self._session() as session:
            query = session.query(
                func.count().label("total"),
                func.sum(func.iif(TestResultModel.passed, 1, 0)).label("passed"),
                func.avg(TestResultModel.score).label("avg_score"),
                func.avg(TestResultModel.duration).label("avg_duration"),
                func.sum(TestResultModel.cost).label("total_cost"),
                func.sum(TestResultModel.tokens_used).label("total_tokens"),
            ).filter(TestResultModel.created_at >= since)

            if test_path:
                query = query.filter(TestResultModel.test_path == test_path)
            if model:
                query = query.filter(TestResultModel.model == model)

            row = query.one()
            total = row.total or 0
            passed = row.passed or 0

            return {
                "total": total,
                "passed": passed,
                "failed": total - passed,
                "pass_rate": (passed / total * 100) if total > 0 else 0,
                "avg_score": row.avg_score or 0,
                "avg_duration": row.avg_duration or 0,
                "total_cost": row.total_cost or 0,
                "total_tokens": row.total_tokens or 0,
                "period_days": days,
            }

    def get_trends(
        self,
        test_path: str | None = None,
        model: str | None = None,
        days: int = 30,
        group_by: str = "day",
    ) -> list[dict[str, Any]]:
        since = (
            datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
            - timedelta(days=days)
        ).isoformat()

        # SQLite date grouping
        if group_by == "hour":
            date_expr = func.strftime("%Y-%m-%d %H:00", TestResultModel.created_at)
        elif group_by == "week":
            date_expr = func.strftime("%Y-W%W", TestResultModel.created_at)
        else:
            date_expr = func.date(TestResultModel.created_at)

        with self._session() as session:
            query = session.query(
                date_expr.label("period"),
                func.count().label("total"),
                func.sum(func.iif(TestResultModel.passed, 1, 0)).label("passed"),
                func.avg(TestResultModel.score).label("avg_score"),
                func.avg(TestResultModel.duration).label("avg_duration"),
                func.sum(TestResultModel.cost).label("total_cost"),
            ).filter(TestResultModel.created_at >= since)

            if test_path:
                query = query.filter(TestResultModel.test_path == test_path)
            if model:
                query = query.filter(TestResultModel.model == model)

            rows = query.group_by("period").order_by("period").all()

            return [
                {
                    "period": row.period,
                    "total": row.total,
                    "passed": row.passed or 0,
                    "failed": row.total - (row.passed or 0),
                    "pass_rate": (
                        (row.passed / row.total * 100) if row.total > 0 and row.passed else 0
                    ),
                    "avg_score": row.avg_score or 0,
                    "avg_duration": row.avg_duration or 0,
                    "total_cost": row.total_cost or 0,
                }
                for row in rows
            ]

    def get_model_comparison(self, days: int = 30) -> list[dict[str, Any]]:
        since = (
            datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
            - timedelta(days=days)
        ).isoformat()

        with self._session() as session:
            rows = (
                session.query(
                    TestResultModel.model,
                    TestResultModel.provider,
                    func.count().label("total"),
                    func.sum(func.iif(TestResultModel.passed, 1, 0)).label("passed"),
                    func.avg(TestResultModel.score).label("avg_score"),
                    func.avg(TestResultModel.duration).label("avg_duration"),
                    func.sum(TestResultModel.cost).label("total_cost"),
                    func.sum(TestResultModel.tokens_used).label("total_tokens"),
                )
                .filter(
                    TestResultModel.created_at >= since,
                    TestResultModel.model.isnot(None),
                    TestResultModel.model != "",
                )
                .group_by(TestResultModel.model, TestResultModel.provider)
                .order_by(text("passed DESC, avg_score DESC"))
                .all()
            )

            return [
                {
                    "model": row.model,
                    "provider": row.provider,
                    "total": row.total,
                    "passed": row.passed or 0,
                    "failed": row.total - (row.passed or 0),
                    "pass_rate": (
                        (row.passed / row.total * 100) if row.total > 0 and row.passed else 0
                    ),
                    "avg_score": row.avg_score or 0,
                    "avg_duration": row.avg_duration or 0,
                    "total_cost": row.total_cost or 0,
                    "total_tokens": row.total_tokens or 0,
                }
                for row in rows
            ]

    def get_failing_tests(self, days: int = 7, min_failures: int = 2) -> list[dict[str, Any]]:
        since = (
            datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
            - timedelta(days=days)
        ).isoformat()

        with self._session() as session:
            failures_col = func.sum(func.iif(TestResultModel.passed, 0, 1)).label("failures")

            rows = (
                session.query(
                    TestResultModel.test_path,
                    TestResultModel.test_name,
                    func.count().label("total"),
                    failures_col,
                    func.max(TestResultModel.error).label("last_error"),
                    func.max(TestResultModel.created_at).label("last_run"),
                )
                .filter(TestResultModel.created_at >= since)
                .group_by(TestResultModel.test_path, TestResultModel.test_name)
                .having(failures_col >= min_failures)
                .order_by(text("failures DESC"))
                .all()
            )

            return [
                {
                    "test_path": row.test_path,
                    "test_name": row.test_name,
                    "total": row.total,
                    "failures": row.failures,
                    "failure_rate": ((row.failures / row.total * 100) if row.total > 0 else 0),
                    "last_error": row.last_error,
                    "last_run": row.last_run,
                }
                for row in rows
            ]

    # ==================== Test Suite Management ====================

    def save_suite(
        self,
        suite_id: str,
        name: str,
        questions: list[dict],
        environment_id: str | None = None,
        description: str | None = None,
        metadata: dict | None = None,
    ) -> dict[str, Any]:
        questions_json = json.dumps(questions, sort_keys=True)
        content_hash = self._hash_content(questions_json)
        now = datetime.now(timezone.utc)

        with self._session() as session:
            existing = session.query(TestSuiteModel).filter_by(suite_id=suite_id).first()

            if existing:
                if existing.content_hash == content_hash:
                    return self._suite_to_dict(existing)

                existing.name = name
                existing.version = existing.version + 1
                existing.environment_id = environment_id
                existing.description = description
                existing.content_hash = content_hash
                existing.questions = questions
                existing.metadata_ = metadata
                existing.updated_at = now
                session.commit()
                session.refresh(existing)
                return self._suite_to_dict(existing)
            else:
                model = TestSuiteModel(
                    suite_id=suite_id,
                    name=name,
                    version=1,
                    environment_id=environment_id,
                    description=description,
                    content_hash=content_hash,
                    questions=questions,
                    metadata_=metadata,
                    created_at=now,
                    updated_at=now,
                )
                session.add(model)
                session.commit()
                session.refresh(model)
                return self._suite_to_dict(model)

    def _suite_to_dict(self, m: TestSuiteModel) -> dict[str, Any]:
        created = (
            m.created_at.isoformat() if isinstance(m.created_at, datetime) else str(m.created_at)
        )
        updated = (
            m.updated_at.isoformat() if isinstance(m.updated_at, datetime) else str(m.updated_at)
        )
        return {
            "id": m.suite_id,
            "name": m.name,
            "version": m.version,
            "environment_id": m.environment_id,
            "description": m.description,
            "questions": m.questions if isinstance(m.questions, list) else json.loads(m.questions),
            "metadata": m.metadata_ or {},
            "tags": m.tags or [],
            "created_at": created,
            "updated_at": updated,
        }

    def get_suite(self, suite_id: str) -> dict[str, Any] | None:
        with self._session() as session:
            m = session.query(TestSuiteModel).filter_by(suite_id=suite_id).first()
            if not m:
                return None
            return self._suite_to_dict(m)

    def list_suites(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._session() as session:
            rows = (
                session.query(TestSuiteModel)
                .order_by(TestSuiteModel.updated_at.desc())
                .limit(limit)
                .all()
            )

            results = []
            for m in rows:
                q = m.questions if isinstance(m.questions, list) else json.loads(m.questions)
                created = (
                    m.created_at.isoformat()
                    if isinstance(m.created_at, datetime)
                    else str(m.created_at)
                )
                updated = (
                    m.updated_at.isoformat()
                    if isinstance(m.updated_at, datetime)
                    else str(m.updated_at)
                )
                results.append(
                    {
                        "id": m.suite_id,
                        "name": m.name,
                        "version": m.version,
                        "environment_id": m.environment_id,
                        "description": m.description,
                        "question_count": len(q),
                        "created_at": created,
                        "updated_at": updated,
                    }
                )
            return results

    # ==================== Test Run Management ====================

    def save_run(
        self,
        run_id: str,
        test_id: str,
        test_version: int,
        model: str,
        provider: str,
        started_at: str,
        environment_id: str | None = None,
        runner_tool: str = "mcp-client",
        mcp_setup_version: str | None = None,
        metadata: dict | None = None,
        mcp_profile_id: str | None = None,
        llm_profile_id: str | None = None,
    ) -> None:
        with self._session() as session:
            run = TestRunModel(
                run_id=run_id,
                suite_id=test_id,
                suite_version=test_version,
                environment_id=environment_id,
                model=model,
                provider=provider,
                mcp_profile_id=mcp_profile_id,
                llm_profile_id=llm_profile_id,
                runner_tool=runner_tool,
                mcp_setup_version=mcp_setup_version,
                status="running",
                started_at=started_at,
                metadata_=metadata,
                created_at=datetime.now(timezone.utc),
            )
            session.add(run)
            session.commit()

    def complete_run(self, run_id: str, completed_at: str) -> None:
        with self._session() as session:
            run = session.query(TestRunModel).filter_by(run_id=run_id).first()
            if run:
                run.completed_at = completed_at
                run.status = "completed"
                # Compute denormalized totals
                results = session.query(QuestionResultModel).filter_by(run_id=run_id).all()
                run.total_tokens = sum(
                    (r.tokens_input or 0) + (r.tokens_output or 0) for r in results
                )
                session.commit()

    def save_question_result(
        self,
        run_id: str,
        question_id: str,
        passed: bool,
        score: float = 0.0,
        answer: str | None = None,
        tool_uses: list | None = None,
        tool_results: list | None = None,
        tokens_input: int = 0,
        tokens_output: int = 0,
        tti_ms: int | None = None,
        duration_ms: int = 0,
        evaluations: list | None = None,
        error: str | None = None,
    ) -> None:
        with self._session() as session:
            result = QuestionResultModel(
                run_id=run_id,
                question_id=question_id,
                answer=answer,
                tool_uses=tool_uses,
                tool_results=tool_results,
                tokens_input=tokens_input,
                tokens_output=tokens_output,
                tti_ms=tti_ms,
                duration_ms=duration_ms,
                evaluations=evaluations,
                score=score,
                passed=passed,
                error=error,
                created_at=datetime.now(timezone.utc),
            )
            session.add(result)
            session.commit()

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self._session() as session:
            run = session.query(TestRunModel).filter_by(run_id=run_id).first()
            if not run:
                return None

            questions = (
                session.query(QuestionResultModel)
                .filter_by(run_id=run_id)
                .order_by(QuestionResultModel.id)
                .all()
            )

            question_results = [
                {
                    "question_id": q.question_id,
                    "answer": q.answer,
                    "tool_uses": q.tool_uses or [],
                    "tool_results": q.tool_results or [],
                    "tokens_input": q.tokens_input,
                    "tokens_output": q.tokens_output,
                    "tti_ms": q.tti_ms,
                    "duration_ms": q.duration_ms,
                    "evaluations": q.evaluations or [],
                    "score": q.score,
                    "passed": bool(q.passed),
                    "error": q.error,
                }
                for q in questions
            ]

            total = len(question_results)
            passed = sum(1 for q in question_results if q["passed"])

            return {
                "run_id": run.run_id,
                "test_id": run.suite_id,
                "test_version": run.suite_version,
                "environment_id": run.environment_id,
                "model": run.model,
                "provider": run.provider,
                "runner_tool": run.runner_tool,
                "mcp_setup_version": run.mcp_setup_version,
                "started_at": run.started_at,
                "completed_at": run.completed_at,
                "metadata": run.metadata_ or {},
                "question_results": question_results,
                "summary": {
                    "total": total,
                    "passed": passed,
                    "failed": total - passed,
                    "pass_rate": (passed / total * 100) if total > 0 else 0,
                    "total_tokens": sum(
                        q["tokens_input"] + q["tokens_output"] for q in question_results
                    ),
                    "total_duration_ms": sum(q["duration_ms"] for q in question_results),
                },
            }

    def list_runs(
        self,
        test_id: str | None = None,
        model: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        with self._session() as session:
            query = session.query(
                TestRunModel.run_id,
                TestRunModel.suite_id,
                TestRunModel.suite_version,
                TestRunModel.environment_id,
                TestRunModel.model,
                TestRunModel.provider,
                TestRunModel.runner_tool,
                TestRunModel.started_at,
                TestRunModel.completed_at,
                func.count(QuestionResultModel.id).label("total_questions"),
                func.sum(func.iif(QuestionResultModel.passed, 1, 0)).label("passed_questions"),
            ).outerjoin(
                QuestionResultModel,
                TestRunModel.run_id == QuestionResultModel.run_id,
            )

            if test_id:
                query = query.filter(TestRunModel.suite_id == test_id)
            if model:
                query = query.filter(TestRunModel.model == model)

            rows = (
                query.group_by(TestRunModel.run_id)
                .order_by(TestRunModel.started_at.desc())
                .limit(limit)
                .all()
            )

            return [
                {
                    "run_id": row.run_id,
                    "test_id": row.suite_id,
                    "test_version": row.suite_version,
                    "environment_id": row.environment_id,
                    "model": row.model,
                    "provider": row.provider,
                    "runner_tool": row.runner_tool,
                    "started_at": row.started_at,
                    "completed_at": row.completed_at,
                    "total_questions": row.total_questions,
                    "passed_questions": row.passed_questions or 0,
                    "pass_rate": (
                        (row.passed_questions / row.total_questions * 100)
                        if row.total_questions > 0 and row.passed_questions
                        else 0
                    ),
                }
                for row in rows
            ]

    # ==================== Smoke Reports ====================

    def save_smoke_report(self, report_data: dict[str, Any]) -> str:
        """Save a smoke report to DB. Returns report_id."""
        import uuid as _uuid

        report_id = report_data.get("report_id") or str(_uuid.uuid4())[
            :8
        ] + "_" + datetime.now().strftime("%Y%m%d_%H%M%S")
        now = datetime.now(timezone.utc)

        with self._session() as session:
            report = SmokeReportModel(
                report_id=report_id,
                profile_id=report_data.get("profile_id"),
                profile_name=report_data.get("profile_name"),
                server_url=report_data.get("server_url"),
                total_tests=report_data.get("total_tests", 0),
                passed=report_data.get("passed", 0),
                failed=report_data.get("failed", 0),
                success_rate=report_data.get("success_rate", 0.0),
                duration_ms=report_data.get("duration_ms", 0),
                created_at=now,
            )
            session.add(report)

            # Save individual tool results
            for result in report_data.get("results", []):
                tool_result = SmokeReportResultModel(
                    report_id=report_id,
                    tool_name=result.get("test_name") or result.get("tool_name", "unknown"),
                    success=result.get("success", False),
                    duration_ms=result.get("duration_ms", 0),
                    error_message=result.get("error_message"),
                    tool_input=result.get("tool_input"),
                    tool_output=result.get("tool_output"),
                    tool_schema=result.get("tool_schema"),
                    details=result.get("details"),
                )
                session.add(tool_result)

            session.commit()

        return report_id

    def get_smoke_report(self, report_id: str) -> dict[str, Any] | None:
        with self._session() as session:
            report = session.query(SmokeReportModel).filter_by(report_id=report_id).first()
            if not report:
                return None

            results = session.query(SmokeReportResultModel).filter_by(report_id=report_id).all()

            return {
                "report_id": report.report_id,
                "profile_id": report.profile_id,
                "profile_name": report.profile_name,
                "server_url": report.server_url,
                "timestamp": report.created_at.isoformat()
                if isinstance(report.created_at, datetime)
                else str(report.created_at),
                "saved_at": report.created_at.isoformat()
                if isinstance(report.created_at, datetime)
                else str(report.created_at),
                "total_tests": report.total_tests,
                "passed": report.passed,
                "failed": report.failed,
                "success_rate": report.success_rate,
                "duration_ms": report.duration_ms,
                "results": [
                    {
                        "test_name": r.tool_name,
                        "success": bool(r.success),
                        "duration_ms": r.duration_ms,
                        "error_message": r.error_message,
                        "tool_input": r.tool_input,
                        "tool_output": r.tool_output,
                        "tool_schema": r.tool_schema,
                        "details": r.details,
                    }
                    for r in results
                ],
            }

    def list_smoke_reports(
        self,
        server_url: str | None = None,
        profile_id: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        with self._session() as session:
            query = session.query(SmokeReportModel)

            if server_url:
                query = query.filter(SmokeReportModel.server_url == server_url)
            if profile_id:
                query = query.filter(SmokeReportModel.profile_id == profile_id)

            rows = query.order_by(SmokeReportModel.created_at.desc()).limit(limit).all()

            return [
                {
                    "report_id": r.report_id,
                    "server_url": r.server_url,
                    "profile_id": r.profile_id,
                    "profile_name": r.profile_name,
                    "timestamp": r.created_at.isoformat()
                    if isinstance(r.created_at, datetime)
                    else str(r.created_at),
                    "saved_at": r.created_at.isoformat()
                    if isinstance(r.created_at, datetime)
                    else str(r.created_at),
                    "total_tests": r.total_tests,
                    "passed": r.passed,
                    "failed": r.failed,
                    "success_rate": r.success_rate,
                    "duration_ms": r.duration_ms,
                }
                for r in rows
            ]

    def delete_smoke_report(self, report_id: str) -> bool:
        with self._session() as session:
            report = session.query(SmokeReportModel).filter_by(report_id=report_id).first()
            if not report:
                return False
            session.delete(report)  # cascade deletes results
            session.commit()
            return True

    def clear_smoke_reports(self) -> int:
        with self._session() as session:
            # Delete child rows first, then parents
            count = session.query(SmokeReportModel).count()
            session.query(SmokeReportResultModel).delete()
            session.query(SmokeReportModel).delete()
            session.commit()
            return count

    # ==================== Generation Logs ====================

    def save_generation_log(self, log_data: dict[str, Any]) -> str:
        """Save a generation log to DB. Returns log_id."""
        import uuid as _uuid

        metadata = log_data.get("metadata", log_data)
        log_id = metadata.get("log_id") or str(_uuid.uuid4())[:8] + "_" + datetime.now().strftime(
            "%Y%m%d_%H%M%S"
        )
        now = datetime.now(timezone.utc)

        with self._session() as session:
            log = GenerationLogModel(
                log_id=log_id,
                tool_name=metadata.get("tool_name", "unknown"),
                tool_description=metadata.get("tool_description"),
                coverage_level=metadata.get("coverage_level"),
                provider=metadata.get("provider"),
                model=metadata.get("model"),
                success=metadata.get("success", False),
                test_count=metadata.get("test_count", 0),
                total_cost=metadata.get("total_cost", 0.0),
                output_file=metadata.get("output_file"),
                tool_schema=log_data.get("tool_schema"),
                generated_yaml=log_data.get("generated_yaml"),
                error=metadata.get("error"),
                created_at=now,
            )
            session.add(log)

            # Save individual LLM calls
            for i, call in enumerate(log_data.get("llm_calls", [])):
                llm_call = GenerationLLMCallModel(
                    log_id=log_id,
                    step=call.get("step", i),
                    prompt=call.get("prompt"),
                    response=call.get("response"),
                    cost=call.get("cost", 0.0),
                    tokens=call.get("tokens", 0),
                    duration_ms=int(call.get("duration", 0) * 1000)
                    if isinstance(call.get("duration"), float)
                    else call.get("duration_ms", 0),
                    created_at=now,
                )
                session.add(llm_call)

            session.commit()

        return log_id

    def get_generation_log(self, log_id: str) -> dict[str, Any] | None:
        with self._session() as session:
            log = session.query(GenerationLogModel).filter_by(log_id=log_id).first()
            if not log:
                return None

            calls = (
                session.query(GenerationLLMCallModel)
                .filter_by(log_id=log_id)
                .order_by(GenerationLLMCallModel.step)
                .all()
            )

            created = (
                log.created_at.isoformat()
                if isinstance(log.created_at, datetime)
                else str(log.created_at)
            )

            return {
                "metadata": {
                    "log_id": log.log_id,
                    "tool_name": log.tool_name,
                    "tool_description": log.tool_description or "",
                    "coverage_level": log.coverage_level or "",
                    "provider": log.provider or "",
                    "model": log.model or "",
                    "timestamp": created,
                    "success": bool(log.success),
                    "test_count": log.test_count,
                    "total_cost": log.total_cost,
                    "output_file": log.output_file,
                    "error": log.error,
                },
                "tool_schema": log.tool_schema or {},
                "llm_calls": [
                    {
                        "step": c.step,
                        "prompt": c.prompt or "",
                        "response": c.response or "",
                        "cost": c.cost,
                        "tokens": c.tokens,
                        "duration": c.duration_ms / 1000.0,
                        "timestamp": c.created_at.isoformat()
                        if isinstance(c.created_at, datetime)
                        else str(c.created_at),
                    }
                    for c in calls
                ],
                "generated_yaml": log.generated_yaml,
            }

    def list_generation_logs(
        self, tool_name: str | None = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        with self._session() as session:
            query = session.query(GenerationLogModel)

            if tool_name:
                query = query.filter(GenerationLogModel.tool_name == tool_name)

            rows = query.order_by(GenerationLogModel.created_at.desc()).limit(limit).all()

            return [
                {
                    "log_id": r.log_id,
                    "tool_name": r.tool_name,
                    "tool_description": r.tool_description or "",
                    "coverage_level": r.coverage_level or "",
                    "provider": r.provider or "",
                    "model": r.model or "",
                    "timestamp": r.created_at.isoformat()
                    if isinstance(r.created_at, datetime)
                    else str(r.created_at),
                    "success": bool(r.success),
                    "test_count": r.test_count,
                    "total_cost": r.total_cost,
                    "output_file": r.output_file,
                    "error": r.error,
                }
                for r in rows
            ]

    def list_generated_tools(self) -> list[dict[str, Any]]:
        """Get unique tools with generation counts."""
        with self._session() as session:
            rows = (
                session.query(
                    GenerationLogModel.tool_name,
                    func.min(GenerationLogModel.tool_description).label("description"),
                    func.count().label("generation_count"),
                    func.max(GenerationLogModel.created_at).label("last_generated"),
                    func.sum(func.iif(GenerationLogModel.success, 1, 0)).label("success_count"),
                )
                .group_by(GenerationLogModel.tool_name)
                .order_by(text("last_generated DESC"))
                .all()
            )

            return [
                {
                    "name": r.tool_name,
                    "description": (r.description or "")[:100],
                    "generation_count": r.generation_count,
                    "last_generated": r.last_generated.isoformat()
                    if isinstance(r.last_generated, datetime)
                    else str(r.last_generated),
                    "success_count": r.success_count or 0,
                }
                for r in rows
            ]

    def delete_generation_log(self, log_id: str) -> bool:
        with self._session() as session:
            log = session.query(GenerationLogModel).filter_by(log_id=log_id).first()
            if not log:
                return False
            session.delete(log)  # cascade deletes llm_calls
            session.commit()
            return True

    def clear_generation_logs(self) -> int:
        with self._session() as session:
            count = session.query(GenerationLogModel).count()
            session.query(GenerationLLMCallModel).delete()
            session.query(GenerationLogModel).delete()
            session.commit()
            return count


# Global storage instance
_storage: TestStorage | None = None


def get_storage() -> TestStorage:
    """Get the global storage instance."""
    global _storage
    if _storage is None:
        _storage = TestStorage()
    return _storage
