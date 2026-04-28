"""Single-rollout execution pipeline.

MiroFish lineage: corresponds to MiroFish's RolloutExecutor.run().
Phase 4A ships execute_rollout() with a MOCKED judge (scores are null
stubs so the full pipeline can be exercised end-to-end).  Phase 4B wires
the real judge (judge.py).

Public API:
  execute_rollout(...)  →  Rollout ORM object (already added to session,
                           not committed — caller commits).
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from .agent_runtime import advance_turn
from .cost_tracker import CostBudget, CostCeilingExceeded
from .rollout_logger import log_event
from .scenario_engine import prepare_rollout

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from ...models import MomentOfTruth, Rollout

logger = logging.getLogger(__name__)

# Sentinel model name used in mock score rows so Phase 4B can distinguish
# rows it needs to back-fill from rows written by real judge calls.
_MOCK_JUDGE_MODEL = "mock/stub-v0"


async def execute_rollout(
    *,
    match_id: str,
    scenario: "MomentOfTruth",
    candidate_persona: dict[str, Any],
    teammates: list[dict[str, Any]],
    k_index: int,
    db: "AsyncSession",
    budget: CostBudget,
    seed: str | None = None,
    company_name: str = "",
) -> "Rollout":
    """Execute one rollout and return a persisted Rollout ORM object.

    The rollout is added to the session but NOT committed.  The caller is
    responsible for the final db.commit().

    Steps
    -----
    1. prepare_rollout() — build WorldState from scenario + personas
    2. Turn loop via advance_turn() — stops on ends_turn signal or max_turns
    3. log_event() calls throughout for audit trail
    4. Mock judge scores (Phase 4A) — one null-score RolloutScore per dim
    5. Add Rollout + RolloutScore rows to session
    """
    from ...models import Rollout, RolloutScore  # deferred to avoid circular import

    world = prepare_rollout(
        scenario,
        candidate_persona,
        teammates,
        seed=seed,
    )

    await log_event(
        match_id,
        None,
        "rollout_started",
        {
            "k_index": k_index,
            "scenario_id": str(scenario.id),
            "scenario_title": scenario.title,
            "seed": world.seed,
            "agent_ids": list(world.agents.keys()),
        },
        db=db,
    )

    status = "completed"
    failure_reason: str | None = None
    max_turns = scenario.max_turns or 6

    try:
        turn_order = None  # advance_turn builds its own canonical order
        while world.current_turn < max_turns:
            ended = await advance_turn(
                world,
                budget=budget,
                company_name=company_name,
                turn_order=turn_order,
            )
            await log_event(
                match_id,
                None,
                "turn_completed",
                {
                    "turn": world.current_turn - 1,
                    "speaker_id": world.turn_history[-1]["speaker_id"],
                    "ends_turn": ended,
                },
                db=db,
            )
            if ended:
                break
    except CostCeilingExceeded as exc:
        status = "aborted"
        failure_reason = f"cost_ceiling: {exc}"
        logger.warning("execute_rollout: aborted match=%s k=%d — %s", match_id, k_index, exc)
    except Exception as exc:  # noqa: BLE001
        status = "failed"
        failure_reason = str(exc)
        logger.exception("execute_rollout: failed match=%s k=%d", match_id, k_index)

    rollout = Rollout(
        match_id=match_id,
        scenario_id=str(scenario.id),
        rollout_index=k_index,
        transcript=world.turn_history,
        final_state={
            "current_turn": world.current_turn,
            "seed": world.seed,
            "agent_ids": list(world.agents.keys()),
        },
        duration_turns=world.current_turn,
        seed=world.seed,
        status=status,
        failure_reason=failure_reason,
    )
    db.add(rollout)

    # We need the rollout.id for the RolloutScore and log rows.  Flush so
    # the DB assigns it without fully committing the transaction.
    await db.flush()

    await log_event(
        match_id,
        rollout.id,
        "rollout_ended",
        {
            "status": status,
            "duration_turns": world.current_turn,
            "failure_reason": failure_reason,
        },
        db=db,
    )

    # --- Phase 4A mock judge -------------------------------------------
    # Emit one null RolloutScore per scoring dimension so downstream
    # aggregation has the row skeleton to fill in Phase 4B.
    for dim_key in (scenario.scoring_dims or []):
        mock_score = RolloutScore(
            rollout_id=rollout.id,
            dimension_key=dim_key,
            score=None,
            justification="(Phase 4A stub — judge not yet wired)",
            evidence_turns=[],
            judge_model=_MOCK_JUDGE_MODEL,
            judge_seed_index=k_index,
            confidence=0.0,
        )
        db.add(mock_score)

    await log_event(
        match_id,
        rollout.id,
        "judge_scored",
        {
            "mock": True,
            "dims": scenario.scoring_dims or [],
        },
        db=db,
    )

    logger.info(
        "execute_rollout: match=%s k=%d scenario=%s turns=%d status=%s",
        match_id, k_index, scenario.id, world.current_turn, status,
    )
    return rollout
