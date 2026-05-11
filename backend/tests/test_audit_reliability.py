"""Roadmap 2 / PR #6 — Reliability + Fairness audit panel.

End-to-end tests against an in-memory SQLite. Covers the
``reliability_report`` chart families, ``fairness_report`` parity gap +
disparate-impact ratio, and the gated audit routes (404 / 403 / 200).
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
    Organization,
    Position,
    Rollout,
    RolloutScore,
    Team,
)
from app.services import reliability as reliability_svc

_MANAGER = CurrentUser(auth_user_id="mgr-r6", email="mgr@example.com", role="manager")


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


def _seed(db, *, enabled: bool = True):
    org = Organization(
        id="org-1",
        name="Acme",
        mission="Build",
        reliability_audit_enabled=enabled,
    )
    team = Team(id="team-1", organization_id=org.id, name="Core")
    pos = Position(
        id="pos-1",
        organization_id=org.id,
        team_id=team.id,
        name="Senior Engineer",
        role="Senior Engineer",
    )
    cands: list[Candidate] = []
    for i, (g, age, edu, sim, base) in enumerate(
        [
            ("F", "25-34", "bachelor", 80, 78),
            ("F", "25-34", "master", 75, 70),
            ("M", "35-44", "bachelor", 50, 60),
            ("M", "35-44", "master", 55, 55),
            ("M", "25-34", "bachelor", 40, 65),
            ("F", "45-54", "master", 90, 85),
        ]
    ):
        c = Candidate(
            id=f"cand-{i}",
            auth_user_id=f"auth-{i}",
            display_name=f"Cand {i}",
            email=f"c{i}@example.com",
            demographics={"gender": g, "age_band": age, "education_tier": edu},
        )
        cands.append(c)
        m = Match(
            id=f"m-{i}",
            candidate_id=c.id,
            position_id=pos.id,
            overall_score=sim,
            status="succeeded",
            finished_at=datetime.now(timezone.utc),
        )
        b = BaselineComparison(
            match_id=m.id,
            overall_score=base,
            per_criterion={},
            band="band",
            band_note="",
            delta_vs_sim={},
            robustness_summary="",
        )
        r = Rollout(
            id=f"r-{i}",
            match_id=m.id,
            scenario_id=f"sc-{i % 2}",
            rollout_index=0,
            transcript=[],
            final_state={"persona_fidelity": {"score": 70 if i % 2 else 50}},
            duration_turns=4,
            status="completed",
            prompt_version="v1",
        )
        db.add_all([c, m, b, r])
        db.flush()
        # Add scores.
        db.add(
            RolloutScore(
                rollout_id=r.id,
                dimension_key="thinking_quality",
                score=sim,
                judge_model="judge",
                confidence=0.7 if i % 2 else 0.5,
                prompt_version="v1",
            )
        )
        db.add(
            RolloutScore(
                rollout_id=r.id,
                dimension_key="persona_fidelity",
                score=70 if i % 2 else 50,
                judge_model="fid",
                confidence=0.8,
                prompt_version="v1",
            )
        )
    db.add_all([org, team, pos])
    db.commit()


def test_reliability_report_shape(db_session):
    _seed(db_session)
    rep = reliability_svc.reliability_report(db_session, "pos-1")
    assert rep["n_matches"] == 6
    assert rep["n_rollouts"] == 6
    assert len(rep["scatter"]["points"]) == 6
    assert isinstance(rep["scatter"]["pearson"], float)
    assert sum(b["count"] for b in rep["delta_histogram"]) == 6
    keys = {c["key"] for c in rep["criteria"]}
    assert "thinking_quality" in keys
    # Flag low agreement triggers when mean conf < 0.65.
    tq = next(c for c in rep["criteria"] if c["key"] == "thinking_quality")
    assert tq["flag_low"] is True
    # Per-scenario sigma populated.
    assert any(s["sigma"] > 0 for s in rep["scenarios"])
    # Fidelity stats present.
    assert rep["fidelity"]["n"] == 6
    assert rep["fidelity"]["mean"] is not None
    # Prompt-version split has v1.
    pvs = {row["prompt_version"] for row in rep["by_prompt_version"]}
    assert pvs == {"v1"}


def test_fairness_report_parity_and_disparate_impact(db_session):
    _seed(db_session)
    rep = reliability_svc.fairness_report(db_session, "pos-1")
    assert rep["n_candidates"] == 6
    gender_dim = next(d for d in rep["dimensions"] if d["dimension"] == "gender")
    labels = {g["label"] for g in gender_dim["groups"]}
    assert "F" in labels and "M" in labels
    # Female mean ≈ (80+75+90)/3=81.67, male ≈ (50+55+40)/3=48.33 → parity gap ~33
    assert gender_dim["parity_gap"] is not None
    assert gender_dim["parity_gap"] > 20
    # Disparate impact flagged (M selection rate 0/3 vs F 3/3 = 0.0).
    assert gender_dim["flag_disparate_impact"] is True


def test_audit_routes_gated_by_org_toggle(db_session):
    _seed(db_session, enabled=False)
    app.dependency_overrides[get_session] = lambda: db_session
    app.dependency_overrides[require_manager] = lambda: _MANAGER
    try:
        c = TestClient(app)
        assert c.get("/audit/positions/pos-1/reliability").status_code == 403
        assert c.get("/audit/positions/pos-1/fairness").status_code == 403
        assert c.get("/audit/positions/missing/reliability").status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_audit_csv_export_when_enabled(db_session):
    _seed(db_session, enabled=True)
    app.dependency_overrides[get_session] = lambda: db_session
    app.dependency_overrides[require_manager] = lambda: _MANAGER
    try:
        c = TestClient(app)
        rep = c.get("/audit/positions/pos-1/reliability")
        assert rep.status_code == 200
        body = rep.json()
        assert body["n_matches"] == 6
        csv_resp = c.get("/audit/positions/pos-1/export.csv")
        assert csv_resp.status_code == 200
        text = csv_resp.text
        # Header + 6 rows.
        lines = [l for l in text.splitlines() if l]
        assert len(lines) == 7
        assert lines[0].startswith("match_id,candidate_id,position_id,sim_score")
    finally:
        app.dependency_overrides.clear()
