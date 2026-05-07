"""Team endpoints — Roadmap 2 / PR #2d.

A Team sits between Organization and Position. It owns the people the
simulation actually uses (synthetic teammates), the scenarios they face,
and the team-structure / sample-comms artefacts that drive the simulation
team synthesizer.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import models, schemas
from ..auth import CurrentUser, require_manager
from ..db import get_session

router = APIRouter(prefix="/teams", tags=["teams"])


@router.get("/{team_id}", response_model=schemas.TeamDetailOut)
def get_team(
    team_id: str,
    _user: CurrentUser = Depends(require_manager),
    db: Session = Depends(get_session),
) -> schemas.TeamDetailOut:
    team = db.get(models.Team, team_id)
    if team is None:
        raise HTTPException(status_code=404, detail="Team not found")
    return schemas.TeamDetailOut.model_validate(team)


@router.patch("/{team_id}", response_model=schemas.TeamOut)
def update_team(
    team_id: str,
    payload: schemas.TeamPatch,
    _user: CurrentUser = Depends(require_manager),
    db: Session = Depends(get_session),
) -> schemas.TeamOut:
    team = db.get(models.Team, team_id)
    if team is None:
        raise HTTPException(status_code=404, detail="Team not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(team, field, value)
    db.commit()
    db.refresh(team)
    return schemas.TeamOut.model_validate(team)


@router.delete("/{team_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_team(
    team_id: str,
    _user: CurrentUser = Depends(require_manager),
    db: Session = Depends(get_session),
) -> None:
    team = db.get(models.Team, team_id)
    if team is None:
        raise HTTPException(status_code=404, detail="Team not found")
    db.delete(team)
    db.commit()


# ---------------------------------------------------------------------------
# Positions nested under a team
# ---------------------------------------------------------------------------

@router.get("/{team_id}/positions", response_model=list[schemas.PositionOut])
def list_positions(
    team_id: str,
    _user: CurrentUser = Depends(require_manager),
    db: Session = Depends(get_session),
) -> list[schemas.PositionOut]:
    team = db.get(models.Team, team_id)
    if team is None:
        raise HTTPException(status_code=404, detail="Team not found")
    return [schemas.PositionOut.model_validate(p) for p in team.positions]
