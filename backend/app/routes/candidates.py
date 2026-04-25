"""Candidate intake + profile + list.

Intake is public (no manager auth). Profile lookup is by UUID — possession
of the UUID is sufficient, which is acceptable at v0 given the localStorage
key model. Listing candidates is manager-gated.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import models, schemas
from ..auth import require_manager
from ..db import get_session
from ..services.persona import synthesize_persona
from ..seed_data import BFI10, SJTS

router = APIRouter(prefix="/candidates", tags=["candidates"])


@router.get("/instruments", response_model=schemas.Instruments)
def get_instruments() -> schemas.Instruments:
    """Served to the quiz UI. Omits SJT signal weights."""
    return schemas.Instruments(
        bfi=[schemas.BFIItem(**item) for item in BFI10],
        sjts=[
            schemas.SJT(
                id=s["id"],
                scenario=s["scenario"],
                question=s["question"],
                options=[schemas.SJTOption(id=o["id"], text=o["text"]) for o in s["options"]],
            )
            for s in SJTS
        ],
    )


@router.post("", response_model=schemas.CandidateOut, status_code=status.HTTP_201_CREATED)
def create_candidate(
    payload: schemas.CandidateIntakeIn,
    db: Session = Depends(get_session),
) -> schemas.CandidateOut:
    """Create a persistent candidate profile from quiz responses.

    The returned `id` (UUID) is what the frontend stores in localStorage as
    the candidate's identity going forward.
    """
    persona = synthesize_persona(payload.bfi_responses, payload.sjt_responses)

    candidate = models.Candidate(
        display_name=payload.display_name,
        email=payload.email,
        bfi_responses=payload.bfi_responses,
        sjt_responses=payload.sjt_responses,
        cached_big_five=persona["bigFive"],
        cached_sjt_signals=persona["sjtSignals"],
        cached_inconsistencies=persona["inconsistencies"],
        cached_narrative=persona["narrative"],
    )
    db.add(candidate)
    db.commit()
    db.refresh(candidate)

    return _to_out(candidate)


@router.get("/{candidate_id}", response_model=schemas.CandidateOut)
def get_candidate(
    candidate_id: str,
    db: Session = Depends(get_session),
) -> schemas.CandidateOut:
    candidate = db.get(models.Candidate, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return _to_out(candidate)


@router.patch("/{candidate_id}", response_model=schemas.CandidateOut)
def update_candidate(
    candidate_id: str,
    payload: schemas.CandidateIntakeIn,
    db: Session = Depends(get_session),
) -> schemas.CandidateOut:
    """Allow re-submitting the quiz — e.g. if the candidate wants to revise.

    We overwrite raw responses and re-synthesize the cached persona. Any
    existing matches remain attached but become stale; refreshing a match
    re-runs the matcher against current responses.
    """
    candidate = db.get(models.Candidate, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate not found")

    if payload.display_name is not None:
        candidate.display_name = payload.display_name
    if payload.email is not None:
        candidate.email = payload.email
    if payload.bfi_responses:
        candidate.bfi_responses = payload.bfi_responses
    if payload.sjt_responses:
        candidate.sjt_responses = payload.sjt_responses

    persona = synthesize_persona(candidate.bfi_responses, candidate.sjt_responses)
    candidate.cached_big_five = persona["bigFive"]
    candidate.cached_sjt_signals = persona["sjtSignals"]
    candidate.cached_inconsistencies = persona["inconsistencies"]
    candidate.cached_narrative = persona["narrative"]

    db.commit()
    db.refresh(candidate)
    return _to_out(candidate)


@router.get(
    "",
    response_model=list[schemas.CandidateListItem],
    dependencies=[Depends(require_manager)],
)
def list_candidates(
    db: Session = Depends(get_session),
) -> list[schemas.CandidateListItem]:
    rows = db.query(models.Candidate).order_by(models.Candidate.created_at.desc()).all()
    return [
        schemas.CandidateListItem(
            id=c.id,
            display_name=c.display_name,
            narrative=c.cached_narrative,
            created_at=c.created_at,
        )
        for c in rows
    ]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _to_out(candidate: models.Candidate) -> schemas.CandidateOut:
    persona: schemas.PersonaSummary | None = None
    if candidate.cached_big_five is not None:
        persona = schemas.PersonaSummary(
            big_five=candidate.cached_big_five or {},
            sjt_signals=candidate.cached_sjt_signals or {},
            inconsistencies=[
                schemas.InconsistencyFlag(**f)
                for f in (candidate.cached_inconsistencies or [])
            ],
            narrative=candidate.cached_narrative or "",
        )
    return schemas.CandidateOut(
        id=candidate.id,
        display_name=candidate.display_name,
        email=candidate.email,
        created_at=candidate.created_at,
        updated_at=candidate.updated_at,
        persona=persona,
    )
