"""Result model: statuses, exit codes and the machine-readable report."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from testmcpy.gateway_smoke.config import REPORT_SCHEMA


class Status(str, Enum):
    """PASS is only reachable when every step ran and every check passed."""

    PASS = "PASS"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"
    ERROR = "ERROR"
    SKIPPED = "SKIPPED"  # not run because an earlier step stopped the lane
    INFO = "INFO"  # not applicable (e.g. an optional capability not advertised)


EXIT_CODES = {Status.PASS: 0, Status.FAIL: 1, Status.ERROR: 2, Status.BLOCKED: 3}

# Worst wins. BLOCKED outranks nothing that is a real signal: a FAIL or ERROR
# found before the lane was blocked must not be hidden by the block.
_SEVERITY = (Status.ERROR, Status.FAIL, Status.BLOCKED)


def worst(statuses: list[Status]) -> Status:
    for status in _SEVERITY:
        if status in statuses:
            return status
    if Status.SKIPPED in statuses:
        # Something that should have run did not, and nothing explains why.
        return Status.ERROR
    return Status.PASS


@dataclass
class Check:
    id: str
    status: Status
    message: str
    http_status: int | None = None
    duration_ms: int = 0
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "id": self.id,
            "status": self.status.value,
            "message": self.message,
            "duration_ms": self.duration_ms,
            "evidence": self.evidence,
        }
        if self.http_status is not None:
            out["http_status"] = self.http_status
        return out


@dataclass
class Step:
    id: str
    title: str
    checks: list[Check] = field(default_factory=list)
    skipped_reason: str | None = None
    duration_ms: int = 0

    @property
    def status(self) -> Status:
        if self.skipped_reason is not None and not self.checks:
            return Status.SKIPPED
        return worst(
            [c.status for c in self.checks if c.status is not Status.INFO] or [Status.PASS]
        )

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "id": self.id,
            "title": self.title,
            "status": self.status.value,
            "duration_ms": self.duration_ms,
            "checks": [c.to_dict() for c in self.checks],
        }
        if self.skipped_reason is not None:
            out["reason"] = self.skipped_reason
        return out


@dataclass
class SmokeReport:
    run_id: str
    tool_version: str
    started_at: str
    duration_ms: int
    environment: str | None
    workspace_id: str | None
    workspace_name: str | None
    mcp_url: str | None
    spec_profile: str | None
    steps: list[Step]
    limits: dict[str, Any]
    usage: dict[str, Any]
    calls: list[dict[str, Any]]

    @property
    def status(self) -> Status:
        return worst([s.status for s in self.steps])

    @property
    def exit_code(self) -> int:
        return EXIT_CODES[self.status]

    @property
    def reason(self) -> str:
        """The first non-pass check message, for one-line summaries."""
        for step in self.steps:
            for check in step.checks:
                if check.status in _SEVERITY:
                    return f"{step.id}: {check.message}"
        return "all steps passed" if self.status is Status.PASS else "incomplete"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": REPORT_SCHEMA,
            "run": {
                "id": self.run_id,
                "tool_version": self.tool_version,
                "started_at": self.started_at,
                "duration_ms": self.duration_ms,
            },
            "environment": self.environment,
            "workspace": {"id": self.workspace_id, "name": self.workspace_name},
            "target": {"mcp_url": self.mcp_url, "spec_profile": self.spec_profile},
            "status": self.status.value,
            "exit_code": self.exit_code,
            "reason": self.reason,
            "steps": [s.to_dict() for s in self.steps],
            "limits": self.limits,
            "usage": self.usage,
            "calls": self.calls,
            # Constants by construction: the lane has no LLM client and no
            # write path. They are stated so a consumer need not infer them.
            "lane": {"llm_calls": 0, "writes": 0, "read_only": True},
        }
