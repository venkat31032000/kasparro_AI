import json

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analysis.service import run_analysis
from app.db import get_db
from app.llm.live import OpenAIAdapter
from app.llm.replay import ReplayAdapter
from app.models import AnalysisResult, AnalysisRun, Response
from app.schemas import CreateAnalysisRequest


router = APIRouter(
    prefix="/analyses",
    tags=["analyses"],
)


# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------

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


def get_analysis_run_or_404(
    analysis_id: str,
    db: Session,
) -> AnalysisRun:
    normalized_id = normalize_analysis_id(
        analysis_id
    )

    analysis_run = db.scalar(
        select(AnalysisRun).where(
            AnalysisRun.analysis_id
            == normalized_id
        )
    )

    if analysis_run is None:
        raise HTTPException(
            status_code=404,
            detail="Analysis not found.",
        )

    return analysis_run


# ---------------------------------------------------------
# POST /analyses
# ---------------------------------------------------------

@router.post(
    "",
    status_code=201,
)
def create_analysis(
    request: CreateAnalysisRequest,
    db: Session = Depends(get_db),
):
    """
    Start or resume an analysis.

    The analysis service is responsible for idempotency:
    identical configurations reuse the existing analysis
    run and completed results are not processed again.
    """

    if request.execution_mode == "live":
        try:
            adapter = OpenAIAdapter()

        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail=(
                    "Live model adapter could not "
                    f"be initialized: {exc}"
                ),
            ) from exc

    else:
        adapter = ReplayAdapter()

    try:
        summary = run_analysis(
            db=db,
            dataset_id=request.dataset_id,
            adapter=adapter,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                "Analysis execution failed: "
                f"{exc}"
            ),
        ) from exc

    return summary


# ---------------------------------------------------------
# GET /analyses/{analysis_id}
# ---------------------------------------------------------

@router.get("/{analysis_id}")
def get_analysis(
    analysis_id: str,
    db: Session = Depends(get_db),
):
    analysis_run = get_analysis_run_or_404(
        analysis_id,
        db,
    )

    results = db.scalars(
        select(AnalysisResult).where(
            AnalysisResult.analysis_run_id
            == analysis_run.id
        )
    ).all()

    total = len(results)

    success = sum(
        1
        for result in results
        if result.status == "success"
    )

    failed = sum(
        1
        for result in results
        if result.status == "failed"
    )

    skipped = sum(
        1
        for result in results
        if result.status == "skipped"
    )

    accounted = (
        success
        + failed
        + skipped
    )

    successful_results = [
        result
        for result in results
        if result.status == "success"
    ]

    mentioned = sum(
        1
        for result in successful_results
        if result.mentioned is True
    )

    recommended = sum(
        1
        for result in successful_results
        if result.recommended is True
    )

    negative = sum(
        1
        for result in successful_results
        if result.negative is True
    )

    scores = [
        result.visibility_score
        for result in successful_results
        if result.visibility_score is not None
    ]

    average_score = (
        round(
            sum(scores) / len(scores),
            1,
        )
        if scores
        else None
    )

    coverage_pct = (
        round(
            success / total * 100,
            1,
        )
        if total
        else 0.0
    )

    return {
        "analysis_id": (
            analysis_run.analysis_id
        ),
        "status": (
            analysis_run.status
        ),
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
        "coverage": {
            "total": total,
            "success": success,
            "failed": failed,
            "skipped": skipped,
            "accounted": accounted,
            "coverage_pct": coverage_pct,
        },
        "metrics": {
            "mentioned": mentioned,
            "recommended": recommended,
            "negative": negative,
            "average_visibility_score": (
                average_score
            ),
        },
        "created_at": (
            analysis_run.created_at
        ),
        "completed_at": (
            analysis_run.completed_at
        ),
    }


# ---------------------------------------------------------
# GET /analyses/{analysis_id}/results
# ---------------------------------------------------------

@router.get(
    "/{analysis_id}/results"
)
def get_analysis_results(
    analysis_id: str,

    engine: str | None = Query(
        default=None,
        pattern=(
            "^(aimode|chatgpt|gemini)$"
        ),
    ),

    status: str | None = Query(
        default=None,
        pattern=(
            "^(success|failed|skipped)$"
        ),
    ),

    limit: int = Query(
        default=20,
        ge=1,
        le=100,
    ),

    offset: int = Query(
        default=0,
        ge=0,
    ),

    db: Session = Depends(get_db),
):
    analysis_run = get_analysis_run_or_404(
        analysis_id,
        db,
    )

    filters = [
        AnalysisResult.analysis_run_id
        == analysis_run.id
    ]

    if status is not None:
        filters.append(
            AnalysisResult.status
            == status
        )

    if engine is not None:
        filters.append(
            Response.engine
            == engine
        )

    # -----------------------------------------------------
    # Count filtered results
    # -----------------------------------------------------

    count_statement = (
        select(
            func.count(
                AnalysisResult.id
            )
        )
        .join(
            Response,
            Response.id
            == AnalysisResult.response_db_id,
        )
        .where(*filters)
    )

    total = (
        db.scalar(
            count_statement
        )
        or 0
    )

    # -----------------------------------------------------
    # Fetch paginated results
    # -----------------------------------------------------

    statement = (
        select(
            AnalysisResult,
            Response,
        )
        .join(
            Response,
            Response.id
            == AnalysisResult.response_db_id,
        )
        .where(*filters)
        .order_by(
            AnalysisResult.id
        )
        .offset(offset)
        .limit(limit)
    )

    rows = db.execute(
        statement
    ).all()

    items = []

    # -----------------------------------------------------
    # Serialize results
    # -----------------------------------------------------

    for result, response in rows:

        competitors = []

        if result.competitors_json:
            try:
                competitors = json.loads(
                    result.competitors_json
                )

            except json.JSONDecodeError:
                competitors = []

        evidence = []

        if result.evidence_json:
            try:
                evidence = json.loads(
                    result.evidence_json
                )

            except json.JSONDecodeError:
                evidence = []

        failure = None

        if result.status == "failed":
            failure = {
                "code": (
                    result.failure_code
                ),
                "message": (
                    result.failure_message
                ),
            }

        items.append(
            {
                "response_id": (
                    response.response_id
                ),
                "prompt_id": (
                    response.prompt_id
                ),
                "engine": (
                    response.engine
                ),
                "status": (
                    result.status
                ),
                "labels": {
                    "mentioned": (
                        result.mentioned
                    ),
                    "recommended": (
                        result.recommended
                    ),
                    "negative": (
                        result.negative
                    ),
                },
                "recommendation_position": (
                    result.recommendation_position
                ),
                "visibility_score": (
                    result.visibility_score
                ),
                "confidence": (
                    result.confidence
                ),
                "competitors": competitors,
                "evidence": evidence,
                "failure": failure,
                "attempts": (
                    result.attempts
                ),
            }
        )

    return {
        "analysis_id": (
            analysis_run.analysis_id
        ),
        "status": (
            analysis_run.status
        ),
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
        "filters": {
            "engine": engine,
            "status": status,
        },
        "pagination": {
            "total": total,
            "limit": limit,
            "offset": offset,
            "returned": len(items),
            "has_more": (
                offset + len(items)
                < total
            ),
        },
        "items": items,
    }