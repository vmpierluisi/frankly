"""Tests for GET /matches/{id}/rollouts, /rollouts/{rid}, /baseline — Phase 5A."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import CurrentUser, require_manager
from app.db import Base, get_session
from app.main import app
from app.models import BaselineComparison, Match, Rollout, RolloutScore

_MANAGER = CurrentUser(auth_user_id="mgr-001", email="mgr@test.com", role="manager")


# ---------------------------------------------------------------------------
# DB + client fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture()
def client(db_session):
    app.dependency_overrides[get_session] = lambda: db_session
    app.dependency_overrides[require_manager] = lambda: _MANAGER
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------

def _seed_match(db) -> Match:
    m = Match(
        id="match-001",
        candidate_id="cand-001",
        position_id="co-001",
        overall_score=78,
        band="Strong fit",
        band_note="Worth a call.",
        report={"version": "v2"},
    )
    db.add(m)
    db.flush()
    return m


def _seed_rollout(db, match_id="match-001", idx=0, summary="Strong reasoning.") -> Rollout:
    r = Rollout(
        match_id=match_id,
        scenario_id="scen-001",
        rollout_index=idx,
        transcript=[{"turn": 0, "speaker_name": "Candidate", "content": "Hello."}],
        final_state={"transcript_summary": summary},
        duration_turns=1,
        status="completed",
    )
    db.add(r)
    db.flush()
    return r


def _seed_score(db, rollout_id: str, key="written_rigor", score=80) -> RolloutScore:
    s = RolloutScore(
        rollout_id=rollout_id,
        dimension_key=key,
        score=score,
        confidence=0.85,
        justification="Clear writing.",
        evidence_turns=[0],
        judge_model="judge-v1",
        judge_seed_index=0,
    )
    db.add(s)
    db.flush()
    return s


def _seed_baseline(db, match_id="match-001") -> BaselineComparison:
    bc = BaselineComparison(
        match_id=match_id,
        overall_score=72,
        per_criterion={"written_rigor": {"score": 72, "justification": "Solid."}},
        band="Plausible fit",
        band_note="Worth a conversation.",
        delta_vs_sim={"written_rigor": 8},
        robustness_summary="Sim and baseline agree directionally.",
    )
    db.merge(bc)
    db.flush()
    return bc


# ---------------------------------------------------------------------------
# Tests — list rollouts
# ---------------------------------------------------------------------------

def test_list_rollouts_empty(client, db_session):
    _seed_match(db_session)
    resp = client.get("/matches/match-001/rollouts")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_rollouts_returns_summaries(client, db_session):
    _seed_match(db_session)
    r = _seed_rollout(db_session, idx=0, summary="Candidate showed clarity.")
    _seed_score(db_session, r.id, "written_rigor", 80)
    db_session.commit()

    resp = client.get("/matches/match-001/rollouts")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["rollout_index"] == 0
    assert data[0]["headline"] == "Candidate showed clarity."
    assert data[0]["scores"]["written_rigor"] == 80
    assert data[0]["status"] == "completed"


def test_list_rollouts_sorted_by_index(client, db_session):
    _seed_match(db_session)
    _seed_rollout(db_session, idx=1)
    _seed_rollout(db_session, idx=0)
    db_session.commit()

    resp = client.get("/matches/match-001/rollouts")
    assert resp.status_code == 200
    indices = [r["rollout_index"] for r in resp.json()]
    assert indices == [0, 1]


def test_list_rollouts_404_on_unknown_match(client, db_session):
    resp = client.get("/matches/nope/rollouts")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Tests — get rollout detail
# ---------------------------------------------------------------------------

def test_get_rollout_returns_transcript(client, db_session):
    _seed_match(db_session)
    r = _seed_rollout(db_session)
    _seed_score(db_session, r.id)
    db_session.commit()

    resp = client.get(f"/matches/match-001/rollouts/{r.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == r.id
    assert isinstance(data["transcript"], list)
    assert len(data["transcript"]) == 1
    assert len(data["score_rows"]) == 1
    assert data["score_rows"][0]["dimension_key"] == "written_rigor"
    assert data["score_rows"][0]["score"] == 80


def test_get_rollout_404_on_unknown(client, db_session):
    _seed_match(db_session)
    resp = client.get("/matches/match-001/rollouts/bad-id")
    assert resp.status_code == 404


def test_get_rollout_404_on_wrong_match(client, db_session):
    _seed_match(db_session)
    m2 = Match(id="match-002", candidate_id="c", position_id="co", overall_score=0, band="", band_note="", report={})
    db_session.add(m2)
    db_session.flush()
    r = _seed_rollout(db_session, match_id="match-002")
    db_session.commit()

    resp = client.get(f"/matches/match-001/rollouts/{r.id}")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Tests — get baseline
# ---------------------------------------------------------------------------

def test_get_baseline_returns_comparison(client, db_session):
    _seed_match(db_session)
    _seed_baseline(db_session)
    db_session.commit()

    resp = client.get("/matches/match-001/baseline")
    assert resp.status_code == 200
    data = resp.json()
    assert data["overall_score"] == 72
    assert data["band"] == "Plausible fit"
    assert "written_rigor" in data["per_criterion"]
    assert data["delta_vs_sim"]["written_rigor"] == 8


def test_get_baseline_404_when_absent(client, db_session):
    _seed_match(db_session)
    db_session.commit()
    resp = client.get("/matches/match-001/baseline")
    assert resp.status_code == 404
