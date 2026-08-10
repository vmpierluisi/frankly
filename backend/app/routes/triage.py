"""Manager Shortlist V7 — triage queue + decisions (optional manual flow).

Manager-gated and feature-flagged behind ``settings.enable_v7``. Writing a
triage decision never notifies the candidate — blind matching / mutual opt-in
is preserved (invariant §11); only /interviews/schedule contacts a candidate.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models, schemas
from ..auth import CurrentUser, require_manager
from ..config import settings
from ..db import get_session
from ..services.comparison_builder import build_triage_queue

router = APIRouter(prefix="/positions", tags=["triage"])


def _require_v7() -> None:
    if not settings.enable_v7:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="V7 not enabled")


@router.get("/{position_id}/queue", response_model=schemas.TriageQueue)
def triage_queue(
    position_id: str,
    db: Session = Depends(get_session),
    user: CurrentUser = Depends(require_manager),
) -> schemas.TriageQueue:
    _require_v7()
    try:
        payload = build_triage_queue(position_id, user.auth_user_id, db)
    except LookupError:
        raise HTTPException(status_code=404, detail="Position not found")
    return schemas.TriageQueue.model_validate(payload)


@router.post("/{position_id}/queue/decision", status_code=status.HTTP_204_NO_CONTENT)
def triage_decide(
    position_id: str,
    payload: schemas.TriageDecisionPayload,
    db: Session = Depends(get_session),
    user: CurrentUser = Depends(require_manager),
) -> None:
    _require_v7()

    position = db.get(models.Position, position_id)
    if position is None:
        raise HTTPException(status_code=404, detail="Position not found")
    candidate = db.get(models.Candidate, payload.candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate not found")

    existing = db.execute(
        select(models.TriageDecision).where(
            models.TriageDecision.manager_id == user.auth_user_id,
            models.TriageDecision.position_id == position_id,
            models.TriageDecision.candidate_id == payload.candidate_id,
        )
    ).scalar_one_or_none()

    # "undecided" clears any stored decision.
    if payload.decision == "undecided":
        if existing is not None:
            db.delete(existing)
            db.commit()
        return None

    if existing is None:
        db.add(
            models.TriageDecision(
                manager_id=user.auth_user_id,
                position_id=position_id,
                candidate_id=payload.candidate_id,
                decision=payload.decision,
            )
        )
    else:
        existing.decision = payload.decision
    db.commit()
    return None
