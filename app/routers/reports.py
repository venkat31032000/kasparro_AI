import json
import uuid
from datetime import timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import (
    CurrentUser,
    get_current_user,
    require_analyst,
    require_reviewer,
)
from app.db import get_db
from app.models import (
    AnalysisRun,
    Report,
    ReportVersion,
    ReviewDecision,
    utc_now,
)
from app.schemas import (
    CreateReportRequest,
    ReviewDecisionRequest,
    SubmitReportRequest,
    UpdateReportRequest,
)


router = APIRouter(
    prefix="/reports",
    tags=["reports"],
)


# ============================================================
# HELPERS
# ============================================================

def normalize_analysis_id(
    analysis_id: str,
) -> str:
    """
    Accept either:

        analysis:<uuid>

    or:

        <uuid>
    """

    if analysis_id.startswith("analysis:"):
        return analysis_id

    return f"analysis:{analysis_id}"


def normalize_report_id(
    report_id: str,
) -> str:
    """
    Accept either:

        report:<uuid>

    or:

        <uuid>
    """

    if report_id.startswith("report:"):
        return report_id

    return f"report:{report_id}"


def get_report_or_404(
    report_id: str,
    db: Session,
) -> Report:
    """
    Load a report using its public report ID.
    """

    normalized_id = normalize_report_id(
        report_id
    )

    report = db.scalar(
        select(Report).where(
            Report.report_id == normalized_id
        )
    )

    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report not found.",
        )

    return report


def get_latest_version(
    report: Report,
    db: Session,
) -> ReportVersion | None:
    """
    Return the most recent report version.
    """

    return db.scalar(
        select(ReportVersion)
        .where(
            ReportVersion.report_id == report.id
        )
        .order_by(
            ReportVersion.version_number.desc()
        )
        .limit(1)
    )


def ensure_utc(value):
    """
    SQLite can return a naive datetime even when
    timezone-aware datetimes were originally stored.

    Normalize before comparing timestamps.
    """

    if value is None:
        return None

    if value.tzinfo is None:
        return value.replace(
            tzinfo=timezone.utc
        )

    return value.astimezone(
        timezone.utc
    )


# ============================================================
# POST /reports
# ============================================================

@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
)
def create_report(
    request: CreateReportRequest,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(
        require_analyst
    ),
):
    """
    Create the first draft report for a completed analysis.

    Only an analyst may create reports.

    Report creation is idempotent:
    if the analysis already has a report,
    return the existing report.
    """

    analysis_id = normalize_analysis_id(
        request.analysis_id
    )

    analysis_run = db.scalar(
        select(AnalysisRun).where(
            AnalysisRun.analysis_id
            == analysis_id
        )
    )

    if analysis_run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Analysis not found.",
        )

    if analysis_run.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "A report can only be created "
                "from a completed analysis."
            ),
        )

    # --------------------------------------------------------
    # Idempotent report creation
    # --------------------------------------------------------

    existing_report = db.scalar(
        select(Report).where(
            Report.analysis_run_id
            == analysis_run.id
        )
    )

    if existing_report is not None:
        latest_version = get_latest_version(
            existing_report,
            db,
        )

        return {
            "report_id": (
                existing_report.report_id
            ),
            "analysis_id": (
                analysis_run.analysis_id
            ),
            "version": (
                latest_version.version_number
                if latest_version
                else None
            ),
            "status": (
                latest_version.status
                if latest_version
                else None
            ),
            "reused": True,
        }

    # --------------------------------------------------------
    # Create report + initial draft atomically
    # --------------------------------------------------------

    report = Report(
        report_id=f"report:{uuid.uuid4()}",
        analysis_run_id=analysis_run.id,
        created_by=user.user_id,
    )

    db.add(report)

    try:
        # Obtain report.id without committing.
        db.flush()

        first_version = ReportVersion(
            report_id=report.id,
            version_number=1,
            status="draft",
            content_json=json.dumps(
                {
                    "summary": "",
                    "diagnostics": [],
                    "remedies": [],
                },
                ensure_ascii=False,
            ),
            created_by=user.user_id,
        )

        db.add(first_version)

        db.commit()

        db.refresh(report)
        db.refresh(first_version)

    except Exception:
        db.rollback()
        raise

    return {
        "report_id": report.report_id,
        "analysis_id": (
            analysis_run.analysis_id
        ),
        "version": (
            first_version.version_number
        ),
        "status": first_version.status,
        "created_by": report.created_by,
        "created_at": report.created_at,
        "reused": False,
    }


# ============================================================
# PATCH /reports/{report_id}
# ============================================================

@router.patch("/{report_id}")
def update_report(
    report_id: str,
    request: UpdateReportRequest,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(
        require_analyst
    ),
):
    """
    Edit report content.

    expected_version protects against stale edits.

    Draft:
        update in place.

    Submitted/approved/rejected:
        preserve the frozen version and create a new draft.
    """

    report = get_report_or_404(
        report_id,
        db,
    )

    latest_version = get_latest_version(
        report,
        db,
    )

    if latest_version is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Report has no versions.",
        )

    # --------------------------------------------------------
    # Optimistic concurrency protection
    # --------------------------------------------------------

    if (
        request.expected_version
        != latest_version.version_number
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Stale report version.",
                "expected_version": (
                    request.expected_version
                ),
                "current_version": (
                    latest_version.version_number
                ),
            },
        )

    content_json = json.dumps(
        request.content.model_dump(),
        ensure_ascii=False,
    )

    # --------------------------------------------------------
    # Draft -> edit existing draft
    # --------------------------------------------------------

    if latest_version.status == "draft":
        latest_version.content_json = (
            content_json
        )

        latest_version.updated_at = utc_now()

        try:
            db.commit()
            db.refresh(latest_version)

        except Exception:
            db.rollback()
            raise

        return {
            "report_id": report.report_id,
            "version": (
                latest_version.version_number
            ),
            "status": latest_version.status,
            "created_new_version": False,
            "updated_at": (
                latest_version.updated_at
            ),
        }

    # --------------------------------------------------------
    # Frozen version -> create a new draft
    # --------------------------------------------------------

    if latest_version.status in {
        "submitted",
        "approved",
        "rejected",
    }:
        new_version = ReportVersion(
            report_id=report.id,
            version_number=(
                latest_version.version_number
                + 1
            ),
            status="draft",
            content_json=content_json,
            created_by=user.user_id,
        )

        db.add(new_version)

        try:
            db.commit()
            db.refresh(new_version)

        except IntegrityError:
            db.rollback()

            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Another report version was "
                    "created concurrently. Reload "
                    "the report and retry."
                ),
            )

        except Exception:
            db.rollback()
            raise

        return {
            "report_id": report.report_id,
            "version": (
                new_version.version_number
            ),
            "status": new_version.status,
            "created_new_version": True,
            "based_on_version": (
                latest_version.version_number
            ),
            "created_at": (
                new_version.created_at
            ),
        }

    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=(
            "Report version is in an "
            "unsupported state: "
            f"{latest_version.status}"
        ),
    )


# ============================================================
# POST /reports/{report_id}/submit
# ============================================================

@router.post("/{report_id}/submit")
def submit_report(
    report_id: str,
    request: SubmitReportRequest,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(
        require_analyst
    ),
):
    """
    Submit the latest draft for human review.

    Rules:
    - Only analysts may submit.
    - Only the latest version may be submitted.
    - Only a draft may be submitted.
    - Exactly 3 diagnostics are required.
    - Exactly 3 remedies are required.
    - Submission freezes the version.
    - Review expires after 24 hours.
    """

    report = get_report_or_404(
        report_id,
        db,
    )

    latest_version = get_latest_version(
        report,
        db,
    )

    if latest_version is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Report has no versions.",
        )

    # --------------------------------------------------------
    # Stale submission protection
    # --------------------------------------------------------

    if (
        request.version
        != latest_version.version_number
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Stale report version.",
                "requested_version": (
                    request.version
                ),
                "current_version": (
                    latest_version.version_number
                ),
            },
        )

    # --------------------------------------------------------
    # Only drafts may be submitted
    # --------------------------------------------------------

    if latest_version.status != "draft":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Only a draft can be submitted. "
                f"Current status: "
                f"{latest_version.status}"
            ),
        )

    # --------------------------------------------------------
    # Validate stored content
    # --------------------------------------------------------

    try:
        content = json.loads(
            latest_version.content_json
        )

    except (
        json.JSONDecodeError,
        TypeError,
    ):
        raise HTTPException(
            status_code=(
                status.HTTP_422_UNPROCESSABLE_ENTITY
            ),
            detail=(
                "Stored report content "
                "is invalid JSON."
            ),
        )

    diagnostics = content.get(
        "diagnostics",
        [],
    )

    remedies = content.get(
        "remedies",
        [],
    )

    if len(diagnostics) != 3:
        raise HTTPException(
            status_code=(
                status.HTTP_422_UNPROCESSABLE_ENTITY
            ),
            detail={
                "message": (
                    "Report must contain exactly "
                    "3 diagnostics before submission."
                ),
                "diagnostic_count": (
                    len(diagnostics)
                ),
            },
        )

    if len(remedies) != 3:
        raise HTTPException(
            status_code=(
                status.HTTP_422_UNPROCESSABLE_ENTITY
            ),
            detail={
                "message": (
                    "Report must contain exactly "
                    "3 remedies before submission."
                ),
                "remedy_count": (
                    len(remedies)
                ),
            },
        )

    # --------------------------------------------------------
    # Freeze + submit
    # --------------------------------------------------------

    now = utc_now()

    latest_version.status = "submitted"

    latest_version.submitted_by = (
        user.user_id
    )

    latest_version.submitted_at = now

    latest_version.review_expires_at = (
        now + timedelta(hours=24)
    )

    latest_version.updated_at = now

    try:
        db.commit()
        db.refresh(latest_version)

    except Exception:
        db.rollback()
        raise

    return {
        "report_id": report.report_id,
        "version": (
            latest_version.version_number
        ),
        "status": latest_version.status,
        "submitted_by": (
            latest_version.submitted_by
        ),
        "submitted_at": (
            latest_version.submitted_at
        ),
        "review_expires_at": (
            latest_version.review_expires_at
        ),
    }


# ============================================================
# POST /reports/{report_id}/decision
# ============================================================

@router.post("/{report_id}/decision")
def decide_report(
    report_id: str,
    request: ReviewDecisionRequest,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(
        require_reviewer
    ),
):
    """
    Approve or reject a submitted report.

    Rules:
    - Only reviewer identity may decide.
    - Requested version must be the latest version.
    - Version must currently be submitted.
    - Review window must still be active.
    - Exactly one final decision is allowed.
    """

    report = get_report_or_404(
        report_id,
        db,
    )

    latest_version = get_latest_version(
        report,
        db,
    )

    if latest_version is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Report has no versions.",
        )

    # --------------------------------------------------------
    # Stale reviewer protection
    # --------------------------------------------------------

    if (
        request.version
        != latest_version.version_number
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Stale report version.",
                "requested_version": (
                    request.version
                ),
                "current_version": (
                    latest_version.version_number
                ),
            },
        )

    # --------------------------------------------------------
    # Only submitted versions may be reviewed
    # --------------------------------------------------------

    if latest_version.status != "submitted":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Only a submitted report can "
                "receive a review decision. "
                f"Current status: "
                f"{latest_version.status}"
            ),
        )

    # --------------------------------------------------------
    # Server-side review expiry
    # --------------------------------------------------------

    expires_at = ensure_utc(
        latest_version.review_expires_at
    )

    now = ensure_utc(
        utc_now()
    )

    if expires_at is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Submitted report has no "
                "review expiry timestamp."
            ),
        )

    if now > expires_at:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": (
                    "Review window expired. "
                    "The report was not auto-approved."
                ),
                "review_expires_at": (
                    expires_at.isoformat()
                ),
            },
        )

    # --------------------------------------------------------
    # Prevent repeated decisions
    # --------------------------------------------------------

    existing_decision = db.scalar(
        select(ReviewDecision).where(
            ReviewDecision.report_version_id
            == latest_version.id
        )
    )

    if existing_decision is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "This report version already "
                "has a final review decision."
            ),
        )

    # --------------------------------------------------------
    # Persist decision + state transition atomically
    # --------------------------------------------------------

    decision = ReviewDecision(
        report_version_id=latest_version.id,
        decision=request.decision,
        reviewer_id=user.user_id,
        comment=request.comment,
        decided_at=now,
    )

    db.add(decision)

    latest_version.status = (
        request.decision
    )

    latest_version.updated_at = now

    try:
        db.commit()

        db.refresh(decision)
        db.refresh(latest_version)

    except IntegrityError:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "A final review decision already "
                "exists for this report version."
            ),
        )

    except Exception:
        db.rollback()
        raise

    return {
        "report_id": report.report_id,
        "version": (
            latest_version.version_number
        ),
        "status": latest_version.status,
        "decision": decision.decision,
        "reviewer_id": (
            decision.reviewer_id
        ),
        "comment": decision.comment,
        "decided_at": (
            decision.decided_at
        ),
    }


# ============================================================
# GET /reports/{report_id}/export
# ============================================================

@router.get("/{report_id}/export")
def export_report(
    report_id: str,
    version: int | None = None,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(
        get_current_user
    ),
):
    """
    Export an approved report version.

    Rules:
    - Authentication is required.
    - Only approved versions may be exported.
    - If version is provided, export that exact version.
    - If version is omitted, export the latest approved version.
    - Older approved versions remain exportable if a newer
      draft is later created.
    """

    report = get_report_or_404(
        report_id,
        db,
    )

    analysis_run = db.get(
        AnalysisRun,
        report.analysis_run_id,
    )

    if analysis_run is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Report is not connected to "
                "a valid analysis."
            ),
        )

    # --------------------------------------------------------
    # Explicit version requested
    # --------------------------------------------------------

    if version is not None:
        report_version = db.scalar(
            select(ReportVersion).where(
                ReportVersion.report_id
                == report.id,
                ReportVersion.version_number
                == version,
            )
        )

        if report_version is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=(
                    f"Report version {version} "
                    "not found."
                ),
            )

        if report_version.status != "approved":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "message": (
                        "Only approved report "
                        "versions can be exported."
                    ),
                    "version": (
                        report_version.version_number
                    ),
                    "status": (
                        report_version.status
                    ),
                },
            )

    # --------------------------------------------------------
    # No version requested -> latest approved version
    # --------------------------------------------------------

    else:
        report_version = db.scalar(
            select(ReportVersion)
            .where(
                ReportVersion.report_id
                == report.id,
                ReportVersion.status
                == "approved",
            )
            .order_by(
                ReportVersion.version_number.desc()
            )
            .limit(1)
        )

        if report_version is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "No approved report version "
                    "is available for export."
                ),
            )

    # --------------------------------------------------------
    # Verify human approval
    # --------------------------------------------------------

    decision = db.scalar(
        select(ReviewDecision).where(
            ReviewDecision.report_version_id
            == report_version.id
        )
    )

    if decision is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Approved report version has no "
                "recorded review decision."
            ),
        )

    if decision.decision != "approved":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Report review decision does "
                "not permit export."
            ),
        )

    # --------------------------------------------------------
    # Parse frozen report content
    # --------------------------------------------------------

    try:
        content = json.loads(
            report_version.content_json
        )

    except (
        json.JSONDecodeError,
        TypeError,
    ):
        raise HTTPException(
            status_code=(
                status.HTTP_500_INTERNAL_SERVER_ERROR
            ),
            detail=(
                "Approved report contains "
                "invalid stored content."
            ),
        )

    # --------------------------------------------------------
    # Return version-safe export
    # --------------------------------------------------------

    return {
        "report_id": report.report_id,
        "analysis_id": (
            analysis_run.analysis_id
        ),
        "version": (
            report_version.version_number
        ),
        "status": (
            report_version.status
        ),
        "analysis_config": {
            "execution_mode": (
                analysis_run.execution_mode
            ),
            "model_name": (
                analysis_run.model_name
            ),
            "prompt_version": (
                analysis_run.prompt_version
            ),
            "scoring_version": (
                analysis_run.scoring_version
            ),
            "config_hash": (
                analysis_run.config_hash
            ),
        },
        "review": {
            "decision": (
                decision.decision
            ),
            "reviewer_id": (
                decision.reviewer_id
            ),
            "comment": (
                decision.comment
            ),
            "decided_at": (
                decision.decided_at
            ),
        },
        "content": content,
    }


# ============================================================
# GET /reports/{report_id}
# ============================================================

@router.get("/{report_id}")
def get_report(
    report_id: str,
    db: Session = Depends(get_db),
):
    """
    Return report metadata and complete version history.
    """

    report = get_report_or_404(
        report_id,
        db,
    )

    analysis_run = db.get(
        AnalysisRun,
        report.analysis_run_id,
    )

    versions = db.scalars(
        select(ReportVersion)
        .where(
            ReportVersion.report_id
            == report.id
        )
        .order_by(
            ReportVersion.version_number
        )
    ).all()

    serialized_versions = []

    for version in versions:
        try:
            content = json.loads(
                version.content_json
            )

        except (
            json.JSONDecodeError,
            TypeError,
        ):
            content = {}

        decision = db.scalar(
            select(ReviewDecision).where(
                ReviewDecision.report_version_id
                == version.id
            )
        )

        serialized_versions.append(
            {
                "version": (
                    version.version_number
                ),
                "status": (
                    version.status
                ),
                "content": content,
                "created_by": (
                    version.created_by
                ),
                "created_at": (
                    version.created_at
                ),
                "updated_at": (
                    version.updated_at
                ),
                "submitted_by": (
                    version.submitted_by
                ),
                "submitted_at": (
                    version.submitted_at
                ),
                "review_expires_at": (
                    version.review_expires_at
                ),
                "review": (
                    {
                        "decision": (
                            decision.decision
                        ),
                        "reviewer_id": (
                            decision.reviewer_id
                        ),
                        "comment": (
                            decision.comment
                        ),
                        "decided_at": (
                            decision.decided_at
                        ),
                    }
                    if decision
                    else None
                ),
            }
        )

    return {
        "report_id": report.report_id,
        "analysis_id": (
            analysis_run.analysis_id
            if analysis_run
            else None
        ),
        "created_by": (
            report.created_by
        ),
        "created_at": (
            report.created_at
        ),
        "versions": (
            serialized_versions
        ),
    }