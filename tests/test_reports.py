from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
from app.models import (
    AnalysisRun,
    Report,
    ReportVersion,
    utc_now,
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
    """
    Provide a database session backed by this module's
    isolated in-memory SQLite test database.
    """

    db = TestingSessionLocal()

    try:
        yield db
    finally:
        db.close()


client = TestClient(app)


# ============================================================
# AUTH
# ============================================================

ANALYST_HEADERS = {
    "Authorization": (
        "Bearer local-analyst-token"
    )
}

REVIEWER_HEADERS = {
    "Authorization": (
        "Bearer local-reviewer-token"
    )
}


# ============================================================
# SAMPLE REPORT CONTENT
# ============================================================

VALID_CONTENT = {
    "summary": (
        "Kasparro is strongly recognized in branded "
        "prompts but has weak organic discovery visibility."
    ),
    "diagnostics": [
        {
            "title": "Organic discovery gap",
            "finding": (
                "Kasparro did not appear in the "
                "evaluated unbranded discovery prompts."
            ),
            "response_ids": [
                "response:test-1"
            ],
            "evidence": [
                (
                    "0 of 75 successful discovery responses "
                    "mentioned Kasparro."
                )
            ],
        },
        {
            "title": (
                "Recognition does not guarantee recommendation"
            ),
            "finding": (
                "Branded mention frequency was much "
                "higher than recommendation frequency."
            ),
            "response_ids": [
                "response:test-2"
            ],
            "evidence": [
                (
                    "70 of 73 branded responses mentioned "
                    "Kasparro while 19 recommended it."
                )
            ],
        },
        {
            "title": "Negative characterization risk",
            "finding": (
                "Negative characterization differed "
                "materially across engines."
            ),
            "response_ids": [
                "response:test-3"
            ],
            "evidence": [
                (
                    "ChatGPT showed the highest negative "
                    "characterization rate."
                )
            ],
        },
    ],
    "remedies": [
        {
            "title": (
                "Build independent category authority"
            ),
            "problem": (
                "Kasparro has weak organic discovery."
            ),
            "action": (
                "Publish evidence-backed category content "
                "and earn independent references."
            ),
            "expected_benefit": (
                "Increase organic discovery visibility."
            ),
            "effort": "high",
            "uncertainty": (
                "Model retrieval and ranking behavior "
                "may vary over time."
            ),
            "validation": (
                "Repeat the same discovery prompt set "
                "and compare mention rates."
            ),
        },
        {
            "title": (
                "Strengthen recommendation evidence"
            ),
            "problem": (
                "Mentions do not consistently become "
                "recommendations."
            ),
            "action": (
                "Add comparative proof, case studies "
                "and recommendation-oriented evidence."
            ),
            "expected_benefit": (
                "Improve recommendation frequency."
            ),
            "effort": "high",
            "uncertainty": (
                "Recommendation behavior differs "
                "between engines."
            ),
            "validation": (
                "Compare recommendation rate against "
                "the existing branded baseline."
            ),
        },
        {
            "title": (
                "Investigate negative themes"
            ),
            "problem": (
                "Some branded responses characterize "
                "Kasparro negatively."
            ),
            "action": (
                "Cluster negative claims and identify "
                "their likely evidence sources."
            ),
            "expected_benefit": (
                "Reduce recurring negative themes."
            ),
            "effort": "medium",
            "uncertainty": (
                "Some negative claims may originate "
                "from changing external sources."
            ),
            "validation": (
                "Repeat affected prompts and compare "
                "negative characterization rate."
            ),
        },
    ],
}


# ============================================================
# FIXTURES
# ============================================================

@pytest.fixture(autouse=True)
def reset_database():
    """
    Give every test a clean database and install this module's
    FastAPI database dependency override.

    test_analysis.py and test_reports.py share the same global
    FastAPI application object. Each module has its own isolated
    SQLite database, so dependency overrides must be scoped to
    each individual test rather than installed at module import.
    """

    # Install this module's database dependency.
    app.dependency_overrides[get_db] = override_get_db

    # Start every test with a clean schema.
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    yield

    # Clean up the test database.
    Base.metadata.drop_all(bind=engine)

    # Do not leak this module's database override into
    # tests belonging to another module.
    app.dependency_overrides.pop(
        get_db,
        None,
    )


@pytest.fixture
def completed_analysis():
    """
    Create a completed analysis that can be used
    to create reports.
    """

    db = TestingSessionLocal()

    try:
        analysis = AnalysisRun(
            analysis_id="analysis:test-analysis",
            dataset_id=1,
            status="completed",
            execution_mode="replay",
            model_name="test-model",
            prompt_version="test-prompt-v1",
            scoring_version="visibility-v1",
            config_hash="test-config-hash",
        )

        db.add(analysis)
        db.commit()
        db.refresh(analysis)

        return analysis.analysis_id

    finally:
        db.close()


# ============================================================
# HELPERS
# ============================================================

def create_report(
    analysis_id: str,
):
    response = client.post(
        "/reports",
        headers=ANALYST_HEADERS,
        json={
            "analysis_id": analysis_id,
        },
    )

    assert response.status_code in {
        200,
        201,
    }

    return response.json()


def populate_report(
    report_id: str,
    version: int = 1,
):
    response = client.patch(
        f"/reports/{report_id}",
        headers=ANALYST_HEADERS,
        json={
            "expected_version": version,
            "content": VALID_CONTENT,
        },
    )

    assert response.status_code == 200

    return response.json()


def submit_report(
    report_id: str,
    version: int = 1,
):
    response = client.post(
        f"/reports/{report_id}/submit",
        headers=ANALYST_HEADERS,
        json={
            "version": version,
        },
    )

    assert response.status_code == 200

    return response.json()


def approve_report(
    report_id: str,
    version: int = 1,
):
    response = client.post(
        f"/reports/{report_id}/decision",
        headers=REVIEWER_HEADERS,
        json={
            "version": version,
            "decision": "approved",
            "comment": (
                "Evidence reviewed and approved."
            ),
        },
    )

    assert response.status_code == 200

    return response.json()


def create_populated_report(
    analysis_id: str,
):
    created = create_report(
        analysis_id
    )

    report_id = created["report_id"]

    populate_report(
        report_id,
        version=1,
    )

    return report_id


def create_approved_report(
    analysis_id: str,
):
    report_id = create_populated_report(
        analysis_id
    )

    submit_report(
        report_id,
        version=1,
    )

    approve_report(
        report_id,
        version=1,
    )

    return report_id


# ============================================================
# TEST 1
# ANALYST CAN CREATE / EDIT / SUBMIT
# ============================================================

def test_analyst_can_create_edit_and_submit(
    completed_analysis,
):
    report = create_report(
        completed_analysis
    )

    assert report["version"] == 1
    assert report["status"] == "draft"

    updated = populate_report(
        report["report_id"]
    )

    assert updated["status"] == "draft"

    submitted = submit_report(
        report["report_id"]
    )

    assert (
        submitted["status"]
        == "submitted"
    )

    assert (
        submitted["submitted_by"]
        == "analyst"
    )


# ============================================================
# TEST 2
# REVIEWER CANNOT CREATE REPORT
# ============================================================

def test_reviewer_cannot_create_report(
    completed_analysis,
):
    response = client.post(
        "/reports",
        headers=REVIEWER_HEADERS,
        json={
            "analysis_id": completed_analysis,
        },
    )

    assert response.status_code == 403


# ============================================================
# TEST 3
# ANALYST CANNOT APPROVE
# ============================================================

def test_analyst_cannot_approve(
    completed_analysis,
):
    report_id = create_populated_report(
        completed_analysis
    )

    submit_report(
        report_id
    )

    response = client.post(
        f"/reports/{report_id}/decision",
        headers=ANALYST_HEADERS,
        json={
            "version": 1,
            "decision": "approved",
            "comment": (
                "Analyst should not be "
                "allowed to approve."
            ),
        },
    )

    assert response.status_code == 403


# ============================================================
# TEST 4
# REVIEWER CAN APPROVE
# ============================================================

def test_reviewer_can_approve(
    completed_analysis,
):
    report_id = create_populated_report(
        completed_analysis
    )

    submit_report(
        report_id
    )

    result = approve_report(
        report_id
    )

    assert (
        result["status"]
        == "approved"
    )

    assert (
        result["decision"]
        == "approved"
    )

    assert (
        result["reviewer_id"]
        == "reviewer"
    )


# ============================================================
# TEST 5
# REPEATED DECISION IS REJECTED
# ============================================================

def test_repeated_decision_returns_409(
    completed_analysis,
):
    report_id = create_approved_report(
        completed_analysis
    )

    response = client.post(
        f"/reports/{report_id}/decision",
        headers=REVIEWER_HEADERS,
        json={
            "version": 1,
            "decision": "rejected",
            "comment": (
                "Attempting second decision."
            ),
        },
    )

    assert response.status_code == 409


# ============================================================
# TEST 6
# EXPIRED REVIEW CANNOT BE APPROVED
# ============================================================

def test_expired_review_returns_409(
    completed_analysis,
):
    report_id = create_populated_report(
        completed_analysis
    )

    submit_report(
        report_id
    )

    db = TestingSessionLocal()

    try:
        report = db.scalar(
            select(Report).where(
                Report.report_id
                == report_id
            )
        )

        assert report is not None

        version = db.scalar(
            select(ReportVersion).where(
                ReportVersion.report_id
                == report.id,
                ReportVersion.version_number
                == 1,
            )
        )

        assert version is not None

        version.review_expires_at = (
            utc_now()
            - timedelta(minutes=1)
        )

        db.commit()

    finally:
        db.close()

    response = client.post(
        f"/reports/{report_id}/decision",
        headers=REVIEWER_HEADERS,
        json={
            "version": 1,
            "decision": "approved",
            "comment": (
                "This review should be expired."
            ),
        },
    )

    assert response.status_code == 409

    assert "expired" in (
        str(response.json()).lower()
    )


# ============================================================
# TEST 7
# SUBMITTED REPORT CANNOT EXPORT
# ============================================================

def test_unapproved_report_cannot_export(
    completed_analysis,
):
    report_id = create_populated_report(
        completed_analysis
    )

    submit_report(
        report_id
    )

    response = client.get(
        f"/reports/{report_id}/export",
        headers=ANALYST_HEADERS,
        params={
            "version": 1,
        },
    )

    assert response.status_code == 409


# ============================================================
# TEST 8
# APPROVED REPORT CAN EXPORT
# ============================================================

def test_approved_report_can_export(
    completed_analysis,
):
    report_id = create_approved_report(
        completed_analysis
    )

    response = client.get(
        f"/reports/{report_id}/export",
        headers=ANALYST_HEADERS,
        params={
            "version": 1,
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert body["version"] == 1

    assert (
        body["status"]
        == "approved"
    )

    assert (
        body["review"]["decision"]
        == "approved"
    )

    assert (
        body["content"]["summary"]
        == VALID_CONTENT["summary"]
    )


# ============================================================
# TEST 9
# EDIT AFTER APPROVAL CREATES VERSION 2
# ============================================================

def test_edit_after_approval_creates_new_draft(
    completed_analysis,
):
    report_id = create_approved_report(
        completed_analysis
    )

    new_content = dict(
        VALID_CONTENT
    )

    new_content["summary"] = (
        "Updated summary for version two."
    )

    response = client.patch(
        f"/reports/{report_id}",
        headers=ANALYST_HEADERS,
        json={
            "expected_version": 1,
            "content": new_content,
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert body["version"] == 2

    assert body["status"] == "draft"

    assert (
        body["created_new_version"]
        is True
    )


# ============================================================
# TEST 10
# APPROVED V1 REMAINS EXPORTABLE AFTER V2 DRAFT
# ============================================================

def test_old_approved_version_remains_exportable(
    completed_analysis,
):
    report_id = create_approved_report(
        completed_analysis
    )

    new_content = dict(
        VALID_CONTENT
    )

    new_content["summary"] = (
        "Version two is still a draft."
    )

    update_response = client.patch(
        f"/reports/{report_id}",
        headers=ANALYST_HEADERS,
        json={
            "expected_version": 1,
            "content": new_content,
        },
    )

    assert update_response.status_code == 200

    assert (
        update_response.json()["version"]
        == 2
    )

    # Explicitly export immutable approved v1.
    export_response = client.get(
        f"/reports/{report_id}/export",
        headers=ANALYST_HEADERS,
        params={
            "version": 1,
        },
    )

    assert export_response.status_code == 200

    body = export_response.json()

    assert body["version"] == 1

    assert (
        body["status"]
        == "approved"
    )

    assert (
        body["content"]["summary"]
        == VALID_CONTENT["summary"]
    )


# ============================================================
# TEST 11
# STALE EDIT IS REJECTED
# ============================================================

def test_stale_edit_returns_409(
    completed_analysis,
):
    report_id = create_approved_report(
        completed_analysis
    )

    # Approved v1 -> editing creates draft v2.
    first_update = client.patch(
        f"/reports/{report_id}",
        headers=ANALYST_HEADERS,
        json={
            "expected_version": 1,
            "content": VALID_CONTENT,
        },
    )

    assert first_update.status_code == 200

    assert (
        first_update.json()["version"]
        == 2
    )

    # Client still thinks v1 is current.
    stale_update = client.patch(
        f"/reports/{report_id}",
        headers=ANALYST_HEADERS,
        json={
            "expected_version": 1,
            "content": VALID_CONTENT,
        },
    )

    assert stale_update.status_code == 409


# ============================================================
# TEST 12
# REJECTED REPORT CANNOT EXPORT
# ============================================================

def test_rejected_report_cannot_export(
    completed_analysis,
):
    report_id = create_populated_report(
        completed_analysis
    )

    submit_report(
        report_id
    )

    decision_response = client.post(
        f"/reports/{report_id}/decision",
        headers=REVIEWER_HEADERS,
        json={
            "version": 1,
            "decision": "rejected",
            "comment": (
                "Evidence requires revision."
            ),
        },
    )

    assert decision_response.status_code == 200

    assert (
        decision_response.json()["status"]
        == "rejected"
    )

    export_response = client.get(
        f"/reports/{report_id}/export",
        headers=ANALYST_HEADERS,
        params={
            "version": 1,
        },
    )

    assert export_response.status_code == 409