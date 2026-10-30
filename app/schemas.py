from typing import Any, Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------
# Shared types
# ---------------------------------------------------------

Engine = Literal[
    "aimode",
    "chatgpt",
    "gemini",
]

CitationType = Literal[
    "inline_hyperlink",
    "sources_panel",
]


# ---------------------------------------------------------
# Dataset input schemas
# ---------------------------------------------------------

class PromptInput(BaseModel):
    prompt_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    text: str = Field(min_length=1)


class ResponseInput(BaseModel):
    response_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    prompt_id: str = Field(min_length=1)

    engine: Engine
    engine_name: str | None = None
    model_version: str | None = None

    answer_text: str = Field(min_length=1)
    answer_markdown: str | None = None

    capture_status: Literal["captured"]

    provider_timestamp: str | None = None
    archive_stored_at: str = Field(min_length=1)

    settings: dict[str, Any] = Field(
        default_factory=dict
    )


class CitationInput(BaseModel):
    citation_id: str = Field(min_length=1)
    response_id: str = Field(min_length=1)
    prompt_id: str = Field(min_length=1)

    engine: Engine

    order: int = Field(ge=1)
    citation_type: CitationType

    url: str = Field(min_length=1)

    domain: str | None = None
    title: str | None = None
    source_name: str | None = None
    publication_date: str | None = None


# ---------------------------------------------------------
# LLM semantic analysis schemas
# ---------------------------------------------------------

class EvidenceItem(BaseModel):
    label: Literal[
        "mentioned",
        "recommended",
        "negative",
    ]

    quote: str = Field(min_length=1)


class ModelAnalysisOutput(BaseModel):
    mentioned: bool
    recommended: bool
    negative: bool

    recommendation_position: int | None = Field(
        default=None,
        ge=1,
    )

    competitors: list[str] = Field(
        default_factory=list
    )

    evidence: list[EvidenceItem] = Field(
        default_factory=list
    )

    confidence: float = Field(
        ge=0.0,
        le=1.0,
    )


# ---------------------------------------------------------
# Analysis API schemas
# ---------------------------------------------------------

class CreateAnalysisRequest(BaseModel):
    """
    Request body for POST /analyses.

    replay:
        Uses the deterministic baseline adapter.

    live:
        Uses the configured LLM provider.
    """

    dataset_id: str = Field(
        min_length=1
    )

    execution_mode: Literal[
        "replay",
        "live",
    ] = "replay"


# ---------------------------------------------------------
# Report content schemas
# ---------------------------------------------------------

class DiagnosticInput(BaseModel):
    """
    One evidence-backed diagnostic finding.
    """

    title: str = Field(
        min_length=1,
        max_length=200,
    )

    finding: str = Field(
        min_length=1,
    )

    response_ids: list[str] = Field(
        default_factory=list,
    )

    evidence: list[str] = Field(
        default_factory=list,
    )


class RemedyInput(BaseModel):
    """
    One prioritized action derived from a diagnostic.
    """

    title: str = Field(
        min_length=1,
        max_length=200,
    )

    problem: str = Field(
        min_length=1,
    )

    action: str = Field(
        min_length=1,
    )

    expected_benefit: str = Field(
        min_length=1,
    )

    effort: Literal[
        "low",
        "medium",
        "high",
    ]

    uncertainty: str = Field(
        min_length=1,
    )

    validation: str = Field(
        min_length=1,
    )


class ReportContent(BaseModel):
    """
    Editable human-facing report content.

    A final report may contain up to three diagnostics
    and three prioritized remedies.
    """

    summary: str = ""

    diagnostics: list[DiagnosticInput] = Field(
        default_factory=list,
        max_length=3,
    )

    remedies: list[RemedyInput] = Field(
        default_factory=list,
        max_length=3,
    )


# ---------------------------------------------------------
# Report API schemas
# ---------------------------------------------------------

class CreateReportRequest(BaseModel):
    """
    Create the first draft report from a completed analysis.
    """

    analysis_id: str = Field(
        min_length=1,
    )


class UpdateReportRequest(BaseModel):
    """
    Update report content.

    expected_version provides optimistic concurrency
    protection against stale edits.
    """

    expected_version: int = Field(
        ge=1,
    )

    content: ReportContent


class SubmitReportRequest(BaseModel):
    """
    Freeze a specific draft version and submit it
    for human review.
    """

    version: int = Field(
        ge=1,
    )


class ReviewDecisionRequest(BaseModel):
    """
    Approve or reject a submitted report version.

    Reviewer identity and role are derived from the
    authenticated bearer token, not the request body.
    """

    version: int = Field(
        ge=1,
    )

    decision: Literal[
        "approved",
        "rejected",
    ]

    comment: str = Field(
        min_length=1,
        max_length=2000,
    )