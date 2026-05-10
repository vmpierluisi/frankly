"""Notification feed — Roadmap 2 / PR #4.

A single endpoint surface that powers the bell icon in both candidate and
manager dashboards. Routing rule: the route reads `require_user`, then
filters by the user's role:

  * candidate → notifications where ``candidate_id`` matches the caller's
    candidate row.
  * manager   → notifications where ``recipient_email`` matches the
    caller's email.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models, schemas
from ..auth import CurrentUser, require_user
from ..db import get_session

router = APIRouter(prefix="/notifications", tags=["notifications"])


def _notifications_for_user(db: Session, user: CurrentUser):
    q = select(models.Notification).order_by(models.Notification.created_at.desc())
    if user.role == "candidate":
        cand = (
            db.query(models.Candidate)
            .filter(models.Candidate.auth_user_id == user.auth_user_id)
            .first()
        )
        if cand is None:
            return []
        return db.execute(q.where(models.Notification.candidate_id == cand.id)).scalars().all()
    return db.execute(q.where(models.Notification.recipient_email == user.email)).scalars().all()


@router.get("", response_model=list[schemas.NotificationOut])
def list_notifications(
    user: CurrentUser = Depends(require_user),
    db: Session = Depends(get_session),
) -> list[schemas.NotificationOut]:
    return [schemas.NotificationOut.model_validate(n) for n in _notifications_for_user(db, user)]


def _load_owned(db: Session, notif_id: str, user: CurrentUser) -> models.Notification:
    n = db.get(models.Notification, notif_id)
    if n is None:
        raise HTTPException(status_code=404, detail="Notification not found")
    if user.role == "candidate":
        cand = (
            db.query(models.Candidate)
            .filter(models.Candidate.auth_user_id == user.auth_user_id)
            .first()
        )
        if cand is None or n.candidate_id != cand.id:
            raise HTTPException(status_code=404, detail="Notification not found")
    else:
        if (n.recipient_email or "") != user.email:
            raise HTTPException(status_code=404, detail="Notification not found")
    return n


@router.post("/{notif_id}/read", response_model=schemas.NotificationOut)
def mark_read(
    notif_id: str,
    user: CurrentUser = Depends(require_user),
    db: Session = Depends(get_session),
) -> schemas.NotificationOut:
    n = _load_owned(db, notif_id, user)
    n.status = "read"
    db.commit()
    db.refresh(n)
    return schemas.NotificationOut.model_validate(n)


@router.post("/read-all")
def mark_all_read(
    user: CurrentUser = Depends(require_user),
    db: Session = Depends(get_session),
) -> dict:
    rows = _notifications_for_user(db, user)
    updated = 0
    for n in rows:
        if n.status != "dismissed" and n.status != "read":
            n.status = "read"
            updated += 1
    db.commit()
    return {"updated": updated}


@router.post("/{notif_id}/dismiss", response_model=schemas.NotificationOut)
def dismiss(
    notif_id: str,
    user: CurrentUser = Depends(require_user),
    db: Session = Depends(get_session),
) -> schemas.NotificationOut:
    n = _load_owned(db, notif_id, user)
    n.status = "dismissed"
    db.commit()
    db.refresh(n)
    return schemas.NotificationOut.model_validate(n)
