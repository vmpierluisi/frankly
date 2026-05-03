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

from . import PROMPT_VERSION
from .agent_runtime import advance_turn
from .cost_tracker import CostBudget, CostCeilingExceeded
from .fidelity_judge import (
    FIDELITY_DIMENSION_KEY,
    FIDELITY_JUDGE_TAG,
    FIDELITY_MAX_RETRIES,
    FIDELITY_RERUN_THRESHOLD,
    score_persona_fidelity,
)
from .judge import score_rollout
from .rollout_logger import log_event
from .scenario_engine import prepare_rollout
from .skill_gap_briefing import compute_gap_briefing

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
    retry_count: int = 0,
    superseded_rollout_id: str | None = None,
) -> "Rollout":
    """Execute one rollout, score it, and return the persisted Rollout ORM object.

    The rollout is added to the session but NOT committed.  The caller is
    responsible for the final db.commit().

    Steps
    -----
    1. prepare_rollout() — build WorldState from scenario + personas
    2. Pre-flight skill-gap briefing (PR #1.4)
    3. Turn loop via advance_turn() — stops on ends_turn signal or max_turns
    4. Persist Rollout row (flush to get ID)
    5. score_rollout() — two judge LLM calls, merged into RolloutScore rows
    6. score_persona_fidelity() — separate judge call; persisted as a
       non-criterion RolloutScore row with dimension_key="persona_fidelity".
       Below FIDELITY_RERUN_THRESHOLD, the rollout is marked "superseded"
       and re-run once with a fresh seed (retry_count incremented).
    """
    from ...models import Rollout  # deferred to avoid circular import

    world = prepare_rollout(
        scenario,
        candidate_persona,
        teammates,
        seed=seed,
    )

    # ---- Pre-flight skill-gap briefing (PR #1.4) --------------------------
    # Reuse the briefing across rollouts of the same (scenario, candidate)
    # pair via the shared candidate_persona dict. The first rollout pays the
    # cost; subsequent rollouts pull from the cache.
    briefing = candidate_persona.get("_gap_briefings", {}).get(str(scenario.id)) if isinstance(candidate_persona, dict) else None
    if briefing is None:
        verified_profile = candidate_persona.get("verified_profile") if isinstance(candidate_persona, dict) else None
        capability_ledger = (verified_profile or {}).get("capability_ledger")
        briefing = await compute_gap_briefing(
            scenario=scenario,
            capability_ledger=capability_ledger,
            budget=budget,
        )
        if isinstance(candidate_persona, dict):
            cache = candidate_persona.setdefault("_gap_briefings", {})
            cache[str(scenario.id)] = briefing  # may be None — caches the negative
    if briefing is not None:
        world.scenario["gap_briefing"] = briefing

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
            "gap_briefing": {
                "required_skills": (briefing or {}).get("required_skills", []) if briefing else [],
                "gap_count": len((briefing or {}).get("gaps", [])) if briefing else 0,
            },
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
        prompt_version=PROMPT_VERSION,
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

    # --- Persona fidelity (PR #1.6) ---------------------------------------
    # Cost optimization: fidelity is largely a function of prompt setup
    # (verified profile + gap briefing + persona constraints), not rollout
    # variance. We score it on the FIRST rollout per scenario only — when a
    # retry is triggered, we still re-score (so we know the retry actually
    # improved fidelity). Subsequent rollouts of the same scenario reuse
    # the first rollout's score for retry decisioning.
    from ...models import RolloutScore  # deferred to avoid circular import

    verified_profile = (
        candidate_persona.get("verified_profile") if isinstance(candidate_persona, dict) else None
    )
    fidelity = None
    fidelity_scored_here = False
    fidelity_cache_key = str(scenario.id)
    fidelity_cache: dict[str, Any] = (
        candidate_persona.setdefault("_fidelity_scores", {})
        if isinstance(candidate_persona, dict) else {}
    )
    already_scored_for_scenario = fidelity_cache_key in fidelity_cache

    should_score_fidelity = (
        status == "completed"
        and verified_profile is not None
        and (
            not already_scored_for_scenario
            or retry_count > 0  # always re-score on retries
        )
    )
    if should_score_fidelity:
        fidelity = await score_persona_fidelity(
            transcript=world.turn_history,
            verified_profile=verified_profile,
            gap_briefing=world.scenario.get("gap_briefing"),
            budget=budget,
        )
        if fidelity is not None:
            fidelity_scored_here = True
            fidelity_cache[fidelity_cache_key] = {
                "score": fidelity.get("score"),
                "confidence": fidelity.get("confidence"),
                "rollout_id": rollout.id,
            }

    if fidelity is not None:
        db.add(
            RolloutScore(
                rollout_id=rollout.id,
                dimension_key=FIDELITY_DIMENSION_KEY,
                score=fidelity.get("score"),
                justification=fidelity.get("justification", ""),
                evidence_turns=[v.get("turn_index") for v in fidelity.get("violations", [])],
                judge_model=FIDELITY_JUDGE_TAG,
                judge_seed_index=0,
                confidence=float(fidelity.get("confidence") or 0.0),
                prompt_version=PROMPT_VERSION,
            )
        )
        rollout.final_state = {
            **rollout.final_state,
            "persona_fidelity": {
                "score": fidelity.get("score"),
                "confidence": fidelity.get("confidence"),
                "violations": fidelity.get("violations", []),
                "retry_count": retry_count,
            },
        }
        await log_event(
            match_id,
            rollout.id,
            "persona_fidelity_scored",
            {
                "score": fidelity.get("score"),
                "confidence": fidelity.get("confidence"),
                "violation_count": len(fidelity.get("violations", [])),
                "retry_count": retry_count,
            },
            db=db,
        )

    # --- Auto re-run on low fidelity --------------------------------------
    fidelity_score = (fidelity or {}).get("score")
    should_retry = (
        fidelity_score is not None
        and fidelity_score < FIDELITY_RERUN_THRESHOLD
        and retry_count < FIDELITY_MAX_RETRIES
        and status == "completed"
    )
    if should_retry:
        rollout.status = "superseded"
        rollout.failure_reason = (
            f"persona_fidelity={fidelity_score} below threshold "
            f"{FIDELITY_RERUN_THRESHOLD}; re-running"
        )
        await log_event(
            match_id,
            rollout.id,
            "rollout_retry_for_fidelity",
            {
                "previous_fidelity": fidelity_score,
                "threshold": FIDELITY_RERUN_THRESHOLD,
                "retry_count": retry_count + 1,
            },
            db=db,
        )
        db.flush()

        return await execute_rollout(
            match_id=match_id,
            scenario=scenario,
            candidate_persona=candidate_persona,
            teammates=teammates,
            criteria=criteria,
            k_index=k_index,
            db=db,
            budget=budget,
            seed=None,  # fresh seed
            company_name=company_name,
            role=role,
            candidate_label=candidate_label,
            retry_count=retry_count + 1,
            superseded_rollout_id=rollout.id,
        )

    if superseded_rollout_id:
        rollout.final_state = {
            **rollout.final_state,
            "superseded_rollout_id": superseded_rollout_id,
        }

    # If we skipped fidelity scoring because another rollout for this scenario
    # already paid the cost, record the reference for the audit trail so the
    # manager can see which rollout's score "covers" this one.
    if (
        not fidelity_scored_here
        and already_scored_for_scenario
        and status == "completed"
        and verified_profile is not None
    ):
        cached = fidelity_cache.get(fidelity_cache_key) or {}
        rollout.final_state = {
            **rollout.final_state,
            "persona_fidelity_inherited_from": cached.get("rollout_id"),
            "persona_fidelity_inherited_score": cached.get("score"),
        }

    logger.info(
        "execute_rollout: match=%s k=%d scenario=%s turns=%d status=%s scores=%d "
        "fidelity=%s retry=%d",
        match_id, k_index, scenario.id, world.current_turn, status,
        len(judge_result.rows), fidelity_score, retry_count,
    )
    return rollout
