"""Roadmap 2 / PR #4 — interview scheduling + notifications.

Covers the manager-proposes → candidate-responds round trip:
  * Recruiter POST /interviews creates an interview row + candidate notification.
  * Candidate accept/decline/counter mutates state + fires a manager notification.
  * Candidate sees vacancy details (position name / role / org) via
    GET /interviews/me — the vacancy-reveal surface.

Email sending is disabled (PYTEST_CURRENT_TEST short-circuits the Resend
helper). We assert DB state + response payloads.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import CurrentUser, require_candidate, require_manager, require_user
from app.db import Base, get_session
from app.main import app
from app.models import Candidate, Match, Notification, Organization, Position, Team


_MANAGER = CurrentUser(auth_user_id="mgr-1", email="mgr@example.com", role="manager")
_CANDIDATE_USER = CurrentUser(
    auth_user_id="auth-cand-1", email="cand@example.com", role="candidate"
)


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    s = Session()
    try:
        yield s
    finally:
        s.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture()
def seeded(db_session):
    org = Organization(id="org-1", name="Acme", mission="Build")
    team = Team(id="team-1", organization_id=org.id, name="Core")
    pos = Position(
        id="pos-1",
        organization_id=org.id,
        team_id=team.id,
        name="Acme Senior Engineer",
        role="Senior Software Engineer",
    )
    cand = Candidate(
        id="cand-1",
        auth_user_id=_CANDIDATE_USER.auth_user_id,
        display_name="Dana Devon",
        email="cand@example.com",
    )
    match = Match(id="match-1", candidate_id=cand.id, position_id=pos.id)
    db_session.add_all([org, team, pos, cand, match])
    db_session.commit()
    return {"cand": cand, "pos": pos, "match": match}


def _override_session(db):
    app.dependency_overrides[get_session] = lambda: db


@pytest.fixture()
def mgr_client(db_session):
    _override_session(db_session)
    app.dependency_overrides[require_manager] = lambda: _MANAGER
    app.dependency_overrides[require_user] = lambda: _MANAGER
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def cand_client(db_session):
    _override_session(db_session)
    app.dependency_overrides[require_candidate] = lambda: _CANDIDATE_USER
    app.dependency_overrides[require_user] = lambda: _CANDIDATE_USER
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    app.dependency_overrides.clear()


def test_manager_proposes_interview(mgr_client, db_session, seeded):
    resp = mgr_client.post(
        "/interviews",
        json={
            "match_id": seeded["match"].id,
            "proposed_slots": ["2026-05-15T10:00:00Z", "2026-05-16T14:00:00Z"],
        },
    )
    assert resp.status_code == 200, resp.text
    iv = resp.json()
    assert iv["status"] == "proposed"
    assert len(iv["proposed_slots"]) == 2
    notifs = db_session.query(Notification).all()
    assert len(notifs) == 1
    assert notifs[0].user_kind == "candidate"
    assert notifs[0].candidate_id == seeded["cand"].id


def test_candidate_sees_vacancy_on_invite(mgr_client, cand_client, seeded):
    assert cand_client.get("/interviews/me").json() == []
    mgr_client.post(
        "/interviews",
        json={"match_id": seeded["match"].id, "proposed_slots": ["2026-05-15T10:00:00Z"]},
    )
    rows = cand_client.get("/interviews/me").json()
    assert len(rows) == 1
    assert rows[0]["position_name"] == "Acme Senior Engineer"
    assert rows[0]["organization_name"] == "Acme"


def test_candidate_accept(mgr_client, cand_client, db_session, seeded):
    iv = mgr_client.post(
        "/interviews",
        json={
            "match_id": seeded["match"].id,
            "proposed_slots": ["2026-05-15T10:00:00Z", "2026-05-16T14:00:00Z"],
        },
    ).json()
    resp = cand_client.post(
        f"/interviews/{iv['id']}/accept",
        json={"selected_slot": "2026-05-16T14:00:00Z"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "accepted"
    mgr_notifs = [
        n for n in db_session.query(Notification).all() if n.user_kind == "manager"
    ]
    assert len(mgr_notifs) == 1
    assert mgr_notifs[0].type == "interview_accepted"


def test_candidate_accept_rejects_unknown_slot(mgr_client, cand_client, seeded):
    iv = mgr_client.post(
        "/interviews",
        json={"match_id": seeded["match"].id, "proposed_slots": ["2026-05-15T10:00:00Z"]},
    ).json()
    resp = cand_client.post(
        f"/interviews/{iv['id']}/accept",
        json={"selected_slot": "2099-01-01T00:00:00Z"},
    )
    assert resp.status_code == 400


def test_candidate_decline(mgr_client, cand_client, db_session, seeded):
    iv = mgr_client.post(
        "/interviews",
        json={"match_id": seeded["match"].id, "proposed_slots": ["2026-05-15T10:00:00Z"]},
    ).json()
    resp = cand_client.post(
        f"/interviews/{iv['id']}/decline", json={"message": "Not now."}
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "declined"


def test_candidate_counter(mgr_client, cand_client, db_session, seeded):
    iv = mgr_client.post(
        "/interviews",
        json={"match_id": seeded["match"].id, "proposed_slots": ["2026-05-15T10:00:00Z"]},
    ).json()
    resp = cand_client.post(
        f"/interviews/{iv['id']}/counter",
        json={"counter_slots": ["2026-05-20T09:00:00Z"]},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "rescheduled"


def test_notification_feed_and_mark_read(mgr_client, cand_client, seeded):
    mgr_client.post(
        "/interviews",
        json={"match_id": seeded["match"].id, "proposed_slots": ["2026-05-15T10:00:00Z"]},
    )
    rows = cand_client.get("/notifications").json()
    assert len(rows) == 1
    assert rows[0]["type"] == "interview_invite"
    nid = rows[0]["id"]
    assert cand_client.post(f"/notifications/{nid}/read").json()["status"] == "read"
