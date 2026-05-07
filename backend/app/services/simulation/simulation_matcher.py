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
from .proof_layer import get_proof_layer
from .rollout import execute_rollout
from .rollout_logger import log_event
from ...config import settings


class NoRolloutsScored(RuntimeError):
    """Raised by run_match when zero rollouts produced any RolloutScore rows.

    Without scores the aggregator produces a meaningless 0/0/0 fit profile,
    and callers should mark the Match as ``failed`` rather than ``succeeded``
    so demos and analytics aren't polluted with phantom-success entries.
    Roadmap 2 / PR #2d.4.a — fixes the bug where transient infra failures
    silently produced "succeeded" matches with all-zero scores.
    """

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from ...models import Candidate, Company, MomentOfTruth, Rollout, RolloutScore

logger = logging.getLogger(__name__)

# Default K rollouts per scenario.
_DEFAULT_K = 1  # keep cheap in v0; raise via config when ready


# ---------------------------------------------------------------------------
# Persona resolution
# ---------------------------------------------------------------------------

def _verified_profile_payload(candidate: "Candidate") -> dict[str, Any] | None:
    """Extract VerifiedProfile fields used by the agent prompt and pre-flight.

    Returns None when the candidate has no VerifiedProfile row. The payload
    contains everything the simulation pipeline needs to enforce skill /
    communication faithfulness — the public-facing profile fields plus the
    internal capability_ledger, communication_ledger, and voice_samples.
    """
    vp = getattr(candidate, "verified_profile", None)
    if vp is None:
        return None
    return {
        "education": list(vp.education or []),
        "experience": list(vp.experience or []),
        "skills": list(vp.skills or []),
        "github_repos": list(vp.github_repos or []),
        "capability_ledger": dict(vp.capability_ledger or {}),
        "communication_ledger": dict(vp.communication_ledger or {}),
        "voice_samples": list(vp.voice_samples or []),
    }


def _resolve_persona(candidate: "Candidate") -> dict[str, Any]:
    """Return the best available persona dict for this candidate.

    Prefers aggregated_persona (Phase 1B). Falls back to synthesizing from
    BFI/SJT responses via the legacy persona module.

    The VerifiedProfile (if present) is stitched in under
    ``verified_profile`` so downstream rollout / agent prompt code can render
    the capability ledger, communication style, and voice samples.
    """
    verified_payload = _verified_profile_payload(candidate)

    if candidate.aggregated_persona:
        persona = dict(candidate.aggregated_persona)
        if verified_payload is not None:
            persona["verified_profile"] = verified_payload
        return persona

    from ...services.persona import synthesize_persona  # deferred
    legacy = synthesize_persona(
        candidate.bfi_responses or {},
        candidate.sjt_responses or {},
    )
    # Wrap legacy shape so it's compatible with simulation pipeline fields.
    persona = {
        "narrative": legacy.get("narrative", ""),
        "structured_traits": {
            "big_five": legacy.get("bigFive", {}),
            "sjt_signals": legacy.get("sjtSignals", {}),
        },
        "inconsistencies": legacy.get("inconsistencies", []),
        # Legacy persona passes through for baseline_matcher compatibility.
        "_legacy": legacy,
    }
    if verified_payload is not None:
        persona["verified_profile"] = verified_payload
    return persona


def _candidate_label(candidate: "Candidate") -> str:
    return candidate.display_name or candidate.email or "Candidate"


# ---------------------------------------------------------------------------
# Company data helpers
# ---------------------------------------------------------------------------

def _teammates_as_dicts(company: "Position") -> list[dict[str, Any]]:
    team = getattr(company, "team", None)
    teammates = (team.teammates if team is not None else None) or []
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
        for t in teammates
    ]


def _criteria_as_dicts(company: "Position") -> list[dict[str, Any]]:
    return [
        {
            "key": c.key,
            "label": c.label,
            "description": c.description,
            "weight": c.weight,
        }
        for c in sorted(company.criteria, key=lambda c: c.ordering)
    ]


def _company_as_dict(company: "Position") -> dict[str, Any]:
    org = getattr(company, "organization", None)
    team = getattr(company, "team", None)
    return {
        "id": company.id,
        "name": company.name,
        "role": company.role,
        "tagline": (org.tagline if org is not None else None) or "",
        "artifact_values": (org.mission if org is not None else None) or "",
        "artifact_role_spec": company.artifact_role_spec or "",
        "artifact_team_structure": (team.artifact_team_structure if team is not None else None) or "",
        "artifact_sample_comms": (team.artifact_sample_comms if team is not None else None) or "",
        "criteria": _criteria_as_dicts(company),
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def run_match(
    *,
    match_id: str,
    candidate: "Candidate",
    company: "Position",
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

    await log_event(
        match_id, None, "match_started",
        {
            "candidate_id": candidate.id,
            "position_id": company.id,
            "k_per_scenario": k_per_scenario,
        },
        db=db,
    )

    # ---- Validate prerequisites -------------------------------------------
    teammates = _teammates_as_dicts(company)
    if not teammates:
        raise HTTPException(
            status_code=409,
            detail="Company has no synthetic team — synthesize the team first.",
        )

    team = getattr(company, "team", None)
    scenarios: list["MomentOfTruth"] = list(
        (team.scenarios if team is not None else None) or []
    )
    if not scenarios:
        raise HTTPException(
            status_code=409,
            detail="Company has no scenario library — draft scenarios first.",
        )

    # Fast mode: cap scenarios + K for live demo speed (~30s/match).
    if settings.sim_fast_mode:
        scenarios = scenarios[:2]
        k_per_scenario = 1

    await log_event(
        match_id, None, "team_loaded",
        {"teammate_count": len(teammates), "scenario_count": len(scenarios)},
        db=db,
    )

    criteria = _criteria_as_dicts(company)
    company_dict = _company_as_dict(company)

    # ---- Persona resolution -----------------------------------------------
    try:
        persona = _resolve_persona(candidate)
    except Exception as exc:  # noqa: BLE001
        await log_event(match_id, None, "persona_aggregation_failed", {"error": str(exc)}, db=db)
        raise HTTPException(status_code=502, detail=f"Persona resolution failed: {exc}") from exc

    persona = await get_proof_layer().attest_persona(persona)

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
        # Make sure RolloutScore rows added by execute_rollout are visible to
        # the select below — sessions configured with ``autoflush=False``
        # (incl. our test fixtures) won't surface uncommitted writes otherwise.
        db.flush()
        all_scores = db.execute(
            select(RolloutScore).where(RolloutScore.rollout_id.in_(rollout_ids))
        ).scalars().all()

    # PR #2d.4.a — refuse to call this match "succeeded" if zero criteria
    # judges scored anything. Fidelity-judge rows alone don't count because
    # they don't drive overall_fit. Without at least one criteria score the
    # aggregator returns 0/0/0 — that masks upstream failures and pollutes
    # leaderboards with phantom-success rows.
    criteria_scores = [
        s for s in all_scores
        if s.dimension_key != "persona_fidelity" and s.score is not None
    ]
    if not criteria_scores:
        await log_event(
            match_id, None, "match_aborted_no_scores",
            {"total_rollouts": total, "completed_rollouts": len(all_rollouts)},
            db=db,
        )
        raise NoRolloutsScored(
            f"All {total} rollouts failed or produced no criteria scores; "
            "marking match as failed rather than succeeded with zero score."
        )

    # ---- Baseline matcher (runs in parallel with rollouts conceptually;
    #      here we run it after since we need persona which is ready) ---------
    baseline_report: dict[str, Any] | None = None
    legacy_persona = persona.get("_legacy") or persona
    try:
        baseline_report = await asyncio.wait_for(
            baseline_run_match(persona=legacy_persona, company=company_dict),
            timeout=60,
        )
        await log_event(
            match_id, None, "baseline_run",
            {"overall_score": baseline_report.get("overallScore"), "band": baseline_report.get("band")},
            db=db,
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

    # PR #2d.3 — feed dual-score inputs (required_skills + candidate's
    # capability_ledger) to the aggregator so it can compute skills_fit
    # alongside behaviour_fit.
    verified_for_aggr = (
        persona.get("verified_profile") if isinstance(persona, dict) else None
    )
    fit_profile = aggregate_fit_profile(
        all_rollouts,
        list(all_scores),
        criteria,
        match_id=match_id,
        position_id=company.id,
        company_name=company.name,
        role=company.role,
        baseline_report=baseline_report,
        audit_extra=audit_extra,
        required_skills=list(getattr(company, "required_skills", []) or []),
        capability_ledger=(verified_for_aggr or {}).get("capability_ledger"),
    )

    # ---- ProofLayer — attest per-dimension scores then build proof chain ----
    per_dim = fit_profile.get("dimensionScores") or fit_profile.get("criterionScores") or {}
    attested_dims: dict[str, Any] = {}
    for dim_key, dim_val in per_dim.items():
        evidence = {"dimension": dim_key, "rollout_count": len(all_rollouts)}
        attested = await get_proof_layer().attest_score(
            {"key": dim_key, "value": dim_val}, evidence
        )
        attested_dims[dim_key] = attested.get("value", dim_val)

    proof = await get_proof_layer().build_proof_chain(fit_profile, all_rollouts)
    fit_profile["proofChain"] = proof

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

    await log_event(
        match_id, None, "match_finished",
        {
            "overall_score": fit_profile["overallScore"],
            "band": fit_profile["band"],
            "wall_ms": wall_ms,
            "budget_spent_usd": round(budget.spent_usd, 4),
            "n_rollouts": len(all_rollouts),
        },
        db=db,
    )

    logger.info(
        "run_match: match=%s rollouts=%d score=%d band=%s budget=$%.3f wall=%dms",
        match_id, len(all_rollouts), fit_profile["overallScore"],
        fit_profile["band"], budget.spent_usd, wall_ms,
    )
    return fit_profile
