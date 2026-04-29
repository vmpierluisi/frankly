"""Fit-profile aggregator — combines K rollouts × N scenarios into FitProfile v2.

MiroFish lineage: corresponds to MiroFish's FitAggregator.
Phase 4C: aggregate_fit_profile() produces the Appendix B.8 shape and is the
source of truth for Match.report in v2 matches.

Public API:
  aggregate_fit_profile(rollouts, scores, criteria, *, baseline_report,
                        audit_extra) -> dict
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from ...models import Rollout, RolloutScore


# Band thresholds — shared with baseline_matcher for consistency.
def _band_for(score: float) -> tuple[str, str]:
    if score >= 75:
        return "Strong fit", "Recommend surfacing to hiring manager for mutual opt-in."
    if score >= 60:
        return "Plausible fit", "Worth a conversation; specific tensions worth probing in interview."
    if score >= 45:
        return "Edge case", "Environmental fit is uncertain. Not recommended without additional signal."
    return "Low fit", "Candidate strengths likely lie in structurally different environments."


def aggregate_fit_profile(
    rollouts: "list[Rollout]",
    scores: "list[RolloutScore]",
    criteria: list[dict[str, Any]],
    *,
    match_id: str = "",
    company_id: str = "",
    company_name: str = "",
    role: str = "",
    baseline_report: dict[str, Any] | None = None,
    audit_extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Aggregate rollout scores into a FitProfile v2 dict.

    Returns the full Match.report payload. Legacy fields are included for
    backward-compat with FitReport.jsx; v2 fields are layered on top.

    Args:
        rollouts:   Rollout ORM objects (already scored).
        scores:     All RolloutScore rows for those rollouts.
        criteria:   Company criteria dicts with keys: key, label, description, weight.
        baseline_report: Output of baseline_matcher.run_match (may be None).
        audit_extra: Additional keys merged into auditTrailV2.
    """
    criteria_by_key = {c["key"]: c for c in criteria}
    weights = {c["key"]: float(c.get("weight", 0.0)) for c in criteria}
    total_weight = sum(weights.values()) or 1.0

    # Index scores by rollout_id → dim_key → RolloutScore
    scores_by_rollout: dict[str, dict[str, Any]] = {}
    for s in scores:
        scores_by_rollout.setdefault(s.rollout_id, {})[s.dimension_key] = s

    # -----------------------------------------------------------------------
    # Per-dimension stats across all rollouts
    # -----------------------------------------------------------------------
    dim_values: dict[str, list[float]] = {c["key"]: [] for c in criteria}
    dim_confidences: dict[str, list[float]] = {c["key"]: [] for c in criteria}

    rollout_by_id = {r.id: r for r in rollouts}

    for rollout in rollouts:
        if rollout.status not in ("completed", "aborted"):
            continue
        dim_scores = scores_by_rollout.get(rollout.id, {})
        for key in dim_values:
            s = dim_scores.get(key)
            if s is not None and s.score is not None:
                dim_values[key].append(float(s.score))
                dim_confidences[key].append(float(s.confidence or 0.0))

    dimensional_fit: dict[str, dict[str, Any]] = {}
    for key, values in dim_values.items():
        n = len(values)
        if n == 0:
            dimensional_fit[key] = {"mean": None, "std": None, "n": 0, "judgeAgreement": None}
            continue
        mean = sum(values) / n
        std = math.sqrt(sum((v - mean) ** 2 for v in values) / n) if n > 1 else 0.0
        confs = dim_confidences[key]
        judge_agreement = sum(confs) / len(confs) if confs else 0.0
        dimensional_fit[key] = {
            "mean": round(mean, 1),
            "std": round(std, 1),
            "n": n,
            "judgeAgreement": round(judge_agreement, 3),
        }

    # -----------------------------------------------------------------------
    # Overall score — weighted mean of per-dimension means
    # -----------------------------------------------------------------------
    weighted_sum = 0.0
    for key, df in dimensional_fit.items():
        mean = df.get("mean")
        if mean is not None:
            weighted_sum += mean * weights.get(key, 0.0)
    overall = int(round(max(0.0, min(100.0, weighted_sum / total_weight))))
    band, band_note = _band_for(overall)

    # -----------------------------------------------------------------------
    # Legacy criterionScores — use dimensional means for backward-compat
    # -----------------------------------------------------------------------
    criterion_scores: dict[str, dict[str, Any]] = {}
    for key, df in dimensional_fit.items():
        mean = df.get("mean")
        crit = criteria_by_key.get(key, {})
        # Use the first non-null justification from scores for this dim
        justification = ""
        for rollout in rollouts:
            s = scores_by_rollout.get(rollout.id, {}).get(key)
            if s and s.justification:
                justification = s.justification
                break
        criterion_scores[key] = {
            "score": int(round(mean)) if mean is not None else 0,
            "justification": justification or f"Aggregated from {df['n']} simulation rollouts.",
        }

    # -----------------------------------------------------------------------
    # Rollout summaries
    # -----------------------------------------------------------------------
    rollout_summaries = []
    for rollout in sorted(rollouts, key=lambda r: r.rollout_index):
        dim_scores = scores_by_rollout.get(rollout.id, {})
        per_dim_scores = {
            key: s.score
            for key, s in dim_scores.items()
            if s.score is not None
        }
        headline = (rollout.final_state or {}).get("transcript_summary", "")
        rollout_summaries.append({
            "rolloutId": rollout.id,
            "scenarioId": rollout.scenario_id or "",
            "scenarioTitle": (rollout.final_state or {}).get("scenario_title", ""),
            "kIndex": rollout.rollout_index,
            "headline": headline,
            "scores": per_dim_scores,
        })

    # -----------------------------------------------------------------------
    # Confidence signals
    # -----------------------------------------------------------------------
    per_criterion_std = {
        key: df["std"] for key, df in dimensional_fit.items() if df["std"] is not None
    }
    stds = [v for v in per_criterion_std.values() if v is not None]
    overall_std = round(sum(stds) / len(stds), 2) if stds else 0.0
    min_n = min((df["n"] for df in dimensional_fit.values()), default=0)
    agreements = [df["judgeAgreement"] for df in dimensional_fit.values() if df["judgeAgreement"] is not None]
    judge_agreement_mean = round(sum(agreements) / len(agreements), 3) if agreements else 0.0

    confidence_signals = {
        "overallStd": overall_std,
        "perCriterionStd": per_criterion_std,
        "minNRollouts": min_n,
        "judgeAgreementMean": judge_agreement_mean,
    }

    # -----------------------------------------------------------------------
    # Baseline comparison
    # -----------------------------------------------------------------------
    baseline_comparison: dict[str, Any] | None = None
    if baseline_report:
        baseline_criterion = baseline_report.get("criterionScores", {})
        delta_vs_sim: dict[str, Any] = {}
        for key in criteria_by_key:
            sim_mean = dimensional_fit.get(key, {}).get("mean")
            base_score = baseline_criterion.get(key, {}).get("score")
            if sim_mean is not None and base_score is not None:
                delta_vs_sim[key] = round(sim_mean - base_score, 1)

        delta_lines = []
        for key, delta in sorted(delta_vs_sim.items(), key=lambda kv: abs(kv[1]), reverse=True)[:3]:
            label = criteria_by_key.get(key, {}).get("label", key)
            sign = "+" if delta >= 0 else ""
            delta_lines.append(f"Sim {sign}{delta:+.0f} on {label}")
        robustness_summary = "; ".join(delta_lines) if delta_lines else "No significant delta."

        baseline_comparison = {
            "overallScore": baseline_report.get("overallScore", 0),
            "perCriterion": baseline_criterion,
            "deltaVsSim": delta_vs_sim,
            "robustnessSummary": robustness_summary,
        }

    # -----------------------------------------------------------------------
    # Audit trail v2
    # -----------------------------------------------------------------------
    audit_trail_v2: dict[str, Any] = {
        "personaAggregatorVersion": "v0.1",
        "judgeModel": "judge-v1",
        "judgeCount": 2,
        "kPerScenario": len(rollouts),
        "scenariosRun": len({r.scenario_id for r in rollouts if r.scenario_id}),
        "proofLayer": "null",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if audit_extra:
        audit_trail_v2.update(audit_extra)

    # -----------------------------------------------------------------------
    # Assemble final profile (additive on legacy shape)
    # -----------------------------------------------------------------------
    profile: dict[str, Any] = {
        # Legacy fields
        "matchId": match_id,
        "companyId": company_id,
        "companyName": company_name,
        "role": role,
        "overallScore": overall,
        "band": band,
        "bandNote": band_note,
        "criterionScores": criterion_scores,
        "inconsistencyFlags": [],
        "auditTrail": {
            "model": "simulation-pipeline-v1",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "note": "v2 report from simulation pipeline. Legacy fields preserved for backward compat.",
        },
        # v2 fields
        "version": "v2",
        "dimensionalFit": dimensional_fit,
        "rolloutSummaries": rollout_summaries,
        "confidenceSignals": confidence_signals,
        "auditTrailV2": audit_trail_v2,
    }
    if baseline_comparison is not None:
        profile["baselineComparison"] = baseline_comparison

    return profile
