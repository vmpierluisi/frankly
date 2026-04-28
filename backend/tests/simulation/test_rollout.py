"""Unit + integration tests for services/simulation/rollout.py — Phase 4A.

Validation gate:
  (1) execute_rollout() returns a Rollout ORM object with correct fields.
  (2) Rollout.transcript contains the turn history.
  (3) Rollout.status == "completed" on normal exit.
  (4) Rollout.status == "aborted" when CostCeilingExceeded is raised.
  (5) Mock RolloutScore stubs are created for each scoring dimension.
  (6) RolloutLog rows are written (rollout_started, turn_completed, rollout_ended, judge_scored).
  (7) ends_turn=True signal stops the loop early.
  (8) Loop stops at max_turns even without ends_turn signal.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch, MagicMock

import pytest
import pytest_asyncio
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.db import Base
from app.models import Rollout, RolloutScore, RolloutLog
from app.services.simulation.rollout import execute_rollout
from app.services.simulation.cost_tracker import CostBudget, CostCeilingExceeded


# ---------------------------------------------------------------------------
# Async SQLite fixture
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture()
async def async_db():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


# ---------------------------------------------------------------------------
# Stub objects
# ---------------------------------------------------------------------------

class _StubCriterion:
    def __init__(self, key):
        self.key = key
        self.label = key
        self.weight = 0.25


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


_CANDIDATE_PERSONA = {
    "narrative": "Strong analytical background.",
    "structured_traits": {
        "big_five": {"openness": 4.0, "conscientiousness": 4.5},
    },
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

_STUB_TURN = {
    "utterance": "Hello.",
    "intent": "open",
    "internal_state": "calm",
    "ends_turn": False,
}

_STUB_TURN_ENDS = {**_STUB_TURN, "ends_turn": True}

_STUB_MATCH_ID = "match-001"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_budget(ceiling: float = 1.0) -> CostBudget:
    return CostBudget(ceiling_usd=ceiling)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_execute_rollout_returns_rollout_object(async_db):
    with patch(
        "app.services.simulation.agent_runtime.tracked_chat_json",
        new=AsyncMock(return_value=_STUB_TURN),
    ):
        rollout = await execute_rollout(
            match_id=_STUB_MATCH_ID,
            scenario=_StubScenario(),
            candidate_persona=_CANDIDATE_PERSONA,
            teammates=_TEAMMATES,
            k_index=0,
            db=async_db,
            budget=_make_budget(),
        )

    assert isinstance(rollout, Rollout)
    assert rollout.match_id == _STUB_MATCH_ID
    assert rollout.rollout_index == 0


@pytest.mark.asyncio
async def test_execute_rollout_status_completed(async_db):
    with patch(
        "app.services.simulation.agent_runtime.tracked_chat_json",
        new=AsyncMock(return_value=_STUB_TURN),
    ):
        rollout = await execute_rollout(
            match_id=_STUB_MATCH_ID,
            scenario=_StubScenario(),
            candidate_persona=_CANDIDATE_PERSONA,
            teammates=_TEAMMATES,
            k_index=0,
            db=async_db,
            budget=_make_budget(),
        )

    assert rollout.status == "completed"
    assert rollout.failure_reason is None


@pytest.mark.asyncio
async def test_execute_rollout_transcript_populated(async_db):
    with patch(
        "app.services.simulation.agent_runtime.tracked_chat_json",
        new=AsyncMock(return_value=_STUB_TURN),
    ):
        rollout = await execute_rollout(
            match_id=_STUB_MATCH_ID,
            scenario=_StubScenario(),
            candidate_persona=_CANDIDATE_PERSONA,
            teammates=_TEAMMATES,
            k_index=0,
            db=async_db,
            budget=_make_budget(),
        )

    assert isinstance(rollout.transcript, list)
    assert len(rollout.transcript) > 0


@pytest.mark.asyncio
async def test_execute_rollout_stops_at_max_turns(async_db):
    scenario = _StubScenario()
    scenario.max_turns = 2

    with patch(
        "app.services.simulation.agent_runtime.tracked_chat_json",
        new=AsyncMock(return_value=_STUB_TURN),
    ):
        rollout = await execute_rollout(
            match_id=_STUB_MATCH_ID,
            scenario=scenario,
            candidate_persona=_CANDIDATE_PERSONA,
            teammates=_TEAMMATES,
            k_index=0,
            db=async_db,
            budget=_make_budget(),
        )

    assert rollout.duration_turns <= 2


@pytest.mark.asyncio
async def test_execute_rollout_stops_on_ends_turn(async_db):
    # First call returns ends_turn=True — loop should stop after one turn.
    with patch(
        "app.services.simulation.agent_runtime.tracked_chat_json",
        new=AsyncMock(return_value=_STUB_TURN_ENDS),
    ):
        rollout = await execute_rollout(
            match_id=_STUB_MATCH_ID,
            scenario=_StubScenario(),
            candidate_persona=_CANDIDATE_PERSONA,
            teammates=_TEAMMATES,
            k_index=0,
            db=async_db,
            budget=_make_budget(),
        )

    assert rollout.duration_turns == 1
    assert rollout.status == "completed"


@pytest.mark.asyncio
async def test_execute_rollout_aborted_on_cost_ceiling(async_db):
    with patch(
        "app.services.simulation.agent_runtime.tracked_chat_json",
        new=AsyncMock(side_effect=CostCeilingExceeded("over budget")),
    ):
        rollout = await execute_rollout(
            match_id=_STUB_MATCH_ID,
            scenario=_StubScenario(),
            candidate_persona=_CANDIDATE_PERSONA,
            teammates=_TEAMMATES,
            k_index=0,
            db=async_db,
            budget=_make_budget(),
        )

    assert rollout.status == "aborted"
    assert "cost_ceiling" in rollout.failure_reason


@pytest.mark.asyncio
async def test_mock_rollout_scores_created(async_db):
    with patch(
        "app.services.simulation.agent_runtime.tracked_chat_json",
        new=AsyncMock(return_value=_STUB_TURN_ENDS),
    ):
        rollout = await execute_rollout(
            match_id=_STUB_MATCH_ID,
            scenario=_StubScenario(),
            candidate_persona=_CANDIDATE_PERSONA,
            teammates=_TEAMMATES,
            k_index=0,
            db=async_db,
            budget=_make_budget(),
        )
        await async_db.commit()

    from sqlalchemy import select
    rows = (await async_db.execute(
        select(RolloutScore).where(RolloutScore.rollout_id == rollout.id)
    )).scalars().all()

    assert len(rows) == 2  # one per scoring_dim ("written_rigor", "decisiveness")
    dim_keys = {r.dimension_key for r in rows}
    assert "written_rigor" in dim_keys
    assert "decisiveness" in dim_keys
    # Phase 4A scores are null stubs.
    assert all(r.score is None for r in rows)


@pytest.mark.asyncio
async def test_rollout_log_events_written(async_db):
    with patch(
        "app.services.simulation.agent_runtime.tracked_chat_json",
        new=AsyncMock(return_value=_STUB_TURN_ENDS),
    ):
        await execute_rollout(
            match_id=_STUB_MATCH_ID,
            scenario=_StubScenario(),
            candidate_persona=_CANDIDATE_PERSONA,
            teammates=_TEAMMATES,
            k_index=0,
            db=async_db,
            budget=_make_budget(),
        )
        await async_db.commit()

    from sqlalchemy import select
    rows = (await async_db.execute(
        select(RolloutLog).where(RolloutLog.match_id == _STUB_MATCH_ID)
    )).scalars().all()

    event_types = {r.event_type for r in rows}
    assert "rollout_started" in event_types
    assert "rollout_ended" in event_types
    assert "judge_scored" in event_types
