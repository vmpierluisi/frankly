"""Unit tests for services/hero_quote.py (V7)."""
from __future__ import annotations

import pytest

from app import models
from app.services.hero_quote import pick_hero_quote
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


def test_picks_candidate_utterance_with_scenario_and_teammate(db):
    world = build_world(
        db,
        candidate_specs=[
            {"name": "Alex", "overall": 80,
             "scenario_scores": {"asterisk": 95, "model_gap": 40}}
        ],
    )
    match = _match_for(db, world["candidates"][0])
    quote = pick_hero_quote(match, db)

    assert "Alex" in quote["text"]
    # The asterisk scenario scored highest → its turn should be the hero quote.
    assert quote["scenario_id"] == world["scenarios"]["asterisk"].id
    # The teammate they replied to on that scenario is Maya.
    assert quote["to_teammate_id"] == world["teammates"]["maya"].id
    assert "honesty" in quote["dimensions"]


def test_low_confidence_scores_are_ignored(db):
    world = build_world(db, candidate_specs=[{"name": "Sam", "overall": 60}])
    match = _match_for(db, world["candidates"][0])
    # Drop every score's confidence below threshold.
    for score in db.query(models.RolloutScore).all():
        score.confidence = 0.4
    db.commit()

    quote = pick_hero_quote(match, db)
    assert quote["text"] == ""
    assert quote["scenario_id"] == ""
