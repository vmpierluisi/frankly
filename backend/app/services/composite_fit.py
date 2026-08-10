"""Manager Shortlist V7 — composite fit calculators.

Derives the ``team_fit`` (per-teammate) and ``overall_fit`` (six composite
axes) numbers the V7 radar chart renders. Everything here is *derived at
request time* from existing rollout / judge / match data — no new persistence,
no changes to the simulation output shape (invariant §11).

Every heuristic is tagged ``v0`` — these are honest MVP approximations, not
ground truth. Replace each when a real signal exists (see plan §12 open
questions #1 and #2). All functions degrade gracefully to the match's overall
behaviour score when the finer signal is missing, so they always return a
sensible 0..100 value.
"""
from __future__ import annotations

from statistics import mean
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models

if TYPE_CHECKING:  # pragma: no cover
    from ..models import Match

# Judge dimension that scores persona fidelity, not candidate quality — it must
# never contribute to a fit number.
_FIDELITY_DIM = "persona_fidelity"


def _clamp(v: float) -> int:
    return int(round(max(0.0, min(100.0, v))))


def _rollouts_for_match(match: "Match", db: Session) -> list[models.Rollout]:
    return list(
        db.execute(
            select(models.Rollout).where(models.Rollout.match_id == match.id)
        ).scalars()
    )


def _scores_by_rollout(
    rollout_ids: list[str], db: Session
) -> dict[str, list[models.RolloutScore]]:
    """{rollout_id: [RolloutScore, ...]} for the given rollouts."""
    if not rollout_ids:
        return {}
    grouped: dict[str, list[models.RolloutScore]] = {rid: [] for rid in rollout_ids}
    rows = db.execute(
        select(models.RolloutScore).where(
            models.RolloutScore.rollout_id.in_(rollout_ids)
        )
    ).scalars()
    for s in rows:
        grouped.setdefault(s.rollout_id, []).append(s)
    return grouped


def _rollout_quality(scores: list[models.RolloutScore]) -> float | None:
    """Mean candidate score across a rollout's judged dimensions (0..100).

    Excludes the persona-fidelity dimension and any null scores.
    """
    vals = [
        float(s.score)
        for s in scores
        if s.score is not None and s.dimension_key != _FIDELITY_DIM
    ]
    return mean(vals) if vals else None


def _teammates_for_match(match: "Match") -> list[models.SyntheticTeammate]:
    team = getattr(getattr(match, "position", None), "team", None)
    return list(getattr(team, "teammates", []) or [])


def compute_team_fit(
    match: "Match",
    db: Session | None = None,
    *,
    rollouts: "list[models.Rollout] | None" = None,
    scores_by_rollout: "dict[str, list[models.RolloutScore]] | None" = None,
) -> dict[str, int]:
    """0..100 per synthetic teammate — how productively the candidate worked
    with that teammate across the simulation.

    v0 heuristic: for each teammate, average the candidate's rollout-quality on
    every rollout where that teammate actually spoke (``turn.speaker_id ==
    teammate.id``). Falls back to the position-wide mean rollout-quality when no
    rollout featured a given teammate. A more honest measure is per-turn
    pair-interaction quality, which needs a new judge prompt (plan §12 #2).

    ``rollouts`` / ``scores_by_rollout`` may be prefetched by the caller to
    avoid per-candidate queries (the report builder loads them once for the
    whole request); when omitted they are queried via ``db``.
    """
    teammates = _teammates_for_match(match)
    if not teammates:
        return {}

    if rollouts is None:
        rollouts = _rollouts_for_match(match, db)
    if scores_by_rollout is None:
        scores_by_rollout = _scores_by_rollout([r.id for r in rollouts], db)

    quality_by_rollout: dict[str, float] = {}
    for r in rollouts:
        q = _rollout_quality(scores_by_rollout.get(r.id, []))
        if q is not None:
            quality_by_rollout[r.id] = q

    population_mean = (
        mean(quality_by_rollout.values()) if quality_by_rollout else float(match.overall_score or 0)
    )

    # Which teammates spoke in which rollouts.
    speakers_by_rollout: dict[str, set[str]] = {}
    for r in rollouts:
        speakers_by_rollout[r.id] = {
            (turn or {}).get("speaker_id")
            for turn in (r.transcript or [])
            if (turn or {}).get("speaker_id")
        }

    result: dict[str, int] = {}
    for tm in teammates:
        participated = [
            quality_by_rollout[rid]
            for rid, speakers in speakers_by_rollout.items()
            if tm.id in speakers and rid in quality_by_rollout
        ]
        value = mean(participated) if participated else population_mean
        result[tm.id] = _clamp(value)
    return result


def _dim_mean(report: dict, *keys: str) -> float | None:
    """Mean of the dimensionalFit means for the first of ``keys`` present."""
    dfit = (report or {}).get("dimensionalFit") or {}
    found: list[float] = []
    for k in keys:
        entry = dfit.get(k)
        if entry and entry.get("mean") is not None:
            found.append(float(entry["mean"]))
    return mean(found) if found else None


def _tenure_avg_years(match: "Match") -> float | None:
    """Average tenure (years) across CV experience entries, if available."""
    profile = getattr(getattr(match, "candidate", None), "verified_profile", None)
    experience = getattr(profile, "experience", None) or []
    spans: list[float] = []
    for entry in experience:
        if not isinstance(entry, dict):
            continue
        years = entry.get("duration_years") or entry.get("years")
        if isinstance(years, (int, float)) and years > 0:
            spans.append(float(years))
    return mean(spans) if spans else None


def compute_overall_fit(
    match: "Match",
    db: Session | None = None,
    *,
    rollouts: "list[models.Rollout] | None" = None,
    scores_by_rollout: "dict[str, list[models.RolloutScore]] | None" = None,
    team_fit: dict[str, int] | None = None,
) -> dict[str, int]:
    """Six composite axes, all derived, no new persistence.

    Axes: role_fit, team_chem, memo_culture, conflict_prod, ramp_speed,
    long_cycle. Each degrades to the match overall score when its finer signal
    is unavailable so the radar is always renderable.

    ``rollouts`` / ``scores_by_rollout`` may be prefetched to avoid queries;
    ``team_fit`` may be passed when the caller already computed it (the report
    builder does), avoiding a second team-fit pass.
    """
    report = match.report or {}
    overall = float(match.overall_score or report.get("overallScore") or 0)
    behaviour = float(report.get("behaviourFit", overall) or overall)

    # role_fit — already exists.
    role_fit = overall

    # team_chem — mean of per-teammate fit (reuse the caller's if given).
    if team_fit is None:
        team_fit = compute_team_fit(
            match, db, rollouts=rollouts, scores_by_rollout=scores_by_rollout
        )
    team_values = list(team_fit.values())
    team_chem = mean(team_values) if team_values else behaviour

    # memo_culture — v0: written-dissent + ic-memo-writing signal, else behaviour.
    memo_culture = _dim_mean(
        report, "written_dissent", "writtenDissent", "ic_memo_writing", "icMemoWriting"
    )
    if memo_culture is None:
        memo_culture = behaviour

    # conflict_prod — v0: productive-disagreement intent ratio from rollout
    # transcripts; falls back to low-ego-collab + written-dissent means, then
    # to behaviour. Intent labels are optional, so the ratio path often no-ops.
    conflict_prod = _conflict_productivity(match, db, rollouts=rollouts)
    if conflict_prod is None:
        conflict_prod = _dim_mean(
            report, "low_ego_collaboration", "lowEgoCollaboration", "written_dissent"
        )
    if conflict_prod is None:
        conflict_prod = behaviour

    # ramp_speed — v0: proxy on skills coverage (how ready the candidate is to
    # contribute). Real signal would fold years-of-experience proximity + sector
    # match; skills_fit is the closest available today. Falls back to behaviour.
    ramp_speed = report.get("skillsFit")
    ramp_speed = float(ramp_speed) if ramp_speed is not None else behaviour

    # long_cycle — v0: patience criterion blended with CV tenure average
    # (longer average tenure → more comfort with long feedback cycles).
    patience = _dim_mean(report, "patience", "long_cycle_stamina", "longCycleStamina")
    tenure = _tenure_avg_years(match)
    tenure_score = min(100.0, tenure / 5.0 * 100.0) if tenure is not None else None
    long_cycle_parts = [p for p in (patience, tenure_score) if p is not None]
    long_cycle = mean(long_cycle_parts) if long_cycle_parts else behaviour

    return {
        "role_fit": _clamp(role_fit),
        "team_chem": _clamp(team_chem),
        "memo_culture": _clamp(memo_culture),
        "conflict_prod": _clamp(conflict_prod),
        "ramp_speed": _clamp(ramp_speed),
        "long_cycle": _clamp(long_cycle),
    }


# Intent labels (on RolloutTurn.intent) we treat as productive vs. total
# disagreement. v0 — replace when a dedicated conflict-quality judge exists.
_PRODUCTIVE_INTENTS = {"productive_disagreement", "constructive_challenge", "dissent"}
_DISAGREEMENT_INTENTS = _PRODUCTIVE_INTENTS | {
    "unproductive_disagreement",
    "stonewall",
    "defensive",
    "concede",
}


def _conflict_productivity(
    match: "Match",
    db: Session | None = None,
    *,
    rollouts: "list[models.Rollout] | None" = None,
) -> float | None:
    """(productive disagreement turns / total disagreement turns) * 100.

    Reads the candidate's own turns' ``intent`` labels across all rollouts.
    Returns None when no disagreement intents are present (labels are optional).
    """
    if rollouts is None:
        rollouts = _rollouts_for_match(match, db)
    productive = 0
    total = 0
    for r in rollouts:
        for turn in r.transcript or []:
            if (turn or {}).get("speaker_id") != "candidate":
                continue
            intent = (turn or {}).get("intent") or ""
            if intent in _DISAGREEMENT_INTENTS:
                total += 1
                if intent in _PRODUCTIVE_INTENTS:
                    productive += 1
    if total == 0:
        return None
    return productive / total * 100.0
