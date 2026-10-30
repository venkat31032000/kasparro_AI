import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.models import Citation, Dataset, Prompt, Response
from app.schemas import CitationInput, PromptInput, ResponseInput


def read_jsonl(path: Path) -> list[tuple[int, dict[str, Any]]]:
    records = []

    with path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            line = line.strip()

            if not line:
                continue

            try:
                record = json.loads(line)

                if not isinstance(record, dict):
                    raise ValueError("Record must be a JSON object")

                records.append((line_number, record))

            except (json.JSONDecodeError, ValueError) as exc:
                records.append(
                    (
                        line_number,
                        {
                            "__read_error__": str(exc),
                        },
                    )
                )

    return records


def import_dataset(
    db: Session,
    data_dir: Path,
) -> dict[str, Any]:

    prompts_path = data_dir / "prompts.jsonl"
    responses_path = data_dir / "responses.jsonl"
    citations_path = data_dir / "citations.jsonl"
    run_path = data_dir / "run.json"

    errors: list[dict[str, Any]] = []

    # --------------------------------------------------
    # Read run metadata
    # --------------------------------------------------

    with run_path.open("r", encoding="utf-8") as file:
        run_data = json.load(file)

    source_run_id = run_data["run_id"]

    dataset_key = f"dataset:{source_run_id}"

    # --------------------------------------------------
    # Idempotent dataset creation
    # --------------------------------------------------

    dataset = (
        db.query(Dataset)
        .filter(Dataset.dataset_id == dataset_key)
        .first()
    )

    if dataset is None:
        dataset = Dataset(
            dataset_id=dataset_key,
            source_run_id=source_run_id,
        )

        db.add(dataset)
        db.commit()
        db.refresh(dataset)

    # --------------------------------------------------
    # Import prompts
    # --------------------------------------------------

    prompt_lookup: dict[str, Prompt] = {}

    for line_number, raw in read_jsonl(prompts_path):

        if "__read_error__" in raw:
            errors.append(
                {
                    "record_type": "prompt",
                    "line": line_number,
                    "code": "INVALID_JSON",
                    "message": raw["__read_error__"],
                }
            )
            continue

        try:
            record = PromptInput.model_validate(raw)
        except ValidationError as exc:
            errors.append(
                {
                    "record_type": "prompt",
                    "line": line_number,
                    "code": "VALIDATION_ERROR",
                    "message": str(exc),
                }
            )
            continue

        existing = (
            db.query(Prompt)
            .filter(
                Prompt.dataset_id == dataset.id,
                Prompt.prompt_id == record.prompt_id,
            )
            .first()
        )

        if existing:
            prompt_lookup[record.prompt_id] = existing
            continue

        prompt = Prompt(
            dataset_id=dataset.id,
            prompt_id=record.prompt_id,
            run_id=record.run_id,
            text=record.text,
            raw_json=json.dumps(raw, ensure_ascii=False),
        )

        db.add(prompt)

        try:
            db.commit()
            db.refresh(prompt)
            prompt_lookup[record.prompt_id] = prompt

        except Exception as exc:
            db.rollback()

            errors.append(
                {
                    "record_type": "prompt",
                    "line": line_number,
                    "code": "DATABASE_ERROR",
                    "message": str(exc),
                }
            )

    # Include previously imported prompts in lookup.
    existing_prompts = (
        db.query(Prompt)
        .filter(Prompt.dataset_id == dataset.id)
        .all()
    )

    for prompt in existing_prompts:
        prompt_lookup[prompt.prompt_id] = prompt

    # --------------------------------------------------
    # Import responses
    # --------------------------------------------------

    response_lookup: dict[str, Response] = {}

    for line_number, raw in read_jsonl(responses_path):

        if "__read_error__" in raw:
            errors.append(
                {
                    "record_type": "response",
                    "line": line_number,
                    "code": "INVALID_JSON",
                    "message": raw["__read_error__"],
                }
            )
            continue

        try:
            record = ResponseInput.model_validate(raw)
        except ValidationError as exc:
            errors.append(
                {
                    "record_type": "response",
                    "line": line_number,
                    "code": "VALIDATION_ERROR",
                    "message": str(exc),
                }
            )
            continue

        prompt = prompt_lookup.get(record.prompt_id)

        if prompt is None:
            errors.append(
                {
                    "record_type": "response",
                    "line": line_number,
                    "code": "UNKNOWN_PROMPT",
                    "message": (
                        f"Prompt {record.prompt_id!r} does not exist"
                    ),
                }
            )
            continue

        # Referential integrity beyond Pydantic validation.
        if record.run_id != prompt.run_id:
            errors.append(
                {
                    "record_type": "response",
                    "line": line_number,
                    "code": "RUN_ID_MISMATCH",
                    "message": (
                        f"Response run_id {record.run_id!r} does not "
                        f"match prompt run_id {prompt.run_id!r}"
                    ),
                }
            )
            continue

        existing = (
            db.query(Response)
            .filter(
                Response.dataset_id == dataset.id,
                Response.response_id == record.response_id,
            )
            .first()
        )

        if existing:
            response_lookup[record.response_id] = existing
            continue

        response = Response(
            dataset_id=dataset.id,
            prompt_db_id=prompt.id,
            response_id=record.response_id,
            prompt_id=record.prompt_id,
            run_id=record.run_id,
            engine=record.engine,
            engine_name=record.engine_name,
            model_version=record.model_version,
            answer_text=record.answer_text,
            answer_markdown=record.answer_markdown,
            capture_status=record.capture_status,
            provider_timestamp=record.provider_timestamp,
            archive_stored_at=record.archive_stored_at,
            settings_json=json.dumps(
                record.settings,
                ensure_ascii=False,
            ),
            raw_json=json.dumps(raw, ensure_ascii=False),
        )

        db.add(response)

        try:
            db.commit()
            db.refresh(response)
            response_lookup[record.response_id] = response

        except Exception as exc:
            db.rollback()

            errors.append(
                {
                    "record_type": "response",
                    "line": line_number,
                    "code": "DATABASE_ERROR",
                    "message": str(exc),
                }
            )

    # Include responses from an earlier idempotent import.
    existing_responses = (
        db.query(Response)
        .filter(Response.dataset_id == dataset.id)
        .all()
    )

    for response in existing_responses:
        response_lookup[response.response_id] = response

    # --------------------------------------------------
    # Import citations
    # --------------------------------------------------

    for line_number, raw in read_jsonl(citations_path):

        if "__read_error__" in raw:
            errors.append(
                {
                    "record_type": "citation",
                    "line": line_number,
                    "code": "INVALID_JSON",
                    "message": raw["__read_error__"],
                }
            )
            continue

        try:
            record = CitationInput.model_validate(raw)
        except ValidationError as exc:
            errors.append(
                {
                    "record_type": "citation",
                    "line": line_number,
                    "code": "VALIDATION_ERROR",
                    "message": str(exc),
                }
            )
            continue

        response = response_lookup.get(record.response_id)

        if response is None:
            errors.append(
                {
                    "record_type": "citation",
                    "line": line_number,
                    "code": "UNKNOWN_RESPONSE",
                    "message": (
                        f"Response {record.response_id!r} does not exist"
                    ),
                }
            )
            continue

        # Cross-record consistency checks.
        if record.prompt_id != response.prompt_id:
            errors.append(
                {
                    "record_type": "citation",
                    "line": line_number,
                    "code": "PROMPT_ID_MISMATCH",
                    "message": (
                        "Citation prompt_id does not match its response"
                    ),
                }
            )
            continue

        if record.engine != response.engine:
            errors.append(
                {
                    "record_type": "citation",
                    "line": line_number,
                    "code": "ENGINE_MISMATCH",
                    "message": (
                        "Citation engine does not match its response"
                    ),
                }
            )
            continue

        existing = (
            db.query(Citation)
            .filter(
                Citation.response_db_id == response.id,
                Citation.citation_id == record.citation_id,
            )
            .first()
        )

        if existing:
            continue

        citation = Citation(
            response_db_id=response.id,
            citation_id=record.citation_id,
            response_id=record.response_id,
            prompt_id=record.prompt_id,
            engine=record.engine,
            order=record.order,
            citation_type=record.citation_type,
            url=record.url,
            domain=record.domain,
            title=record.title,
            source_name=record.source_name,
            publication_date=record.publication_date,
            raw_json=json.dumps(raw, ensure_ascii=False),
        )

        db.add(citation)

        try:
            db.commit()

        except Exception as exc:
            db.rollback()

            errors.append(
                {
                    "record_type": "citation",
                    "line": line_number,
                    "code": "DATABASE_ERROR",
                    "message": str(exc),
                }
            )

    # --------------------------------------------------
    # Final authoritative counts
    # --------------------------------------------------

    prompt_count = (
        db.query(Prompt)
        .filter(Prompt.dataset_id == dataset.id)
        .count()
    )

    response_count = (
        db.query(Response)
        .filter(Response.dataset_id == dataset.id)
        .count()
    )

    citation_count = (
        db.query(Citation)
        .join(Response)
        .filter(Response.dataset_id == dataset.id)
        .count()
    )

    return {
        "dataset_id": dataset.dataset_id,
        "prompts": prompt_count,
        "responses": response_count,
        "citations": citation_count,
        "errors": errors,
    }