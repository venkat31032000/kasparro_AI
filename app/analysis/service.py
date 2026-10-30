import hashlib
import json
import time
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analysis.scoring import (
    SCORING_VERSION,
    calculate_visibility_score,
)
from app.analysis.validation import (
    validate_label_consistency,
    validate_model_evidence,
)
from app.llm.base import (
    InvalidModelOutputError,
    ModelAdapter,
    RetryableModelError,
)
from app.llm.prompt import CLASSIFICATION_PROMPT_VERSION
from app.models import (
    AnalysisResult,
    AnalysisRun,
    Citation,
    Dataset,
    LLMCall,
    Response,
)


PROMPT_VERSION = CLASSIFICATION_PROMPT_VERSION
MAX_ATTEMPTS = 3


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def build_config_hash(
    *,
    execution_mode: str,
    model_name: str,
) -> str:
    """
    Stable identity for the analysis configuration.

    Changing the model, execution mode, prompt version,
    or scoring version creates a different configuration.
    """

    payload = {
        "execution_mode": execution_mode,
        "model_name": model_name,
        "prompt_version": PROMPT_VERSION,
        "scoring_version": SCORING_VERSION,
    }

    serialized = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    )

    return hashlib.sha256(
        serialized.encode("utf-8")
    ).hexdigest()


def has_kasparro_citation(
    db: Session,
    response_db_id: int,
) -> bool:
    """
    Check whether a supplied citation points to a Kasparro domain.

    Citation presence does not mean the citation actually verifies
    the claim made in the archived answer.
    """

    citations = db.scalars(
        select(Citation).where(
            Citation.response_db_id == response_db_id
        )
    ).all()

    for citation in citations:
        domain = (citation.domain or "").lower()
        url = (citation.url or "").lower()

        if "kasparro" in domain or "kasparro" in url:
            return True

    return False


def create_or_get_analysis_run(
    *,
    db: Session,
    dataset: Dataset,
    adapter: ModelAdapter,
) -> AnalysisRun:
    """
    Reuse an existing analysis run when the dataset and
    analysis configuration are identical.

    This makes analysis resumable and prevents duplicate
    completed results.
    """

    config_hash = build_config_hash(
        execution_mode=adapter.execution_mode,
        model_name=adapter.model_name,
    )

    existing = db.scalar(
        select(AnalysisRun).where(
            AnalysisRun.dataset_id == dataset.id,
            AnalysisRun.config_hash == config_hash,
        )
    )

    if existing:
        return existing

    analysis_run = AnalysisRun(
        analysis_id=f"analysis:{uuid.uuid4()}",
        dataset_id=dataset.id,
        execution_mode=adapter.execution_mode,
        model_name=adapter.model_name,
        prompt_version=PROMPT_VERSION,
        scoring_version=SCORING_VERSION,
        config_hash=config_hash,
        status="pending",
    )

    db.add(analysis_run)
    db.commit()
    db.refresh(analysis_run)

    return analysis_run


def get_or_create_result(
    *,
    db: Session,
    analysis_run: AnalysisRun,
    response: Response,
) -> AnalysisResult:

    existing = db.scalar(
        select(AnalysisResult).where(
            AnalysisResult.analysis_run_id == analysis_run.id,
            AnalysisResult.response_db_id == response.id,
        )
    )

    if existing:
        return existing

    result = AnalysisResult(
        analysis_run_id=analysis_run.id,
        response_db_id=response.id,
        response_id=response.response_id,
        status="pending",
        attempts=0,
    )

    db.add(result)
    db.commit()
    db.refresh(result)

    return result


def record_llm_call(
    *,
    db: Session,
    analysis_result: AnalysisResult,
    adapter: ModelAdapter,
    attempt_number: int,
    status: str,
    latency_ms: int | None,
    error_code: str | None = None,
) -> None:

    call = LLMCall(
        analysis_result_id=analysis_result.id,
        attempt_number=attempt_number,
        execution_mode=adapter.execution_mode,
        model_name=adapter.model_name,
        status=status,
        latency_ms=latency_ms,
        error_code=error_code,
    )

    db.add(call)
    db.commit()


def process_response(
    *,
    db: Session,
    analysis_run: AnalysisRun,
    response: Response,
    adapter: ModelAdapter,
) -> str:
    """
    Process exactly one archived response.

    Returns:
        success
        failed
        skipped
    """

    result = get_or_create_result(
        db=db,
        analysis_run=analysis_run,
        response=response,
    )

    # Successful work is never repeated.
    if result.status == "success":
        return "skipped"

    # Empty archived content is explicitly skipped.
    # It must never silently become visibility score zero.
    if not response.answer_text.strip():
        result.status = "skipped"
        result.failure_code = "EMPTY_RESPONSE"
        result.failure_message = (
            "Archived response contains no answer text."
        )
        result.completed_at = utc_now()

        db.commit()

        return "skipped"

    # Failed/pending work can be resumed.
    result.status = "running"
    result.started_at = utc_now()
    result.completed_at = None
    result.failure_code = None
    result.failure_message = None

    db.commit()

    for attempt in range(1, MAX_ATTEMPTS + 1):
        result.attempts = attempt
        db.commit()

        started = time.perf_counter()

        try:
            model_output = adapter.classify(
                prompt_text=response.prompt.text,
                answer_text=response.answer_text,
            )

            latency_ms = int(
                (time.perf_counter() - started) * 1000
            )

            # Model-generated evidence is untrusted until
            # deterministically verified against the archive.
            validate_model_evidence(
                model_output,
                response.answer_text,
            )

            validate_label_consistency(
                model_output,
            )

            kasparro_citation = has_kasparro_citation(
                db,
                response.id,
            )

            score = calculate_visibility_score(
                model_output,
                has_kasparro_citation=kasparro_citation,
            )

            record_llm_call(
                db=db,
                analysis_result=result,
                adapter=adapter,
                attempt_number=attempt,
                status="success",
                latency_ms=latency_ms,
            )

            result.mentioned = model_output.mentioned
            result.recommended = model_output.recommended
            result.negative = model_output.negative

            result.recommendation_position = (
                model_output.recommendation_position
            )

            result.competitors_json = json.dumps(
                model_output.competitors,
                ensure_ascii=False,
            )

            result.evidence_json = json.dumps(
                [
                    evidence.model_dump()
                    for evidence in model_output.evidence
                ],
                ensure_ascii=False,
            )

            result.confidence = model_output.confidence
            result.visibility_score = score

            result.status = "success"
            result.failure_code = None
            result.failure_message = None
            result.completed_at = utc_now()

            db.commit()

            return "success"

        except RetryableModelError as exc:
            latency_ms = int(
                (time.perf_counter() - started) * 1000
            )

            record_llm_call(
                db=db,
                analysis_result=result,
                adapter=adapter,
                attempt_number=attempt,
                status="retryable_failure",
                latency_ms=latency_ms,
                error_code="RETRYABLE_MODEL_ERROR",
            )

            if attempt < MAX_ATTEMPTS:
                continue

            result.status = "failed"
            result.failure_code = "RETRY_EXHAUSTED"
            result.failure_message = str(exc)
            result.completed_at = utc_now()

            db.commit()

            return "failed"

        except InvalidModelOutputError as exc:
            latency_ms = int(
                (time.perf_counter() - started) * 1000
            )

            # Keep the exact-evidence guardrail strict.
            # Invalid semantic output gets another bounded chance
            # instead of being accepted or converted into score zero.
            record_llm_call(
                db=db,
                analysis_result=result,
                adapter=adapter,
                attempt_number=attempt,
                status="invalid_output",
                latency_ms=latency_ms,
                error_code="INVALID_MODEL_OUTPUT",
            )

            if attempt < MAX_ATTEMPTS:
                continue

            result.status = "failed"
            result.failure_code = "INVALID_MODEL_OUTPUT"
            result.failure_message = str(exc)
            result.completed_at = utc_now()

            db.commit()

            return "failed"

        except Exception as exc:
            latency_ms = int(
                (time.perf_counter() - started) * 1000
            )

            record_llm_call(
                db=db,
                analysis_result=result,
                adapter=adapter,
                attempt_number=attempt,
                status="unexpected_failure",
                latency_ms=latency_ms,
                error_code="UNEXPECTED_ERROR",
            )

            result.status = "failed"
            result.failure_code = "UNEXPECTED_ERROR"
            result.failure_message = (
                f"{type(exc).__name__}: {exc}"
            )
            result.completed_at = utc_now()

            db.commit()

            return "failed"

    # Defensive fallback.
    result.status = "failed"
    result.failure_code = "UNKNOWN_FAILURE"
    result.failure_message = (
        "Analysis exited without producing a terminal result."
    )
    result.completed_at = utc_now()

    db.commit()

    return "failed"


def run_analysis(
    *,
    db: Session,
    dataset_id: str,
    adapter: ModelAdapter,
) -> dict:

    dataset = db.scalar(
        select(Dataset).where(
            Dataset.dataset_id == dataset_id
        )
    )

    if dataset is None:
        raise ValueError(
            f"Dataset not found: {dataset_id}"
        )

    analysis_run = create_or_get_analysis_run(
        db=db,
        dataset=dataset,
        adapter=adapter,
    )

    analysis_run.status = "running"
    analysis_run.completed_at = None
    db.commit()

    responses = db.scalars(
        select(Response)
        .where(Response.dataset_id == dataset.id)
        .order_by(Response.id)
    ).all()

    invocation_counts = {
        "success": 0,
        "failed": 0,
        "skipped": 0,
    }

    for index, response in enumerate(
        responses,
        start=1,
    ):
        outcome = process_response(
            db=db,
            analysis_run=analysis_run,
            response=response,
            adapter=adapter,
        )

        invocation_counts[outcome] += 1

        print(
            f"[{index}/{len(responses)}] "
            f"{response.response_id} -> {outcome}"
        )

    # Authoritative counts come from persisted state,
    # which is important when resuming an existing run.
    all_results = db.scalars(
        select(AnalysisResult).where(
            AnalysisResult.analysis_run_id == analysis_run.id
        )
    ).all()

    final_counts = {
        "success": sum(
            1
            for item in all_results
            if item.status == "success"
        ),
        "failed": sum(
            1
            for item in all_results
            if item.status == "failed"
        ),
        "skipped": sum(
            1
            for item in all_results
            if item.status == "skipped"
        ),
    }

    total = len(responses)

    accounted = (
        final_counts["success"]
        + final_counts["failed"]
        + final_counts["skipped"]
    )

    if accounted == total:
        analysis_run.status = "completed"
        analysis_run.completed_at = utc_now()
    else:
        analysis_run.status = "partial"

    db.commit()

    return {
        "analysis_id": analysis_run.analysis_id,
        "dataset_id": dataset.dataset_id,
        "execution_mode": analysis_run.execution_mode,
        "model_name": analysis_run.model_name,
        "prompt_version": analysis_run.prompt_version,
        "scoring_version": analysis_run.scoring_version,
        "total_responses": total,
        "success": final_counts["success"],
        "failed": final_counts["failed"],
        "skipped": final_counts["skipped"],
        "accounted": accounted,
        "status": analysis_run.status,
    }