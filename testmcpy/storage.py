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
                -- Test versions table
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

                -- Test results table
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

                -- Indexes for common queries
                CREATE INDEX IF NOT EXISTS idx_versions_path ON test_versions(test_path);
                CREATE INDEX IF NOT EXISTS idx_results_path ON test_results(test_path);
                CREATE INDEX IF NOT EXISTS idx_results_created ON test_results(created_at);
                CREATE INDEX IF NOT EXISTS idx_results_model ON test_results(model);
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


# Global storage instance
_storage: TestStorage | None = None


def get_storage() -> TestStorage:
    """Get the global storage instance."""
    global _storage
    if _storage is None:
        _storage = TestStorage()
    return _storage
