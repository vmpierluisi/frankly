"""Synthetic team management routes. All manager-gated."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import models, schemas
from ..auth import require_manager
from ..config import settings
from ..db import get_session
from ..services.simulation.cost_tracker import CostBudget
from ..services.simulation.team_synthesizer import synthesize

router = APIRouter(
    prefix="/companies/{company_id}/team",
    tags=["team"],
    dependencies=[Depends(require_manager)],
)


def _get_company_or_404(company_id: str, db: Session) -> models.Company:
    company = db.get(models.Company, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")
    return company


@router.get("", response_model=list[schemas.SyntheticTeammateOut])
def list_team(
    company_id: str,
    db: Session = Depends(get_session),
) -> list[schemas.SyntheticTeammateOut]:
    _get_company_or_404(company_id, db)
    rows = (
        db.query(models.SyntheticTeammate)
        .filter_by(company_id=company_id)
        .order_by(models.SyntheticTeammate.ordering)
        .all()
    )
    return [schemas.SyntheticTeammateOut.model_validate(r) for r in rows]


@router.post(
    "/synthesize",
    response_model=list[schemas.SyntheticTeammateOut],
    status_code=status.HTTP_201_CREATED,
)
async def synthesize_team(
    company_id: str,
    db: Session = Depends(get_session),
) -> list[schemas.SyntheticTeammateOut]:
    """Regenerate synthetic teammates for a company.

    Deletes any existing (unedited) teammates and replaces them with a
    freshly generated set.  Teammates marked is_edited=True are preserved.
    """
    company = _get_company_or_404(company_id, db)

    # Delete only auto-generated (unedited) teammates.
    db.query(models.SyntheticTeammate).filter(
        models.SyntheticTeammate.company_id == company_id,
        models.SyntheticTeammate.is_edited == False,  # noqa: E712
    ).delete(synchronize_session=False)

    budget = CostBudget(ceiling_usd=settings.match_cost_ceiling_usd)
    try:
        new_teammates = await synthesize(company, budget=budget)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"LLM synthesis failed: {exc}") from exc

    for t in new_teammates:
        db.add(t)
    db.commit()

    rows = (
        db.query(models.SyntheticTeammate)
        .filter_by(company_id=company_id)
        .order_by(models.SyntheticTeammate.ordering)
        .all()
    )
    return [schemas.SyntheticTeammateOut.model_validate(r) for r in rows]


@router.patch("/{teammate_id}", response_model=schemas.SyntheticTeammateOut)
def update_teammate(
    company_id: str,
    teammate_id: str,
    payload: schemas.SyntheticTeammatePatch,
    db: Session = Depends(get_session),
) -> schemas.SyntheticTeammateOut:
    _get_company_or_404(company_id, db)
    teammate = db.get(models.SyntheticTeammate, teammate_id)
    if teammate is None or teammate.company_id != company_id:
        raise HTTPException(status_code=404, detail="Teammate not found")

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(teammate, field, value)
    teammate.is_edited = True

    db.commit()
    db.refresh(teammate)
    return schemas.SyntheticTeammateOut.model_validate(teammate)


@router.delete("/{teammate_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_teammate(
    company_id: str,
    teammate_id: str,
    db: Session = Depends(get_session),
) -> None:
    _get_company_or_404(company_id, db)
    teammate = db.get(models.SyntheticTeammate, teammate_id)
    if teammate is None or teammate.company_id != company_id:
        raise HTTPException(status_code=404, detail="Teammate not found")
    db.delete(teammate)
    db.commit()
