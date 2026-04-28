"""Integration tests for POST /candidates/me/persona/aggregate and
GET /candidates/me/persona.

Validation gate (Phase 1B):
  - POST populates aggregated_persona, aggregation_audit, aggregated_at on the
    candidate row.
  - GET returns the cached aggregated persona.
  - GET returns 404 before aggregation has been triggered.
  - POST returns 409 when assessment is not yet completed.
  - SQLite create_all picks up the new columns (tested by the DB fixture itself).
  - Existing manager match flow is unaffected (checked via existing test pass).
"""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_session
from app.main import app as fastapi_app
from app import models
from app.auth import CurrentUser, require_candidate

# ---------------------------------------------------------------------------
# In-memory SQLite DB fixture
# ---------------------------------------------------------------------------
# StaticPool ensures all connections share the same in-memory database so that
# tables created in the fixture are visible inside route handlers.

def _make_engine_and_tables():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    return engine


@pytest.fixture()
def db_session():
    engine = _make_engine_and_tables()
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture()
def client(db_session):
    """TestClient wired to the in-memory DB, bypassing JWT via dependency override."""
    def _override_session():
        try:
            yield db_session
        finally:
            pass

    _TEST_USER = CurrentUser(
        auth_user_id="test-user-001",
        email="test@example.com",
        role="candidate",
    )

    def _override_candidate():
        return _TEST_USER

    fastapi_app.dependency_overrides[get_session] = _override_session
    fastapi_app.dependency_overrides[require_candidate] = _override_candidate

    with TestClient(fastapi_app, raise_server_exceptions=True) as c:
        yield c

    fastapi_app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seed_candidate(db_session, *, assessment_status: str = "completed") -> models.Candidate:
    c = models.Candidate(
        auth_user_id="test-user-001",
        display_name="Test Candidate",
        email="test@example.com",
        bfi_responses={"e1": 5, "a1": 4, "c1": 1, "n1": 5, "o1": 1,
                       "e2": 2, "a2": 4, "c2": 5, "n2": 2, "o2": 5},
        sjt_responses={"sjt1": "a", "sjt2": "a", "sjt3": "d"},
        assessment_status=assessment_status,
    )
    db_session.add(c)
    db_session.commit()
    db_session.refresh(c)
    return c


def _make_canned_persona() -> dict[str, Any]:
    return {
        "structured_traits": {
            "big_five": {
                "openness": 5.0, "conscientiousness": 5.0, "extraversion": 1.5,
                "agreeableness": 3.0, "neuroticism": 1.5,
            },
            "sjt_signals": {
                "analyticalRigor": 4.667, "intellectualHonesty": 3.0,
                "writtenDissent": 3.333, "ambiguityTolerance": 1.667,
                "lowEgoCollab": 2.333,
            },
            "skill_inferences": {"written_communication": 0.8},
            "work_style": {"async_pref": 0.7},
        },
        "narrative": "A " * 200,
        "provenance_map": [
            {
                "claim": "High conscientiousness",
                "sources": [{"source": "bfi", "evidence": "c2=5"}],
                "confidence": 0.9,
                "reliability_weight": "high",
            }
        ],
        "inconsistencies": [],
        "evidence_completeness": {
            "bfi_present": True, "sjt_present": True, "cv_present": False,
            "linkedin_present": False, "github_present": False,
            "notes": "No CV, LinkedIn, or GitHub provided.",
        },
        "aggregator_version": "v0.1",
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_get_persona_404_before_aggregation(client, db_session):
    """GET returns 404 when aggregated_persona is not yet set."""
    _seed_candidate(db_session)
    resp = client.get("/candidates/me/persona")
    assert resp.status_code == 404
    assert "aggregate" in resp.json()["detail"].lower()


def test_post_aggregate_409_when_assessment_incomplete(client, db_session):
    """POST returns 409 when assessment_status is 'pending'."""
    _seed_candidate(db_session, assessment_status="pending")
    resp = client.post("/candidates/me/persona/aggregate")
    assert resp.status_code == 409
    assert "assessment" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_post_aggregate_populates_columns(client, db_session):
    """POST populates aggregated_persona, aggregation_audit, aggregated_at."""
    _seed_candidate(db_session)
    canned = _make_canned_persona()

    with patch(
        "app.routes.candidates.aggregate",
        new=AsyncMock(return_value=canned),
    ):
        resp = client.post("/candidates/me/persona/aggregate")

    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["aggregated_persona"] is not None
    assert body["aggregation_audit"] is not None
    assert body["aggregated_at"] is not None

    # Verify the DB row was actually updated
    db_session.expire_all()
    candidate = (
        db_session.query(models.Candidate)
        .filter_by(auth_user_id="test-user-001")
        .first()
    )
    assert candidate.aggregated_persona is not None
    assert candidate.aggregated_at is not None
    assert candidate.aggregation_audit["aggregator_version"] == "v0.1"
    assert candidate.aggregation_audit["n_provenance_claims"] == 1


@pytest.mark.asyncio
async def test_get_persona_returns_cached_after_aggregation(client, db_session):
    """GET returns the cached persona after POST has run."""
    _seed_candidate(db_session)
    canned = _make_canned_persona()

    with patch(
        "app.routes.candidates.aggregate",
        new=AsyncMock(return_value=canned),
    ):
        post_resp = client.post("/candidates/me/persona/aggregate")
    assert post_resp.status_code == 200

    get_resp = client.get("/candidates/me/persona")
    assert get_resp.status_code == 200
    body = get_resp.json()
    bf = body["aggregated_persona"]["structured_traits"]["big_five"]
    assert bf["openness"] == pytest.approx(5.0)
    assert bf["conscientiousness"] == pytest.approx(5.0)


@pytest.mark.asyncio
async def test_post_aggregate_audit_contains_cost_fields(client, db_session):
    """aggregation_audit includes cost/token metadata from the budget."""
    _seed_candidate(db_session)
    canned = _make_canned_persona()

    with patch(
        "app.routes.candidates.aggregate",
        new=AsyncMock(return_value=canned),
    ):
        resp = client.post("/candidates/me/persona/aggregate")

    audit = resp.json()["aggregation_audit"]
    assert "llm_calls" in audit
    assert "tokens_in" in audit
    assert "tokens_out" in audit
    assert "cost_usd" in audit


@pytest.mark.asyncio
async def test_post_aggregate_502_on_llm_failure(client, db_session):
    """POST returns 502 when the LLM call raises."""
    _seed_candidate(db_session)

    with patch(
        "app.routes.candidates.aggregate",
        new=AsyncMock(side_effect=RuntimeError("OpenRouter unavailable")),
    ):
        resp = client.post("/candidates/me/persona/aggregate")

    assert resp.status_code == 502
    assert "aggregation failed" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_post_aggregate_idempotent_overwrites(client, db_session):
    """A second POST overwrites the previous cached persona."""
    _seed_candidate(db_session)
    canned_v1 = _make_canned_persona()
    canned_v2 = dict(_make_canned_persona())
    canned_v2["aggregator_version"] = "v0.1"
    canned_v2["structured_traits"] = dict(canned_v2["structured_traits"])
    canned_v2["structured_traits"]["big_five"] = {
        "openness": 3.0, "conscientiousness": 3.0, "extraversion": 3.0,
        "agreeableness": 3.0, "neuroticism": 3.0,
    }

    with patch("app.routes.candidates.aggregate", new=AsyncMock(return_value=canned_v1)):
        client.post("/candidates/me/persona/aggregate")

    with patch("app.routes.candidates.aggregate", new=AsyncMock(return_value=canned_v2)):
        resp = client.post("/candidates/me/persona/aggregate")

    assert resp.status_code == 200
    bf = resp.json()["aggregated_persona"]["structured_traits"]["big_five"]
    assert bf["openness"] == pytest.approx(3.0)


def test_sqlite_create_all_includes_new_columns(db_session):
    """create_all on SQLite produces all three new columns on candidates."""
    from sqlalchemy import inspect, text
    inspector = inspect(db_session.bind)
    col_names = {c["name"] for c in inspector.get_columns("candidates")}
    assert "aggregated_persona" in col_names
    assert "aggregation_audit" in col_names
    assert "aggregated_at" in col_names
