"""Integration tests for services/simulation/rollout.py — Phase 4B/4C.

Validation gate:
  (1) execute_rollout() returns a Rollout ORM object with correct fields.
  (2) Rollout.transcript contains the turn history.
  (3) Rollout.status == "completed" on normal exit.
  (4) Rollout.status == "aborted" when CostCeilingExceeded is raised by agent.
  (5) RolloutScore rows are created with real scores from the judge.
  (6) RolloutLog rows are written (rollout_started, rollout_ended, judge_scored).
  (7) ends_turn=True signal stops the loop early.
  (8) Loop stops at max_turns even without ends_turn signal.
  (9) transcript_summary is stored in rollout.final_state.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import Rollout, RolloutLog, RolloutScore
from app.services.simulation.rollout import execute_rollout
from app.services.simulation.cost_tracker import CostBudget, CostCeilingExceeded


# ---------------------------------------------------------------------------
# Sync DB fixture (execute_rollout uses sync Session)
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


# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------

class _StubScenario:
    id = "scen-001"
    title = "Budget pressure"
    scenario_type = "dyad"
    prompt = "Q4 targets are at risk. What do you cut?"
    candidate_role = "Analyst presenting options."
    expected_arc = "Structured prioritised recommendation."
    scoring_dims = ["written_rigor", "decisiveness"]
    participating_roles = ["Associate"]
    max_turns = 3
    grounding = ""
    is_llm_drafted = True


_CRITERIA = [
    {"key": "written_rigor", "label": "Written Rigor", "description": "Structures arguments clearly."},
    {"key": "decisiveness", "label": "Decisiveness", "description": "Makes calls without hedging."},
]

_CANDIDATE_PERSONA = {
    "narrative": "Strong analytical background.",
    "structured_traits": {"big_five": {"openness": 4.0}},
}

_TEAMMATES = [
    {
        "id": "tm-001",
        "name": "Alex",
        "role_on_team": "Associate",
        "seniority": "senior",
        "narrative": "Experienced deal-side associate.",
        "trait_sheet": {},
        "private_goals": ["probe reasoning"],
    }
]

_STUB_TURN = {"utterance": "Hello.", "intent": "open", "internal_state": "calm", "ends_turn": False}
_STUB_TURN_ENDS = {**_STUB_TURN, "ends_turn": True}
_STUB_MATCH_ID = "match-001"

_JUDGE_RESPONSE = {
    "dimension_scores": {
        "written_rigor": {"score": 78, "justification": "Clear.", "evidence_turns": [0], "confidence": 0.8},
        "decisiveness":  {"score": 82, "justification": "Direct.", "evidence_turns": [0], "confidence": 0.75},
    },
    "transcript_summary": "Candidate was clear and decisive.",
    "judge_notes": "",
}


def _make_budget(ceiling: float = 5.0) -> CostBudget:
    return CostBudget(ceiling_usd=ceiling)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_execute_rollout_returns_rollout_object(db_session):
    with patch("app.services.simulation.agent_runtime.tracked_chat_json", new=AsyncMock(return_value=_STUB_TURN)), \
         patch("app.services.simulation.judge.tracked_chat_json", new=AsyncMock(return_value=_JUDGE_RESPONSE)):
        rollout = await execute_rollout(
            match_id=_STUB_MATCH_ID, scenario=_StubScenario(),
            candidate_persona=_CANDIDATE_PERSONA, teammates=_TEAMMATES,
            criteria=_CRITERIA, k_index=0, db=db_session, budget=_make_budget(),
        )

    assert isinstance(rollout, Rollout)
    assert rollout.match_id == _STUB_MATCH_ID
    assert rollout.rollout_index == 0


@pytest.mark.asyncio
async def test_execute_rollout_status_completed(db_session):
    with patch("app.services.simulation.agent_runtime.tracked_chat_json", new=AsyncMock(return_value=_STUB_TURN)), \
         patch("app.services.simulation.judge.tracked_chat_json", new=AsyncMock(return_value=_JUDGE_RESPONSE)):
        rollout = await execute_rollout(
            match_id=_STUB_MATCH_ID, scenario=_StubScenario(),
            candidate_persona=_CANDIDATE_PERSONA, teammates=_TEAMMATES,
            criteria=_CRITERIA, k_index=0, db=db_session, budget=_make_budget(),
        )

    assert rollout.status == "completed"
    assert rollout.failure_reason is None


@pytest.mark.asyncio
async def test_execute_rollout_transcript_populated(db_session):
    with patch("app.services.simulation.agent_runtime.tracked_chat_json", new=AsyncMock(return_value=_STUB_TURN)), \
         patch("app.services.simulation.judge.tracked_chat_json", new=AsyncMock(return_value=_JUDGE_RESPONSE)):
        rollout = await execute_rollout(
            match_id=_STUB_MATCH_ID, scenario=_StubScenario(),
            candidate_persona=_CANDIDATE_PERSONA, teammates=_TEAMMATES,
            criteria=_CRITERIA, k_index=0, db=db_session, budget=_make_budget(),
        )

    assert isinstance(rollout.transcript, list)
    assert len(rollout.transcript) > 0


@pytest.mark.asyncio
async def test_execute_rollout_stops_at_max_turns(db_session):
    scenario = _StubScenario()
    scenario.max_turns = 2

    with patch("app.services.simulation.agent_runtime.tracked_chat_json", new=AsyncMock(return_value=_STUB_TURN)), \
         patch("app.services.simulation.judge.tracked_chat_json", new=AsyncMock(return_value=_JUDGE_RESPONSE)):
        rollout = await execute_rollout(
            match_id=_STUB_MATCH_ID, scenario=scenario,
            candidate_persona=_CANDIDATE_PERSONA, teammates=_TEAMMATES,
            criteria=_CRITERIA, k_index=0, db=db_session, budget=_make_budget(),
        )

    assert rollout.duration_turns <= 2


@pytest.mark.asyncio
async def test_execute_rollout_stops_on_ends_turn(db_session):
    with patch("app.services.simulation.agent_runtime.tracked_chat_json", new=AsyncMock(return_value=_STUB_TURN_ENDS)), \
         patch("app.services.simulation.judge.tracked_chat_json", new=AsyncMock(return_value=_JUDGE_RESPONSE)):
        rollout = await execute_rollout(
            match_id=_STUB_MATCH_ID, scenario=_StubScenario(),
            candidate_persona=_CANDIDATE_PERSONA, teammates=_TEAMMATES,
            criteria=_CRITERIA, k_index=0, db=db_session, budget=_make_budget(),
        )

    assert rollout.duration_turns == 1
    assert rollout.status == "completed"


@pytest.mark.asyncio
async def test_execute_rollout_aborted_on_cost_ceiling(db_session):
    with patch("app.services.simulation.agent_runtime.tracked_chat_json",
               new=AsyncMock(side_effect=CostCeilingExceeded("over budget"))), \
         patch("app.services.simulation.judge.tracked_chat_json", new=AsyncMock(return_value=_JUDGE_RESPONSE)):
        rollout = await execute_rollout(
            match_id=_STUB_MATCH_ID, scenario=_StubScenario(),
            candidate_persona=_CANDIDATE_PERSONA, teammates=_TEAMMATES,
            criteria=_CRITERIA, k_index=0, db=db_session, budget=_make_budget(),
        )

    assert rollout.status == "aborted"
    assert "cost_ceiling" in rollout.failure_reason


@pytest.mark.asyncio
async def test_rollout_scores_created_with_real_scores(db_session):
    with patch("app.services.simulation.agent_runtime.tracked_chat_json", new=AsyncMock(return_value=_STUB_TURN_ENDS)), \
         patch("app.services.simulation.judge.tracked_chat_json", new=AsyncMock(return_value=_JUDGE_RESPONSE)):
        rollout = await execute_rollout(
            match_id=_STUB_MATCH_ID, scenario=_StubScenario(),
            candidate_persona=_CANDIDATE_PERSONA, teammates=_TEAMMATES,
            criteria=_CRITERIA, k_index=0, db=db_session, budget=_make_budget(),
        )
        db_session.commit()

    rows = db_session.execute(
        select(RolloutScore).where(RolloutScore.rollout_id == rollout.id)
    ).scalars().all()

    assert len(rows) == 2
    dim_keys = {r.dimension_key for r in rows}
    assert "written_rigor" in dim_keys
    assert "decisiveness" in dim_keys
    assert all(r.score is not None for r in rows)


@pytest.mark.asyncio
async def test_rollout_transcript_summary_stored(db_session):
    with patch("app.services.simulation.agent_runtime.tracked_chat_json", new=AsyncMock(return_value=_STUB_TURN_ENDS)), \
         patch("app.services.simulation.judge.tracked_chat_json", new=AsyncMock(return_value=_JUDGE_RESPONSE)):
        rollout = await execute_rollout(
            match_id=_STUB_MATCH_ID, scenario=_StubScenario(),
            candidate_persona=_CANDIDATE_PERSONA, teammates=_TEAMMATES,
            criteria=_CRITERIA, k_index=0, db=db_session, budget=_make_budget(),
        )

    assert rollout.final_state.get("transcript_summary") == "Candidate was clear and decisive."


@pytest.mark.asyncio
async def test_rollout_log_events_written(db_session):
    with patch("app.services.simulation.agent_runtime.tracked_chat_json", new=AsyncMock(return_value=_STUB_TURN_ENDS)), \
         patch("app.services.simulation.judge.tracked_chat_json", new=AsyncMock(return_value=_JUDGE_RESPONSE)):
        await execute_rollout(
            match_id=_STUB_MATCH_ID, scenario=_StubScenario(),
            candidate_persona=_CANDIDATE_PERSONA, teammates=_TEAMMATES,
            criteria=_CRITERIA, k_index=0, db=db_session, budget=_make_budget(),
        )
        db_session.commit()

    rows = db_session.execute(
        select(RolloutLog).where(RolloutLog.match_id == _STUB_MATCH_ID)
    ).scalars().all()

    event_types = {r.event_type for r in rows}
    assert "rollout_started" in event_types
    assert "rollout_ended" in event_types
    assert "judge_scored" in event_types
