"""
One-time migration script to import existing JSON files into the database.

Usage:
    python -m testmcpy.migrate_json [--db-path .testmcpy/storage.db]

This script is idempotent — it skips records that already exist in the DB
(matched by unique IDs like run_id, report_id, log_id).
"""

import json
import sys
from pathlib import Path

from testmcpy.storage import TestStorage


def migrate_results(storage: TestStorage, results_dir: Path) -> int:
    """Import test results from tests/.results/*.json"""
    if not results_dir.exists():
        print(f"  Skipping results: {results_dir} does not exist")
        return 0

    count = 0
    for result_file in sorted(results_dir.glob("*.json")):
        try:
            with open(result_file) as f:
                data = json.load(f)

            metadata = data.get("metadata", {})
            run_id = metadata.get("run_id")
            if not run_id:
                print(f"  Skipping {result_file.name}: no run_id in metadata")
                continue

            # Check if already imported
            existing = storage.get_run(run_id)
            if existing:
                continue

            test_file = metadata.get("test_file", "unknown")

            # Ensure suite exists
            storage.save_suite(
                suite_id=test_file,
                name=test_file,
                questions=[],
            )

            # Save run
            storage.save_run(
                run_id=run_id,
                test_id=test_file,
                test_version=1,
                model=metadata.get("model", "unknown"),
                provider=metadata.get("provider", "unknown"),
                started_at=metadata.get("timestamp", ""),
                mcp_profile_id=metadata.get("mcp_profile"),
            )

            # Save question results
            for r in data.get("results", []):
                storage.save_question_result(
                    run_id=run_id,
                    question_id=r.get("test_name", r.get("question_id", "unknown")),
                    passed=r.get("passed", False),
                    score=r.get("score", 0.0),
                    answer=r.get("response", r.get("answer")),
                    tool_uses=r.get("tool_calls", r.get("tool_uses")),
                    tool_results=r.get("tool_results"),
                    tokens_input=r.get("token_usage", {}).get("input", 0),
                    tokens_output=r.get("token_usage", {}).get("output", 0),
                    duration_ms=int(r.get("duration", 0) * 1000),
                    evaluations=r.get("evaluations"),
                    error=r.get("error"),
                )

            # Complete run
            storage.complete_run(run_id, metadata.get("timestamp", ""))

            count += 1
            print(f"  Imported result: {run_id}")

        except (json.JSONDecodeError, KeyError, TypeError) as e:
            print(f"  Error importing {result_file.name}: {e}")

    return count


def migrate_smoke_reports(storage: TestStorage, reports_dir: Path) -> int:
    """Import smoke reports from tests/.smoke_reports/*.json"""
    if not reports_dir.exists():
        print(f"  Skipping smoke reports: {reports_dir} does not exist")
        return 0

    count = 0
    for report_file in sorted(reports_dir.glob("*.json")):
        try:
            with open(report_file) as f:
                data = json.load(f)

            report_id = data.get("report_id")
            if not report_id:
                print(f"  Skipping {report_file.name}: no report_id")
                continue

            # Check if already imported
            existing = storage.get_smoke_report(report_id)
            if existing:
                continue

            storage.save_smoke_report(data)
            count += 1
            print(f"  Imported smoke report: {report_id}")

        except (json.JSONDecodeError, KeyError, TypeError) as e:
            print(f"  Error importing {report_file.name}: {e}")

    return count


def migrate_generation_logs(storage: TestStorage, logs_dir: Path) -> int:
    """Import generation logs from tests/.generation_logs/*.json"""
    if not logs_dir.exists():
        print(f"  Skipping generation logs: {logs_dir} does not exist")
        return 0

    count = 0
    for log_file in sorted(logs_dir.glob("*.json")):
        try:
            with open(log_file) as f:
                data = json.load(f)

            metadata = data.get("metadata", data)
            log_id = metadata.get("log_id")
            if not log_id:
                print(f"  Skipping {log_file.name}: no log_id")
                continue

            # Check if already imported
            existing = storage.get_generation_log(log_id)
            if existing:
                continue

            storage.save_generation_log(data)
            count += 1
            print(f"  Imported generation log: {log_id}")

        except (json.JSONDecodeError, KeyError, TypeError) as e:
            print(f"  Error importing {log_file.name}: {e}")

    return count


def main():
    """Run the full migration."""
    db_path = None
    if "--db-path" in sys.argv:
        idx = sys.argv.index("--db-path")
        if idx + 1 < len(sys.argv):
            db_path = sys.argv[idx + 1]

    storage = TestStorage(db_path=db_path)
    base_dir = Path.cwd()

    print("=" * 60)
    print("testmcpy JSON → DB Migration")
    print(f"Database: {storage.db_path}")
    print("=" * 60)

    print("\n1. Migrating test results...")
    results_count = migrate_results(storage, base_dir / "tests" / ".results")
    print(f"   → {results_count} results imported")

    print("\n2. Migrating smoke reports...")
    reports_count = migrate_smoke_reports(storage, base_dir / "tests" / ".smoke_reports")
    print(f"   → {reports_count} reports imported")

    print("\n3. Migrating generation logs...")
    logs_count = migrate_generation_logs(storage, base_dir / "tests" / ".generation_logs")
    print(f"   → {logs_count} logs imported")

    print("\n" + "=" * 60)
    print(
        f"Migration complete: {results_count + reports_count + logs_count} total records imported"
    )
    print("=" * 60)


if __name__ == "__main__":
    main()
