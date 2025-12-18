"""
SQLite storage for test versioning and metrics.

Provides:
- Test file version tracking
- Test result history
- Metrics aggregation and trends
"""

import hashlib
import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


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
    """SQLite storage for test versioning and metrics."""

    def __init__(self, db_path: str | Path | None = None):
        """
        Initialize storage.

        Args:
            db_path: Path to SQLite database. If None, uses default location.
        """
        if db_path is None:
            # Default to .testmcpy/storage.db in current directory
            db_dir = Path.cwd() / ".testmcpy"
            db_dir.mkdir(exist_ok=True)
            db_path = db_dir / "storage.db"

        self.db_path = Path(db_path)
        self._init_db()

    def _init_db(self):
        """Initialize database schema."""
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript("""
                -- Test versions table (legacy, per-file versioning)
                CREATE TABLE IF NOT EXISTS test_versions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    test_path TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    content_hash TEXT NOT NULL,
                    content TEXT NOT NULL,
                    message TEXT,
                    created_at TEXT NOT NULL,
                    UNIQUE(test_path, version)
                );

                -- Test results table (legacy, per-test results)
                CREATE TABLE IF NOT EXISTS test_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    test_path TEXT NOT NULL,
                    test_name TEXT NOT NULL,
                    version_id INTEGER,
                    passed BOOLEAN NOT NULL,
                    score REAL DEFAULT 0.0,
                    duration REAL DEFAULT 0.0,
                    cost REAL DEFAULT 0.0,
                    tokens_used INTEGER DEFAULT 0,
                    model TEXT,
                    provider TEXT,
                    error TEXT,
                    evaluations TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (version_id) REFERENCES test_versions(id)
                );

                -- Test suites table (collection of questions)
                CREATE TABLE IF NOT EXISTS test_suites (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    suite_id TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL,
                    version INTEGER NOT NULL DEFAULT 1,
                    environment_id TEXT,
                    description TEXT,
                    content_hash TEXT NOT NULL,
                    questions TEXT NOT NULL,  -- JSON array of questions
                    metadata TEXT,  -- JSON object
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                -- Test runs table (grouped execution results)
                CREATE TABLE IF NOT EXISTS test_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL UNIQUE,
                    test_id TEXT NOT NULL,
                    test_version INTEGER NOT NULL,
                    environment_id TEXT,
                    model TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    runner_tool TEXT DEFAULT 'mcp-client',
                    mcp_setup_version TEXT,
                    started_at TEXT NOT NULL,
                    completed_at TEXT,
                    metadata TEXT,  -- JSON object
                    FOREIGN KEY (test_id) REFERENCES test_suites(suite_id)
                );

                -- Question results table (per-question results within a run)
                CREATE TABLE IF NOT EXISTS question_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    question_id TEXT NOT NULL,
                    answer TEXT,
                    tool_uses TEXT,  -- JSON array
                    tool_results TEXT,  -- JSON array
                    tokens_input INTEGER DEFAULT 0,
                    tokens_output INTEGER DEFAULT 0,
                    tti_ms INTEGER,  -- Time to first token
                    duration_ms INTEGER DEFAULT 0,
                    evaluations TEXT,  -- JSON array
                    score REAL DEFAULT 0.0,
                    passed BOOLEAN NOT NULL,
                    error TEXT,
                    FOREIGN KEY (run_id) REFERENCES test_runs(run_id)
                );

                -- Indexes for common queries
                CREATE INDEX IF NOT EXISTS idx_versions_path ON test_versions(test_path);
                CREATE INDEX IF NOT EXISTS idx_results_path ON test_results(test_path);
                CREATE INDEX IF NOT EXISTS idx_results_created ON test_results(created_at);
                CREATE INDEX IF NOT EXISTS idx_results_model ON test_results(model);
                CREATE INDEX IF NOT EXISTS idx_suites_id ON test_suites(suite_id);
                CREATE INDEX IF NOT EXISTS idx_runs_test_id ON test_runs(test_id);
                CREATE INDEX IF NOT EXISTS idx_runs_started ON test_runs(started_at);
                CREATE INDEX IF NOT EXISTS idx_question_results_run ON question_results(run_id);
            """)

    def _hash_content(self, content: str) -> str:
        """Generate hash for content."""
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    # ==================== Version Management ====================

    def save_version(self, test_path: str, content: str, message: str | None = None) -> TestVersion:
        """
        Save a new version of a test file.

        Only creates a new version if content has changed.

        Args:
            test_path: Path to the test file
            content: Test file content (YAML)
            message: Optional version message

        Returns:
            TestVersion object (new or existing)
        """
        content_hash = self._hash_content(content)

        with sqlite3.connect(self.db_path) as conn:
            # Check if this exact content already exists
            cursor = conn.execute(
                """
                SELECT id, test_path, version, content_hash, content, created_at, message
                FROM test_versions
                WHERE test_path = ? AND content_hash = ?
                ORDER BY version DESC LIMIT 1
                """,
                (test_path, content_hash),
            )
            row = cursor.fetchone()

            if row:
                # Content unchanged, return existing version
                return TestVersion(
                    id=row[0],
                    test_path=row[1],
                    version=row[2],
                    content_hash=row[3],
                    content=row[4],
                    created_at=row[5],
                    message=row[6],
                )

            # Get next version number
            cursor = conn.execute(
                "SELECT MAX(version) FROM test_versions WHERE test_path = ?",
                (test_path,),
            )
            max_version = cursor.fetchone()[0]
            next_version = (max_version or 0) + 1

            # Insert new version
            now = datetime.now(timezone.utc).isoformat()
            cursor = conn.execute(
                """
                INSERT INTO test_versions (test_path, version, content_hash, content, message, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (test_path, next_version, content_hash, content, message, now),
            )

            return TestVersion(
                id=cursor.lastrowid,
                test_path=test_path,
                version=next_version,
                content_hash=content_hash,
                content=content,
                created_at=now,
                message=message,
            )

    def get_versions(self, test_path: str, limit: int = 50) -> list[TestVersion]:
        """Get version history for a test file."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT id, test_path, version, content_hash, content, created_at, message
                FROM test_versions
                WHERE test_path = ?
                ORDER BY version DESC
                LIMIT ?
                """,
                (test_path, limit),
            )

            return [
                TestVersion(
                    id=row[0],
                    test_path=row[1],
                    version=row[2],
                    content_hash=row[3],
                    content=row[4],
                    created_at=row[5],
                    message=row[6],
                )
                for row in cursor.fetchall()
            ]

    def get_version(self, test_path: str, version: int) -> TestVersion | None:
        """Get a specific version of a test file."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT id, test_path, version, content_hash, content, created_at, message
                FROM test_versions
                WHERE test_path = ? AND version = ?
                """,
                (test_path, version),
            )
            row = cursor.fetchone()

            if row:
                return TestVersion(
                    id=row[0],
                    test_path=row[1],
                    version=row[2],
                    content_hash=row[3],
                    content=row[4],
                    created_at=row[5],
                    message=row[6],
                )
            return None

    def get_latest_version(self, test_path: str) -> TestVersion | None:
        """Get the latest version of a test file."""
        versions = self.get_versions(test_path, limit=1)
        return versions[0] if versions else None

    def diff_versions(self, test_path: str, version1: int, version2: int) -> dict[str, Any]:
        """
        Compare two versions of a test file.

        Returns dict with 'added', 'removed', 'changed' lines.
        """
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

    # ==================== Result Storage ====================

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
        """Save a test execution result."""
        now = datetime.now(timezone.utc).isoformat()
        evaluations_json = json.dumps(evaluations or [])

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                INSERT INTO test_results
                (test_path, test_name, version_id, passed, score, duration, cost,
                 tokens_used, model, provider, error, evaluations, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    test_path,
                    test_name,
                    version_id,
                    passed,
                    score,
                    duration,
                    cost,
                    tokens_used,
                    model,
                    provider,
                    error,
                    evaluations_json,
                    now,
                ),
            )

            return TestResult(
                id=cursor.lastrowid,
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
        """
        Query test results with filters.

        Args:
            test_path: Filter by test file path
            test_name: Filter by specific test name
            model: Filter by model used
            limit: Maximum results to return
            since: ISO timestamp to filter results after
        """
        query = "SELECT * FROM test_results WHERE 1=1"
        params: list[Any] = []

        if test_path:
            query += " AND test_path = ?"
            params.append(test_path)

        if test_name:
            query += " AND test_name = ?"
            params.append(test_name)

        if model:
            query += " AND model = ?"
            params.append(model)

        if since:
            query += " AND created_at >= ?"
            params.append(since)

        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(query, params)

            return [
                TestResult(
                    id=row["id"],
                    test_path=row["test_path"],
                    test_name=row["test_name"],
                    version_id=row["version_id"],
                    passed=bool(row["passed"]),
                    score=row["score"],
                    duration=row["duration"],
                    cost=row["cost"],
                    tokens_used=row["tokens_used"],
                    model=row["model"],
                    provider=row["provider"],
                    error=row["error"],
                    evaluations=row["evaluations"],
                    created_at=row["created_at"],
                )
                for row in cursor.fetchall()
            ]

    # ==================== Metrics & Analytics ====================

    def get_pass_rate(
        self,
        test_path: str | None = None,
        model: str | None = None,
        days: int = 30,
    ) -> dict[str, Any]:
        """Get pass rate statistics."""
        since = (
            datetime.now(timezone.utc)
            .replace(hour=0, minute=0, second=0, microsecond=0)
            .__sub__(__import__("datetime").timedelta(days=days))
            .isoformat()
        )

        query = """
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN passed THEN 1 ELSE 0 END) as passed,
                AVG(score) as avg_score,
                AVG(duration) as avg_duration,
                SUM(cost) as total_cost,
                SUM(tokens_used) as total_tokens
            FROM test_results
            WHERE created_at >= ?
        """
        params: list[Any] = [since]

        if test_path:
            query += " AND test_path = ?"
            params.append(test_path)

        if model:
            query += " AND model = ?"
            params.append(model)

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(query, params).fetchone()

            total = row["total"] or 0
            passed = row["passed"] or 0

            return {
                "total": total,
                "passed": passed,
                "failed": total - passed,
                "pass_rate": (passed / total * 100) if total > 0 else 0,
                "avg_score": row["avg_score"] or 0,
                "avg_duration": row["avg_duration"] or 0,
                "total_cost": row["total_cost"] or 0,
                "total_tokens": row["total_tokens"] or 0,
                "period_days": days,
            }

    def get_trends(
        self,
        test_path: str | None = None,
        model: str | None = None,
        days: int = 30,
        group_by: str = "day",
    ) -> list[dict[str, Any]]:
        """
        Get historical trends grouped by time period.

        Args:
            test_path: Filter by test file
            model: Filter by model
            days: Number of days to look back
            group_by: 'day', 'week', or 'hour'
        """
        since = (
            datetime.now(timezone.utc)
            .replace(hour=0, minute=0, second=0, microsecond=0)
            .__sub__(__import__("datetime").timedelta(days=days))
            .isoformat()
        )

        # SQLite date grouping
        if group_by == "hour":
            date_expr = "strftime('%Y-%m-%d %H:00', created_at)"
        elif group_by == "week":
            date_expr = "strftime('%Y-W%W', created_at)"
        else:  # day
            date_expr = "date(created_at)"

        query = f"""
            SELECT
                {date_expr} as period,
                COUNT(*) as total,
                SUM(CASE WHEN passed THEN 1 ELSE 0 END) as passed,
                AVG(score) as avg_score,
                AVG(duration) as avg_duration,
                SUM(cost) as total_cost
            FROM test_results
            WHERE created_at >= ?
        """
        params: list[Any] = [since]

        if test_path:
            query += " AND test_path = ?"
            params.append(test_path)

        if model:
            query += " AND model = ?"
            params.append(model)

        query += f" GROUP BY {date_expr} ORDER BY period"

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query, params).fetchall()

            return [
                {
                    "period": row["period"],
                    "total": row["total"],
                    "passed": row["passed"],
                    "failed": row["total"] - row["passed"],
                    "pass_rate": (row["passed"] / row["total"] * 100) if row["total"] > 0 else 0,
                    "avg_score": row["avg_score"] or 0,
                    "avg_duration": row["avg_duration"] or 0,
                    "total_cost": row["total_cost"] or 0,
                }
                for row in rows
            ]

    def get_model_comparison(self, days: int = 30) -> list[dict[str, Any]]:
        """Compare performance across different models."""
        since = (
            datetime.now(timezone.utc)
            .replace(hour=0, minute=0, second=0, microsecond=0)
            .__sub__(__import__("datetime").timedelta(days=days))
            .isoformat()
        )

        query = """
            SELECT
                model,
                provider,
                COUNT(*) as total,
                SUM(CASE WHEN passed THEN 1 ELSE 0 END) as passed,
                AVG(score) as avg_score,
                AVG(duration) as avg_duration,
                SUM(cost) as total_cost,
                SUM(tokens_used) as total_tokens
            FROM test_results
            WHERE created_at >= ? AND model IS NOT NULL AND model != ''
            GROUP BY model, provider
            ORDER BY passed DESC, avg_score DESC
        """

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query, (since,)).fetchall()

            return [
                {
                    "model": row["model"],
                    "provider": row["provider"],
                    "total": row["total"],
                    "passed": row["passed"],
                    "failed": row["total"] - row["passed"],
                    "pass_rate": (row["passed"] / row["total"] * 100) if row["total"] > 0 else 0,
                    "avg_score": row["avg_score"] or 0,
                    "avg_duration": row["avg_duration"] or 0,
                    "total_cost": row["total_cost"] or 0,
                    "total_tokens": row["total_tokens"] or 0,
                }
                for row in rows
            ]

    def get_failing_tests(self, days: int = 7, min_failures: int = 2) -> list[dict[str, Any]]:
        """Get tests that are frequently failing."""
        since = (
            datetime.now(timezone.utc)
            .replace(hour=0, minute=0, second=0, microsecond=0)
            .__sub__(__import__("datetime").timedelta(days=days))
            .isoformat()
        )

        query = """
            SELECT
                test_path,
                test_name,
                COUNT(*) as total,
                SUM(CASE WHEN passed THEN 0 ELSE 1 END) as failures,
                MAX(error) as last_error,
                MAX(created_at) as last_run
            FROM test_results
            WHERE created_at >= ?
            GROUP BY test_path, test_name
            HAVING failures >= ?
            ORDER BY failures DESC
        """

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query, (since, min_failures)).fetchall()

            return [
                {
                    "test_path": row["test_path"],
                    "test_name": row["test_name"],
                    "total": row["total"],
                    "failures": row["failures"],
                    "failure_rate": (row["failures"] / row["total"] * 100)
                    if row["total"] > 0
                    else 0,
                    "last_error": row["last_error"],
                    "last_run": row["last_run"],
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
        """
        Save a test suite. Auto-increments version if content changes.

        Returns:
            Dict with suite info including version number
        """
        questions_json = json.dumps(questions, sort_keys=True)
        content_hash = self._hash_content(questions_json)
        now = datetime.now(timezone.utc).isoformat()

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row

            # Check if suite exists and if content changed
            existing = conn.execute(
                "SELECT version, content_hash FROM test_suites WHERE suite_id = ?",
                (suite_id,),
            ).fetchone()

            if existing:
                if existing["content_hash"] == content_hash:
                    # No changes, return existing
                    return self.get_suite(suite_id)

                # Content changed, increment version
                new_version = existing["version"] + 1
                conn.execute(
                    """
                    UPDATE test_suites SET
                        name = ?,
                        version = ?,
                        environment_id = ?,
                        description = ?,
                        content_hash = ?,
                        questions = ?,
                        metadata = ?,
                        updated_at = ?
                    WHERE suite_id = ?
                    """,
                    (
                        name,
                        new_version,
                        environment_id,
                        description,
                        content_hash,
                        questions_json,
                        json.dumps(metadata) if metadata else None,
                        now,
                        suite_id,
                    ),
                )
            else:
                # New suite
                new_version = 1
                conn.execute(
                    """
                    INSERT INTO test_suites
                    (suite_id, name, version, environment_id, description,
                     content_hash, questions, metadata, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        suite_id,
                        name,
                        new_version,
                        environment_id,
                        description,
                        content_hash,
                        questions_json,
                        json.dumps(metadata) if metadata else None,
                        now,
                        now,
                    ),
                )

            conn.commit()
            return self.get_suite(suite_id)

    def get_suite(self, suite_id: str) -> dict[str, Any] | None:
        """Get a test suite by ID."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM test_suites WHERE suite_id = ?", (suite_id,)
            ).fetchone()

            if not row:
                return None

            return {
                "id": suite_id,
                "name": row["name"],
                "version": row["version"],
                "environment_id": row["environment_id"],
                "description": row["description"],
                "questions": json.loads(row["questions"]),
                "metadata": json.loads(row["metadata"]) if row["metadata"] else {},
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }

    def list_suites(self, limit: int = 100) -> list[dict[str, Any]]:
        """List all test suites."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT suite_id, name, version, environment_id, description,
                       created_at, updated_at,
                       json_array_length(questions) as question_count
                FROM test_suites
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

            return [
                {
                    "id": row["suite_id"],
                    "name": row["name"],
                    "version": row["version"],
                    "environment_id": row["environment_id"],
                    "description": row["description"],
                    "question_count": row["question_count"],
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                }
                for row in rows
            ]

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
    ) -> None:
        """Save a new test run."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO test_runs
                (run_id, test_id, test_version, environment_id, model, provider,
                 runner_tool, mcp_setup_version, started_at, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    test_id,
                    test_version,
                    environment_id,
                    model,
                    provider,
                    runner_tool,
                    mcp_setup_version,
                    started_at,
                    json.dumps(metadata) if metadata else None,
                ),
            )
            conn.commit()

    def complete_run(self, run_id: str, completed_at: str) -> None:
        """Mark a test run as completed."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE test_runs SET completed_at = ? WHERE run_id = ?",
                (completed_at, run_id),
            )
            conn.commit()

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
        """Save a question result within a run."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO question_results
                (run_id, question_id, answer, tool_uses, tool_results,
                 tokens_input, tokens_output, tti_ms, duration_ms,
                 evaluations, score, passed, error)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    question_id,
                    answer,
                    json.dumps(tool_uses) if tool_uses else None,
                    json.dumps(tool_results) if tool_results else None,
                    tokens_input,
                    tokens_output,
                    tti_ms,
                    duration_ms,
                    json.dumps(evaluations) if evaluations else None,
                    score,
                    passed,
                    error,
                ),
            )
            conn.commit()

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        """Get a test run with all its question results."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row

            run = conn.execute("SELECT * FROM test_runs WHERE run_id = ?", (run_id,)).fetchone()

            if not run:
                return None

            questions = conn.execute(
                "SELECT * FROM question_results WHERE run_id = ? ORDER BY id",
                (run_id,),
            ).fetchall()

            question_results = [
                {
                    "question_id": q["question_id"],
                    "answer": q["answer"],
                    "tool_uses": json.loads(q["tool_uses"]) if q["tool_uses"] else [],
                    "tool_results": json.loads(q["tool_results"]) if q["tool_results"] else [],
                    "tokens_input": q["tokens_input"],
                    "tokens_output": q["tokens_output"],
                    "tti_ms": q["tti_ms"],
                    "duration_ms": q["duration_ms"],
                    "evaluations": json.loads(q["evaluations"]) if q["evaluations"] else [],
                    "score": q["score"],
                    "passed": bool(q["passed"]),
                    "error": q["error"],
                }
                for q in questions
            ]

            total = len(question_results)
            passed = sum(1 for q in question_results if q["passed"])

            return {
                "run_id": run["run_id"],
                "test_id": run["test_id"],
                "test_version": run["test_version"],
                "environment_id": run["environment_id"],
                "model": run["model"],
                "provider": run["provider"],
                "runner_tool": run["runner_tool"],
                "mcp_setup_version": run["mcp_setup_version"],
                "started_at": run["started_at"],
                "completed_at": run["completed_at"],
                "metadata": json.loads(run["metadata"]) if run["metadata"] else {},
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
        """List test runs with optional filters."""
        query = """
            SELECT
                r.run_id, r.test_id, r.test_version, r.environment_id,
                r.model, r.provider, r.runner_tool, r.started_at, r.completed_at,
                COUNT(q.id) as total_questions,
                SUM(CASE WHEN q.passed THEN 1 ELSE 0 END) as passed_questions
            FROM test_runs r
            LEFT JOIN question_results q ON r.run_id = q.run_id
        """
        params = []
        conditions = []

        if test_id:
            conditions.append("r.test_id = ?")
            params.append(test_id)

        if model:
            conditions.append("r.model = ?")
            params.append(model)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += """
            GROUP BY r.run_id
            ORDER BY r.started_at DESC
            LIMIT ?
        """
        params.append(limit)

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query, params).fetchall()

            return [
                {
                    "run_id": row["run_id"],
                    "test_id": row["test_id"],
                    "test_version": row["test_version"],
                    "environment_id": row["environment_id"],
                    "model": row["model"],
                    "provider": row["provider"],
                    "runner_tool": row["runner_tool"],
                    "started_at": row["started_at"],
                    "completed_at": row["completed_at"],
                    "total_questions": row["total_questions"],
                    "passed_questions": row["passed_questions"] or 0,
                    "pass_rate": (
                        (row["passed_questions"] / row["total_questions"] * 100)
                        if row["total_questions"] > 0
                        else 0
                    ),
                }
                for row in rows
            ]


# Global storage instance
_storage: TestStorage | None = None


def get_storage() -> TestStorage:
    """Get the global storage instance."""
    global _storage
    if _storage is None:
        _storage = TestStorage()
    return _storage
