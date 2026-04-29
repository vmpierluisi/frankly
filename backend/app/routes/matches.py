"""Match trigger + list. Manager-gated.

Matching always re-synthesizes persona from stored raw responses so we pick up
any candidate edits since the last match.
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..auth import require_manager
from ..db import get_session
from ..services.baseline_matcher import project_fit_axes
from ..services.baseline_matcher import run_match as baseline_run_match
from ..services.persona import synthesize_persona
from ..services.simulation import simulation_matcher

router = APIRouter(
    prefix="/matches",
    tags=["matches"],
    dependencies=[Depends(require_manager)],
)


def _company_to_dict(company: models.Company) -> dict:
    return {
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

    # Create Match row first so simulation_matcher can write logs against its id.
    match = models.Match(
        candidate_id=candidate.id,
        company_id=company.id,
        overall_score=0,
        band="",
        band_note="",
        report={},
    )
    db.add(match)
    db.flush()

    report = await simulation_matcher.run_match(
        match_id=match.id,
        candidate=candidate,
        company=company,
        db=db,
    )

    match.overall_score = report["overallScore"]
    match.band = report["band"]
    match.band_note = report.get("bandNote", "")
    match.report = report

    db.commit()
    db.refresh(match)

    return schemas.MatchOut.model_validate(match)


@router.post("/search", response_model=schemas.SearchMatchOut)
async def search_candidates(
    payload: schemas.SearchMatchIn,
    db: Session = Depends(get_session),
) -> schemas.SearchMatchOut:
    """Run the matcher across the entire candidate pool for a single company.

    Position-first batch matching. Reuses cached Match rows by default; pass
    ``refresh=true`` to force fresh LLM calls for every candidate.
    """
    company = db.get(models.Company, payload.company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")
    if not company.criteria:
        raise HTTPException(
            status_code=400,
            detail="Company has no criteria — extract or add criteria before searching.",
        )

    company_dict = _company_to_dict(company)
    candidates = db.query(models.Candidate).all()

    # Bound concurrency so we don't hammer OpenRouter with the full pool at once.
    sem = asyncio.Semaphore(4)

    async def score_candidate(candidate: models.Candidate) -> tuple[models.Candidate, dict, bool]:
        if not payload.refresh:
            existing = (
                db.query(models.Match)
                .filter(
                    models.Match.candidate_id == candidate.id,
                    models.Match.company_id == company.id,
                )
                .order_by(models.Match.created_at.desc())
                .first()
            )
            if existing is not None:
                return candidate, existing.report, True

        async with sem:
            persona = synthesize_persona(
                candidate.bfi_responses or {}, candidate.sjt_responses or {}
            )
            report = await baseline_run_match(persona=persona, company=company_dict)
        return candidate, report, False

    scored = await asyncio.gather(*(score_candidate(c) for c in candidates))

    # Persist any fresh runs so subsequent (non-refresh) searches hit cache.
    for candidate, report, cached in scored:
        if cached:
            continue
        db.add(
            models.Match(
                candidate_id=candidate.id,
                company_id=company.id,
                overall_score=report["overallScore"],
                band=report["band"],
                band_note=report["bandNote"],
                report=report,
            )
        )
    db.commit()

    items: list[schemas.SearchMatchResultItem] = []
    for candidate, report, cached in scored:
        axes = project_fit_axes(report, company_dict["criteria"])
        items.append(
            schemas.SearchMatchResultItem(
                candidate_id=candidate.id,
                display_name=candidate.display_name,
                narrative=candidate.cached_narrative,
                overall_score=report["overallScore"],
                band=report["band"],
                band_note=report["bandNote"],
                report=report,
                fit_axes=schemas.FitAxes(**axes),
                cached=cached,
                is_seed=candidate.is_seed,
            )
        )
    items.sort(key=lambda r: r.overall_score, reverse=True)

    return schemas.SearchMatchOut(
        company_id=company.id,
        company_name=company.name,
        role=company.role,
        pool_size=len(candidates),
        results=items,
    )


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
