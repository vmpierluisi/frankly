"""Position CRUD + list. Manager-gated."""
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
    prefix="/positions",
    tags=["positions"],
    dependencies=[Depends(require_manager)],
)


# Public list used by candidate-side intake has a separate endpoint below —
# carved out via inclusion order in main.py.
@router.get("", response_model=list[schemas.PositionListItem])
def list_positions(db: Session = Depends(get_session)) -> list[schemas.PositionListItem]:
    rows = db.query(models.Position).order_by(models.Position.name).all()
    out: list[schemas.PositionListItem] = []
    for c in rows:
        item = schemas.PositionListItem.model_validate(c)
        item.reliability_audit_enabled = bool(
            getattr(getattr(c, "organization", None), "reliability_audit_enabled", False)
        )
        out.append(item)
    return out


@router.post("", response_model=schemas.PositionOut, status_code=status.HTTP_201_CREATED)
def create_position(
    payload: schemas.PositionIn,
    db: Session = Depends(get_session),
) -> schemas.PositionOut:
    position_id = payload.id or _slugify(payload.name)
    if db.get(models.Position, position_id) is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Position id '{position_id}' already exists.",
        )

    # Build the Position under an Organization → Team. If ``team_id`` is
    # supplied, attach to that team. Otherwise the legacy artefact_* fields
    # on the payload (still posted by the old TemplateSetup pre-#2d UI) are
    # used to spin up a fresh Org + Team here, explicitly. The previous
    # version of this branch relied on a back-compat ``Position.__init__``
    # that absorbed those kwargs; PR #2d.4.b moves the absorption out of the
    # model and into this single call site so the model stays clean.
    position_kwargs: dict = dict(
        id=position_id,
        name=payload.name,
        role=payload.role,
        role_family=payload.role_family,
        target_seniority=payload.target_seniority,
        is_open=payload.is_open,
        artifact_role_spec=payload.artifact_role_spec,
        required_skills=[s.model_dump() for s in payload.required_skills],
    )
    if payload.team_id is not None:
        team = db.get(models.Team, payload.team_id)
        if team is None:
            raise HTTPException(
                status_code=404, detail=f"Team {payload.team_id} not found"
            )
        position_kwargs["team_id"] = team.id
        position_kwargs["organization_id"] = team.organization_id
    else:
        # Legacy path: spin up an Org + Team from the payload's artefact
        # fields so the new Position has somewhere to live.
        org = models.Organization(
            name=payload.name,
            tagline=payload.tagline,
            mission=payload.artifact_values or "",
        )
        db.add(org)
        team = models.Team(
            organization=org,
            name=f"{payload.name} core team",
            artifact_team_structure=payload.artifact_team_structure or "",
            artifact_sample_comms=payload.artifact_sample_comms or "",
        )
        db.add(team)
        db.flush()  # populate org.id / team.id for the FK assignment below
        position_kwargs["organization_id"] = org.id
        position_kwargs["team_id"] = team.id
    position = models.Position(**position_kwargs)
    for i, crit in enumerate(payload.criteria):
        position.criteria.append(
            models.Criterion(
                key=crit.key,
                label=crit.label,
                description=crit.description,
                weight=crit.weight,
                ordering=i,
            )
        )
    db.add(position)
    db.commit()
    db.refresh(position)
    return schemas.PositionOut.model_validate(position)


@router.get("/{position_id}", response_model=schemas.PositionOut)
def get_position(
    position_id: str,
    db: Session = Depends(get_session),
) -> schemas.PositionOut:
    position = db.get(models.Position, position_id)
    if position is None:
        raise HTTPException(status_code=404, detail="Position not found")
    return schemas.PositionOut.model_validate(position)


@router.put("/{position_id}", response_model=schemas.PositionOut)
def update_position(
    position_id: str,
    payload: schemas.PositionIn,
    db: Session = Depends(get_session),
) -> schemas.PositionOut:
    position = db.get(models.Position, position_id)
    if position is None:
        raise HTTPException(status_code=404, detail="Position not found")

    # PR #2d: position-level fields only. Org / team artefacts are edited
    # via /organizations/{id} and /teams/{id} respectively. Legacy artifact_*
    # fields on the payload are silently ignored.
    position.name = payload.name
    position.role = payload.role
    position.role_family = payload.role_family
    position.target_seniority = payload.target_seniority
    position.is_open = payload.is_open
    position.artifact_role_spec = payload.artifact_role_spec
    position.required_skills = [s.model_dump() for s in payload.required_skills]

    # Replace the criteria set wholesale. (The manager approves criteria as a
    # batch during template setup, so partial mutation isn't a v0 need.)
    position.criteria.clear()
    for i, crit in enumerate(payload.criteria):
        position.criteria.append(
            models.Criterion(
                key=crit.key,
                label=crit.label,
                description=crit.description,
                weight=crit.weight,
                ordering=i,
            )
        )
    db.commit()
    db.refresh(position)
    return schemas.PositionOut.model_validate(position)


@router.delete("/{position_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_position(
    position_id: str,
    db: Session = Depends(get_session),
) -> None:
    position = db.get(models.Position, position_id)
    if position is None:
        raise HTTPException(status_code=404, detail="Position not found")
    db.delete(position)
    db.commit()


# ---------------------------------------------------------------------------
# GET /positions/{position_id}/leaderboard
# ---------------------------------------------------------------------------

@router.get("/{position_id}/leaderboard", response_model=schemas.LeaderboardOut)
def get_leaderboard(
    position_id: str,
    db: Session = Depends(get_session),
) -> schemas.LeaderboardOut:
    """Return all Match rows for a position ordered by status then overall_score."""
    position = db.get(models.Position, position_id)
    if position is None:
        raise HTTPException(status_code=404, detail="Position not found")

    matches = db.execute(
        select(models.Match, models.Candidate)
        .join(models.Candidate, models.Match.candidate_id == models.Candidate.id)
        .where(models.Match.position_id == position_id)
        .order_by(
            # succeeded rows first, then by score descending, then by finish time
            (models.Match.status != "succeeded").asc(),
            models.Match.overall_score.desc(),
            models.Match.finished_at.desc(),
        )
    ).all()

    # PR #3 — recompute peer percentiles at serve time using the current peer
    # pool. Avoids the chicken-and-egg where the first-scored match had no
    # peers and the last had all of them. Percentile written into the
    # response payload only; the stored report is unchanged.
    peer_scores: list[int] | None = None
    if position.role_family:
        peer_scores = db.execute(
            select(models.Match.overall_score)
            .join(models.Position, models.Position.id == models.Match.position_id)
            .where(
                models.Match.status == "succeeded",
                models.Position.role_family == position.role_family,
            )
        ).scalars().all()

    rows: list[schemas.LeaderboardRow] = []
    for match, candidate in matches:
        report = dict(match.report or {})
        if peer_scores and match.status == "succeeded":
            # Exclude this candidate's own score when ranking themselves.
            others = [s for s in peer_scores if s != match.overall_score] + [
                s for s in peer_scores if s == match.overall_score
            ][1:]  # drop one occurrence
            if len(others) >= 5:
                lower = sum(1 for s in others if (s or 0) < match.overall_score)
                pct = int(round(100 * lower / len(others)))
                report["percentile"] = {
                    "percentile": pct,
                    "sample_size": len(others),
                    "role_family": position.role_family,
                }
        rows.append(
            schemas.LeaderboardRow(
                match_id=match.id,
                candidate_id=candidate.id,
                display_name=candidate.display_name,
                candidate_seniority=candidate.target_seniority,
                status=match.status,
                overall_score=match.overall_score,
                band=match.band,
                report=report,
                started_at=match.started_at,
                finished_at=match.finished_at,
                error_message=match.error_message,
                cv_path=candidate.cv_path,
                linkedin_url=candidate.linkedin_url,
                github_url=candidate.github_url,
                portfolio_url=candidate.portfolio_url,
                profile_accuracy_score=candidate.profile_accuracy_score or 0,
                # Roadmap 2 / PR #2d.3 — dual scores. Legacy reports without
                # behaviourFit fall back to overall_score (which was
                # behaviour-only before this PR).
                behaviour_fit=(match.report or {}).get("behaviourFit", match.overall_score),
                skills_fit=(match.report or {}).get("skillsFit"),
            )
        )

    return schemas.LeaderboardOut(
        position_id=position.id,
        company_name=position.name,
        role=position.role,
        role_family=position.role_family,
        target_seniority=position.target_seniority,
        is_open=position.is_open,
        reliability_audit_enabled=bool(
            getattr(getattr(position, "organization", None), "reliability_audit_enabled", False)
        ),
        results=rows,
    )


# ---------------------------------------------------------------------------
def _slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s[:60] or "position"
