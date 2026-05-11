"""Roadmap 2 / PR #6 follow-up — multi-position audit overview.

Covers:
  * ``positions_in_scope`` respects ``reliability_audit_enabled``.
  * ``reliability_overview`` aggregates scatter + criteria + scenarios.
  * ``fairness_overview`` rolls up demographics across positions.
  * ``GET /audit/overview/export.csv`` adds ``position_name`` to each row.
  * Per-position ``scenario_name`` + ``position_id`` are surfaced.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import CurrentUser, require_manager
from app.db import Base, get_session
from app.main import app
from app.models import (
    BaselineComparison,
    Candidate,
    Match,
    MomentOfTruth,
    Organization,
    Position,
    Rollout,
    RolloutScore,
    Team,
)
from app.services import reliability as reliability_svc

_MGR = CurrentUser(auth_user_id="mgr", email="mgr@x.com", role="manager")


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


def _make_position(
    db, *, org_id, team_id, pos_id, name, is_open=True
):
    pos = Position(
        id=pos_id,
        organization_id=org_id,
        team_id=team_id,
        name=name,
        role="role",
        is_open=is_open,
    )
    db.add(pos)
    return pos


def _seed_match(
    db, *, position_id, candidate_id, sim, baseline, scenario_id, demo
):
    cand = Candidate(
        id=candidate_id,
        auth_user_id=f"auth-{candidate_id}",
        display_name=candidate_id,
        email=f"{candidate_id}@x.com",
        demographics=demo,
    )
    match = Match(
        id=f"m-{candidate_id}-{position_id}",
        candidate_id=cand.id,
        position_id=position_id,
        overall_score=sim,
        status="succeeded",
        finished_at=datetime.now(timezone.utc),
    )
    baseline_row = BaselineComparison(
        match_id=match.id,
        overall_score=baseline,
        per_criterion={},
        band="b",
        band_note="",
        delta_vs_sim={},
        robustness_summary="",
    )
    rollout = Rollout(
        id=f"r-{candidate_id}-{position_id}",
        match_id=match.id,
        scenario_id=scenario_id,
        rollout_index=0,
        transcript=[],
        final_state={"persona_fidelity": {"score": 70}},
        duration_turns=4,
        status="completed",
        prompt_version="v1",
    )
    db.add_all([cand, match, baseline_row, rollout])
    db.flush()
    db.add(
        RolloutScore(
            rollout_id=rollout.id,
            dimension_key="thinking_quality",
            score=sim,
            judge_model="judge",
            confidence=0.7,
            prompt_version="v1",
        )
    )
    db.add(
        RolloutScore(
            rollout_id=rollout.id,
            dimension_key="persona_fidelity",
            score=70,
            judge_model="fid",
            confidence=0.8,
            prompt_version="v1",
        )
    )


@pytest.fixture()
def seeded_multi(db_session):
    # Org A — audit on, two positions (one open one closed).
    org_a = Organization(id="org-a", name="A", mission="m", reliability_audit_enabled=True)
    team_a = Team(id="team-a", organization_id=org_a.id, name="core")
    db_session.add_all([org_a, team_a])
    p_open = _make_position(
        db_session, org_id=org_a.id, team_id=team_a.id, pos_id="p-open",
        name="Open Senior", is_open=True,
    )
    p_closed = _make_position(
        db_session, org_id=org_a.id, team_id=team_a.id, pos_id="p-closed",
        name="Closed Senior", is_open=False,
    )
    # Org B — audit OFF, one open position (should be excluded).
    org_b = Organization(id="org-b", name="B", mission="m", reliability_audit_enabled=False)
    team_b = Team(id="team-b", organization_id=org_b.id, name="core")
    db_session.add_all([org_b, team_b])
    _make_position(
        db_session, org_id=org_b.id, team_id=team_b.id, pos_id="p-b",
        name="B Position", is_open=True,
    )
    # Scenarios with real titles.
    s1 = MomentOfTruth(
        id="sc-1", team_id=team_a.id, title="Toxic teammate moment",
        scenario_type="conflict", prompt="", candidate_role="",
        expected_arc="", scoring_dims=[], participating_roles=[],
        ordering=0,
    )
    s2 = MomentOfTruth(
        id="sc-2", team_id=team_a.id, title="Ambiguous priorities",
        scenario_type="priorities", prompt="", candidate_role="",
        expected_arc="", scoring_dims=[], participating_roles=[],
        ordering=1,
    )
    db_session.add_all([s1, s2])

    # Matches on open position.
    _seed_match(db_session, position_id="p-open", candidate_id="c1",
                sim=80, baseline=78, scenario_id="sc-1",
                demo={"gender": "F", "age_band": "25-34", "education_tier": "bachelor"})
    _seed_match(db_session, position_id="p-open", candidate_id="c2",
                sim=50, baseline=60, scenario_id="sc-1",
                demo={"gender": "M", "age_band": "25-34", "education_tier": "bachelor"})
    # Matches on closed position.
    _seed_match(db_session, position_id="p-closed", candidate_id="c3",
                sim=70, baseline=72, scenario_id="sc-2",
                demo={"gender": "F", "age_band": "35-44", "education_tier": "master"})
    # Match under org B (should be excluded by scope).
    _seed_match(db_session, position_id="p-b", candidate_id="c4",
                sim=90, baseline=90, scenario_id=None,
                demo={"gender": "F", "age_band": "25-34", "education_tier": "bachelor"})
    db_session.commit()


def test_positions_in_scope_filters_by_toggle_and_open_closed(db_session, seeded_multi):
    all_pos = reliability_svc.positions_in_scope(db_session, "all")
    assert {p.id for p in all_pos} == {"p-open", "p-closed"}  # org-b excluded
    open_pos = reliability_svc.positions_in_scope(db_session, "open")
    assert {p.id for p in open_pos} == {"p-open"}
    closed_pos = reliability_svc.positions_in_scope(db_session, "closed")
    assert {p.id for p in closed_pos} == {"p-closed"}


def test_reliability_overview_aggregates_scatter_and_scenarios(db_session, seeded_multi):
    rep = reliability_svc.reliability_overview(db_session, "all")
    assert rep["n_positions"] == 2
    assert rep["n_matches"] == 3  # c1, c2, c3 (c4 excluded)
    # Three baseline pairs in the cloud.
    assert len(rep["scatter"]["points"]) == 3
    # Scenarios include name + position_id.
    sc_names = {row["scenario_name"] for row in rep["scenarios"]}
    assert "Toxic teammate moment" in sc_names
    assert "Ambiguous priorities" in sc_names
    pos_ids = {row["position_id"] for row in rep["scenarios"]}
    assert pos_ids <= {"p-open", "p-closed"}


def test_per_position_report_carries_scenario_name(db_session, seeded_multi):
    rep = reliability_svc.reliability_report(db_session, "p-open")
    sc = next((s for s in rep["scenarios"] if s["scenario_id"] == "sc-1"), None)
    assert sc is not None
    assert sc["scenario_name"] == "Toxic teammate moment"
    assert sc["position_id"] == "p-open"


def test_fairness_overview_aggregates_across_positions(db_session, seeded_multi):
    rep = reliability_svc.fairness_overview(db_session, "all")
    assert rep["n_positions"] == 2
    assert rep["n_matches"] == 3
    gender_dim = next(d for d in rep["dimensions"] if d["dimension"] == "gender")
    labels = {g["label"]: g["n"] for g in gender_dim["groups"]}
    assert labels.get("F", 0) >= 2
    assert labels.get("M", 0) >= 1


def test_overview_routes_and_scoped_csv(db_session, seeded_multi):
    app.dependency_overrides[get_session] = lambda: db_session
    app.dependency_overrides[require_manager] = lambda: _MGR
    try:
        c = TestClient(app)
        r = c.get("/audit/overview/reliability?scope=all").json()
        assert r["n_positions"] == 2
        r_open = c.get("/audit/overview/reliability?scope=open").json()
        assert r_open["n_positions"] == 1
        f = c.get("/audit/overview/fairness?scope=closed").json()
        assert f["n_positions"] == 1
        # Bad scope.
        assert c.get("/audit/overview/reliability?scope=foo").status_code == 400

        csv_resp = c.get("/audit/overview/export.csv?scope=all")
        assert csv_resp.status_code == 200
        text = csv_resp.text
        lines = [l for l in text.splitlines() if l]
        # Header + 3 rows from p-open + p-closed.
        assert len(lines) == 4
        assert "position_name" in lines[0]
        # Each non-header row must include a position name.
        assert any("Open Senior" in line for line in lines[1:])
        assert any("Closed Senior" in line for line in lines[1:])
    finally:
        app.dependency_overrides.clear()
