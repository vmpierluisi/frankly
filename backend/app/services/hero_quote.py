"""Manager Shortlist V7 — hero-quote picker.

Selects the single most-defining simulated turn per match for the triage /
signal card. Rule-based (no LLM call) — the highest-weighted, highest-impact
evidence turn. Good enough for v7; an LLM-picked "story" quote is deferred
(plan §12 #4).

Returns a plain dict matching the ``HeroQuote`` schema.
"""
from __future__ import annotations

from statistics import median
from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models

if TYPE_CHECKING:  # pragma: no cover
    from ..models import Match

_FIDELITY_DIM = "persona_fidelity"
_MIN_CONFIDENCE = 0.7


def _empty_quote() -> dict[str, Any]:
    return {"text": "", "scenario_id": "", "to_teammate_id": None, "dimensions": []}


def pick_hero_quote(
    match: "Match",
    db: Session | None = None,
    *,
    rollouts: "list[models.Rollout] | None" = None,
    scores: "list[models.RolloutScore] | None" = None,
) -> dict[str, Any]:
    """Pick the candidate's most signature simulated utterance.

    Algorithm:
      1. Consider RolloutScores with confidence >= 0.7 (drop the persona-fidelity
         dimension). Each contributes its top-weighted evidence turn, where
         weight = criterion weight * judge confidence.
      2. Among those, prefer the turn whose dimension score is furthest above
         the population median for that dimension — the most "signature" moment.
      3. Return the candidate's utterance + scenario + the teammate they were
         responding to + the dimensions that turn fed.

    ``rollouts`` / ``scores`` may be prefetched by the caller to avoid queries;
    when omitted they are loaded via ``db``. Degrades to an empty quote when the
    match has no usable scored evidence.
    """
    if rollouts is None:
        rollouts = list(
            db.execute(
                select(models.Rollout).where(models.Rollout.match_id == match.id)
            ).scalars()
        )
    if not rollouts:
        return _empty_quote()
    rollout_by_id = {r.id: r for r in rollouts}

    if scores is None:
        scores = list(
            db.execute(
                select(models.RolloutScore).where(
                    models.RolloutScore.rollout_id.in_([r.id for r in rollouts])
                )
            ).scalars()
        )
    scores = [
        s
        for s in scores
        if s.dimension_key != _FIDELITY_DIM
        and s.score is not None
        and (s.confidence or 0.0) >= _MIN_CONFIDENCE
        and (s.evidence_turns or [])
    ]
    if not scores:
        return _empty_quote()

    # Criterion weights (for the impact term) keyed by criterion key.
    weight_by_key: dict[str, float] = {
        c.key: float(c.weight or 0.0)
        for c in getattr(getattr(match, "position", None), "criteria", []) or []
    }

    # Population median per dimension across this match's scores (for "signature").
    values_by_dim: dict[str, list[float]] = {}
    for s in scores:
        values_by_dim.setdefault(s.dimension_key, []).append(float(s.score))
    median_by_dim = {k: median(v) for k, v in values_by_dim.items()}

    best = None
    best_rank: tuple[float, float] = (float("-inf"), float("-inf"))
    for s in scores:
        weight = weight_by_key.get(s.dimension_key, 0.0)
        impact = (weight or 1.0) * float(s.confidence or 0.0)
        signature = float(s.score) - median_by_dim.get(s.dimension_key, float(s.score))
        rank = (signature, impact)
        if rank > best_rank:
            best_rank = rank
            best = s

    if best is None:
        return _empty_quote()

    rollout = rollout_by_id.get(best.rollout_id)
    turn_index = (best.evidence_turns or [None])[0]
    text, to_teammate_id = _resolve_turn(rollout, turn_index)

    # Dimensions this turn fed: every scored dimension that cites this turn.
    dimensions = sorted(
        {
            s.dimension_key
            for s in scores
            if turn_index in (s.evidence_turns or [])
        }
    )
    if best.dimension_key not in dimensions:
        dimensions.insert(0, best.dimension_key)

    return {
        "text": text,
        "scenario_id": (rollout.scenario_id if rollout else None) or "",
        "to_teammate_id": to_teammate_id,
        "dimensions": dimensions,
    }


def _resolve_turn(
    rollout: "models.Rollout | None", turn_index: int | None
) -> tuple[str, str | None]:
    """Return (candidate utterance text, teammate id they replied to).

    The teammate replied-to is the last non-candidate speaker before the
    candidate's turn.
    """
    if rollout is None or turn_index is None:
        return "", None
    transcript = rollout.transcript or []

    # Locate the turn by its ``turn`` field, falling back to list index.
    target = None
    for t in transcript:
        if (t or {}).get("turn") == turn_index:
            target = t
            break
    if target is None and 0 <= turn_index < len(transcript):
        target = transcript[turn_index]
    if target is None:
        return "", None

    text = (target or {}).get("content", "") or ""

    to_teammate_id = None
    idx = transcript.index(target)
    for prev in reversed(transcript[:idx]):
        speaker = (prev or {}).get("speaker_id")
        if speaker and speaker != "candidate":
            to_teammate_id = speaker
            break
    return text, to_teammate_id
