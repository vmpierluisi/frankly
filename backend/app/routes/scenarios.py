"""Scenario library CRUD + LLM drafting routes. All manager-gated."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import models, schemas
from ..auth import require_manager
from ..config import settings
from ..db import get_session
from ..services.simulation.cost_tracker import CostBudget
from ..services.simulation.scenario_engine import (
    draft_scenarios,
    validate_scoring_dims,
)

router = APIRouter(
    prefix="/positions/{position_id}/scenarios",
    tags=["scenarios"],
    dependencies=[Depends(require_manager)],
)


def _get_company_or_404(position_id: str, db: Session) -> models.Position:
    company = db.get(models.Position, position_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")
    return company


def _get_scenario_or_404(
    scenario_id: str, position_id: str, db: Session
) -> models.MomentOfTruth:
    scenario = db.get(models.MomentOfTruth, scenario_id)
    if scenario is None:
        raise HTTPException(status_code=404, detail="Scenario not found")
    company = db.get(models.Position, position_id)
    if company is None or scenario.team_id != company.team_id:
        raise HTTPException(status_code=404, detail="Scenario not found")
    return scenario


def _check_scoring_dims(dims: list[str], company: models.Position) -> None:
    invalid = validate_scoring_dims(dims, company)
    if invalid:
        raise HTTPException(
            status_code=422,
            detail=f"scoring_dims contains keys not in company criteria: {invalid}",
        )


@router.get("", response_model=list[schemas.MomentOfTruthOut])
def list_scenarios(
    position_id: str,
    db: Session = Depends(get_session),
) -> list[schemas.MomentOfTruthOut]:
    company = _get_company_or_404(position_id, db)
    rows = (
        db.query(models.MomentOfTruth)
        .filter_by(team_id=company.team_id)
        .order_by(models.MomentOfTruth.ordering)
        .all()
    )
    return [schemas.MomentOfTruthOut.model_validate(r) for r in rows]


@router.post(
    "/draft",
    response_model=list[schemas.MomentOfTruthOut],
    status_code=status.HTTP_201_CREATED,
)
async def draft_scenario_library(
    position_id: str,
    db: Session = Depends(get_session),
) -> list[schemas.MomentOfTruthOut]:
    """LLM-draft a scenario library from company artifacts.

    Replaces all existing unedited (is_llm_drafted=True) scenarios.
    Hand-authored scenarios (is_llm_drafted=False) are preserved.
    """
    company = _get_company_or_404(position_id, db)

    # Remove auto-drafted scenarios, keep hand-authored ones.
    db.query(models.MomentOfTruth).filter(
        models.MomentOfTruth.team_id == company.team_id,
        models.MomentOfTruth.is_llm_drafted == True,  # noqa: E712
    ).delete(synchronize_session=False)

    budget = CostBudget(ceiling_usd=settings.match_cost_ceiling_usd)
    try:
        new_scenarios = await draft_scenarios(company, budget=budget)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"LLM drafting failed: {exc}") from exc

    for s in new_scenarios:
        db.add(s)
    db.commit()

    rows = (
        db.query(models.MomentOfTruth)
        .filter_by(team_id=company.team_id)
        .order_by(models.MomentOfTruth.ordering)
        .all()
    )
    return [schemas.MomentOfTruthOut.model_validate(r) for r in rows]


@router.post("", response_model=schemas.MomentOfTruthOut, status_code=status.HTTP_201_CREATED)
def create_scenario(
    position_id: str,
    payload: schemas.MomentOfTruthIn,
    db: Session = Depends(get_session),
) -> schemas.MomentOfTruthOut:
    """Create a hand-authored scenario."""
    company = _get_company_or_404(position_id, db)
    _check_scoring_dims(payload.scoring_dims, company)

    # Ordering: append after existing scenarios on this team.
    count = db.query(models.MomentOfTruth).filter_by(team_id=company.team_id).count()
    scenario = models.MomentOfTruth(
        team_id=company.team_id,
        title=payload.title,
        scenario_type=payload.scenario_type,
        prompt=payload.prompt,
        candidate_role=payload.candidate_role,
        expected_arc=payload.expected_arc,
        scoring_dims=payload.scoring_dims,
        participating_roles=payload.participating_roles,
        max_turns=payload.max_turns,
        grounding=payload.grounding,
        is_llm_drafted=False,
        ordering=count,
    )
    db.add(scenario)
    db.commit()
    db.refresh(scenario)
    return schemas.MomentOfTruthOut.model_validate(scenario)


@router.patch("/{scenario_id}", response_model=schemas.MomentOfTruthOut)
def update_scenario(
    position_id: str,
    scenario_id: str,
    payload: schemas.MomentOfTruthPatch,
    db: Session = Depends(get_session),
) -> schemas.MomentOfTruthOut:
    company = _get_company_or_404(position_id, db)
    scenario = _get_scenario_or_404(scenario_id, position_id, db)

    update_data = payload.model_dump(exclude_unset=True)
    if "scoring_dims" in update_data:
        _check_scoring_dims(update_data["scoring_dims"], company)

    for field, value in update_data.items():
        setattr(scenario, field, value)

    db.commit()
    db.refresh(scenario)
    return schemas.MomentOfTruthOut.model_validate(scenario)


@router.delete("/{scenario_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_scenario(
    position_id: str,
    scenario_id: str,
    db: Session = Depends(get_session),
) -> None:
    _get_company_or_404(position_id, db)
    scenario = _get_scenario_or_404(scenario_id, position_id, db)
    db.delete(scenario)
    db.commit()
