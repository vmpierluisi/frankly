"""Match trigger + list. Manager-gated.

Matching always re-synthesizes persona from stored raw responses so we pick up
any candidate edits since the last match.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..auth import require_manager
from ..db import get_session
from ..services.matcher import run_match
from ..services.persona import synthesize_persona

router = APIRouter(
    prefix="/matches",
    tags=["matches"],
    dependencies=[Depends(require_manager)],
)


@router.post("/trigger", response_model=schemas.MatchOut)
async def trigger_match(
    payload: schemas.TriggerMatchIn,
    db: Session = Depends(get_session),
) -> schemas.MatchOut:
    candidate = db.get(models.Candidate, payload.candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate not found")
    company = db.get(models.Company, payload.company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")

    persona = synthesize_persona(candidate.bfi_responses or {}, candidate.sjt_responses or {})

    company_dict = {
        "id": company.id,
        "name": company.name,
        "role": company.role,
        "tagline": company.tagline,
        "artifact_values": company.artifact_values,
        "artifact_role_spec": company.artifact_role_spec,
        "artifact_team_structure": company.artifact_team_structure,
        "artifact_sample_comms": company.artifact_sample_comms,
        "criteria": [
            {
                "key": c.key,
                "label": c.label,
                "description": c.description,
                "weight": c.weight,
            }
            for c in company.criteria
        ],
    }

    report = await run_match(persona=persona, company=company_dict)

    match = models.Match(
        candidate_id=candidate.id,
        company_id=company.id,
        overall_score=report["overallScore"],
        band=report["band"],
        band_note=report["bandNote"],
        report=report,
    )
    db.add(match)
    db.commit()
    db.refresh(match)

    return schemas.MatchOut.model_validate(match)


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
