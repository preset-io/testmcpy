"""
Core data models for MCP test framework.

This module defines the canonical data structures for:
- TestSuite: A collection of questions with versioning
- Question: Individual test prompts with evaluators and weights
- TestRun: A complete test execution with grouped results
- QuestionResult: Result from executing a single question
"""

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class Question:
    """A single question/prompt within a test suite.

    Attributes:
        id: Unique identifier for this question within the suite
        prompt: The prompt to send to the LLM
        evaluators: List of evaluator configurations
        weight: Relative weight for scoring (default 1.0)
        timeout: Max seconds to wait for response
        metadata: Additional question metadata
    """

    id: str
    prompt: str
    evaluators: list[dict[str, Any]] = field(default_factory=list)
    weight: float = 1.0
    timeout: float = 30.0
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Question":
        """Create Question from dictionary."""
        return cls(
            id=data["id"],
            prompt=data["prompt"],
            evaluators=data.get("evaluators", []),
            weight=data.get("weight", 1.0),
            timeout=data.get("timeout", 30.0),
            metadata=data.get("metadata", {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TestSuite:
    """A collection of questions that form a complete test.

    Attributes:
        id: Unique identifier for the test suite
        name: Human-readable name
        version: Version number (auto-incremented on changes)
        environment_id: Synthetic environment identifier (e.g., "examples-sdx-v2")
        questions: List of questions in this suite
        description: Optional description
        metadata: Additional suite metadata
    """

    id: str
    name: str
    version: int = 1
    environment_id: str | None = None
    questions: list[Question] = field(default_factory=list)
    description: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TestSuite":
        """Create TestSuite from dictionary (e.g., parsed YAML)."""
        questions = [Question.from_dict(q) for q in data.get("questions", [])]
        return cls(
            id=data["id"],
            name=data.get("name", data["id"]),
            version=data.get("version", 1),
            environment_id=data.get("environment_id"),
            questions=questions,
            description=data.get("description"),
            metadata=data.get("metadata", {}),
        )

    @classmethod
    def from_yaml_file(cls, path: str) -> "TestSuite":
        """Load TestSuite from a YAML file."""
        from pathlib import Path

        import yaml

        content = Path(path).read_text()
        data = yaml.safe_load(content)
        return cls.from_dict(data)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d

    @property
    def total_weight(self) -> float:
        """Total weight of all questions."""
        return sum(q.weight for q in self.questions)


@dataclass
class QuestionResult:
    """Result from executing a single question.

    Attributes:
        question_id: ID of the question that was executed
        answer: The LLM's response text
        tool_uses: List of tool calls made
        tool_results: Results from tool executions
        tokens_input: Input tokens used
        tokens_output: Output tokens generated
        tti_ms: Time to first token in milliseconds
        duration_ms: Total execution time in milliseconds
        evaluations: Results from each evaluator
        score: Weighted score (0.0 to 1.0)
        passed: Whether the question passed
        error: Error message if failed
    """

    question_id: str
    answer: str | None = None
    tool_uses: list[dict[str, Any]] = field(default_factory=list)
    tool_results: list[dict[str, Any]] = field(default_factory=list)
    tokens_input: int = 0
    tokens_output: int = 0
    tti_ms: int | None = None  # Time to first token
    duration_ms: int = 0
    evaluations: list[dict[str, Any]] = field(default_factory=list)
    score: float = 0.0
    passed: bool = False
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TestRun:
    """A complete test execution run.

    Groups all question results from a single test suite execution.

    Attributes:
        run_id: Unique identifier for this run
        test_id: ID of the TestSuite that was run
        test_version: Version of the TestSuite
        environment_id: Synthetic environment used
        model: LLM model used (e.g., "claude-sonnet-4-5")
        provider: LLM provider (e.g., "anthropic")
        runner_tool: Test runner tool used (e.g., "mcp-client")
        mcp_setup_version: Version of MCP server setup (if known)
        started_at: ISO timestamp when run started
        completed_at: ISO timestamp when run completed
        question_results: Results for each question
        metadata: Additional run metadata
    """

    run_id: str
    test_id: str
    test_version: int
    environment_id: str | None = None
    model: str = ""
    provider: str = ""
    runner_tool: str = "mcp-client"
    mcp_setup_version: str | None = None
    started_at: str = ""
    completed_at: str | None = None
    question_results: list[QuestionResult] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        test_suite: TestSuite,
        model: str,
        provider: str,
        runner_tool: str = "mcp-client",
        mcp_setup_version: str | None = None,
    ) -> "TestRun":
        """Create a new TestRun for a TestSuite."""
        return cls(
            run_id=f"run_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}",
            test_id=test_suite.id,
            test_version=test_suite.version,
            environment_id=test_suite.environment_id,
            model=model,
            provider=provider,
            runner_tool=runner_tool,
            mcp_setup_version=mcp_setup_version,
            started_at=datetime.now(timezone.utc).isoformat(),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def complete(self) -> None:
        """Mark the run as completed."""
        self.completed_at = datetime.now(timezone.utc).isoformat()

    def add_result(self, result: QuestionResult) -> None:
        """Add a question result to this run."""
        self.question_results.append(result)

    @property
    def total_questions(self) -> int:
        return len(self.question_results)

    @property
    def passed_questions(self) -> int:
        return sum(1 for r in self.question_results if r.passed)

    @property
    def failed_questions(self) -> int:
        return sum(1 for r in self.question_results if not r.passed)

    @property
    def pass_rate(self) -> float:
        """Percentage of questions that passed (0.0 to 1.0)."""
        if not self.question_results:
            return 0.0
        return self.passed_questions / self.total_questions

    @property
    def weighted_score(self) -> float:
        """Weighted average score across all questions."""
        if not self.question_results:
            return 0.0
        # Note: weights come from Question, need to track them
        total_score = sum(r.score for r in self.question_results)
        return total_score / self.total_questions

    @property
    def total_tokens(self) -> dict[str, int]:
        """Total tokens used across all questions."""
        return {
            "input": sum(r.tokens_input for r in self.question_results),
            "output": sum(r.tokens_output for r in self.question_results),
            "total": sum(r.tokens_input + r.tokens_output for r in self.question_results),
        }

    @property
    def total_duration_ms(self) -> int:
        """Total duration in milliseconds."""
        return sum(r.duration_ms for r in self.question_results)

    def summary(self) -> dict[str, Any]:
        """Generate a summary of the test run."""
        return {
            "run_id": self.run_id,
            "test_id": self.test_id,
            "test_version": self.test_version,
            "environment_id": self.environment_id,
            "model": self.model,
            "provider": self.provider,
            "runner_tool": self.runner_tool,
            "total_questions": self.total_questions,
            "passed": self.passed_questions,
            "failed": self.failed_questions,
            "pass_rate": self.pass_rate,
            "weighted_score": self.weighted_score,
            "total_tokens": self.total_tokens,
            "total_duration_ms": self.total_duration_ms,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }
