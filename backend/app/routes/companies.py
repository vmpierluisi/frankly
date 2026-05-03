"""Company CRUD + list. Manager-gated."""
from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models, schemas
from ..auth import require_manager
from ..db import get_session

router = APIRouter(
    prefix="/companies",
    tags=["companies"],
    dependencies=[Depends(require_manager)],
)


# Public list used by candidate-side intake has a separate endpoint below —
# carved out via inclusion order in main.py.
@router.get("", response_model=list[schemas.CompanyListItem])
def list_companies(db: Session = Depends(get_session)) -> list[schemas.CompanyListItem]:
    rows = db.query(models.Company).order_by(models.Company.name).all()
    return [schemas.CompanyListItem.model_validate(c) for c in rows]


@router.post("", response_model=schemas.CompanyOut, status_code=status.HTTP_201_CREATED)
def create_company(
    payload: schemas.CompanyIn,
    db: Session = Depends(get_session),
) -> schemas.CompanyOut:
    company_id = payload.id or _slugify(payload.name)
    if db.get(models.Company, company_id) is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Company id '{company_id}' already exists.",
        )

    company = models.Company(
        id=company_id,
        name=payload.name,
        tagline=payload.tagline,
        role=payload.role,
        role_family=payload.role_family,
        target_seniority=payload.target_seniority,
        is_open=payload.is_open,
        artifact_values=payload.artifact_values,
        artifact_role_spec=payload.artifact_role_spec,
        artifact_team_structure=payload.artifact_team_structure,
        artifact_sample_comms=payload.artifact_sample_comms,
        required_skills=[s.model_dump() for s in payload.required_skills],
        skill_match_weight=payload.skill_match_weight,
    )
    for i, crit in enumerate(payload.criteria):
        company.criteria.append(
            models.Criterion(
                key=crit.key,
                label=crit.label,
                description=crit.description,
                weight=crit.weight,
                ordering=i,
            )
        )
    db.add(company)
    db.commit()
    db.refresh(company)
    return schemas.CompanyOut.model_validate(company)


@router.get("/{company_id}", response_model=schemas.CompanyOut)
def get_company(
    company_id: str,
    db: Session = Depends(get_session),
) -> schemas.CompanyOut:
    company = db.get(models.Company, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")
    return schemas.CompanyOut.model_validate(company)


@router.put("/{company_id}", response_model=schemas.CompanyOut)
def update_company(
    company_id: str,
    payload: schemas.CompanyIn,
    db: Session = Depends(get_session),
) -> schemas.CompanyOut:
    company = db.get(models.Company, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")

    company.name = payload.name
    company.tagline = payload.tagline
    company.role = payload.role
    company.role_family = payload.role_family
    company.target_seniority = payload.target_seniority
    company.is_open = payload.is_open
    company.artifact_values = payload.artifact_values
    company.artifact_role_spec = payload.artifact_role_spec
    company.artifact_team_structure = payload.artifact_team_structure
    company.artifact_sample_comms = payload.artifact_sample_comms
    company.required_skills = [s.model_dump() for s in payload.required_skills]
    company.skill_match_weight = payload.skill_match_weight

    # Replace the criteria set wholesale. (The manager approves criteria as a
    # batch during template setup, so partial mutation isn't a v0 need.)
    company.criteria.clear()
    for i, crit in enumerate(payload.criteria):
        company.criteria.append(
            models.Criterion(
                key=crit.key,
                label=crit.label,
                description=crit.description,
                weight=crit.weight,
                ordering=i,
            )
        )
    db.commit()
    db.refresh(company)
    return schemas.CompanyOut.model_validate(company)


@router.delete("/{company_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_company(
    company_id: str,
    db: Session = Depends(get_session),
) -> None:
    company = db.get(models.Company, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")
    db.delete(company)
    db.commit()


# ---------------------------------------------------------------------------
# GET /companies/{company_id}/leaderboard
# ---------------------------------------------------------------------------

@router.get("/{company_id}/leaderboard", response_model=schemas.LeaderboardOut)
def get_leaderboard(
    company_id: str,
    db: Session = Depends(get_session),
) -> schemas.LeaderboardOut:
    """Return all Match rows for a company ordered by status then overall_score."""
    company = db.get(models.Company, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")

    matches = db.execute(
        select(models.Match, models.Candidate)
        .join(models.Candidate, models.Match.candidate_id == models.Candidate.id)
        .where(models.Match.company_id == company_id)
        .order_by(
            # succeeded rows first, then by score descending, then by finish time
            (models.Match.status != "succeeded").asc(),
            models.Match.overall_score.desc(),
            models.Match.finished_at.desc(),
        )
    ).all()

    rows: list[schemas.LeaderboardRow] = []
    for match, candidate in matches:
        rows.append(
            schemas.LeaderboardRow(
                match_id=match.id,
                candidate_id=candidate.id,
                display_name=candidate.display_name,
                candidate_seniority=candidate.target_seniority,
                status=match.status,
                overall_score=match.overall_score,
                band=match.band,
                report=match.report or {},
                started_at=match.started_at,
                finished_at=match.finished_at,
                error_message=match.error_message,
            )
        )

    return schemas.LeaderboardOut(
        company_id=company.id,
        company_name=company.name,
        role=company.role,
        role_family=company.role_family,
        target_seniority=company.target_seniority,
        is_open=company.is_open,
        results=rows,
    )


# ---------------------------------------------------------------------------
def _slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s[:60] or "company"
