"""Reliability + Fairness audit computations — Roadmap 2 / PR #6.

Recruiter-facing analytics over leaderboard data for a single position.
Stat helpers are intentionally dependency-free (no scipy) so the audit
endpoint can run in the same lightweight FastAPI process as everything
else. Math is plain-Python and small-N safe.

Two top-level entry points:
  * ``reliability_report(db, position_id)``  — five chart families.
  * ``fairness_report(db, position_id)``     — demographic distributions.

A third entry point exposes the same data as flat CSV rows for export.
"""
from __future__ import annotations

import math
from collections import defaultdict
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models


# ---------------------------------------------------------------------------
# Stat primitives — duplicated from admin.py to keep this module self-contained.
# ---------------------------------------------------------------------------
def _mean(xs: Iterable[float]) -> float:
    xs = list(xs)
    return sum(xs) / len(xs) if xs else 0.0


def _std(xs: Iterable[float]) -> float:
    xs = list(xs)
    if len(xs) < 2:
        return 0.0
    m = _mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def _pearson(xs: list[float], ys: list[float]) -> float:
    n = len(xs)
    if n < 2:
        return 0.0
    mx, my = _mean(xs), _mean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if dx == 0 or dy == 0:
        return 0.0
    return num / (dx * dy)


def _linear_fit(xs: list[float], ys: list[float]) -> dict[str, float]:
    """Least-squares slope+intercept. Returns zeros when degenerate."""
    n = len(xs)
    if n < 2:
        return {"slope": 0.0, "intercept": _mean(ys) if ys else 0.0}
    mx, my = _mean(xs), _mean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    denom = sum((x - mx) ** 2 for x in xs)
    slope = num / denom if denom else 0.0
    return {"slope": slope, "intercept": my - slope * mx}


def _histogram(values: list[float], bins: list[float]) -> list[dict[str, Any]]:
    """Bucket values into [bins[i], bins[i+1])."""
    out: list[dict[str, Any]] = []
    for i in range(len(bins) - 1):
        lo, hi = bins[i], bins[i + 1]
        # Last bucket is closed on both ends.
        last = i == len(bins) - 2
        if last:
            count = sum(1 for v in values if lo <= v <= hi)
        else:
            count = sum(1 for v in values if lo <= v < hi)
        out.append({"lo": lo, "hi": hi, "count": count})
    return out


# ---------------------------------------------------------------------------
# Reliability
# ---------------------------------------------------------------------------
def _matches_for_position(db: Session, position_id: str) -> list[models.Match]:
    return (
        db.execute(
            select(models.Match)
            .where(models.Match.position_id == position_id)
            .where(models.Match.status == "succeeded")
        )
        .scalars()
        .all()
    )


def _baseline_by_match(db: Session, match_ids: list[str]) -> dict[str, models.BaselineComparison]:
    if not match_ids:
        return {}
    rows = (
        db.execute(
            select(models.BaselineComparison).where(
                models.BaselineComparison.match_id.in_(match_ids)
            )
        )
        .scalars()
        .all()
    )
    return {b.match_id: b for b in rows}


def _rollouts_for_matches(db: Session, match_ids: list[str]) -> list[models.Rollout]:
    if not match_ids:
        return []
    return (
        db.execute(
            select(models.Rollout).where(models.Rollout.match_id.in_(match_ids))
        )
        .scalars()
        .all()
    )


def _scenario_names(db: Session, scenario_ids: list[str]) -> dict[str, str]:
    if not scenario_ids:
        return {}
    rows = (
        db.execute(
            select(models.MomentOfTruth).where(
                models.MomentOfTruth.id.in_(scenario_ids)
            )
        )
        .scalars()
        .all()
    )
    return {s.id: (getattr(s, "title", None) or s.id) for s in rows}


def _scores_for_rollouts(db: Session, rollout_ids: list[str]) -> list[models.RolloutScore]:
    if not rollout_ids:
        return []
    return (
        db.execute(
            select(models.RolloutScore).where(
                models.RolloutScore.rollout_id.in_(rollout_ids)
            )
        )
        .scalars()
        .all()
    )


def reliability_report(db: Session, position_id: str) -> dict[str, Any]:
    """Build the five chart families plus a per-prompt-version split."""
    matches = _matches_for_position(db, position_id)
    match_ids = [m.id for m in matches]
    baselines = _baseline_by_match(db, match_ids)
    rollouts = _rollouts_for_matches(db, match_ids)
    rollout_ids = [r.id for r in rollouts]
    scores = _scores_for_rollouts(db, rollout_ids)

    # ---- 1. Baseline vs simulation scatter -------------------------------
    scatter_pairs: list[tuple[float, float, str]] = []
    for m in matches:
        b = baselines.get(m.id)
        if b is None or m.overall_score is None:
            continue
        scatter_pairs.append((float(b.overall_score), float(m.overall_score), m.candidate_id))
    xs = [p[0] for p in scatter_pairs]
    ys = [p[1] for p in scatter_pairs]
    pearson = _pearson(xs, ys)
    fit = _linear_fit(xs, ys)
    healthy_band = 0.4 <= pearson <= 0.7

    # ---- 2. |Δ| histogram of |sim − baseline| ----------------------------
    deltas = [abs(x - y) for x, y in zip(xs, ys)]
    delta_hist = _histogram(deltas, bins=[0, 5, 10, 15, 20, 30, 50])

    # ---- 3. Per-criterion judge agreement --------------------------------
    # Treat per-criterion judge confidence as the agreement proxy. Group
    # rollout_scores by criterion and aggregate.
    by_criterion: dict[str, list[float]] = defaultdict(list)
    for s in scores:
        if s.dimension_key == "persona_fidelity" or s.score is None:
            continue
        if s.confidence is not None:
            by_criterion[s.dimension_key].append(float(s.confidence))
    criterion_rows = []
    for key, confs in by_criterion.items():
        mean_conf = _mean(confs)
        criterion_rows.append(
            {
                "key": key,
                "n": len(confs),
                "mean_agreement": round(mean_conf, 3),
                "flag_low": mean_conf < 0.65,
            }
        )
    criterion_rows.sort(key=lambda r: r["mean_agreement"])

    # ---- 4. σ across rollouts per scenario -------------------------------
    rollout_by_id = {r.id: r for r in rollouts}
    by_scenario: dict[str, list[float]] = defaultdict(list)
    scenario_to_position: dict[str, str] = {}
    for s in scores:
        if s.dimension_key == "persona_fidelity" or s.score is None:
            continue
        r = rollout_by_id.get(s.rollout_id)
        if r is None or r.scenario_id is None:
            continue
        by_scenario[r.scenario_id].append(float(s.score))
        # Map scenario → position so the UI can route links.
        match = next((m for m in matches if m.id == r.match_id), None)
        if match is not None:
            scenario_to_position[r.scenario_id] = match.position_id
    scenario_names = _scenario_names(db, list(by_scenario.keys()))
    scenario_rows = []
    for sid, vals in by_scenario.items():
        sigma = _std(vals)
        scenario_rows.append(
            {
                "scenario_id": sid,
                "scenario_name": scenario_names.get(sid) or sid,
                "position_id": scenario_to_position.get(sid),
                "n": len(vals),
                "sigma": round(sigma, 2),
                "flag_high": sigma > 12,
            }
        )
    scenario_rows.sort(key=lambda r: -r["sigma"])

    # ---- 5. Persona fidelity stats ---------------------------------------
    fidelity_scores = [
        float(s.score) for s in scores
        if s.dimension_key == "persona_fidelity" and s.score is not None
    ]
    fidelity_hist = _histogram(fidelity_scores, bins=[0, 20, 40, 60, 80, 100])
    superseded = sum(1 for r in rollouts if r.status == "superseded")
    fidelity_block = {
        "n": len(fidelity_scores),
        "mean": round(_mean(fidelity_scores), 1) if fidelity_scores else None,
        "low_count": sum(1 for v in fidelity_scores if v < 60),
        "retry_rate": round(superseded / len(rollouts), 3) if rollouts else None,
        "histogram": fidelity_hist,
    }

    # ---- 6. Prompt-version split -----------------------------------------
    pv_buckets: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"rollouts": 0, "fidelity": [], "deltas": []}
    )
    for r in rollouts:
        pv_buckets[r.prompt_version or "legacy"]["rollouts"] += 1
    rollout_match: dict[str, str] = {r.id: r.match_id for r in rollouts}
    match_pv: dict[str, str] = {}
    for r in rollouts:
        match_pv[r.match_id] = r.prompt_version or "legacy"
    for s in scores:
        if s.dimension_key == "persona_fidelity" and s.score is not None:
            pv = (s.prompt_version or "legacy")
            pv_buckets[pv]["fidelity"].append(float(s.score))
    for m in matches:
        b = baselines.get(m.id)
        if b is None or m.overall_score is None:
            continue
        pv = match_pv.get(m.id, "legacy")
        pv_buckets[pv]["deltas"].append(abs(float(b.overall_score) - float(m.overall_score)))

    pv_rows = []
    for pv, bucket in pv_buckets.items():
        pv_rows.append(
            {
                "prompt_version": pv,
                "rollouts": bucket["rollouts"],
                "fidelity_mean": round(_mean(bucket["fidelity"]), 1) if bucket["fidelity"] else None,
                "delta_mean": round(_mean(bucket["deltas"]), 1) if bucket["deltas"] else None,
            }
        )
    pv_rows.sort(key=lambda r: r["prompt_version"])

    return {
        "position_id": position_id,
        "n_matches": len(matches),
        "n_rollouts": len(rollouts),
        "scatter": {
            "points": [
                {"baseline": p[0], "sim": p[1], "candidate_id": p[2]} for p in scatter_pairs
            ],
            "pearson": round(pearson, 3),
            "healthy_band": healthy_band,
            "regression": {
                "slope": round(fit["slope"], 3),
                "intercept": round(fit["intercept"], 3),
            },
        },
        "delta_histogram": delta_hist,
        "criteria": criterion_rows,
        "scenarios": scenario_rows,
        "fidelity": fidelity_block,
        "by_prompt_version": pv_rows,
    }


# ---------------------------------------------------------------------------
# Fairness
# ---------------------------------------------------------------------------
DEMO_DIMENSIONS = ("gender", "age_band", "education_tier")


# ---------------------------------------------------------------------------
# Multi-position scoping helpers (overview tab — Roadmap 2 / PR #6 follow-up)
# ---------------------------------------------------------------------------
def positions_in_scope(db: Session, scope: str) -> list[models.Position]:
    """Return positions whose org has the audit toggle on, filtered by scope.

    ``scope`` is one of:
      * "all"    — every audit-enabled position.
      * "open"   — only ``is_open=True`` positions.
      * "closed" — only ``is_open=False`` positions.
    """
    if scope not in ("all", "open", "closed"):
        return []
    q = (
        select(models.Position)
        .join(models.Organization, models.Organization.id == models.Position.organization_id)
        .where(models.Organization.reliability_audit_enabled.is_(True))
    )
    if scope == "open":
        q = q.where(models.Position.is_open.is_(True))
    elif scope == "closed":
        q = q.where(models.Position.is_open.is_(False))
    return db.execute(q).scalars().all()


def reliability_overview(db: Session, scope: str) -> dict[str, Any]:
    """Aggregate the same five chart families across every position in
    scope. Scatter + delta histogram + fidelity histogram are summed into
    a single cloud; per-criterion rows are weighted-averaged; per-scenario
    rows are kept individual (each scenario has a clear identity)."""
    positions = positions_in_scope(db, scope)
    if not positions:
        return _empty_overview(scope)

    per_pos = [reliability_report(db, p.id) for p in positions]

    # Scatter — flatten all points and recompute pearson + fit.
    all_points = []
    for r in per_pos:
        all_points.extend(r["scatter"]["points"])
    xs = [p["baseline"] for p in all_points]
    ys = [p["sim"] for p in all_points]
    pearson = _pearson(xs, ys)
    fit = _linear_fit(xs, ys)

    # Delta histogram — sum bin counts (all reports use the same bin edges).
    delta_bins = _zip_bins([r["delta_histogram"] for r in per_pos])
    fidelity_bins = _zip_bins([r["fidelity"]["histogram"] for r in per_pos])

    # Criterion rows — weighted average by n.
    crit_agg: dict[str, dict[str, float]] = defaultdict(lambda: {"n": 0, "weighted": 0.0})
    for r in per_pos:
        for row in r["criteria"]:
            n = row["n"] or 0
            crit_agg[row["key"]]["n"] += n
            crit_agg[row["key"]]["weighted"] += n * (row["mean_agreement"] or 0.0)
    criterion_rows = []
    for key, agg in crit_agg.items():
        n = agg["n"]
        mean = round(agg["weighted"] / n, 3) if n else 0.0
        criterion_rows.append(
            {"key": key, "n": n, "mean_agreement": mean, "flag_low": mean < 0.65}
        )
    criterion_rows.sort(key=lambda r: r["mean_agreement"])

    # Scenario rows — kept per scenario (already tagged with position_id).
    scenario_rows: list[dict[str, Any]] = []
    for r in per_pos:
        scenario_rows.extend(r["scenarios"])
    scenario_rows.sort(key=lambda r: -r["sigma"])

    # Fidelity stats — recompute mean/low/retry-rate from totals.
    fid_n = sum(r["fidelity"]["n"] for r in per_pos)
    fid_mean_num = sum(
        (r["fidelity"]["mean"] or 0.0) * (r["fidelity"]["n"] or 0) for r in per_pos
    )
    fid_low = sum(r["fidelity"]["low_count"] for r in per_pos)
    # retry_rate is per-position; aggregate as rollout-weighted mean.
    retry_num = 0.0
    rollout_total = 0
    for r in per_pos:
        rr = r["fidelity"]["retry_rate"]
        n_r = r["n_rollouts"] or 0
        if rr is not None:
            retry_num += rr * n_r
            rollout_total += n_r
    fidelity_block = {
        "n": fid_n,
        "mean": round(fid_mean_num / fid_n, 1) if fid_n else None,
        "low_count": fid_low,
        "retry_rate": round(retry_num / rollout_total, 3) if rollout_total else None,
        "histogram": fidelity_bins,
    }

    # Prompt-version split — weighted means.
    pv_agg: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"rollouts": 0, "fid_n": 0, "fid_sum": 0.0, "delta_n": 0, "delta_sum": 0.0}
    )
    for r in per_pos:
        for row in r["by_prompt_version"]:
            pv = row["prompt_version"]
            pv_agg[pv]["rollouts"] += row["rollouts"] or 0
            if row["fidelity_mean"] is not None:
                # Without raw n per pv we approximate; the per-pos query already
                # uses n via fidelity_block — here we treat each pos as one obs.
                pv_agg[pv]["fid_n"] += 1
                pv_agg[pv]["fid_sum"] += row["fidelity_mean"]
            if row["delta_mean"] is not None:
                pv_agg[pv]["delta_n"] += 1
                pv_agg[pv]["delta_sum"] += row["delta_mean"]
    pv_rows = []
    for pv, agg in pv_agg.items():
        pv_rows.append(
            {
                "prompt_version": pv,
                "rollouts": agg["rollouts"],
                "fidelity_mean": round(agg["fid_sum"] / agg["fid_n"], 1) if agg["fid_n"] else None,
                "delta_mean": round(agg["delta_sum"] / agg["delta_n"], 1) if agg["delta_n"] else None,
            }
        )
    pv_rows.sort(key=lambda r: r["prompt_version"])

    return {
        "scope": scope,
        "n_positions": len(positions),
        "n_matches": sum(r["n_matches"] for r in per_pos),
        "n_rollouts": sum(r["n_rollouts"] for r in per_pos),
        "scatter": {
            "points": all_points,
            "pearson": round(pearson, 3),
            "healthy_band": 0.4 <= pearson <= 0.7,
            "regression": {
                "slope": round(fit["slope"], 3),
                "intercept": round(fit["intercept"], 3),
            },
        },
        "delta_histogram": delta_bins,
        "criteria": criterion_rows,
        "scenarios": scenario_rows,
        "fidelity": fidelity_block,
        "by_prompt_version": pv_rows,
    }


def fairness_overview(db: Session, scope: str) -> dict[str, Any]:
    """Same fairness report computed across all candidates matched against
    any in-scope position. Demographics are read off the candidate, not
    duplicated per match — so duplicate candidates across positions still
    weight by total match count."""
    positions = positions_in_scope(db, scope)
    if not positions:
        return {"scope": scope, "n_positions": 0, "n_matches": 0, "dimensions": []}

    pos_ids = [p.id for p in positions]
    matches = (
        db.execute(
            select(models.Match)
            .where(models.Match.position_id.in_(pos_ids))
            .where(models.Match.status == "succeeded")
        )
        .scalars()
        .all()
    )
    cand_ids = list({m.candidate_id for m in matches})
    if not cand_ids:
        return {
            "scope": scope,
            "n_positions": len(positions),
            "n_matches": 0,
            "dimensions": [],
        }

    cands = (
        db.execute(
            select(models.Candidate).where(models.Candidate.id.in_(cand_ids))
        )
        .scalars()
        .all()
    )
    demo_by_cand = {c.id: (c.demographics or {}) for c in cands}
    dim_rows = []
    for dim in DEMO_DIMENSIONS:
        groups: dict[str, list[float]] = defaultdict(list)
        for m in matches:
            if m.overall_score is None:
                continue
            label = _bucket_label((demo_by_cand.get(m.candidate_id) or {}).get(dim))
            groups[label].append(float(m.overall_score))

        group_rows = []
        for label, vals in groups.items():
            group_rows.append(
                {
                    "label": label,
                    "n": len(vals),
                    "mean_score": round(_mean(vals), 1) if vals else None,
                    "selection_rate": round(
                        sum(1 for v in vals if v >= 60) / len(vals), 3
                    ) if vals else None,
                }
            )
        group_rows.sort(key=lambda r: r["label"])

        disclosed = [
            g for g in group_rows
            if g["label"] != "(not disclosed)" and g["mean_score"] is not None
        ]
        parity_gap = (
            round(max(g["mean_score"] for g in disclosed) - min(g["mean_score"] for g in disclosed), 1)
            if len(disclosed) >= 2 else None
        )
        rates = [g["selection_rate"] for g in disclosed if g["selection_rate"] is not None]
        disparate_impact = (
            round(min(rates) / max(rates), 3)
            if len(rates) >= 2 and max(rates) > 0 else None
        )
        dim_rows.append(
            {
                "dimension": dim,
                "groups": group_rows,
                "parity_gap": parity_gap,
                "disparate_impact": disparate_impact,
                "flag_disparate_impact": (
                    disparate_impact is not None and disparate_impact < 0.8
                ),
            }
        )

    return {
        "scope": scope,
        "n_positions": len(positions),
        "n_matches": len(matches),
        "n_candidates": len(cand_ids),
        "dimensions": dim_rows,
    }


def export_rows_scoped(db: Session, scope: str) -> list[dict[str, Any]]:
    """Flat per-match audit rows across every in-scope position. Adds a
    ``position_name`` column so a single export reads cleanly even when
    it spans dozens of vacancies."""
    positions = positions_in_scope(db, scope)
    pos_name_by_id = {p.id: p.name for p in positions}
    rows: list[dict[str, Any]] = []
    for p in positions:
        for r in export_rows(db, p.id):
            rows.append({**r, "position_name": pos_name_by_id.get(p.id, "")})
    return rows


def _zip_bins(reports: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """Sum counts across reports that share the same bin edges. Reports
    must all be non-empty and same-length — they are because every call
    uses the same bin definition in this module."""
    if not reports:
        return []
    first = reports[0]
    out = [{"lo": b["lo"], "hi": b["hi"], "count": 0} for b in first]
    for rep in reports:
        for i, b in enumerate(rep):
            if i < len(out):
                out[i]["count"] += b["count"]
    return out


def _empty_overview(scope: str) -> dict[str, Any]:
    return {
        "scope": scope,
        "n_positions": 0,
        "n_matches": 0,
        "n_rollouts": 0,
        "scatter": {
            "points": [],
            "pearson": 0.0,
            "healthy_band": False,
            "regression": {"slope": 0.0, "intercept": 0.0},
        },
        "delta_histogram": [],
        "criteria": [],
        "scenarios": [],
        "fidelity": {
            "n": 0,
            "mean": None,
            "low_count": 0,
            "retry_rate": None,
            "histogram": [],
        },
        "by_prompt_version": [],
    }


def _bucket_label(value: Any) -> str:
    if value is None or value == "":
        return "(not disclosed)"
    return str(value)


def fairness_report(db: Session, position_id: str) -> dict[str, Any]:
    matches = _matches_for_position(db, position_id)
    cand_ids = list({m.candidate_id for m in matches})
    if not cand_ids:
        return {"position_id": position_id, "n_matches": 0, "dimensions": []}

    cands = (
        db.execute(
            select(models.Candidate).where(models.Candidate.id.in_(cand_ids))
        )
        .scalars()
        .all()
    )
    demo_by_cand = {c.id: (c.demographics or {}) for c in cands}
    score_by_cand: dict[str, list[float]] = defaultdict(list)
    for m in matches:
        if m.overall_score is None:
            continue
        score_by_cand[m.candidate_id].append(float(m.overall_score))

    dim_rows = []
    for dim in DEMO_DIMENSIONS:
        groups: dict[str, list[float]] = defaultdict(list)
        for cid, scores in score_by_cand.items():
            label = _bucket_label((demo_by_cand.get(cid) or {}).get(dim))
            groups[label].extend(scores)

        # Aggregate per group.
        group_rows = []
        for label, vals in groups.items():
            group_rows.append(
                {
                    "label": label,
                    "n": len(vals),
                    "mean_score": round(_mean(vals), 1) if vals else None,
                    "selection_rate": round(
                        sum(1 for v in vals if v >= 60) / len(vals), 3
                    ) if vals else None,
                }
            )
        group_rows.sort(key=lambda r: r["label"])

        # Statistical parity gap = max mean - min mean across disclosed groups.
        disclosed = [g for g in group_rows if g["label"] != "(not disclosed)" and g["mean_score"] is not None]
        if len(disclosed) >= 2:
            means = [g["mean_score"] for g in disclosed]
            parity_gap = round(max(means) - min(means), 1)
        else:
            parity_gap = None

        # Disparate-impact ratio = min selection rate / max selection rate.
        selection_rates = [g["selection_rate"] for g in disclosed if g["selection_rate"] is not None]
        if len(selection_rates) >= 2 and max(selection_rates) > 0:
            disparate_impact = round(min(selection_rates) / max(selection_rates), 3)
        else:
            disparate_impact = None

        dim_rows.append(
            {
                "dimension": dim,
                "groups": group_rows,
                "parity_gap": parity_gap,
                "disparate_impact": disparate_impact,
                # The four-fifths heuristic — flag when DI < 0.8.
                "flag_disparate_impact": (
                    disparate_impact is not None and disparate_impact < 0.8
                ),
            }
        )

    return {
        "position_id": position_id,
        "n_matches": len(matches),
        "n_candidates": len(cand_ids),
        "dimensions": dim_rows,
    }


# ---------------------------------------------------------------------------
# CSV export (defensible audit log)
# ---------------------------------------------------------------------------
def export_rows(db: Session, position_id: str) -> list[dict[str, Any]]:
    """Flat per-match audit rows for the CSV export. Demographics are
    included verbatim (with empty strings for "not disclosed") so the
    exported report is genuinely auditable.
    """
    matches = _matches_for_position(db, position_id)
    if not matches:
        return []
    cand_ids = list({m.candidate_id for m in matches})
    cands = {
        c.id: c
        for c in (
            db.execute(
                select(models.Candidate).where(models.Candidate.id.in_(cand_ids))
            )
            .scalars()
            .all()
        )
    }
    baselines = _baseline_by_match(db, [m.id for m in matches])

    rows = []
    for m in matches:
        demo = (cands.get(m.candidate_id).demographics if cands.get(m.candidate_id) else None) or {}
        b = baselines.get(m.id)
        rows.append(
            {
                "match_id": m.id,
                "candidate_id": m.candidate_id,
                "position_id": m.position_id,
                "sim_score": m.overall_score,
                "baseline_score": b.overall_score if b else None,
                "delta": (
                    abs(int(m.overall_score) - int(b.overall_score))
                    if b and m.overall_score is not None
                    else None
                ),
                "band": m.band or "",
                "gender": demo.get("gender") or "",
                "age_band": demo.get("age_band") or "",
                "education_tier": demo.get("education_tier") or "",
                "finished_at": m.finished_at.isoformat() if m.finished_at else "",
            }
        )
    return rows
