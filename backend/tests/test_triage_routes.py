"""Route tests for V7 triage + shortlist endpoints."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import models
from app.auth import CurrentUser, require_manager
from app.db import get_session
from app.main import app as fastapi_app
from tests._v7_fixtures import build_world, make_session

_MANAGER = CurrentUser(auth_user_id="mgr-1", email="mgr@example.com", role="manager")


@pytest.fixture()
def client_db():
    db = make_session()
    build_world(
        db,
        candidate_specs=[
            {"name": "Alex", "overall": 90},
            {"name": "Priya", "overall": 82},
            {"name": "Sam", "overall": 74},
        ],
    )

    fastapi_app.dependency_overrides[get_session] = lambda: db
    fastapi_app.dependency_overrides[require_manager] = lambda: _MANAGER
    with TestClient(fastapi_app, raise_server_exceptions=True) as c:
        yield c, db
    fastapi_app.dependency_overrides.clear()
    db.close()


def _cid(db, name):
    return (
        db.query(models.Candidate)
        .filter(models.Candidate.display_name == name)
        .one()
        .id
    )


def test_shortlist_endpoint_auto_top_n(client_db):
    client, db = client_db
    resp = client.get("/positions/meridian-fa/shortlist?top_n=2")
    assert resp.status_code == 200
    data = resp.json()
    assert data["selection_mode"] == "auto_top_n"
    assert [c["name"] for c in data["candidates"]] == ["Alex", "Priya"]


def test_shortlist_endpoint_explicit_ids(client_db):
    client, db = client_db
    alex, sam = _cid(db, "Alex"), _cid(db, "Sam")
    resp = client.get(
        f"/positions/meridian-fa/shortlist?candidate_ids={alex}&candidate_ids={sam}"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["selection_mode"] == "explicit"
    assert {c["id"] for c in data["candidates"]} == {alex, sam}


def test_shortlist_unknown_position_404(client_db):
    client, _ = client_db
    assert client.get("/positions/nope/shortlist").status_code == 404


def test_triage_queue_and_decision_roundtrip(client_db):
    client, db = client_db
    # Initially nothing decided.
    q = client.get("/positions/meridian-fa/queue").json()
    assert q["decided"] == {}
    assert len(q["candidates"]) == 3

    alex = _cid(db, "Alex")
    r = client.post(
        "/positions/meridian-fa/queue/decision",
        json={"candidate_id": alex, "decision": "shortlist"},
    )
    assert r.status_code == 204

    q2 = client.get("/positions/meridian-fa/queue").json()
    assert q2["decided"][alex] == "shortlist"

    # Decision surfaces in the shortlist report too.
    report = client.get("/positions/meridian-fa/shortlist?top_n=3").json()
    alex_row = next(c for c in report["candidates"] if c["id"] == alex)
    assert alex_row["triage_decision"] == "shortlist"


def test_triage_decision_is_upsert(client_db):
    client, db = client_db
    alex = _cid(db, "Alex")
    client.post("/positions/meridian-fa/queue/decision",
                json={"candidate_id": alex, "decision": "pass"})
    client.post("/positions/meridian-fa/queue/decision",
                json={"candidate_id": alex, "decision": "shortlist"})

    rows = (
        db.query(models.TriageDecision)
        .filter(models.TriageDecision.candidate_id == alex)
        .all()
    )
    assert len(rows) == 1
    assert rows[0].decision == "shortlist"


def test_triage_undecided_clears_decision(client_db):
    client, db = client_db
    alex = _cid(db, "Alex")
    client.post("/positions/meridian-fa/queue/decision",
                json={"candidate_id": alex, "decision": "pass"})
    client.post("/positions/meridian-fa/queue/decision",
                json={"candidate_id": alex, "decision": "undecided"})

    rows = (
        db.query(models.TriageDecision)
        .filter(models.TriageDecision.candidate_id == alex)
        .all()
    )
    assert rows == []


def test_triage_decision_unknown_candidate_404(client_db):
    client, _ = client_db
    r = client.post("/positions/meridian-fa/queue/decision",
                    json={"candidate_id": "ghost", "decision": "pass"})
    assert r.status_code == 404
