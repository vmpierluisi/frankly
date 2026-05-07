"""Organization endpoints — Roadmap 2 / PR #2d.

An Organization sits at the top of the three-tier hierarchy:
    Organization → Team → Position (= Company in code).

Owns culture artefacts (mission, code_of_conduct, tagline, name) that
were previously duplicated across each per-vacancy Company row.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import models, schemas
from ..auth import CurrentUser, require_manager
from ..db import get_session

router = APIRouter(prefix="/organizations", tags=["organizations"])


# ---------------------------------------------------------------------------
# Org CRUD
# ---------------------------------------------------------------------------

@router.get("", response_model=list[schemas.OrganizationOut])
def list_organizations(
    _user: CurrentUser = Depends(require_manager),
    db: Session = Depends(get_session),
) -> list[schemas.OrganizationOut]:
    rows = db.query(models.Organization).order_by(models.Organization.name).all()
    return [schemas.OrganizationOut.model_validate(r) for r in rows]


@router.post(
    "",
    response_model=schemas.OrganizationOut,
    status_code=status.HTTP_201_CREATED,
)
def create_organization(
    payload: schemas.OrganizationIn,
    _user: CurrentUser = Depends(require_manager),
    db: Session = Depends(get_session),
) -> schemas.OrganizationOut:
    org = models.Organization(
        name=payload.name,
        tagline=payload.tagline,
        mission=payload.mission,
        code_of_conduct=payload.code_of_conduct,
    )
    db.add(org)
    db.commit()
    db.refresh(org)
    return schemas.OrganizationOut.model_validate(org)


@router.get("/{org_id}", response_model=schemas.OrganizationDetailOut)
def get_organization(
    org_id: str,
    _user: CurrentUser = Depends(require_manager),
    db: Session = Depends(get_session),
) -> schemas.OrganizationDetailOut:
    org = db.get(models.Organization, org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    return schemas.OrganizationDetailOut.model_validate(org)


@router.patch("/{org_id}", response_model=schemas.OrganizationOut)
def update_organization(
    org_id: str,
    payload: schemas.OrganizationPatch,
    _user: CurrentUser = Depends(require_manager),
    db: Session = Depends(get_session),
) -> schemas.OrganizationOut:
    org = db.get(models.Organization, org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(org, field, value)
    db.commit()
    db.refresh(org)
    return schemas.OrganizationOut.model_validate(org)


@router.delete("/{org_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_organization(
    org_id: str,
    _user: CurrentUser = Depends(require_manager),
    db: Session = Depends(get_session),
) -> None:
    org = db.get(models.Organization, org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    db.delete(org)
    db.commit()


# ---------------------------------------------------------------------------
# Teams nested under an org
# ---------------------------------------------------------------------------

@router.get("/{org_id}/teams", response_model=list[schemas.TeamOut])
def list_teams(
    org_id: str,
    _user: CurrentUser = Depends(require_manager),
    db: Session = Depends(get_session),
) -> list[schemas.TeamOut]:
    org = db.get(models.Organization, org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    rows = (
        db.query(models.Team)
        .filter_by(organization_id=org_id)
        .order_by(models.Team.created_at)
        .all()
    )
    return [schemas.TeamOut.model_validate(r) for r in rows]


@router.post(
    "/{org_id}/teams",
    response_model=schemas.TeamOut,
    status_code=status.HTTP_201_CREATED,
)
def create_team(
    org_id: str,
    payload: schemas.TeamIn,
    _user: CurrentUser = Depends(require_manager),
    db: Session = Depends(get_session),
) -> schemas.TeamOut:
    org = db.get(models.Organization, org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")

    team = models.Team(
        organization_id=org_id,
        name=payload.name,
        artifact_team_structure=payload.artifact_team_structure,
        artifact_sample_comms=payload.artifact_sample_comms,
    )
    db.add(team)
    db.commit()
    db.refresh(team)
    return schemas.TeamOut.model_validate(team)
