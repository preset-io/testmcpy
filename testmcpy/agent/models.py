"""
Data models for the Test Execution Agent.

Defines session state, run reports, and tool invocation records
used by the agent hooks and orchestrator.
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class ToolInvocation:
    """Record of a single tool call made by the agent."""

    tool_name: str
    arguments: dict[str, Any]
    result_summary: str
    is_error: bool = False
    duration_ms: float = 0.0
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AgentSession:
    """Mutable state accumulated during an agent run.

    Used by hooks to track progress and build the final report.
    """

    # Test execution tracking
    tests_run: int = 0
    tests_passed: int = 0
    tests_failed: int = 0

    # Cost tracking (orchestrator vs test execution)
    orchestrator_cost_usd: float = 0.0
    test_execution_cost_usd: float = 0.0

    # Token tracking
    orchestrator_tokens_input: int = 0
    orchestrator_tokens_output: int = 0
    test_execution_tokens: int = 0

    # Tool call history
    tool_call_history: list[ToolInvocation] = field(default_factory=list)
    tool_call_counts: dict[str, int] = field(default_factory=dict)

    # Errors
    errors: list[str] = field(default_factory=list)

    # Timing
    started_at: str = ""
    completed_at: str = ""

    def __post_init__(self):
        if not self.started_at:
            self.started_at = datetime.now(timezone.utc).isoformat()

    def record_tool_call(self, invocation: ToolInvocation) -> None:
        """Record a tool invocation."""
        self.tool_call_history.append(invocation)
        self.tool_call_counts[invocation.tool_name] = (
            self.tool_call_counts.get(invocation.tool_name, 0) + 1
        )

    def record_test_result(self, passed: bool) -> None:
        """Record a test result."""
        self.tests_run += 1
        if passed:
            self.tests_passed += 1
        else:
            self.tests_failed += 1

    def record_error(self, error: str) -> None:
        """Record an error."""
        self.errors.append(error)

    def complete(self) -> None:
        """Mark the session as completed."""
        self.completed_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["tool_call_history"] = [t.to_dict() for t in self.tool_call_history]
        return d


@dataclass
class AgentRunReport:
    """Final report from an agent run.

    Separates orchestrator costs from test execution costs.
    """

    # Run metadata
    run_id: str = ""
    started_at: str = ""
    completed_at: str = ""
    duration_ms: float = 0.0

    # Test results summary
    tests_run: int = 0
    tests_passed: int = 0
    tests_failed: int = 0
    pass_rate: float = 0.0

    # Cost breakdown
    orchestrator_cost_usd: float = 0.0
    test_execution_cost_usd: float = 0.0
    total_cost_usd: float = 0.0

    # Token breakdown
    orchestrator_tokens_input: int = 0
    orchestrator_tokens_output: int = 0
    test_execution_tokens: int = 0

    # Agent activity
    total_tool_calls: int = 0
    tool_call_counts: dict[str, int] = field(default_factory=dict)
    tool_call_history: list[ToolInvocation] = field(default_factory=list)

    # Errors
    errors: list[str] = field(default_factory=list)

    # Agent's final analysis (text from the agent)
    analysis: str = ""

    # Number of agent turns
    num_turns: int = 0

    @classmethod
    def from_session(cls, session: AgentSession, run_id: str = "") -> "AgentRunReport":
        """Build a report from a completed agent session."""
        session.complete()

        started = datetime.fromisoformat(session.started_at)
        completed = datetime.fromisoformat(session.completed_at)
        duration_ms = (completed - started).total_seconds() * 1000

        total_cost = session.orchestrator_cost_usd + session.test_execution_cost_usd
        pass_rate = session.tests_passed / session.tests_run if session.tests_run > 0 else 0.0

        return cls(
            run_id=run_id,
            started_at=session.started_at,
            completed_at=session.completed_at,
            duration_ms=duration_ms,
            tests_run=session.tests_run,
            tests_passed=session.tests_passed,
            tests_failed=session.tests_failed,
            pass_rate=pass_rate,
            orchestrator_cost_usd=session.orchestrator_cost_usd,
            test_execution_cost_usd=session.test_execution_cost_usd,
            total_cost_usd=total_cost,
            orchestrator_tokens_input=session.orchestrator_tokens_input,
            orchestrator_tokens_output=session.orchestrator_tokens_output,
            test_execution_tokens=session.test_execution_tokens,
            total_tool_calls=len(session.tool_call_history),
            tool_call_counts=dict(session.tool_call_counts),
            tool_call_history=list(session.tool_call_history),
            errors=list(session.errors),
        )

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["tool_call_history"] = [t.to_dict() for t in self.tool_call_history]
        return d
