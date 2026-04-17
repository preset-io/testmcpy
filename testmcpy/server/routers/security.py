"""
API routes for security-focused test result aggregation.

Filters test results that have security-tagged evaluators and
groups by severity level.
"""

from typing import Any

from fastapi import APIRouter, Query

from testmcpy.db import get_session_factory, init_db
from testmcpy.models import QuestionResultModel, TestRunModel

router = APIRouter(prefix="/api/security", tags=["security"])

# Evaluator names that are considered security-related
SECURITY_EVALUATORS = {
    "no_leaked_data",
    "response_not_includes",
    "no_injection",
    "no_sensitive_data",
    "no_pii",
    "no_credentials",
    "no_secrets",
    "sanitized_output",
    "input_validation",
    "no_sql_injection",
    "no_xss",
    "no_code_injection",
    "safe_output",
}

# Keywords in evaluator names that suggest security relevance
SECURITY_KEYWORDS = [
    "security",
    "injection",
    "leak",
    "sensitive",
    "pii",
    "credential",
    "secret",
    "sanitiz",
    "xss",
    "auth",
    "permission",
    "access_control",
]

# Severity mapping for known evaluators
SEVERITY_MAP = {
    "no_leaked_data": "critical",
    "no_credentials": "critical",
    "no_secrets": "critical",
    "no_pii": "high",
    "no_sensitive_data": "high",
    "no_injection": "critical",
    "no_sql_injection": "critical",
    "no_xss": "high",
    "no_code_injection": "critical",
    "response_not_includes": "medium",
    "input_validation": "medium",
    "sanitized_output": "medium",
    "safe_output": "low",
}


def _is_security_evaluator(evaluator_name: str) -> bool:
    """Check if an evaluator name is security-related."""
    name_lower = evaluator_name.lower()
    if name_lower in SECURITY_EVALUATORS:
        return True
    return any(kw in name_lower for kw in SECURITY_KEYWORDS)


def _get_severity(evaluator_name: str) -> str:
    """Get severity level for a security evaluator."""
    name_lower = evaluator_name.lower()
    if name_lower in SEVERITY_MAP:
        return SEVERITY_MAP[name_lower]
    # Infer severity from keywords
    if any(kw in name_lower for kw in ["inject", "credential", "secret", "leak"]):
        return "critical"
    if any(kw in name_lower for kw in ["pii", "sensitive", "xss"]):
        return "high"
    if any(kw in name_lower for kw in ["sanitiz", "validation"]):
        return "medium"
    return "low"


@router.get("")
async def get_security_results(
    limit: int = Query(200, description="Max results to scan"),
) -> dict[str, Any]:
    """
    Get security-related test results.

    Filters question results that have security-tagged evaluators,
    groups by severity (critical/high/medium/low), and shows pass/fail counts.
    """
    init_db()
    session_factory = get_session_factory()
    session = session_factory()

    try:
        # Get recent question results with their evaluations
        results = (
            session.query(
                QuestionResultModel.run_id,
                QuestionResultModel.question_id,
                QuestionResultModel.passed,
                QuestionResultModel.evaluations,
                QuestionResultModel.error,
                QuestionResultModel.created_at,
                TestRunModel.model,
                TestRunModel.provider,
                TestRunModel.suite_id,
            )
            .join(TestRunModel, QuestionResultModel.run_id == TestRunModel.run_id)
            .order_by(QuestionResultModel.created_at.desc())
            .limit(limit)
            .all()
        )

        # Filter and categorize security evaluations
        severity_counts = {
            "critical": {"passed": 0, "failed": 0, "total": 0},
            "high": {"passed": 0, "failed": 0, "total": 0},
            "medium": {"passed": 0, "failed": 0, "total": 0},
            "low": {"passed": 0, "failed": 0, "total": 0},
        }
        security_results = []

        for row in results:
            evaluations = row.evaluations or []
            if not isinstance(evaluations, list):
                continue

            for ev in evaluations:
                if not isinstance(ev, dict):
                    continue

                evaluator_name = ev.get("evaluator") or ev.get("name") or ""
                if not _is_security_evaluator(evaluator_name):
                    continue

                severity = _get_severity(evaluator_name)
                ev_passed = ev.get("passed", False)

                severity_counts[severity]["total"] += 1
                if ev_passed:
                    severity_counts[severity]["passed"] += 1
                else:
                    severity_counts[severity]["failed"] += 1

                security_results.append(
                    {
                        "run_id": row.run_id,
                        "question_id": row.question_id,
                        "suite_id": row.suite_id,
                        "model": row.model,
                        "provider": row.provider,
                        "evaluator": evaluator_name,
                        "severity": severity,
                        "passed": ev_passed,
                        "score": ev.get("score"),
                        "reason": ev.get("reason"),
                        "created_at": row.created_at.isoformat()
                        if hasattr(row.created_at, "isoformat")
                        else str(row.created_at),
                    }
                )

        total_security = sum(s["total"] for s in severity_counts.values())
        total_passed = sum(s["passed"] for s in severity_counts.values())
        total_failed = sum(s["failed"] for s in severity_counts.values())

        return {
            "summary": {
                "total": total_security,
                "passed": total_passed,
                "failed": total_failed,
                "pass_rate": round(
                    (total_passed / total_security * 100) if total_security > 0 else 0,
                    1,
                ),
            },
            "severity_breakdown": severity_counts,
            "results": security_results,
        }
    finally:
        session.close()
