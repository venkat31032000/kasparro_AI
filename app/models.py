from datetime import datetime, timezone

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utc_now():
    return datetime.now(timezone.utc)


# ============================================================
# DATASET
# ============================================================

class Dataset(Base):
    __tablename__ = "datasets"

    id: Mapped[int] = mapped_column(primary_key=True)

    dataset_id: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        index=True,
    )

    source_run_id: Mapped[str] = mapped_column(
        String(200),
        index=True,
    )

    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
    )

    prompts: Mapped[list["Prompt"]] = relationship(
        back_populates="dataset",
        cascade="all, delete-orphan",
    )

    responses: Mapped[list["Response"]] = relationship(
        back_populates="dataset",
        cascade="all, delete-orphan",
    )


# ============================================================
# PROMPT
# ============================================================

class Prompt(Base):
    __tablename__ = "prompts"

    id: Mapped[int] = mapped_column(primary_key=True)

    dataset_id: Mapped[int] = mapped_column(
        ForeignKey("datasets.id"),
        index=True,
    )

    prompt_id: Mapped[str] = mapped_column(
        String(200),
        index=True,
    )

    run_id: Mapped[str] = mapped_column(
        String(200),
    )

    text: Mapped[str] = mapped_column(Text)

    raw_json: Mapped[str] = mapped_column(Text)

    dataset: Mapped["Dataset"] = relationship(
        back_populates="prompts",
    )

    responses: Mapped[list["Response"]] = relationship(
        back_populates="prompt",
    )

    __table_args__ = (
        UniqueConstraint(
            "dataset_id",
            "prompt_id",
            name="uq_dataset_prompt",
        ),
    )


# ============================================================
# RESPONSE
# ============================================================

class Response(Base):
    __tablename__ = "responses"

    id: Mapped[int] = mapped_column(primary_key=True)

    dataset_id: Mapped[int] = mapped_column(
        ForeignKey("datasets.id"),
        index=True,
    )

    prompt_db_id: Mapped[int] = mapped_column(
        ForeignKey("prompts.id"),
        index=True,
    )

    response_id: Mapped[str] = mapped_column(
        String(200),
        index=True,
    )

    prompt_id: Mapped[str] = mapped_column(
        String(200),
        index=True,
    )

    run_id: Mapped[str] = mapped_column(
        String(200),
    )

    engine: Mapped[str] = mapped_column(
        String(50),
        index=True,
    )

    engine_name: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    model_version: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
    )

    answer_text: Mapped[str] = mapped_column(Text)

    answer_markdown: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    capture_status: Mapped[str] = mapped_column(
        String(50),
    )

    provider_timestamp: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    archive_stored_at: Mapped[str] = mapped_column(
        String(100),
    )

    settings_json: Mapped[str] = mapped_column(
        Text,
        default="{}",
    )

    raw_json: Mapped[str] = mapped_column(Text)

    dataset: Mapped["Dataset"] = relationship(
        back_populates="responses",
    )

    prompt: Mapped["Prompt"] = relationship(
        back_populates="responses",
    )

    citations: Mapped[list["Citation"]] = relationship(
        back_populates="response",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint(
            "dataset_id",
            "response_id",
            name="uq_dataset_response",
        ),
    )


# ============================================================
# CITATION
# ============================================================

class Citation(Base):
    __tablename__ = "citations"

    id: Mapped[int] = mapped_column(primary_key=True)

    response_db_id: Mapped[int] = mapped_column(
        ForeignKey("responses.id"),
        index=True,
    )

    citation_id: Mapped[str] = mapped_column(
        String(200),
        index=True,
    )

    response_id: Mapped[str] = mapped_column(
        String(200),
        index=True,
    )

    prompt_id: Mapped[str] = mapped_column(
        String(200),
        index=True,
    )

    engine: Mapped[str] = mapped_column(
        String(50),
    )

    order: Mapped[int] = mapped_column(Integer)

    citation_type: Mapped[str] = mapped_column(
        String(50),
    )

    url: Mapped[str] = mapped_column(Text)

    domain: Mapped[str | None] = mapped_column(
        String(300),
        nullable=True,
    )

    title: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    source_name: Mapped[str | None] = mapped_column(
        String(300),
        nullable=True,
    )

    publication_date: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    raw_json: Mapped[str] = mapped_column(Text)

    response: Mapped["Response"] = relationship(
        back_populates="citations",
    )

    __table_args__ = (
        UniqueConstraint(
            "response_db_id",
            "citation_id",
            name="uq_response_citation",
        ),
    )


# ============================================================
# ANALYSIS RUN
# ============================================================

class AnalysisRun(Base):
    __tablename__ = "analysis_runs"

    id: Mapped[int] = mapped_column(primary_key=True)

    analysis_id: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        index=True,
    )

    dataset_id: Mapped[int] = mapped_column(
        ForeignKey("datasets.id"),
        index=True,
    )

    execution_mode: Mapped[str] = mapped_column(
        String(30),
    )

    model_name: Mapped[str] = mapped_column(
        String(200),
    )

    prompt_version: Mapped[str] = mapped_column(
        String(50),
    )

    scoring_version: Mapped[str] = mapped_column(
        String(50),
    )

    config_hash: Mapped[str] = mapped_column(
        String(64),
        index=True,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        default="pending",
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    results: Mapped[list["AnalysisResult"]] = relationship(
        back_populates="analysis_run",
        cascade="all, delete-orphan",
    )

    reports: Mapped[list["Report"]] = relationship(
        back_populates="analysis_run",
    )


# ============================================================
# ANALYSIS RESULT
# ============================================================

class AnalysisResult(Base):
    __tablename__ = "analysis_results"

    id: Mapped[int] = mapped_column(primary_key=True)

    analysis_run_id: Mapped[int] = mapped_column(
        ForeignKey("analysis_runs.id"),
        index=True,
    )

    response_db_id: Mapped[int] = mapped_column(
        ForeignKey("responses.id"),
        index=True,
    )

    response_id: Mapped[str] = mapped_column(
        String(200),
        index=True,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        default="pending",
        index=True,
    )

    mentioned: Mapped[bool | None] = mapped_column(
        nullable=True,
    )

    recommended: Mapped[bool | None] = mapped_column(
        nullable=True,
    )

    negative: Mapped[bool | None] = mapped_column(
        nullable=True,
    )

    recommendation_position: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    competitors_json: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    evidence_json: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    confidence: Mapped[float | None] = mapped_column(
        nullable=True,
    )

    visibility_score: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    failure_code: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    failure_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    attempts: Mapped[int] = mapped_column(
        Integer,
        default=0,
    )

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    analysis_run: Mapped["AnalysisRun"] = relationship(
        back_populates="results",
    )

    __table_args__ = (
        UniqueConstraint(
            "analysis_run_id",
            "response_db_id",
            name="uq_analysis_response",
        ),
    )


# ============================================================
# LLM CALL
# ============================================================

class LLMCall(Base):
    __tablename__ = "llm_calls"

    id: Mapped[int] = mapped_column(primary_key=True)

    analysis_result_id: Mapped[int] = mapped_column(
        ForeignKey("analysis_results.id"),
        index=True,
    )

    attempt_number: Mapped[int] = mapped_column(Integer)

    execution_mode: Mapped[str] = mapped_column(
        String(30),
    )

    model_name: Mapped[str] = mapped_column(
        String(200),
    )

    status: Mapped[str] = mapped_column(
        String(30),
    )

    latency_ms: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    error_code: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
    )


# ============================================================
# REPORT
# ============================================================

class Report(Base):
    """
    Stable identity for a report.

    The report itself does not contain mutable report content.
    Content lives in ReportVersion so historical submitted and
    approved versions remain immutable.
    """

    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(primary_key=True)

    report_id: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        index=True,
    )

    analysis_run_id: Mapped[int] = mapped_column(
        ForeignKey("analysis_runs.id"),
        index=True,
    )

    created_by: Mapped[str] = mapped_column(
        String(100),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
    )

    analysis_run: Mapped["AnalysisRun"] = relationship(
        back_populates="reports",
    )

    versions: Mapped[list["ReportVersion"]] = relationship(
        back_populates="report",
        cascade="all, delete-orphan",
        order_by="ReportVersion.version_number",
    )


# ============================================================
# REPORT VERSION
# ============================================================

class ReportVersion(Base):
    """
    Immutable after submission.

    States:
        draft
        submitted
        approved
        rejected
    """

    __tablename__ = "report_versions"

    id: Mapped[int] = mapped_column(primary_key=True)

    report_id: Mapped[int] = mapped_column(
        ForeignKey("reports.id"),
        index=True,
    )

    version_number: Mapped[int] = mapped_column(
        Integer,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        default="draft",
        index=True,
    )

    # Report content is stored as JSON so diagnostics/remedies
    # remain structured rather than flattened into prose.
    content_json: Mapped[str] = mapped_column(
        Text,
        default="{}",
    )

    created_by: Mapped[str] = mapped_column(
        String(100),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )

    submitted_by: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Review must happen before this server-side deadline.
    review_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    report: Mapped["Report"] = relationship(
        back_populates="versions",
    )

    decisions: Mapped[list["ReviewDecision"]] = relationship(
        back_populates="report_version",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint(
            "report_id",
            "version_number",
            name="uq_report_version",
        ),
    )


# ============================================================
# REVIEW DECISION
# ============================================================

class ReviewDecision(Base):
    """
    Audit record for a human review decision.

    The authenticated backend identity determines reviewer_id.
    It must never be trusted from a caller-supplied role field.
    """

    __tablename__ = "review_decisions"

    id: Mapped[int] = mapped_column(primary_key=True)

    report_version_id: Mapped[int] = mapped_column(
        ForeignKey("report_versions.id"),
        index=True,
    )

    decision: Mapped[str] = mapped_column(
        String(30),
    )

    reviewer_id: Mapped[str] = mapped_column(
        String(100),
    )

    comment: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
    )

    report_version: Mapped["ReportVersion"] = relationship(
        back_populates="decisions",
    )

    # One final human decision per version.
    __table_args__ = (
        UniqueConstraint(
            "report_version_id",
            name="uq_review_decision_version",
        ),
    )