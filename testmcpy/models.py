"""
SQLAlchemy ORM models for testmcpy.

Defines all database tables for test suites, runs, results,
smoke reports, generation logs, and audit logging.
"""

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON


class Base(DeclarativeBase):
    """Base class for all ORM models."""

    pass


# ==================== Legacy Tables (kept for backward compat) ====================


class TestVersionModel(Base):
    """Legacy: per-file YAML versioning. No new writes."""

    __tablename__ = "test_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    test_path: Mapped[str] = mapped_column(String, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(String, nullable=False)

    __table_args__ = (
        Index("idx_versions_path", "test_path"),
        {"sqlite_autoincrement": True},
    )


class TestResultModel(Base):
    """Legacy: per-test execution results. No new writes."""

    __tablename__ = "test_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    test_path: Mapped[str] = mapped_column(String, nullable=False)
    test_name: Mapped[str] = mapped_column(String, nullable=False)
    version_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("test_versions.id"), nullable=True
    )
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    duration: Mapped[float] = mapped_column(Float, default=0.0)
    cost: Mapped[float] = mapped_column(Float, default=0.0)
    tokens_used: Mapped[int] = mapped_column(Integer, default=0)
    model: Mapped[str | None] = mapped_column(String, nullable=True)
    provider: Mapped[str | None] = mapped_column(String, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    evaluations: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON string
    created_at: Mapped[str] = mapped_column(String, nullable=False)

    __table_args__ = (
        Index("idx_results_path", "test_path"),
        Index("idx_results_created", "created_at"),
        Index("idx_results_model", "model"),
        {"sqlite_autoincrement": True},
    )


# ==================== Core Tables ====================


class TestSuiteModel(Base):
    """Test suite — a collection of questions with auto-versioning."""

    __tablename__ = "test_suites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    suite_id: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    environment_id: Mapped[str | None] = mapped_column(String, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_hash: Mapped[str] = mapped_column(String, nullable=False)
    questions: Mapped[dict | list] = mapped_column(JSON, nullable=False)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)
    tags: Mapped[list | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    runs: Mapped[list["TestRunModel"]] = relationship(back_populates="suite")

    __table_args__ = (
        Index("idx_suites_id", "suite_id"),
        {"sqlite_autoincrement": True},
    )


class TestRunModel(Base):
    """Test run — a grouped execution of a test suite."""

    __tablename__ = "test_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    suite_id: Mapped[str] = mapped_column(
        "test_id", String, ForeignKey("test_suites.suite_id"), nullable=False
    )
    suite_version: Mapped[int] = mapped_column("test_version", Integer, nullable=False)
    environment_id: Mapped[str | None] = mapped_column(String, nullable=True)
    model: Mapped[str] = mapped_column(String, nullable=False)
    provider: Mapped[str] = mapped_column(String, nullable=False)
    mcp_profile_id: Mapped[str | None] = mapped_column(String, nullable=True)
    llm_profile_id: Mapped[str | None] = mapped_column(String, nullable=True)
    runner_tool: Mapped[str] = mapped_column(String, default="mcp-client")
    mcp_setup_version: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, default="running")
    total_cost: Mapped[float] = mapped_column(Float, default=0.0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[str] = mapped_column(String, nullable=False)
    completed_at: Mapped[str | None] = mapped_column(String, nullable=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    suite: Mapped["TestSuiteModel"] = relationship(back_populates="runs")
    question_results: Mapped[list["QuestionResultModel"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_runs_model_provider_started", "model", "provider", "started_at"),
        Index("idx_runs_test_id", "test_id"),
        Index("idx_runs_started", "started_at"),
        Index("idx_runs_status", "status"),
        {"sqlite_autoincrement": True},
    )


class QuestionResultModel(Base):
    """Per-question result within a test run."""

    __tablename__ = "question_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String, ForeignKey("test_runs.run_id"), nullable=False)
    question_id: Mapped[str] = mapped_column(String, nullable=False)
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    tool_uses: Mapped[list | None] = mapped_column(JSON, nullable=True)
    tool_results: Mapped[list | None] = mapped_column(JSON, nullable=True)
    tokens_input: Mapped[int] = mapped_column(Integer, default=0)
    tokens_output: Mapped[int] = mapped_column(Integer, default=0)
    tti_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    evaluations: Mapped[list | None] = mapped_column(JSON, nullable=True)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    run: Mapped["TestRunModel"] = relationship(back_populates="question_results")

    __table_args__ = (
        Index("idx_question_results_run", "run_id"),
        Index("idx_question_results_run_passed", "run_id", "passed"),
        {"sqlite_autoincrement": True},
    )


# ==================== Smoke Reports ====================


class SmokeReportModel(Base):
    """Smoke report — tool discovery/health check results."""

    __tablename__ = "smoke_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_id: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    profile_id: Mapped[str | None] = mapped_column(String, nullable=True)
    profile_name: Mapped[str | None] = mapped_column(String, nullable=True)
    server_url: Mapped[str | None] = mapped_column(String, nullable=True)
    total_tests: Mapped[int] = mapped_column(Integer, default=0)
    passed: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    success_rate: Mapped[float] = mapped_column(Float, default=0.0)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    results: Mapped[list["SmokeReportResultModel"]] = relationship(
        back_populates="report", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_smoke_reports_profile_created", "profile_id", "created_at"),
        Index("idx_smoke_reports_server_url", "server_url"),
        {"sqlite_autoincrement": True},
    )


class SmokeReportResultModel(Base):
    """Per-tool result within a smoke report."""

    __tablename__ = "smoke_report_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_id: Mapped[str] = mapped_column(
        String, ForeignKey("smoke_reports.report_id"), nullable=False
    )
    tool_name: Mapped[str] = mapped_column(String, nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    tool_input: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    tool_output: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    tool_schema: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Relationships
    report: Mapped["SmokeReportModel"] = relationship(back_populates="results")

    __table_args__ = (
        Index("idx_smoke_report_results_report", "report_id"),
        Index("idx_smoke_report_results_tool", "tool_name"),
        {"sqlite_autoincrement": True},
    )


# ==================== Generation Logs ====================


class GenerationLogModel(Base):
    """Generation log — AI test generation metadata."""

    __tablename__ = "generation_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    log_id: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    tool_name: Mapped[str] = mapped_column(String, nullable=False)
    tool_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    coverage_level: Mapped[str | None] = mapped_column(String, nullable=True)
    provider: Mapped[str | None] = mapped_column(String, nullable=True)
    model: Mapped[str | None] = mapped_column(String, nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    test_count: Mapped[int] = mapped_column(Integer, default=0)
    total_cost: Mapped[float] = mapped_column(Float, default=0.0)
    output_file: Mapped[str | None] = mapped_column(String, nullable=True)
    tool_schema: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    generated_yaml: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    llm_calls: Mapped[list["GenerationLLMCallModel"]] = relationship(
        back_populates="log", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_generation_logs_tool_created", "tool_name", "created_at"),
        Index("idx_generation_logs_success", "success"),
        {"sqlite_autoincrement": True},
    )


class GenerationLLMCallModel(Base):
    """Individual LLM call during test generation."""

    __tablename__ = "generation_llm_calls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    log_id: Mapped[str] = mapped_column(
        String, ForeignKey("generation_logs.log_id"), nullable=False
    )
    step: Mapped[int] = mapped_column(Integer, nullable=False)
    prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    response: Mapped[str | None] = mapped_column(Text, nullable=True)
    cost: Mapped[float] = mapped_column(Float, default=0.0)
    tokens: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    log: Mapped["GenerationLogModel"] = relationship(back_populates="llm_calls")

    __table_args__ = (
        Index("idx_generation_llm_calls_log", "log_id"),
        {"sqlite_autoincrement": True},
    )


# ==================== Audit Log ====================


class AuditLogModel(Base):
    """Audit log for profile/config changes."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_type: Mapped[str] = mapped_column(String, nullable=False)
    entity_id: Mapped[str] = mapped_column(String, nullable=False)
    action: Mapped[str] = mapped_column(String, nullable=False)
    changes: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        Index("idx_audit_log_entity", "entity_type", "entity_id"),
        Index("idx_audit_log_created", "created_at"),
        {"sqlite_autoincrement": True},
    )
