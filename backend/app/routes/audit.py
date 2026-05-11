"""Reliability + Fairness audit panel — Roadmap 2 / PR #6.

Recruiter-only, gated behind the per-organization
``reliability_audit_enabled`` toggle. Three endpoints under
``/audit/positions/{position_id}``:

  GET .../reliability   — five chart families.
  GET .../fairness      — demographic distributions + parity gap.
  GET .../export.csv    — flat per-match audit rows.

Manager auth (Supabase JWT) — the same surface used elsewhere in the
recruiter UI. Toggling the feature on the wrong org → 403.
"""
from __future__ import annotations

import csv
import io
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from .. import models
from ..auth import CurrentUser, require_manager
from ..db import get_session
from ..services import reliability as reliability_svc

router = APIRouter(prefix="/audit", tags=["audit"])


_VALID_SCOPES = {"all", "open", "closed"}


def _normalize_scope(scope: str) -> str:
    if scope not in _VALID_SCOPES:
        raise HTTPException(
            status_code=400, detail=f"scope must be one of: {sorted(_VALID_SCOPES)}"
        )
    return scope


def _load_position(db: Session, position_id: str) -> models.Position:
    pos = db.get(models.Position, position_id)
    if pos is None:
        raise HTTPException(status_code=404, detail="Position not found")
    return pos


def _require_feature(pos: models.Position) -> None:
    org = pos.organization
    if org is None or not org.reliability_audit_enabled:
        raise HTTPException(
            status_code=403,
            detail="Reliability + Fairness audit is disabled for this organization.",
        )


@router.get("/overview/reliability")
def get_reliability_overview(
    scope: str = "all",
    _user: CurrentUser = Depends(require_manager),
    db: Session = Depends(get_session),
) -> dict[str, Any]:
    """Aggregated reliability report across every audit-enabled position.

    ``scope`` filters by open/closed status. The endpoint is intentionally
    not 403 when no orgs have the toggle on — it returns an empty report
    so the UI can render a non-error empty state.
    """
    return reliability_svc.reliability_overview(db, _normalize_scope(scope))


@router.get("/overview/fairness")
def get_fairness_overview(
    scope: str = "all",
    _user: CurrentUser = Depends(require_manager),
    db: Session = Depends(get_session),
) -> dict[str, Any]:
    return reliability_svc.fairness_overview(db, _normalize_scope(scope))


@router.get("/overview/export.csv")
def export_csv_overview(
    scope: str = "all",
    _user: CurrentUser = Depends(require_manager),
    db: Session = Depends(get_session),
) -> StreamingResponse:
    scope = _normalize_scope(scope)
    rows = reliability_svc.export_rows_scoped(db, scope)
    columns = [
        "match_id",
        "candidate_id",
        "position_id",
        "position_name",
        "sim_score",
        "baseline_score",
        "delta",
        "band",
        "gender",
        "age_band",
        "education_tier",
        "finished_at",
    ]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for r in rows:
        writer.writerow(r)
    buf.seek(0)
    filename = f"audit_overview_{scope}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/positions/{position_id}/reliability")
def get_reliability(
    position_id: str,
    _user: CurrentUser = Depends(require_manager),
    db: Session = Depends(get_session),
) -> dict[str, Any]:
    pos = _load_position(db, position_id)
    _require_feature(pos)
    return reliability_svc.reliability_report(db, position_id)


@router.get("/positions/{position_id}/fairness")
def get_fairness(
    position_id: str,
    _user: CurrentUser = Depends(require_manager),
    db: Session = Depends(get_session),
) -> dict[str, Any]:
    pos = _load_position(db, position_id)
    _require_feature(pos)
    return reliability_svc.fairness_report(db, position_id)


@router.get("/positions/{position_id}/export.csv")
def export_csv(
    position_id: str,
    _user: CurrentUser = Depends(require_manager),
    db: Session = Depends(get_session),
) -> StreamingResponse:
    pos = _load_position(db, position_id)
    _require_feature(pos)
    rows = reliability_svc.export_rows(db, position_id)
    columns = [
        "match_id",
        "candidate_id",
        "position_id",
        "sim_score",
        "baseline_score",
        "delta",
        "band",
        "gender",
        "age_band",
        "education_tier",
        "finished_at",
    ]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for r in rows:
        writer.writerow(r)
    buf.seek(0)
    filename = f"audit_{position_id}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
