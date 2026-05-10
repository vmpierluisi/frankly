"""Interview scheduling routes — Roadmap 2 / PR #4.

Three actor surfaces:

  * Manager: POST /interviews            — propose 1..5 time slots.
  * Candidate: GET /interviews/me        — list interviews (+ vacancy reveal).
  * Candidate: POST /interviews/{id}/{accept|decline|counter} — respond.

Every state transition does three things atomically (best-effort on email):
  1. Update the interview row.
  2. Insert a Notification for the *other* side.
  3. Fire a Resend email to the other side.

The vacancy-reveal rule (candidate sees position name/role/org only after
the invite arrives) is enforced by the simple fact that we expose vacancy
fields only through the candidate's interview list — not through any
``/positions/*`` endpoint accessible to candidates.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models, schemas
from ..auth import CurrentUser, require_candidate, require_manager, require_user
from ..db import get_session
from ..services import email as email_svc

router = APIRouter(prefix="/interviews", tags=["interviews"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _candidate_for_user(db: Session, user: CurrentUser) -> models.Candidate:
    cand = (
        db.query(models.Candidate)
        .filter(models.Candidate.auth_user_id == user.auth_user_id)
        .first()
    )
    if cand is None:
        raise HTTPException(status_code=404, detail="Candidate row not found for this user")
    return cand


def _notify(
    db: Session,
    *,
    user_kind: str,
    candidate_id: str | None,
    recipient_email: str | None,
    type_: str,
    payload: dict,
) -> None:
    db.add(
        models.Notification(
            user_kind=user_kind,
            candidate_id=candidate_id,
            recipient_email=recipient_email,
            type=type_,
            payload=payload,
        )
    )


def _hydrate(interview: models.Interview, candidate: models.Candidate, position: models.Position) -> dict:
    org_name = position.organization.name if position.organization else None
    return {
        "id": interview.id,
        "match_id": interview.match_id,
        "candidate_id": interview.candidate_id,
        "position_id": interview.position_id,
        "recruiter_email": interview.recruiter_email,
        "proposed_slots": interview.proposed_slots or [],
        "selected_slot": interview.selected_slot,
        "counter_slots": interview.counter_slots or [],
        "candidate_message": interview.candidate_message or "",
        "status": interview.status,
        "created_at": interview.created_at,
        "updated_at": interview.updated_at,
        "candidate_display_name": candidate.display_name,
        "candidate_email": candidate.email,
        "position_name": position.name,
        "position_role": position.role,
        "organization_name": org_name,
    }


# ---------------------------------------------------------------------------
# Manager — propose
# ---------------------------------------------------------------------------
@router.post("", response_model=schemas.InterviewOut)
def propose_interview(
    payload: schemas.InterviewProposeIn,
    user: CurrentUser = Depends(require_manager),
    db: Session = Depends(get_session),
) -> schemas.InterviewOut:
    match = db.get(models.Match, payload.match_id)
    if match is None:
        raise HTTPException(status_code=404, detail="Match not found")
    candidate = db.get(models.Candidate, match.candidate_id)
    position = db.get(models.Position, match.position_id)
    if candidate is None or position is None:
        raise HTTPException(status_code=404, detail="Candidate or position missing")

    interview = models.Interview(
        match_id=match.id,
        candidate_id=candidate.id,
        position_id=position.id,
        recruiter_email=user.email,
        proposed_slots=list(payload.proposed_slots),
        status="proposed",
    )
    db.add(interview)
    db.flush()

    _notify(
        db,
        user_kind="candidate",
        candidate_id=candidate.id,
        recipient_email=None,
        type_="interview_invite",
        payload={
            "interview_id": interview.id,
            "position_name": position.name,
            "position_role": position.role,
            "proposed_slots": interview.proposed_slots,
        },
    )
    db.commit()
    db.refresh(interview)

    email_svc.send_interview_invite(
        to=candidate.email or "",
        position_name=position.name,
        role=position.role,
        proposed_slots=interview.proposed_slots,
    )
    return schemas.InterviewOut(**_hydrate(interview, candidate, position))


# ---------------------------------------------------------------------------
# Manager — list (by candidate, or all that this recruiter sent)
# ---------------------------------------------------------------------------
@router.get("", response_model=list[schemas.InterviewOut])
def list_interviews_for_manager(
    candidate_id: str | None = None,
    user: CurrentUser = Depends(require_manager),
    db: Session = Depends(get_session),
) -> list[schemas.InterviewOut]:
    stmt = select(models.Interview).order_by(models.Interview.created_at.desc())
    if candidate_id:
        stmt = stmt.where(models.Interview.candidate_id == candidate_id)
    else:
        stmt = stmt.where(models.Interview.recruiter_email == user.email)
    rows = db.execute(stmt).scalars().all()
    out: list[schemas.InterviewOut] = []
    for iv in rows:
        cand = db.get(models.Candidate, iv.candidate_id)
        pos = db.get(models.Position, iv.position_id)
        if cand is None or pos is None:
            continue
        out.append(schemas.InterviewOut(**_hydrate(iv, cand, pos)))
    return out


# ---------------------------------------------------------------------------
# Candidate — list
# ---------------------------------------------------------------------------
@router.get("/me", response_model=list[schemas.CandidateInterviewOut])
def list_my_interviews(
    user: CurrentUser = Depends(require_candidate),
    db: Session = Depends(get_session),
) -> list[schemas.CandidateInterviewOut]:
    cand = _candidate_for_user(db, user)
    rows = (
        db.execute(
            select(models.Interview)
            .where(models.Interview.candidate_id == cand.id)
            .order_by(models.Interview.created_at.desc())
        )
        .scalars()
        .all()
    )
    out: list[schemas.CandidateInterviewOut] = []
    for iv in rows:
        pos = db.get(models.Position, iv.position_id)
        if pos is None:
            continue
        out.append(schemas.CandidateInterviewOut(**_hydrate(iv, cand, pos)))
    return out


# ---------------------------------------------------------------------------
# Candidate — accept / decline / counter
# ---------------------------------------------------------------------------
def _load_for_candidate(db: Session, interview_id: str, user: CurrentUser) -> tuple[models.Interview, models.Candidate, models.Position]:
    cand = _candidate_for_user(db, user)
    iv = db.get(models.Interview, interview_id)
    if iv is None or iv.candidate_id != cand.id:
        raise HTTPException(status_code=404, detail="Interview not found")
    pos = db.get(models.Position, iv.position_id)
    if pos is None:
        raise HTTPException(status_code=404, detail="Position missing")
    return iv, cand, pos


@router.post("/{interview_id}/accept", response_model=schemas.CandidateInterviewOut)
def accept_interview(
    interview_id: str,
    payload: schemas.InterviewAcceptIn,
    user: CurrentUser = Depends(require_candidate),
    db: Session = Depends(get_session),
) -> schemas.CandidateInterviewOut:
    iv, cand, pos = _load_for_candidate(db, interview_id, user)
    if iv.status not in ("proposed", "rescheduled"):
        raise HTTPException(status_code=409, detail=f"Cannot accept from status={iv.status}")
    # Allow either an originally-proposed slot or one of our own counter slots
    # (in case the recruiter accepts our counter and we then confirm).
    valid_slots = set(iv.proposed_slots or []) | set(iv.counter_slots or [])
    if payload.selected_slot not in valid_slots:
        raise HTTPException(status_code=400, detail="selected_slot is not among proposed slots")
    iv.selected_slot = payload.selected_slot
    iv.status = "accepted"
    iv.candidate_message = payload.message or ""

    _notify(
        db,
        user_kind="manager",
        candidate_id=None,
        recipient_email=iv.recruiter_email,
        type_="interview_accepted",
        payload={
            "interview_id": iv.id,
            "candidate_display_name": cand.display_name,
            "position_name": pos.name,
            "selected_slot": iv.selected_slot,
        },
    )
    db.commit()
    db.refresh(iv)

    email_svc.send_interview_accepted(
        to=iv.recruiter_email,
        candidate_name=cand.display_name or cand.email or "Candidate",
        position_name=pos.name,
        selected_slot=iv.selected_slot or "",
    )
    return schemas.CandidateInterviewOut(**_hydrate(iv, cand, pos))


@router.post("/{interview_id}/decline", response_model=schemas.CandidateInterviewOut)
def decline_interview(
    interview_id: str,
    payload: schemas.InterviewDeclineIn,
    user: CurrentUser = Depends(require_candidate),
    db: Session = Depends(get_session),
) -> schemas.CandidateInterviewOut:
    iv, cand, pos = _load_for_candidate(db, interview_id, user)
    if iv.status not in ("proposed", "rescheduled"):
        raise HTTPException(status_code=409, detail=f"Cannot decline from status={iv.status}")
    iv.status = "declined"
    iv.candidate_message = payload.message or ""

    _notify(
        db,
        user_kind="manager",
        candidate_id=None,
        recipient_email=iv.recruiter_email,
        type_="interview_declined",
        payload={
            "interview_id": iv.id,
            "candidate_display_name": cand.display_name,
            "position_name": pos.name,
            "message": iv.candidate_message,
        },
    )
    db.commit()
    db.refresh(iv)

    email_svc.send_interview_declined(
        to=iv.recruiter_email,
        candidate_name=cand.display_name or cand.email or "Candidate",
        position_name=pos.name,
        message=iv.candidate_message or None,
    )
    return schemas.CandidateInterviewOut(**_hydrate(iv, cand, pos))


@router.post("/{interview_id}/counter", response_model=schemas.CandidateInterviewOut)
def counter_interview(
    interview_id: str,
    payload: schemas.InterviewCounterIn,
    user: CurrentUser = Depends(require_candidate),
    db: Session = Depends(get_session),
) -> schemas.CandidateInterviewOut:
    iv, cand, pos = _load_for_candidate(db, interview_id, user)
    if iv.status not in ("proposed", "rescheduled"):
        raise HTTPException(status_code=409, detail=f"Cannot counter-propose from status={iv.status}")
    iv.counter_slots = list(payload.counter_slots)
    iv.status = "rescheduled"
    iv.candidate_message = payload.message or ""

    _notify(
        db,
        user_kind="manager",
        candidate_id=None,
        recipient_email=iv.recruiter_email,
        type_="interview_counter",
        payload={
            "interview_id": iv.id,
            "candidate_display_name": cand.display_name,
            "position_name": pos.name,
            "counter_slots": iv.counter_slots,
            "message": iv.candidate_message,
        },
    )
    db.commit()
    db.refresh(iv)

    email_svc.send_interview_counter(
        to=iv.recruiter_email,
        candidate_name=cand.display_name or cand.email or "Candidate",
        position_name=pos.name,
        counter_slots=iv.counter_slots,
        message=iv.candidate_message or None,
    )
    return schemas.CandidateInterviewOut(**_hydrate(iv, cand, pos))
