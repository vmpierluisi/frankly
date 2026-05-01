"""Tests for GET /companies/{id}/leaderboard."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_session
from app.main import app as fastapi_app
from app import models
from app.auth import CurrentUser, require_manager


def _make_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    return engine


_TEST_MANAGER = CurrentUser(
    auth_user_id="manager-001",
    email="manager@example.com",
    role="manager",
)


@pytest.fixture()
def client_and_db():
    engine = _make_engine()
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    db = Session()

    company = models.Company(
        id="test-co",
        name="Test Co",
        role="Analyst",
        role_family="financial_analyst",
        target_seniority="mid",
        is_open=True,
    )
    db.add(company)

    cand_a = models.Candidate(
        display_name="Alice",
        target_role_family="financial_analyst",
        target_seniority="mid",
        assessment_status="completed",
        bfi_responses={},
        sjt_responses={},
    )
    cand_b = models.Candidate(
        display_name="Bob",
        target_role_family="financial_analyst",
        target_seniority="mid",
        assessment_status="completed",
        bfi_responses={},
        sjt_responses={},
    )
    cand_c = models.Candidate(
        display_name="Carol",
        target_role_family="financial_analyst",
        target_seniority="mid",
        assessment_status="completed",
        bfi_responses={},
        sjt_responses={},
    )
    db.add_all([cand_a, cand_b, cand_c])
    db.flush()

    now = datetime.now(timezone.utc)
    match_a = models.Match(
        candidate_id=cand_a.id,
        company_id="test-co",
        status="succeeded",
        overall_score=85,
        band="Strong fit",
        band_note="",
        report={"overallScore": 85},
        finished_at=now,
    )
    match_b = models.Match(
        candidate_id=cand_b.id,
        company_id="test-co",
        status="succeeded",
        overall_score=70,
        band="Good fit",
        band_note="",
        report={"overallScore": 70},
        finished_at=now,
    )
    match_c = models.Match(
        candidate_id=cand_c.id,
        company_id="test-co",
        status="pending",
        overall_score=0,
        band="",
        band_note="",
        report={},
    )
    db.add_all([match_a, match_b, match_c])
    db.commit()

    def _override_session():
        try:
            yield db
        finally:
            pass

    def _override_manager():
        return _TEST_MANAGER

    fastapi_app.dependency_overrides[get_session] = _override_session
    fastapi_app.dependency_overrides[require_manager] = _override_manager

    with TestClient(fastapi_app, raise_server_exceptions=True) as c:
        yield c, db, company, cand_a, cand_b, cand_c

    fastapi_app.dependency_overrides.clear()
    db.close()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def test_leaderboard_returns_all_statuses(client_and_db):
    client, db, company, *_ = client_and_db
    resp = client.get("/companies/test-co/leaderboard")
    assert resp.status_code == 200
    data = resp.json()
    assert data["company_id"] == "test-co"
    assert data["is_open"] is True
    assert len(data["results"]) == 3


def test_leaderboard_succeeded_before_pending(client_and_db):
    client, db, company, cand_a, cand_b, cand_c = client_and_db
    resp = client.get("/companies/test-co/leaderboard")
    results = resp.json()["results"]

    statuses = [r["status"] for r in results]
    # succeeded rows should come before pending
    assert statuses[0] == "succeeded"
    assert statuses[1] == "succeeded"
    assert statuses[2] == "pending"


def test_leaderboard_succeeded_ordered_by_score_desc(client_and_db):
    client, db, company, cand_a, cand_b, cand_c = client_and_db
    resp = client.get("/companies/test-co/leaderboard")
    results = resp.json()["results"]

    succeeded = [r for r in results if r["status"] == "succeeded"]
    assert succeeded[0]["overall_score"] == 85
    assert succeeded[1]["overall_score"] == 70


def test_leaderboard_404_for_unknown_company(client_and_db):
    client, *_ = client_and_db
    resp = client.get("/companies/does-not-exist/leaderboard")
    assert resp.status_code == 404


def test_leaderboard_requires_manager_auth():
    """Without manager override, the endpoint should return 401."""
    engine = _make_engine()
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    db = Session()
    company = models.Company(
        id="auth-test-co", name="Auth Test", role="Analyst",
        role_family="financial_analyst", target_seniority="mid", is_open=True,
    )
    db.add(company)
    db.commit()

    def _override_session():
        try:
            yield db
        finally:
            pass

    fastapi_app.dependency_overrides[get_session] = _override_session
    # Do NOT override require_manager — let real auth run.

    with TestClient(fastapi_app, raise_server_exceptions=False) as c:
        resp = c.get("/companies/auth-test-co/leaderboard")

    fastapi_app.dependency_overrides.clear()
    db.close()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()

    assert resp.status_code in (401, 403)
