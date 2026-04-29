"""Simulation matcher orchestrator — top-level entry point for a v2 match.

MiroFish lineage: corresponds to MiroFish's MatchOrchestrator.
Phase 4C: replaces the single-LLM-call route handler for POST /matches/trigger.

Orchestration order
-------------------
1. Resolve candidate persona (cached aggregated_persona or synthesize fallback).
2. Load company teammates + scenario library; abort with 409 if missing.
3. Construct CostBudget for the match.
4. For each scenario, run K rollouts concurrently (asyncio.gather + semaphore).
5. In parallel, run baseline_matcher.run_match for the BaselineComparison row.
6. Aggregate rollouts → FitProfile v2 via aggregator.aggregate_fit_profile.
7. Return (fit_profile_dict, rollouts, scores) — caller persists Match +
   BaselineComparison rows.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, TYPE_CHECKING

from ..baseline_matcher import run_match as baseline_run_match
from .aggregator import aggregate_fit_profile
from .cost_tracker import CostBudget, CostCeilingExceeded
from .rollout import execute_rollout
from .rollout_logger import log_event
from ...config import settings

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from ...models import Candidate, Company, MomentOfTruth, Rollout, RolloutScore

logger = logging.getLogger(__name__)

# Default K rollouts per scenario.
_DEFAULT_K = 1  # keep cheap in v0; raise via config when ready


# ---------------------------------------------------------------------------
# Persona resolution
# ---------------------------------------------------------------------------

def _resolve_persona(candidate: "Candidate") -> dict[str, Any]:
    """Return the best available persona dict for this candidate.

    Prefers aggregated_persona (Phase 1B). Falls back to synthesizing from
    BFI/SJT responses via the legacy persona module.
    """
    if candidate.aggregated_persona:
        return candidate.aggregated_persona

    from ...services.persona import synthesize_persona  # deferred
    legacy = synthesize_persona(
        candidate.bfi_responses or {},
        candidate.sjt_responses or {},
    )
    # Wrap legacy shape so it's compatible with simulation pipeline fields.
    return {
        "narrative": legacy.get("narrative", ""),
        "structured_traits": {
            "big_five": legacy.get("bigFive", {}),
            "sjt_signals": legacy.get("sjtSignals", {}),
        },
        "inconsistencies": legacy.get("inconsistencies", []),
        # Legacy persona passes through for baseline_matcher compatibility.
        "_legacy": legacy,
    }


def _candidate_label(candidate: "Candidate") -> str:
    return candidate.display_name or candidate.email or "Candidate"


# ---------------------------------------------------------------------------
# Company data helpers
# ---------------------------------------------------------------------------

def _teammates_as_dicts(company: "Company") -> list[dict[str, Any]]:
    return [
        {
            "id": t.id,
            "name": t.name,
            "role_on_team": t.role_on_team,
            "seniority": t.seniority,
            "narrative": t.narrative,
            "trait_sheet": t.trait_sheet or {},
            "private_goals": t.private_goals or [],
        }
        for t in (company.teammates or [])
    ]


def _criteria_as_dicts(company: "Company") -> list[dict[str, Any]]:
    return [
        {
            "key": c.key,
            "label": c.label,
            "description": c.description,
            "weight": c.weight,
        }
        for c in sorted(company.criteria, key=lambda c: c.ordering)
    ]


def _company_as_dict(company: "Company") -> dict[str, Any]:
    return {
        "id": company.id,
        "name": company.name,
        "role": company.role,
        "tagline": company.tagline or "",
        "artifact_values": company.artifact_values or "",
        "artifact_role_spec": company.artifact_role_spec or "",
        "artifact_team_structure": company.artifact_team_structure or "",
        "artifact_sample_comms": company.artifact_sample_comms or "",
        "criteria": _criteria_as_dicts(company),
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def run_match(
    *,
    match_id: str,
    candidate: "Candidate",
    company: "Company",
    db: "Session",
    k_per_scenario: int = _DEFAULT_K,
) -> dict[str, Any]:
    """Run the full simulation pipeline for one candidate × company pair.

    Returns the FitProfile v2 dict (to be stored in Match.report). All
    Rollout, RolloutScore, RolloutLog, and BaselineComparison rows are added
    to `db` and flushed but NOT committed — caller commits.

    Raises:
        HTTPException 409 — company has no synthetic team or no scenarios.
        HTTPException 502 — persona resolution failed.
    """
    from fastapi import HTTPException
    from ...models import BaselineComparison  # deferred

    wall_start = datetime.now(timezone.utc)

    # ---- Validate prerequisites -------------------------------------------
    teammates = _teammates_as_dicts(company)
    if not teammates:
        raise HTTPException(
            status_code=409,
            detail="Company has no synthetic team — synthesize the team first.",
        )

    scenarios: list["MomentOfTruth"] = list(getattr(company, "scenarios", []) or [])
    if not scenarios:
        raise HTTPException(
            status_code=409,
            detail="Company has no scenario library — draft scenarios first.",
        )

    criteria = _criteria_as_dicts(company)
    company_dict = _company_as_dict(company)

    # ---- Persona resolution -----------------------------------------------
    try:
        persona = _resolve_persona(candidate)
    except Exception as exc:  # noqa: BLE001
        await log_event(match_id, None, "persona_aggregation_failed", {"error": str(exc)}, db=db)
        raise HTTPException(status_code=502, detail=f"Persona resolution failed: {exc}") from exc

    await log_event(
        match_id, None, "persona_aggregated",
        {"aggregator_version": persona.get("aggregator_version", "legacy")},
        db=db,
    )

    # ---- Cost budget -------------------------------------------------------
    budget = CostBudget(ceiling_usd=settings.match_cost_ceiling_usd)

    # ---- Rollout execution — K per scenario --------------------------------
    sem = asyncio.Semaphore(settings.sim_rollouts_concurrency)

    all_rollouts: list["Rollout"] = []
    aborted = False

    async def _run_one(scenario: "MomentOfTruth", k_index: int) -> "Rollout | None":
        async with sem:
            try:
                rollout = await asyncio.wait_for(
                    execute_rollout(
                        match_id=match_id,
                        scenario=scenario,
                        candidate_persona=persona,
                        teammates=teammates,
                        criteria=criteria,
                        k_index=k_index,
                        db=db,
                        budget=budget,
                        company_name=company.name,
                        role=company.role,
                        candidate_label=_candidate_label(candidate),
                    ),
                    timeout=settings.sim_rollout_wall_timeout_s,
                )
                return rollout
            except asyncio.TimeoutError:
                logger.warning("Rollout timed out: match=%s scenario=%s k=%d", match_id, scenario.id, k_index)
                await log_event(match_id, None, "rollout_failed",
                                {"reason": "wall_timeout", "scenario_id": str(scenario.id), "k_index": k_index},
                                db=db)
                return None
            except CostCeilingExceeded:
                raise
            except Exception as exc:  # noqa: BLE001
                logger.exception("Rollout failed: match=%s scenario=%s k=%d", match_id, scenario.id, k_index)
                await log_event(match_id, None, "rollout_failed",
                                {"reason": str(exc), "scenario_id": str(scenario.id), "k_index": k_index},
                                db=db)
                return None

    tasks = [
        _run_one(scenario, k)
        for scenario in scenarios
        for k in range(k_per_scenario)
    ]

    try:
        async def _run_all_with_timeout():
            return await asyncio.gather(*tasks, return_exceptions=True)

        results = await asyncio.wait_for(
            _run_all_with_timeout(),
            timeout=settings.sim_match_wall_timeout_s,
        )
    except asyncio.TimeoutError:
        aborted = True
        await log_event(match_id, None, "match_aborted",
                        {"reason": "wall_timeout", "budget_spent": budget.spent_usd}, db=db)
        results = []
    except CostCeilingExceeded:
        aborted = True
        await log_event(match_id, None, "match_aborted_cost_ceiling",
                        {"budget_spent": budget.spent_usd}, db=db)
        results = []

    for r in results:
        if isinstance(r, BaseException):
            logger.error("Gather exception in run_match: %s", r)
        elif r is not None:
            all_rollouts.append(r)

    # ---- Abort guard — too many failures -----------------------------------
    total = len(tasks)
    failed = total - len(all_rollouts)
    if total > 0 and failed > (total // 2 + 1):
        await log_event(match_id, None, "match_partial_failure",
                        {"total": total, "failed": failed}, db=db)

    # ---- Collect scores from DB (already flushed by execute_rollout) -------
    from ...models import RolloutScore  # deferred
    from sqlalchemy import select

    rollout_ids = [r.id for r in all_rollouts]
    all_scores: list["RolloutScore"] = []
    if rollout_ids:
        all_scores = db.execute(
            select(RolloutScore).where(RolloutScore.rollout_id.in_(rollout_ids))
        ).scalars().all()

    # ---- Baseline matcher (runs in parallel with rollouts conceptually;
    #      here we run it after since we need persona which is ready) ---------
    baseline_report: dict[str, Any] | None = None
    legacy_persona = persona.get("_legacy") or persona
    try:
        baseline_report = await asyncio.wait_for(
            baseline_run_match(persona=legacy_persona, company=company_dict),
            timeout=60,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Baseline matcher failed for match=%s: %s", match_id, exc)
        await log_event(match_id, None, "baseline_failed", {"error": str(exc)}, db=db)

    # Persist BaselineComparison row if we have baseline results
    if baseline_report:
        from ...models import BaselineComparison
        delta_vs_sim: dict[str, Any] = {}
        bc = BaselineComparison(
            match_id=match_id,
            overall_score=baseline_report.get("overallScore", 0),
            per_criterion=baseline_report.get("criterionScores", {}),
            band=baseline_report.get("band", ""),
            band_note=baseline_report.get("bandNote", ""),
            delta_vs_sim=delta_vs_sim,
            robustness_summary="",
        )
        db.merge(bc)

    # ---- Aggregate ---------------------------------------------------------
    wall_ms = int((datetime.now(timezone.utc) - wall_start).total_seconds() * 1000)
    audit_extra = {
        "totalLLMCalls": budget.calls_made,
        "totalTokens": {"prompt": budget.tokens_in, "completion": budget.tokens_out},
        "wallTimeMs": wall_ms,
        "kPerScenario": k_per_scenario,
        "scenariosRun": len(scenarios),
    }
    if aborted:
        audit_extra["aborted"] = "cost_ceiling_or_wall_timeout"

    fit_profile = aggregate_fit_profile(
        all_rollouts,
        list(all_scores),
        criteria,
        company_id=company.id,
        company_name=company.name,
        role=company.role,
        baseline_report=baseline_report,
        audit_extra=audit_extra,
    )

    # Patch baseline delta into the BaselineComparison row now that we have it
    if baseline_report and fit_profile.get("baselineComparison"):
        from ...models import BaselineComparison
        bc_row = db.get(BaselineComparison, match_id)
        if bc_row:
            bc_row.delta_vs_sim = fit_profile["baselineComparison"].get("deltaVsSim", {})
            bc_row.robustness_summary = fit_profile["baselineComparison"].get("robustnessSummary", "")

    await log_event(
        match_id, None, "fit_aggregated",
        {
            "overall_score": fit_profile["overallScore"],
            "band": fit_profile["band"],
            "n_rollouts": len(all_rollouts),
            "budget_spent_usd": round(budget.spent_usd, 4),
        },
        db=db,
    )

    logger.info(
        "run_match: match=%s rollouts=%d score=%d band=%s budget=$%.3f wall=%dms",
        match_id, len(all_rollouts), fit_profile["overallScore"],
        fit_profile["band"], budget.spent_usd, wall_ms,
    )
    return fit_profile
