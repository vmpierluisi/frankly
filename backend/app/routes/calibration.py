"""Calibration loop — Roadmap 2 / PR #5.

Candidate-facing endpoints powering the "How well we know you" loop:

  GET   /calibration            list this candidate's pending + submitted rows
  GET   /calibration/{id}       single row (auth: candidate must own it)
  POST  /calibration/{id}/submit  record answer + bump profile_accuracy
  GET   /calibration/timeline   timeline view shown when the ring is tapped

Sampling (which rollouts become calibration prompts) happens inside the
background runner — see ``services.calibration.sample_after_match``.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..auth import CurrentUser, require_candidate
from ..db import get_session
from ..services import calibration as calibration_svc

router = APIRouter(prefix="/calibration", tags=["calibration"])


def _candidate_for_user(db: Session, user: CurrentUser) -> models.Candidate:
    cand = (
        db.query(models.Candidate)
        .filter(models.Candidate.auth_user_id == user.auth_user_id)
        .first()
    )
    if cand is None:
        raise HTTPException(status_code=404, detail="Candidate row not found for this user")
    return cand


def _serialize(row: models.CalibrationResponse) -> dict:
    # Strip ``is_agent_answer`` from the options — never surface to candidate.
    safe_options = [
        {"text": o.get("text", ""), "skill_level": o.get("skill_level", "")}
        for o in (row.mcq_options or [])
    ]
    return {
        "id": row.id,
        "candidate_id": row.candidate_id,
        "rollout_id": row.rollout_id,
        "scenario_id": row.scenario_id,
        "agent_response_text": row.agent_response_text,
        "mcq_options": safe_options,
        "mode": row.mode,
        "status": row.status,
        "divergence_score": row.divergence_score,
        "candidate_selection_index": row.candidate_selection_index,
        "candidate_free_text": row.candidate_free_text,
        "accuracy_before": row.accuracy_before,
        "accuracy_after": row.accuracy_after,
        "created_at": row.created_at,
        "submitted_at": row.submitted_at,
    }


@router.get("", response_model=list[schemas.CalibrationOut])
def list_my_calibrations(
    user: CurrentUser = Depends(require_candidate),
    db: Session = Depends(get_session),
) -> list[schemas.CalibrationOut]:
    cand = _candidate_for_user(db, user)
    rows = calibration_svc.list_for_candidate(db, cand.id)
    return [schemas.CalibrationOut(**_serialize(r)) for r in rows]


@router.get("/timeline", response_model=schemas.CalibrationTimelineOut)
def my_timeline(
    user: CurrentUser = Depends(require_candidate),
    db: Session = Depends(get_session),
) -> schemas.CalibrationTimelineOut:
    cand = _candidate_for_user(db, user)
    points = calibration_svc.timeline_for_candidate(db, cand)
    return schemas.CalibrationTimelineOut(
        current_accuracy=cand.profile_accuracy_score or 0,
        points=[schemas.CalibrationTimelinePoint(**p) for p in points],
    )


@router.get("/{calibration_id}", response_model=schemas.CalibrationOut)
def get_calibration(
    calibration_id: str,
    user: CurrentUser = Depends(require_candidate),
    db: Session = Depends(get_session),
) -> schemas.CalibrationOut:
    cand = _candidate_for_user(db, user)
    row = db.get(models.CalibrationResponse, calibration_id)
    if row is None or row.candidate_id != cand.id:
        raise HTTPException(status_code=404, detail="Calibration not found")
    return schemas.CalibrationOut(**_serialize(row))


@router.post("/{calibration_id}/submit", response_model=schemas.CalibrationOut)
def submit_calibration(
    calibration_id: str,
    payload: schemas.CalibrationSubmitIn,
    user: CurrentUser = Depends(require_candidate),
    db: Session = Depends(get_session),
) -> schemas.CalibrationOut:
    cand = _candidate_for_user(db, user)
    row = db.get(models.CalibrationResponse, calibration_id)
    if row is None or row.candidate_id != cand.id:
        raise HTTPException(status_code=404, detail="Calibration not found")
    if row.status != "pending":
        raise HTTPException(status_code=409, detail="Calibration already submitted")
    if payload.selection_index is None and not (payload.free_text and payload.free_text.strip()):
        raise HTTPException(
            status_code=400,
            detail="Provide a selection_index, a free_text answer, or both.",
        )
    if payload.selection_index is not None:
        if payload.selection_index < 0 or payload.selection_index >= len(row.mcq_options or []):
            raise HTTPException(status_code=400, detail="selection_index out of range")
    updated = calibration_svc.submit_response(
        db=db,
        calibration=row,
        candidate=cand,
        selection_index=payload.selection_index,
        free_text=payload.free_text,
    )
    return schemas.CalibrationOut(**_serialize(updated))
