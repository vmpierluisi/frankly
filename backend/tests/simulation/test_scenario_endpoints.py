"""Integration tests for scenario library routes — Phase 3A.

Validation gate:
  (1) GET /scenarios returns [] before any scenarios exist.
  (2) POST /scenarios/draft creates LLM-drafted scenarios.
  (3) POST /scenarios creates a hand-authored scenario.
  (4) PATCH /scenarios/:sid updates fields.
  (5) DELETE /scenarios/:sid removes the scenario.
  (6) POST /draft preserves hand-authored (is_llm_drafted=False) scenarios.
  (7) POST /scenarios rejects scoring_dims not in company criteria.
  (8) PATCH rejects invalid scoring_dims.
  (9) 404 for unknown company or scenario.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

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
# DB + client fixtures
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

    fastapi_app.dependency_overrides[get_session] = _override_session
    fastapi_app.dependency_overrides[require_manager] = lambda: CurrentUser(
        auth_user_id="mgr-001", email="mgr@example.com", role="manager"
    )

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
    company.criteria.append(
        models.Criterion(key="analyticalRigor", label="Analytical Rigor",
                         description="Depth of quant analysis.", weight=0.5, ordering=0)
    )
    company.criteria.append(
        models.Criterion(key="writtenDissent", label="Written Dissent",
                         description="Disagrees in writing.", weight=0.5, ordering=1)
    )
    db_session.add(company)
    db_session.commit()
    db_session.refresh(company)
    return company


def _make_canned_library():
    return {
        "scenarios": [
            {
                "title": "IC Memo Pressure",
                "type": "dyad",
                "prompt": "Review deal memo with tight deadline.",
                "candidate_role": "Draft recommendation.",
                "expected_arc": "Ground recommendation in data.",
                "scoring_dims": ["analyticalRigor", "writtenDissent"],
                "participating_roles": ["Pod VP"],
                "max_turns": 6,
                "grounding": "Role spec: 'Analysts own deal memos.'",
            },
            {
                "title": "Morning Deal Review",
                "type": "small_group",
                "prompt": "Weekly pod deal review.",
                "candidate_role": "Present and defend analysis.",
                "expected_arc": "Defend quantitative positions.",
                "scoring_dims": ["analyticalRigor"],
                "participating_roles": ["Senior Analyst", "Pod VP"],
                "max_turns": 10,
                "grounding": "Team structure: weekly reviews.",
            },
        ]
    }


def _mock_draft(canned):
    async def _fake(budget, system="", user="", schema=None, schema_name="",
                    temperature=0.6, max_tokens=4500):
        return canned
    return _fake


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_list_scenarios_empty(client, db_session):
    """(1) GET returns [] before any scenarios exist."""
    _seed_company(db_session)
    resp = client.get("/positions/test-co/scenarios")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_scenarios_404_unknown_company(client, db_session):
    """(9) 404 for unknown company."""
    resp = client.get("/positions/no-such-co/scenarios")
    assert resp.status_code == 404


def test_draft_creates_scenarios(client, db_session):
    """(2) POST /draft creates LLM-drafted scenarios."""
    _seed_company(db_session)
    canned = _make_canned_library()

    with patch(
        "app.services.simulation.scenario_engine.tracked_chat_json",
        new=_mock_draft(canned),
    ):
        resp = client.post("/positions/test-co/scenarios/draft")

    assert resp.status_code == 201
    data = resp.json()
    assert len(data) == 2
    assert data[0]["title"] == "IC Memo Pressure"
    assert data[0]["is_llm_drafted"] is True
    assert data[0]["team_id"] is not None


def test_draft_404_unknown_company(client, db_session):
    """(9) POST /draft returns 404 for unknown company."""
    resp = client.post("/positions/no-such-co/scenarios/draft")
    assert resp.status_code == 404


def test_create_hand_authored_scenario(client, db_session):
    """(3) POST /scenarios creates a hand-authored scenario."""
    _seed_company(db_session)
    payload = {
        "title": "Custom Scenario",
        "scenario_type": "written",
        "prompt": "Write a dissent memo.",
        "candidate_role": "Author the memo.",
        "expected_arc": "Clear, data-driven dissent.",
        "scoring_dims": ["writtenDissent"],
        "participating_roles": [],
        "max_turns": 4,
        "grounding": "Values doc: 'written rigor'.",
    }
    resp = client.post("/positions/test-co/scenarios", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "Custom Scenario"
    assert data["is_llm_drafted"] is False
    assert data["scoring_dims"] == ["writtenDissent"]


def test_create_rejects_invalid_scoring_dims(client, db_session):
    """(7) POST /scenarios rejects scoring_dims not in company criteria."""
    _seed_company(db_session)
    payload = {
        "title": "Bad Scenario",
        "scenario_type": "dyad",
        "prompt": "A prompt.",
        "candidate_role": "Do something.",
        "expected_arc": "Do it well.",
        "scoring_dims": ["analyticalRigor", "NONEXISTENT"],
        "participating_roles": [],
        "max_turns": 6,
        "grounding": "",
    }
    resp = client.post("/positions/test-co/scenarios", json=payload)
    assert resp.status_code == 422
    assert "NONEXISTENT" in resp.json()["detail"]


def test_patch_scenario(client, db_session):
    """(4) PATCH updates fields."""
    _seed_company(db_session)
    canned = _make_canned_library()

    with patch(
        "app.services.simulation.scenario_engine.tracked_chat_json",
        new=_mock_draft(canned),
    ):
        draft = client.post("/positions/test-co/scenarios/draft")

    sid = draft.json()[0]["id"]
    resp = client.patch(
        f"/positions/test-co/scenarios/{sid}",
        json={"title": "Edited Title", "max_turns": 8},
    )
    assert resp.status_code == 200
    assert resp.json()["title"] == "Edited Title"
    assert resp.json()["max_turns"] == 8


def test_patch_rejects_invalid_scoring_dims(client, db_session):
    """(8) PATCH rejects invalid scoring_dims."""
    _seed_company(db_session)
    canned = _make_canned_library()

    with patch(
        "app.services.simulation.scenario_engine.tracked_chat_json",
        new=_mock_draft(canned),
    ):
        draft = client.post("/positions/test-co/scenarios/draft")

    sid = draft.json()[0]["id"]
    resp = client.patch(
        f"/positions/test-co/scenarios/{sid}",
        json={"scoring_dims": ["analyticalRigor", "BOGUS"]},
    )
    assert resp.status_code == 422


def test_delete_scenario(client, db_session):
    """(5) DELETE removes the scenario."""
    _seed_company(db_session)
    canned = _make_canned_library()

    with patch(
        "app.services.simulation.scenario_engine.tracked_chat_json",
        new=_mock_draft(canned),
    ):
        draft = client.post("/positions/test-co/scenarios/draft")

    sid = draft.json()[0]["id"]
    resp = client.delete(f"/positions/test-co/scenarios/{sid}")
    assert resp.status_code == 204

    remaining = client.get("/positions/test-co/scenarios").json()
    assert all(s["id"] != sid for s in remaining)


def test_draft_preserves_hand_authored(client, db_session):
    """(6) POST /draft replaces LLM-drafted scenarios but keeps hand-authored ones."""
    _seed_company(db_session)

    # Create a hand-authored scenario first.
    hand = client.post("/positions/test-co/scenarios", json={
        "title": "Hand Authored",
        "scenario_type": "dyad",
        "prompt": "A hand-crafted scenario.",
        "candidate_role": "Engage thoughtfully.",
        "expected_arc": "Strong performance.",
        "scoring_dims": ["analyticalRigor"],
        "participating_roles": [],
        "max_turns": 6,
        "grounding": "Custom.",
    })
    hand_id = hand.json()["id"]

    # Now draft (replaces LLM-drafted only).
    canned = _make_canned_library()
    with patch(
        "app.services.simulation.scenario_engine.tracked_chat_json",
        new=_mock_draft(canned),
    ):
        resp = client.post("/positions/test-co/scenarios/draft")

    ids = [s["id"] for s in resp.json()]
    assert hand_id in ids

    hand_scenario = next(s for s in resp.json() if s["id"] == hand_id)
    assert hand_scenario["is_llm_drafted"] is False
