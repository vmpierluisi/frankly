"""Unit tests for services/composite_fit.py (V7)."""
from __future__ import annotations

import pytest

from app import models
from app.services.composite_fit import compute_overall_fit, compute_team_fit
from tests._v7_fixtures import build_world, make_session


@pytest.fixture()
def db():
    session = make_session()
    yield session
    session.close()


def _match_for(db, candidate):
    return (
        db.query(models.Match)
        .filter(models.Match.candidate_id == candidate.id)
        .first()
    )


def test_team_fit_reflects_participation(db):
    world = build_world(
        db,
        candidate_specs=[
            {
                "name": "Alex",
                "overall": 80,
                "scenario_scores": {"asterisk": 90, "model_gap": 50},
            }
        ],
    )
    match = _match_for(db, world["candidates"][0])
    team_fit = compute_team_fit(match, db)

    maya_id = world["teammates"]["maya"].id  # spoke in the asterisk (score 90)
    devon_id = world["teammates"]["devon"].id  # spoke in the model gap (score 50)

    assert set(team_fit.keys()) == {maya_id, devon_id}
    # Maya's rollout scored higher than Devon's → higher team fit.
    assert team_fit[maya_id] > team_fit[devon_id]
    assert 0 <= team_fit[devon_id] <= 100


def test_team_fit_falls_back_to_population_mean(db):
    """A teammate who never spoke gets the population mean, not zero."""
    world = build_world(
        db, candidate_specs=[{"name": "Sam", "overall": 70}]
    )
    match = _match_for(db, world["candidates"][0])
    # Remove Devon from every transcript so he never "participated".
    devon_id = world["teammates"]["devon"].id
    for rollout in match_rollouts(db, match):
        rollout.transcript = [
            t for t in rollout.transcript if t["speaker_id"] != devon_id
        ]
    db.commit()

    team_fit = compute_team_fit(match, db)
    assert team_fit[devon_id] > 0  # fell back, did not collapse to 0


def match_rollouts(db, match):
    return (
        db.query(models.Rollout)
        .filter(models.Rollout.match_id == match.id)
        .all()
    )


def test_overall_fit_has_six_axes(db):
    world = build_world(db, candidate_specs=[{"name": "Alex", "overall": 82}])
    match = _match_for(db, world["candidates"][0])
    overall = compute_overall_fit(match, db)

    assert set(overall.keys()) == {
        "role_fit",
        "team_chem",
        "memo_culture",
        "conflict_prod",
        "ramp_speed",
        "long_cycle",
    }
    for value in overall.values():
        assert 0 <= value <= 100
    # role_fit mirrors the match overall score.
    assert overall["role_fit"] == 82


def test_conflict_productivity_from_intents(db):
    world = build_world(
        db,
        candidate_specs=[{"name": "Alex", "overall": 60, "intent": "productive_disagreement"}],
    )
    match = _match_for(db, world["candidates"][0])
    overall = compute_overall_fit(match, db)
    # All candidate turns are productive disagreement → 100.
    assert overall["conflict_prod"] == 100
