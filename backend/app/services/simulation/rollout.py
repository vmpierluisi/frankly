"""Single-rollout execution pipeline.

MiroFish lineage: corresponds to MiroFish's RolloutExecutor.run().
Phase 4B wires the real judge (judge.py) — mock stubs from Phase 4A removed.

Public API:
  execute_rollout(...)  →  Rollout ORM object (already added to session,
                           not committed — caller commits).
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from .agent_runtime import advance_turn
from .cost_tracker import CostBudget, CostCeilingExceeded
from .judge import score_rollout
from .rollout_logger import log_event
from .scenario_engine import prepare_rollout

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from ...models import MomentOfTruth, Rollout

logger = logging.getLogger(__name__)


async def execute_rollout(
    *,
    match_id: str,
    scenario: "MomentOfTruth",
    candidate_persona: dict[str, Any],
    teammates: list[dict[str, Any]],
    criteria: list[dict[str, Any]],
    k_index: int,
    db: "Session",
    budget: CostBudget,
    seed: str | None = None,
    company_name: str = "",
    role: str = "",
    candidate_label: str = "Candidate",
) -> "Rollout":
    """Execute one rollout, score it, and return the persisted Rollout ORM object.

    The rollout is added to the session but NOT committed.  The caller is
    responsible for the final db.commit().

    Steps
    -----
    1. prepare_rollout() — build WorldState from scenario + personas
    2. Turn loop via advance_turn() — stops on ends_turn signal or max_turns
    3. Persist Rollout row (flush to get ID)
    4. score_rollout() — two judge LLM calls, merged into RolloutScore rows
    """
    from ...models import Rollout  # deferred to avoid circular import

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
        while world.current_turn < max_turns:
            ended = await advance_turn(
                world,
                budget=budget,
                company_name=company_name,
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

    scenario_dict = {
        "id": str(scenario.id),
        "prompt": scenario.prompt,
        "expected_arc": scenario.expected_arc,
    }

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

    # Flush so rollout.id is assigned before scoring rows reference it.
    db.flush()

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

    # --- Real judge scoring (Phase 4B) ------------------------------------
    judge_result = await score_rollout(
        rollout,
        scenario_dict,
        criteria,
        budget=budget,
        db=db,
        match_id=match_id,
        company_name=company_name,
        role=role,
        candidate_label=candidate_label,
    )
    for row in judge_result.rows:
        db.add(row)

    # Store transcript summary for aggregator
    rollout.final_state = {**rollout.final_state, "transcript_summary": judge_result.transcript_summary}

    logger.info(
        "execute_rollout: match=%s k=%d scenario=%s turns=%d status=%s scores=%d",
        match_id, k_index, scenario.id, world.current_turn, status, len(judge_result.rows),
    )
    return rollout
