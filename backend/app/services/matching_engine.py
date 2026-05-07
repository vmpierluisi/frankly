"""Candidate-driven matching engine.

Finds open company positions compatible with a candidate's declared target and
enqueues Match rows for background simulation.

Single-worker uvicorn only — all coordination is in-process asyncio.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..lib.role_families import compatible_seniorities


def find_open_companies_for_candidate(
    db: Session,
    candidate: models.Candidate,
) -> list[models.Position]:
    """Return open companies whose role family and seniority are compatible."""
    if not candidate.target_role_family or not candidate.target_seniority:
        return []

    compat = compatible_seniorities(candidate.target_seniority)
    if not compat:
        return []

    return list(
        db.execute(
            select(models.Position).where(
                models.Position.is_open == True,  # noqa: E712
                models.Position.role_family == candidate.target_role_family,
                models.Position.target_seniority.in_(compat),
            )
        ).scalars().all()
    )


def enqueue_matches_for_candidate(
    db: Session,
    candidate: models.Candidate,
) -> list[models.Match]:
    """Create or reset Match rows for each compatible open company.

    - succeeded matches are immutable (skip).
    - running matches are left alone (in-flight).
    - pending / failed matches are reset to pending.
    - new pairs get a fresh Match with status='pending'.

    Returns the list of Match rows that need a background task spawned.
    """
    companies = find_open_companies_for_candidate(db, candidate)
    to_spawn: list[models.Match] = []

    for company in companies:
        existing = db.execute(
            select(models.Match).where(
                models.Match.candidate_id == candidate.id,
                models.Match.position_id == company.id,
            )
        ).scalar_one_or_none()

        if existing is None:
            match = models.Match(
                candidate_id=candidate.id,
                position_id=company.id,
                status="pending",
                overall_score=0,
                band="",
                band_note="",
                report={},
            )
            db.add(match)
            to_spawn.append(match)
        elif existing.status == "succeeded":
            continue
        elif existing.status == "running":
            continue
        else:
            existing.status = "pending"
            existing.error_message = None
            to_spawn.append(existing)

    return to_spawn
