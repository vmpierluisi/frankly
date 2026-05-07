"""Integration tests for the synthetic team routes (Phase 2B).

Validation gate:
  (1) GET /companies/:id/team returns [] when no teammates exist.
  (2) POST /companies/:id/team/synthesize creates N teammates and returns them.
  (3) PATCH /companies/:id/team/:tid updates fields and sets is_edited=True.
  (4) DELETE /companies/:id/team/:tid removes the teammate.
  (5) POST /synthesize preserves is_edited=True teammates from prior run.
  (6) Routes return 404 for unknown company or teammate id.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_session
from app.main import app as fastapi_app
from app import models
from app.auth import CurrentUser, require_manager


# ---------------------------------------------------------------------------
# In-memory DB + client fixtures
# ---------------------------------------------------------------------------

def _make_engine():
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
    engine = _make_engine()
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    db = Session()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture()
def client(db_session):
    def _override_session():
        try:
            yield db_session
        finally:
            pass

    _MANAGER = CurrentUser(
        auth_user_id="mgr-001",
        email="manager@example.com",
        role="manager",
    )

    def _override_manager():
        return _MANAGER

    fastapi_app.dependency_overrides[get_session] = _override_session
    fastapi_app.dependency_overrides[require_manager] = _override_manager

    with TestClient(fastapi_app, raise_server_exceptions=True) as c:
        yield c

    fastapi_app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seed_company(db_session) -> models.Position:
    org = models.Organization(name="Test Co", mission="We value rigor.")
    db_session.add(org)
    team = models.Team(
        organization=org,
        name="Test Co core team",
        artifact_team_structure="Two analysts per pod.",
        artifact_sample_comms="Pass on this one.",
    )
    db_session.add(team)
    db_session.flush()
    company = models.Position(
        id="test-co",
        organization_id=org.id,
        team_id=team.id,
        name="Test Co",
        role="Analyst",
        artifact_role_spec="Own the memo.",
    )
    db_session.add(company)
    db_session.commit()
    db_session.refresh(company)
    return company


def _make_canned_centroid() -> dict:
    return {
        "big_five_centroid": {
            "openness":          {"value": 4.0, "provenance": "values"},
            "conscientiousness": {"value": 4.5, "provenance": "values"},
            "extraversion":      {"value": 2.5, "provenance": "comms"},
            "agreeableness":     {"value": 3.0, "provenance": "comms"},
            "neuroticism":       {"value": 2.0, "provenance": "role"},
        },
        "skill_centroid": {
            "modeling": {"value": 4.0, "provenance": "role spec"},
        },
        "work_style_centroid": {
            "async_pref": {"value": 0.7, "provenance": "comms"},
        },
        "centroid_tensions": [],
        "sigma_recommendations": {"big_five": 0.5, "skill": 0.5, "work_style": 0.2},
    }


def _make_canned_teammate(n: int = 0) -> dict:
    return {
        "name": f"Jordan Smith {n}",
        "role_on_team": "Senior Analyst",
        "seniority": "senior",
        "trait_sheet": {
            "big_five": {
                "openness": 4.1, "conscientiousness": 4.6,
                "extraversion": 2.4, "agreeableness": 3.1, "neuroticism": 1.9,
            },
            "skill_profile": {"modeling": 3.9},
            "work_style": {"async_pref": 0.65},
        },
        "narrative": "A seasoned analyst known for thorough memos.",
        "private_goals": ["Assess rigor.", "Check written communication."],
        "provenance_notes": "Grounded in values doc.",
    }


def _make_synthesize_mock(centroid, n=5):
    call_index = 0

    async def _fake(budget, **kwargs):
        nonlocal call_index
        call_index += 1
        schema_name = kwargs.get("schema_name", "")
        if schema_name == "team_centroid":
            return centroid
        return _make_canned_teammate(call_index)

    return _fake


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_list_team_empty(client, db_session):
    """(1) GET returns [] when no teammates exist."""
    _seed_company(db_session)
    resp = client.get("/positions/test-co/team")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_team_404_unknown_company(client, db_session):
    """(6) Returns 404 for unknown company."""
    resp = client.get("/positions/no-such-co/team")
    assert resp.status_code == 404


def test_synthesize_creates_teammates(client, db_session):
    """(2) POST /synthesize creates N teammates and returns them."""
    _seed_company(db_session)
    centroid = _make_canned_centroid()

    with patch(
        "app.services.simulation.team_synthesizer.tracked_chat_json",
        new=_make_synthesize_mock(centroid),
    ):
        resp = client.post("/positions/test-co/team/synthesize")

    assert resp.status_code == 201
    data = resp.json()
    assert len(data) == 5  # DEFAULT_TEAM_SIZE
    for t in data:
        assert t["team_id"] is not None
        assert t["is_edited"] is False
        assert "trait_sheet" in t


def test_synthesize_404_unknown_company(client, db_session):
    """(6) POST /synthesize returns 404 for unknown company."""
    resp = client.post("/positions/no-such-co/team/synthesize")
    assert resp.status_code == 404


def test_patch_teammate_updates_fields(client, db_session):
    """(3) PATCH updates fields and sets is_edited=True."""
    _seed_company(db_session)
    centroid = _make_canned_centroid()

    with patch(
        "app.services.simulation.team_synthesizer.tracked_chat_json",
        new=_make_synthesize_mock(centroid),
    ):
        syn = client.post("/positions/test-co/team/synthesize")

    teammate_id = syn.json()[0]["id"]

    resp = client.patch(
        f"/positions/test-co/team/{teammate_id}",
        json={"name": "Edited Name", "seniority": "lead"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Edited Name"
    assert body["seniority"] == "lead"
    assert body["is_edited"] is True


def test_patch_teammate_404_wrong_company(client, db_session):
    """(6) PATCH returns 404 when teammate_id belongs to different company."""
    _seed_company(db_session)
    centroid = _make_canned_centroid()

    with patch(
        "app.services.simulation.team_synthesizer.tracked_chat_json",
        new=_make_synthesize_mock(centroid),
    ):
        syn = client.post("/positions/test-co/team/synthesize")

    teammate_id = syn.json()[0]["id"]

    # Create second company without teammates (auto-creates Org + Team via
    # Company.__init__ since none was supplied).
    db_session.add(models.Position(
        id="other-co", name="Other Co", role="Analyst",
        artifact_role_spec="",
    ))
    db_session.commit()

    resp = client.patch(
        f"/positions/other-co/team/{teammate_id}",
        json={"name": "Hijack"},
    )
    assert resp.status_code == 404


def test_delete_teammate(client, db_session):
    """(4) DELETE removes the teammate."""
    _seed_company(db_session)
    centroid = _make_canned_centroid()

    with patch(
        "app.services.simulation.team_synthesizer.tracked_chat_json",
        new=_make_synthesize_mock(centroid),
    ):
        syn = client.post("/positions/test-co/team/synthesize")

    teammates = syn.json()
    assert len(teammates) == 5
    tid = teammates[0]["id"]

    resp = client.delete(f"/positions/test-co/team/{tid}")
    assert resp.status_code == 204

    remaining = client.get("/positions/test-co/team").json()
    assert len(remaining) == 4
    assert all(t["id"] != tid for t in remaining)


def test_synthesize_preserves_edited_teammates(client, db_session):
    """(5) Re-synthesize keeps is_edited=True teammates."""
    _seed_company(db_session)
    centroid = _make_canned_centroid()

    with patch(
        "app.services.simulation.team_synthesizer.tracked_chat_json",
        new=_make_synthesize_mock(centroid),
    ):
        syn = client.post("/positions/test-co/team/synthesize")

    tid = syn.json()[0]["id"]
    client.patch(f"/positions/test-co/team/{tid}", json={"name": "Keeper"})

    with patch(
        "app.services.simulation.team_synthesizer.tracked_chat_json",
        new=_make_synthesize_mock(centroid),
    ):
        resp = client.post("/positions/test-co/team/synthesize")

    ids = [t["id"] for t in resp.json()]
    assert tid in ids

    names = [t["name"] for t in resp.json() if t["id"] == tid]
    assert names[0] == "Keeper"
