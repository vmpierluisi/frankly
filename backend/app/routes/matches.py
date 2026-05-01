"""Match endpoints. Manager-gated.

Primary match creation happens automatically via background_runner when a
candidate completes intake. The /trigger endpoint is a manual re-run lever.
The /search endpoint has been removed — leaderboard is the primary surface.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models, schemas
from ..auth import require_manager
from ..db import get_session
from ..services.simulation import background_runner

router = APIRouter(
    prefix="/matches",
    tags=["matches"],
    dependencies=[Depends(require_manager)],
)


@router.post("/trigger", response_model=schemas.MatchOut)
def trigger_match(
    payload: schemas.TriggerMatchIn,
    db: Session = Depends(get_session),
) -> schemas.MatchOut:
    """Queue a (re-)simulation for a candidate × company pair.

    Creates a new Match row if none exists, or resets the latest one to pending
    (unless it's already running). Returns immediately; simulation runs in the
    background. Poll GET /companies/{id}/leaderboard to observe status transitions.
    """
    candidate = db.get(models.Candidate, payload.candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate not found")
    company = db.get(models.Company, payload.company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")

    existing = db.execute(
        select(models.Match)
        .where(
            models.Match.candidate_id == payload.candidate_id,
            models.Match.company_id == payload.company_id,
        )
        .order_by(models.Match.created_at.desc())
    ).scalar_one_or_none()

    if existing is not None and existing.status == "running":
        raise HTTPException(status_code=409, detail="Simulation already running for this pair")

    if existing is not None:
        existing.status = "pending"
        existing.error_message = None
        existing.started_at = None
        existing.finished_at = None
        db.commit()
        match = existing
    else:
        match = models.Match(
            candidate_id=candidate.id,
            company_id=company.id,
            status="pending",
            overall_score=0,
            band="",
            band_note="",
            report={},
        )
        db.add(match)
        db.commit()
        db.refresh(match)

    background_runner.schedule(match.id)
    return schemas.MatchOut.model_validate(match)


@router.get("/{match_id}/rollouts", response_model=list[schemas.RolloutSummaryOut])
def list_rollouts(
    match_id: str,
    db: Session = Depends(get_session),
) -> list[schemas.RolloutSummaryOut]:
    match = db.get(models.Match, match_id)
    if match is None:
        raise HTTPException(status_code=404, detail="Match not found")
    rollouts = db.execute(
        select(models.Rollout)
        .where(models.Rollout.match_id == match_id)
        .order_by(models.Rollout.rollout_index)
    ).scalars().all()

    result = []
    for r in rollouts:
        scores = db.execute(
            select(models.RolloutScore).where(models.RolloutScore.rollout_id == r.id)
        ).scalars().all()
        scores_dict = {s.dimension_key: s.score for s in scores if s.score is not None}
        result.append(schemas.RolloutSummaryOut(
            id=r.id,
            match_id=r.match_id,
            scenario_id=r.scenario_id,
            rollout_index=r.rollout_index,
            status=r.status,
            failure_reason=r.failure_reason,
            duration_turns=r.duration_turns,
            headline=r.final_state.get("transcript_summary", ""),
            scores=scores_dict,
            created_at=r.created_at,
        ))
    return result


@router.get("/{match_id}/rollouts/{rollout_id}", response_model=schemas.RolloutDetailOut)
def get_rollout(
    match_id: str,
    rollout_id: str,
    db: Session = Depends(get_session),
) -> schemas.RolloutDetailOut:
    rollout = db.get(models.Rollout, rollout_id)
    if rollout is None or rollout.match_id != match_id:
        raise HTTPException(status_code=404, detail="Rollout not found")
    score_rows = db.execute(
        select(models.RolloutScore).where(models.RolloutScore.rollout_id == rollout_id)
    ).scalars().all()
    return schemas.RolloutDetailOut(
        id=rollout.id,
        match_id=rollout.match_id,
        scenario_id=rollout.scenario_id,
        rollout_index=rollout.rollout_index,
        status=rollout.status,
        failure_reason=rollout.failure_reason,
        duration_turns=rollout.duration_turns,
        transcript=rollout.transcript,
        final_state=rollout.final_state,
        score_rows=[schemas.RolloutScoreOut.model_validate(s) for s in score_rows],
        created_at=rollout.created_at,
    )


@router.get("/{match_id}/baseline", response_model=schemas.BaselineComparisonOut)
def get_baseline(
    match_id: str,
    db: Session = Depends(get_session),
) -> schemas.BaselineComparisonOut:
    row = db.get(models.BaselineComparison, match_id)
    if row is None:
        raise HTTPException(status_code=404, detail="No baseline comparison for this match")
    return schemas.BaselineComparisonOut.model_validate(row)


@router.get("", response_model=list[schemas.MatchOut])
def list_matches(
    candidate_id: str | None = None,
    company_id: str | None = None,
    db: Session = Depends(get_session),
) -> list[schemas.MatchOut]:
    q = db.query(models.Match).order_by(models.Match.created_at.desc())
    if candidate_id:
        q = q.filter(models.Match.candidate_id == candidate_id)
    if company_id:
        q = q.filter(models.Match.company_id == company_id)
    return [schemas.MatchOut.model_validate(m) for m in q.all()]


@router.get("/{match_id}", response_model=schemas.MatchOut)
def get_match(match_id: str, db: Session = Depends(get_session)) -> schemas.MatchOut:
    m = db.get(models.Match, match_id)
    if m is None:
        raise HTTPException(status_code=404, detail="Match not found")
    return schemas.MatchOut.model_validate(m)
