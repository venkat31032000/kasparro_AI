import json
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.analysis.service import run_analysis
from app.db import Base, get_db
from app.llm.replay import ReplayAdapter
from app.main import app
from app.models import (
    AnalysisResult,
    AnalysisRun,
    Dataset,
    LLMCall,
    Prompt,
    Response,
)


# ============================================================
# TEST DATABASE
# ============================================================

TEST_DATABASE_URL = "sqlite://"

engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={
        "check_same_thread": False,
    },
    poolclass=StaticPool,
)

TestingSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


def override_get_db():
    db = TestingSessionLocal()

    try:
        yield db
    finally:
        db.close()


client = TestClient(app)


# ============================================================
# HELPERS
# ============================================================

def utc_now():
    return datetime.now(timezone.utc)


def run_replay_analysis(dataset_id: str):
    db = TestingSessionLocal()

    try:
        return run_analysis(
            db=db,
            dataset_id=dataset_id,
            adapter=ReplayAdapter(),
        )
    finally:
        db.close()


# ============================================================
# DATABASE RESET / DEPENDENCY ISOLATION
# ============================================================

@pytest.fixture(autouse=True)
def reset_database():
    """
    Give every analysis test a clean database and explicitly install
    this module's FastAPI database dependency override.

    test_analysis.py and test_reports.py share the same global FastAPI
    application object. Both suites use their own SQLite test database,
    so installing the override at module-import time would allow one
    test module to overwrite the other during pytest collection.
    """

    app.dependency_overrides[get_db] = override_get_db

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    yield

    Base.metadata.drop_all(bind=engine)

    app.dependency_overrides.pop(get_db, None)


# ============================================================
# SAMPLE DATASET
# ============================================================

@pytest.fixture
def sample_dataset():
    """
    Small deterministic dataset containing:

    1. Kasparro mentioned
    2. Kasparro recommended
    3. Kasparro negatively characterized
    4. Kasparro absent
    5. Empty archived response

    No external model calls are made.
    """

    db = TestingSessionLocal()

    try:
        source_run_id = "test-source-run"

        dataset = Dataset(
            dataset_id="dataset:test-analysis",
            source_run_id=source_run_id,
        )

        db.add(dataset)
        db.flush()

        prompts = []

        for index in range(1, 6):
            prompt_id = f"prompt:test-{index}"

            prompt = Prompt(
                dataset_id=dataset.id,
                prompt_id=prompt_id,
                run_id=source_run_id,
                text=f"Test prompt {index}",
                raw_json=json.dumps(
                    {
                        "prompt_id": prompt_id,
                        "text": f"Test prompt {index}",
                    }
                ),
            )

            db.add(prompt)
            prompts.append(prompt)

        db.flush()

        response_specs = [
            {
                "response_id": "response:test-mentioned",
                "engine": "chatgpt",
                "answer_text": (
                    "Kasparro is an AI visibility platform."
                ),
            },
            {
                "response_id": "response:test-recommended",
                "engine": "gemini",
                "answer_text": (
                    "Consider Kasparro for AI visibility analysis."
                ),
            },
            {
                "response_id": "response:test-negative",
                "engine": "aimode",
                "answer_text": (
                    "Kasparro is limited for this particular use case."
                ),
            },
            {
                "response_id": "response:test-absent",
                "engine": "chatgpt",
                "answer_text": (
                    "Profound and Otterly are tools in this category."
                ),
            },
            {
                "response_id": "response:test-empty",
                "engine": "gemini",
                "answer_text": "",
            },
        ]

        responses = []

        for index, spec in enumerate(response_specs):
            prompt = prompts[index]

            response = Response(
                dataset_id=dataset.id,
                prompt_db_id=prompt.id,
                response_id=spec["response_id"],
                prompt_id=prompt.prompt_id,
                run_id=source_run_id,
                engine=spec["engine"],
                engine_name=spec["engine"],
                model_version="test-model-v1",
                answer_text=spec["answer_text"],
                answer_markdown=None,
                capture_status="success",
                provider_timestamp=None,
                archive_stored_at=utc_now(),
                settings_json=json.dumps({}),
                raw_json=json.dumps(
                    {
                        "response_id": spec["response_id"],
                        "prompt_id": prompt.prompt_id,
                        "engine": spec["engine"],
                        "answer_text": spec["answer_text"],
                    }
                ),
            )

            responses.append(response)

        db.add_all(responses)
        db.commit()

        return dataset.dataset_id

    finally:
        db.close()


# ============================================================
# TEST 1
# ALL RESPONSES ARE ACCOUNTED FOR
# ============================================================

def test_all_responses_are_accounted_for(
    sample_dataset,
):
    result = run_replay_analysis(
        sample_dataset
    )

    assert result["total_responses"] == 5
    assert result["accounted"] == 5

    assert (
        result["success"]
        + result["failed"]
        + result["skipped"]
        == 5
    )

    assert result["status"] == "completed"


# ============================================================
# TEST 2
# EMPTY RESPONSE IS SKIPPED, NOT ZERO
# ============================================================

def test_empty_response_is_explicitly_skipped(
    sample_dataset,
):
    result = run_replay_analysis(
        sample_dataset
    )

    assert result["skipped"] == 1

    db = TestingSessionLocal()

    try:
        analysis_result = db.scalar(
            select(AnalysisResult).where(
                AnalysisResult.response_id
                == "response:test-empty"
            )
        )

        assert analysis_result is not None
        assert analysis_result.status == "skipped"

        assert (
            analysis_result.failure_code
            == "EMPTY_RESPONSE"
        )

        assert (
            analysis_result.visibility_score
            is None
        )

        assert analysis_result.completed_at is not None

    finally:
        db.close()


# ============================================================
# TEST 3
# SAME CONFIG REUSES ANALYSIS RUN
# ============================================================

def test_same_config_reuses_analysis_run(
    sample_dataset,
):
    first = run_replay_analysis(
        sample_dataset
    )

    second = run_replay_analysis(
        sample_dataset
    )

    assert (
        first["analysis_id"]
        == second["analysis_id"]
    )

    db = TestingSessionLocal()

    try:
        count = db.scalar(
            select(
                func.count(
                    AnalysisRun.id
                )
            )
        )

        assert count == 1

    finally:
        db.close()


# ============================================================
# TEST 4
# RERUN DOES NOT DUPLICATE RESULTS
# ============================================================

def test_rerun_does_not_duplicate_results(
    sample_dataset,
):
    first = run_replay_analysis(
        sample_dataset
    )

    run_replay_analysis(
        sample_dataset
    )

    db = TestingSessionLocal()

    try:
        analysis_run = db.scalar(
            select(AnalysisRun).where(
                AnalysisRun.analysis_id
                == first["analysis_id"]
            )
        )

        assert analysis_run is not None

        result_count = db.scalar(
            select(
                func.count(
                    AnalysisResult.id
                )
            ).where(
                AnalysisResult.analysis_run_id
                == analysis_run.id
            )
        )

        assert result_count == 5

    finally:
        db.close()


# ============================================================
# TEST 5
# SUCCESSFUL RESULTS ARE NOT REPROCESSED
# ============================================================

def test_successful_results_are_not_reprocessed(
    sample_dataset,
):
    first = run_replay_analysis(
        sample_dataset
    )

    db = TestingSessionLocal()

    try:
        analysis_run = db.scalar(
            select(AnalysisRun).where(
                AnalysisRun.analysis_id
                == first["analysis_id"]
            )
        )

        assert analysis_run is not None

        calls_before = db.scalar(
            select(
                func.count(
                    LLMCall.id
                )
            )
            .join(
                AnalysisResult,
                AnalysisResult.id
                == LLMCall.analysis_result_id,
            )
            .where(
                AnalysisResult.analysis_run_id
                == analysis_run.id
            )
        )

    finally:
        db.close()

    run_replay_analysis(
        sample_dataset
    )

    db = TestingSessionLocal()

    try:
        analysis_run = db.scalar(
            select(AnalysisRun).where(
                AnalysisRun.analysis_id
                == first["analysis_id"]
            )
        )

        assert analysis_run is not None

        calls_after = db.scalar(
            select(
                func.count(
                    LLMCall.id
                )
            )
            .join(
                AnalysisResult,
                AnalysisResult.id
                == LLMCall.analysis_result_id,
            )
            .where(
                AnalysisResult.analysis_run_id
                == analysis_run.id
            )
        )

        assert calls_after == calls_before

    finally:
        db.close()


# ============================================================
# TEST 6
# REPLAY LABELS ARE PERSISTED
# ============================================================

def test_replay_labels_are_persisted(
    sample_dataset,
):
    run_replay_analysis(
        sample_dataset
    )

    db = TestingSessionLocal()

    try:
        mentioned = db.scalar(
            select(AnalysisResult).where(
                AnalysisResult.response_id
                == "response:test-mentioned"
            )
        )

        recommended = db.scalar(
            select(AnalysisResult).where(
                AnalysisResult.response_id
                == "response:test-recommended"
            )
        )

        negative = db.scalar(
            select(AnalysisResult).where(
                AnalysisResult.response_id
                == "response:test-negative"
            )
        )

        absent = db.scalar(
            select(AnalysisResult).where(
                AnalysisResult.response_id
                == "response:test-absent"
            )
        )

        assert mentioned is not None
        assert mentioned.status == "success"
        assert mentioned.mentioned is True
        assert mentioned.recommended is False
        assert mentioned.negative is False

        assert recommended is not None
        assert recommended.status == "success"
        assert recommended.mentioned is True
        assert recommended.recommended is True

        assert negative is not None
        assert negative.status == "success"
        assert negative.mentioned is True
        assert negative.negative is True

        assert absent is not None
        assert absent.status == "success"
        assert absent.mentioned is False
        assert absent.recommended is False
        assert absent.negative is False

    finally:
        db.close()


# ============================================================
# TEST 7
# FAILURE IS ACCOUNTED FOR AND NOT SCORED ZERO
# ============================================================

def test_failed_result_is_not_treated_as_zero_score(
    sample_dataset,
):
    """
    Simulate a persisted failed result.

    The API must count it as failed and must not
    reinterpret the failure as a successful score of zero.
    """

    first = run_replay_analysis(
        sample_dataset
    )

    db = TestingSessionLocal()

    try:
        failed_result = db.scalar(
            select(AnalysisResult).where(
                AnalysisResult.response_id
                == "response:test-mentioned"
            )
        )

        assert failed_result is not None

        failed_result.status = "failed"
        failed_result.failure_code = (
            "SYNTHETIC_FAILURE"
        )
        failed_result.failure_message = (
            "Synthetic test failure."
        )

        failed_result.visibility_score = None
        failed_result.mentioned = None
        failed_result.recommended = None
        failed_result.negative = None

        db.commit()

    finally:
        db.close()

    response = client.get(
        f"/analyses/{first['analysis_id']}"
    )

    assert response.status_code == 200

    body = response.json()

    assert body["coverage"]["total"] == 5
    assert body["coverage"]["success"] == 3
    assert body["coverage"]["failed"] == 1
    assert body["coverage"]["skipped"] == 1
    assert body["coverage"]["accounted"] == 5

    db = TestingSessionLocal()

    try:
        failed_result = db.scalar(
            select(AnalysisResult).where(
                AnalysisResult.response_id
                == "response:test-mentioned"
            )
        )

        assert failed_result is not None
        assert failed_result.visibility_score is None

    finally:
        db.close()


# ============================================================
# TEST 8
# ANALYSIS SUMMARY API
# ============================================================

def test_analysis_summary_endpoint(
    sample_dataset,
):
    result = run_replay_analysis(
        sample_dataset
    )

    response = client.get(
        f"/analyses/{result['analysis_id']}"
    )

    assert response.status_code == 200

    body = response.json()

    assert (
        body["analysis_id"]
        == result["analysis_id"]
    )

    assert (
        body["execution_mode"]
        == "replay"
    )

    assert (
        body["model_name"]
        == "deterministic-replay-v1"
    )

    assert body["coverage"]["total"] == 5
    assert body["coverage"]["success"] == 4
    assert body["coverage"]["failed"] == 0
    assert body["coverage"]["skipped"] == 1
    assert body["coverage"]["accounted"] == 5

    assert (
        body["coverage"]["coverage_pct"]
        == 80.0
    )

    assert (
        body["metrics"]["mentioned"]
        == 3
    )

    assert (
        body["metrics"]["recommended"]
        == 1
    )

    assert (
        body["metrics"]["negative"]
        == 1
    )


# ============================================================
# TEST 9
# STATUS FILTER
# ============================================================

def test_results_endpoint_filters_by_status(
    sample_dataset,
):
    result = run_replay_analysis(
        sample_dataset
    )

    response = client.get(
        (
            f"/analyses/"
            f"{result['analysis_id']}/results"
        ),
        params={
            "status": "skipped",
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert (
        body["filters"]["status"]
        == "skipped"
    )

    assert (
        body["pagination"]["total"]
        == 1
    )

    assert (
        body["pagination"]["returned"]
        == 1
    )

    assert (
        body["items"][0]["status"]
        == "skipped"
    )

    assert (
        body["items"][0]["response_id"]
        == "response:test-empty"
    )


# ============================================================
# TEST 10
# ENGINE FILTER
# ============================================================

def test_results_endpoint_filters_by_engine(
    sample_dataset,
):
    result = run_replay_analysis(
        sample_dataset
    )

    response = client.get(
        (
            f"/analyses/"
            f"{result['analysis_id']}/results"
        ),
        params={
            "engine": "gemini",
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert (
        body["filters"]["engine"]
        == "gemini"
    )

    assert (
        body["pagination"]["total"]
        == 2
    )

    assert (
        body["pagination"]["returned"]
        == 2
    )

    assert all(
        item["engine"] == "gemini"
        for item in body["items"]
    )


# ============================================================
# TEST 11
# PAGINATION
# ============================================================

def test_results_endpoint_paginates(
    sample_dataset,
):
    result = run_replay_analysis(
        sample_dataset
    )

    first_page = client.get(
        (
            f"/analyses/"
            f"{result['analysis_id']}/results"
        ),
        params={
            "limit": 2,
            "offset": 0,
        },
    )

    assert first_page.status_code == 200

    first_body = first_page.json()

    assert (
        first_body["pagination"]["total"]
        == 5
    )

    assert (
        first_body["pagination"]["limit"]
        == 2
    )

    assert (
        first_body["pagination"]["offset"]
        == 0
    )

    assert (
        first_body["pagination"]["returned"]
        == 2
    )

    assert (
        first_body["pagination"]["has_more"]
        is True
    )

    second_page = client.get(
        (
            f"/analyses/"
            f"{result['analysis_id']}/results"
        ),
        params={
            "limit": 2,
            "offset": 2,
        },
    )

    assert second_page.status_code == 200

    second_body = second_page.json()

    assert (
        second_body["pagination"]["offset"]
        == 2
    )

    assert (
        second_body["pagination"]["returned"]
        == 2
    )

    assert (
        second_body["pagination"]["has_more"]
        is True
    )

    third_page = client.get(
        (
            f"/analyses/"
            f"{result['analysis_id']}/results"
        ),
        params={
            "limit": 2,
            "offset": 4,
        },
    )

    assert third_page.status_code == 200

    third_body = third_page.json()

    assert (
        third_body["pagination"]["offset"]
        == 4
    )

    assert (
        third_body["pagination"]["returned"]
        == 1
    )

    assert (
        third_body["pagination"]["has_more"]
        is False
    )


# ============================================================
# TEST 12
# UNKNOWN ANALYSIS
# ============================================================

def test_unknown_analysis_returns_404():
    response = client.get(
        "/analyses/does-not-exist"
    )

    assert response.status_code == 404