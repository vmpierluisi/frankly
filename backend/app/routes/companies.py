"""Company CRUD + list. Manager-gated."""
from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, status
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
    return [
        schemas.CompanyListItem(id=c.id, name=c.name, role=c.role, tagline=c.tagline)
        for c in rows
    ]


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
        artifact_values=payload.artifact_values,
        artifact_role_spec=payload.artifact_role_spec,
        artifact_team_structure=payload.artifact_team_structure,
        artifact_sample_comms=payload.artifact_sample_comms,
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
    company.artifact_values = payload.artifact_values
    company.artifact_role_spec = payload.artifact_role_spec
    company.artifact_team_structure = payload.artifact_team_structure
    company.artifact_sample_comms = payload.artifact_sample_comms

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
def _slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s[:60] or "company"
