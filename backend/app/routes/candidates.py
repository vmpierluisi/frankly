"""Candidate intake + profile + list + authenticated self-service endpoints."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from .. import models, schemas
from ..auth import CurrentUser, require_candidate, require_manager
from ..config import settings
from ..db import get_session
from ..services.persona import synthesize_persona
from ..services.simulation.cost_tracker import CostBudget
from ..services.simulation.persona_aggregator import aggregate
from ..seed_data import BFI10, SJTS

router = APIRouter(prefix="/candidates", tags=["candidates"])


# ---------------------------------------------------------------------------
# Public — instruments
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# Candidate self-service (/me)  — require_candidate
# ---------------------------------------------------------------------------
@router.get("/me", response_model=schemas.CandidateMeOut)
def get_me(
    user: CurrentUser = Depends(require_candidate),
    db: Session = Depends(get_session),
) -> schemas.CandidateMeOut:
    """Return (or auto-create) the candidate row for the signed-in user."""
    candidate = (
        db.query(models.Candidate)
        .filter(models.Candidate.auth_user_id == user.auth_user_id)
        .first()
    )
    if candidate is None:
        candidate = models.Candidate(
            auth_user_id=user.auth_user_id,
            email=user.email,
            assessment_status="pending",
        )
        db.add(candidate)
        db.commit()
        db.refresh(candidate)
    return _to_me_out(candidate)


@router.patch("/me", response_model=schemas.CandidateMeOut)
def update_me(
    payload: schemas.CandidateMePatchIn,
    user: CurrentUser = Depends(require_candidate),
    db: Session = Depends(get_session),
) -> schemas.CandidateMeOut:
    """Partial update: display_name, linkedin_url, github_url, cv_path."""
    candidate = (
        db.query(models.Candidate)
        .filter(models.Candidate.auth_user_id == user.auth_user_id)
        .first()
    )
    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate not found — call GET /me first.")

    for field in ("display_name", "linkedin_url", "github_url", "cv_path"):
        val = getattr(payload, field)
        if val is not None:
            setattr(candidate, field, val)

    db.commit()
    db.refresh(candidate)
    return _to_me_out(candidate)


@router.post("/me/assessment", response_model=schemas.CandidateMeOut)
def submit_assessment(
    payload: schemas.AssessmentSubmitIn,
    user: CurrentUser = Depends(require_candidate),
    db: Session = Depends(get_session),
) -> schemas.CandidateMeOut:
    """Submit (or re-submit) BFI + SJT responses for the signed-in candidate."""
    candidate = (
        db.query(models.Candidate)
        .filter(models.Candidate.auth_user_id == user.auth_user_id)
        .first()
    )
    if candidate is None:
        candidate = models.Candidate(
            auth_user_id=user.auth_user_id,
            email=user.email,
        )
        db.add(candidate)

    candidate.bfi_responses = payload.bfi_responses
    candidate.sjt_responses = payload.sjt_responses
    candidate.assessment_status = "completed"

    persona = synthesize_persona(payload.bfi_responses, payload.sjt_responses)
    candidate.cached_big_five = persona["bigFive"]
    candidate.cached_sjt_signals = persona["sjtSignals"]
    candidate.cached_inconsistencies = persona["inconsistencies"]
    candidate.cached_narrative = persona["narrative"]

    db.commit()
    db.refresh(candidate)
    return _to_me_out(candidate)


# ---------------------------------------------------------------------------
# Candidate self-service — persona aggregation (simulation pipeline)
# ---------------------------------------------------------------------------
@router.post(
    "/me/persona/aggregate",
    response_model=schemas.AggregatedPersonaOut,
    summary="Trigger aggregated persona generation for the signed-in candidate.",
)
async def aggregate_my_persona(
    user: CurrentUser = Depends(require_candidate),
    db: Session = Depends(get_session),
) -> schemas.AggregatedPersonaOut:
    """Run the persona aggregator over all available evidence sources and
    cache the result on the candidate row.  Re-running overwrites the cache.
    """
    candidate = (
        db.query(models.Candidate)
        .filter(models.Candidate.auth_user_id == user.auth_user_id)
        .first()
    )
    if candidate is None:
        raise HTTPException(
            status_code=404,
            detail="Candidate not found — call GET /me first.",
        )
    if candidate.assessment_status != "completed":
        raise HTTPException(
            status_code=409,
            detail=(
                "Assessment not yet completed. "
                "Submit BFI + SJT responses via POST /me/assessment first."
            ),
        )

    budget = CostBudget(ceiling_usd=settings.match_cost_ceiling_usd)
    try:
        persona = await aggregate(candidate, budget=budget)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Persona aggregation failed: {exc}",
        ) from exc

    now = datetime.now(timezone.utc)
    candidate.aggregated_persona = persona
    candidate.aggregation_audit = {
        "evidence_completeness": persona.get("evidence_completeness"),
        "aggregator_version": persona.get("aggregator_version"),
        "n_provenance_claims": len(persona.get("provenance_map", [])),
        "n_inconsistencies": len(persona.get("inconsistencies", [])),
        "llm_calls": budget.calls_made,
        "tokens_in": budget.tokens_in,
        "tokens_out": budget.tokens_out,
        "cost_usd": round(budget.spent_usd, 6),
    }
    candidate.aggregated_at = now
    db.commit()
    db.refresh(candidate)

    return schemas.AggregatedPersonaOut(
        aggregated_persona=candidate.aggregated_persona,
        aggregation_audit=candidate.aggregation_audit,
        aggregated_at=candidate.aggregated_at,
    )


@router.get(
    "/me/persona",
    response_model=schemas.AggregatedPersonaOut,
    summary="Return the cached aggregated persona for the signed-in candidate.",
)
def get_my_persona(
    user: CurrentUser = Depends(require_candidate),
    db: Session = Depends(get_session),
) -> schemas.AggregatedPersonaOut:
    """Return the cached aggregated persona.  404 if not yet aggregated."""
    candidate = (
        db.query(models.Candidate)
        .filter(models.Candidate.auth_user_id == user.auth_user_id)
        .first()
    )
    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate not found.")
    if candidate.aggregated_persona is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "No aggregated persona found. "
                "Trigger aggregation via POST /me/persona/aggregate first."
            ),
        )
    return schemas.AggregatedPersonaOut(
        aggregated_persona=candidate.aggregated_persona,
        aggregation_audit=candidate.aggregation_audit,
        aggregated_at=candidate.aggregated_at,
    )


# ---------------------------------------------------------------------------
# Public intake (legacy — keeps existing anonymous flow working)
# ---------------------------------------------------------------------------
@router.post("", response_model=schemas.CandidateOut, status_code=status.HTTP_201_CREATED)
def create_candidate(
    payload: schemas.CandidateIntakeIn,
    db: Session = Depends(get_session),
) -> schemas.CandidateOut:
    """Anonymous intake — kept for backwards compatibility."""
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
        assessment_status="completed",
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
    candidate.assessment_status = "completed"

    db.commit()
    db.refresh(candidate)
    return _to_out(candidate)


# ---------------------------------------------------------------------------
# Manager — list
# ---------------------------------------------------------------------------
@router.get(
    "",
    response_model=list[schemas.CandidateListItem],
    dependencies=[Depends(require_manager)],
)
def list_candidates(
    is_seed: bool | None = Query(default=None, description="Filter by seed flag"),
    assessment_status: str | None = Query(default=None, description="Filter by assessment_status"),
    db: Session = Depends(get_session),
) -> list[schemas.CandidateListItem]:
    q = db.query(models.Candidate)
    if is_seed is not None:
        q = q.filter(models.Candidate.is_seed == is_seed)
    if assessment_status is not None:
        q = q.filter(models.Candidate.assessment_status == assessment_status)
    rows = q.order_by(models.Candidate.created_at.desc()).all()
    return [
        schemas.CandidateListItem(
            id=c.id,
            display_name=c.display_name,
            email=c.email,
            narrative=c.cached_narrative,
            assessment_status=c.assessment_status,
            is_seed=c.is_seed,
            created_at=c.created_at,
        )
        for c in rows
    ]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _persona(candidate: models.Candidate) -> schemas.PersonaSummary | None:
    if candidate.cached_big_five is None:
        return None
    return schemas.PersonaSummary(
        big_five=candidate.cached_big_five or {},
        sjt_signals=candidate.cached_sjt_signals or {},
        inconsistencies=[
            schemas.InconsistencyFlag(**f)
            for f in (candidate.cached_inconsistencies or [])
        ],
        narrative=candidate.cached_narrative or "",
    )


def _to_out(candidate: models.Candidate) -> schemas.CandidateOut:
    return schemas.CandidateOut(
        id=candidate.id,
        display_name=candidate.display_name,
        email=candidate.email,
        created_at=candidate.created_at,
        updated_at=candidate.updated_at,
        persona=_persona(candidate),
    )


def _to_me_out(candidate: models.Candidate) -> schemas.CandidateMeOut:
    return schemas.CandidateMeOut(
        id=candidate.id,
        auth_user_id=candidate.auth_user_id,
        display_name=candidate.display_name,
        email=candidate.email,
        cv_path=candidate.cv_path,
        linkedin_url=candidate.linkedin_url,
        github_url=candidate.github_url,
        assessment_status=candidate.assessment_status,
        is_seed=candidate.is_seed,
        created_at=candidate.created_at,
        updated_at=candidate.updated_at,
        persona=_persona(candidate),
    )
