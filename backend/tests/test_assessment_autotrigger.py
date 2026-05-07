"""Integration tests: POST /me/assessment auto-enqueues pending matches."""
from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_session
from app.main import app as fastapi_app
from app import models
from app.auth import CurrentUser, require_candidate


def _make_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    return engine


_TEST_USER = CurrentUser(
    auth_user_id="test-candidate-001",
    email="cand@example.com",
    role="candidate",
)


@pytest.fixture()
def client_and_db():
    engine = _make_engine()
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    db = Session()

    # Seed a matching company
    company = models.Position(
        id="test-meridian",
        name="Test Meridian",
        role="Analyst",
        role_family="financial_analyst",
        target_seniority="mid",
        is_open=True,
    )
    db.add(company)

    # Seed a non-matching company (wrong role family)
    wrong_co = models.Position(
        id="test-eng",
        name="Test Eng",
        role="Engineer",
        role_family="software_engineer",
        target_seniority="mid",
        is_open=True,
    )
    db.add(wrong_co)

    # Seed a closed company (same role family, should be excluded)
    closed_co = models.Position(
        id="test-closed",
        name="Test Closed",
        role="Analyst",
        role_family="financial_analyst",
        target_seniority="mid",
        is_open=False,
    )
    db.add(closed_co)
    db.commit()

    def _override_session():
        try:
            yield db
        finally:
            pass

    def _override_candidate():
        return _TEST_USER

    fastapi_app.dependency_overrides[get_session] = _override_session
    fastapi_app.dependency_overrides[require_candidate] = _override_candidate

    with patch("app.services.simulation.background_runner.schedule") as mock_schedule:
        with TestClient(fastapi_app, raise_server_exceptions=True) as c:
            yield c, db, mock_schedule

    fastapi_app.dependency_overrides.clear()
    db.close()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def test_submit_assessment_creates_pending_match(client_and_db):
    client, db, mock_schedule = client_and_db

    resp = client.post(
        "/candidates/me/assessment",
        json={
            "bfi_responses": {"e1": 3, "a1": 4, "c1": 2, "n1": 3, "o1": 2,
                               "e2": 3, "a2": 3, "c2": 4, "n2": 3, "o2": 4},
            "sjt_responses": {"sjt1": "a", "sjt2": "b", "sjt3": "c"},
            "target_role_family": "financial_analyst",
            "target_seniority": "mid",
        },
    )
    assert resp.status_code == 200

    candidate = db.query(models.Candidate).filter_by(auth_user_id="test-candidate-001").first()
    assert candidate is not None
    assert candidate.target_role_family == "financial_analyst"
    assert candidate.target_seniority == "mid"

    matches = db.query(models.Match).filter_by(candidate_id=candidate.id).all()
    # Only the matching open company should produce a pending match.
    # mid candidate + mid company → compatible. wrong_co (software_engineer) → excluded.
    # closed company → excluded.
    assert len(matches) == 1
    assert matches[0].position_id == "test-meridian"
    assert matches[0].status == "pending"

    # background_runner.schedule should have been called once
    mock_schedule.assert_called_once_with(matches[0].id)


def test_submit_assessment_no_match_when_no_target(client_and_db):
    client, db, mock_schedule = client_and_db

    resp = client.post(
        "/candidates/me/assessment",
        json={
            "bfi_responses": {"e1": 3, "a1": 4, "c1": 2, "n1": 3, "o1": 2,
                               "e2": 3, "a2": 3, "c2": 4, "n2": 3, "o2": 4},
            "sjt_responses": {"sjt1": "a", "sjt2": "b", "sjt3": "c"},
            # No target_role_family or target_seniority
        },
    )
    assert resp.status_code == 200
    mock_schedule.assert_not_called()
