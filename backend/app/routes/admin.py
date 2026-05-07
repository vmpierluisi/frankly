"""Admin endpoints — validation, log export, bias audit.

Auth: all routes require ``Authorization: Bearer <admin_password>``.
No manager JWT involved — this is a separate ops-only credential.
"""
from __future__ import annotations

import csv
import io
import json
import math
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..config import settings
from ..db import get_session

router = APIRouter(prefix="/admin", tags=["admin"])


# ---------------------------------------------------------------------------
# Auth helper
# ---------------------------------------------------------------------------

def _require_admin(authorization: str = Header(default="")) -> None:
    """Raise 401 if the Bearer token doesn't match admin_password."""
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or token != settings.admin_password:
        raise HTTPException(status_code=401, detail="Invalid admin credentials")


# ---------------------------------------------------------------------------
# Statistics helpers (no scipy dependency)
# ---------------------------------------------------------------------------

def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _pearson(xs: list[float], ys: list[float]) -> float:
    n = len(xs)
    if n < 2:
        return 0.0
    mx, my = _mean(xs), _mean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if dx == 0 or dy == 0:
        return 0.0
    return num / (dx * dy)


def _rank(xs: list[float]) -> list[float]:
    """Return average ranks (1-based) for each element."""
    sorted_pairs = sorted(enumerate(xs), key=lambda p: p[1])
    ranks = [0.0] * len(xs)
    i = 0
    while i < len(sorted_pairs):
        j = i
        while j < len(sorted_pairs) - 1 and sorted_pairs[j + 1][1] == sorted_pairs[i][1]:
            j += 1
        avg_rank = (i + j) / 2 + 1  # 1-based average
        for k in range(i, j + 1):
            ranks[sorted_pairs[k][0]] = avg_rank
        i = j + 1
    return ranks


def _spearman(xs: list[float], ys: list[float]) -> float:
    return _pearson(_rank(xs), _rank(ys))


# ---------------------------------------------------------------------------
# POST /admin/validation/retrospective/upload
# ---------------------------------------------------------------------------

@router.post("/validation/retrospective/upload", dependencies=[Depends(_require_admin)])
async def upload_retrospective(
    file: UploadFile = File(...),
    db: Session = Depends(get_session),
) -> dict[str, Any]:
    """Accept a CSV file and create a ValidationRun row."""
    content = await file.read()
    text = content.decode("utf-8", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    rows = [dict(row) for row in reader]

    run = models.ValidationRun(
        name=file.filename or "upload",
        status="pending",
        row_count=len(rows),
        rows=rows,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return {"run_id": run.id, "row_count": run.row_count}


# ---------------------------------------------------------------------------
# POST /admin/validation/retrospective/run/{run_id}
# ---------------------------------------------------------------------------

@router.post("/validation/retrospective/run/{run_id}", dependencies=[Depends(_require_admin)])
async def run_retrospective(
    run_id: str,
    db: Session = Depends(get_session),
) -> dict[str, Any]:
    """Score each CSV row through the baseline matcher and compute correlations."""
    run = db.get(models.ValidationRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="ValidationRun not found")
    if run.status == "running":
        raise HTTPException(status_code=409, detail="Run is already in progress")

    run.status = "running"
    db.commit()

    from ..services.persona import synthesize_persona
    from ..services.baseline_matcher import run_match as baseline_run_match

    rows = run.rows or []
    result_rows: list[dict[str, Any]] = []
    errors: list[str] = []

    for row in rows:
        ext_id = row.get("candidate_id_external", "")
        try:
            bfi = json.loads(row.get("bfi_responses_json") or "{}")
            sjt = json.loads(row.get("sjt_responses_json") or "{}")
        except (json.JSONDecodeError, ValueError) as exc:
            errors.append(f"{ext_id}: bad JSON — {exc}")
            continue

        try:
            performance = float(row.get("performance_rating_12mo") or 0)
        except (ValueError, TypeError):
            performance = 0.0

        hired_raw = str(row.get("hired", "")).strip().lower()
        hired = hired_raw in ("1", "true", "yes", "t")

        try:
            persona = synthesize_persona(bfi, sjt)
            # Build a minimal company dict — use a placeholder since we don't
            # have the company context in a retrospective run.
            company_dict: dict[str, Any] = {
                "id": "retrospective",
                "name": "Retrospective",
                "role": row.get("role", ""),
                "tagline": "",
                "artifact_values": "",
                "artifact_role_spec": "",
                "artifact_team_structure": "",
                "artifact_sample_comms": "",
                "criteria": [],
            }
            import asyncio
            report = await asyncio.wait_for(
                baseline_run_match(persona=persona, company=company_dict),
                timeout=60,
            )
            sim_score = int(report.get("overallScore", 0))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{ext_id}: matcher error — {exc}")
            sim_score = 0

        result_rows.append(
            {
                "external_id": ext_id,
                "sim_score": sim_score,
                "performance_rating": performance,
                "hired": hired,
            }
        )

    # Compute correlations
    sim_scores = [r["sim_score"] for r in result_rows]
    perf_ratings = [r["performance_rating"] for r in result_rows]
    n = len(result_rows)

    pearson_r = _pearson(sim_scores, perf_ratings) if n >= 2 else None
    spearman_r = _spearman(sim_scores, perf_ratings) if n >= 2 else None

    report_dict: dict[str, Any] = {
        "pearson_r": round(pearson_r, 4) if pearson_r is not None else None,
        "spearman_r": round(spearman_r, 4) if spearman_r is not None else None,
        "n": n,
        "mean_sim_score": round(_mean(sim_scores), 2) if sim_scores else None,
        "mean_performance": round(_mean(perf_ratings), 2) if perf_ratings else None,
        "rows": result_rows,
        "errors": errors,
    }

    run.status = "done"
    run.results = report_dict
    db.commit()
    return report_dict


# ---------------------------------------------------------------------------
# GET /admin/validation/retrospective/{run_id}
# ---------------------------------------------------------------------------

@router.get("/validation/retrospective/{run_id}", dependencies=[Depends(_require_admin)])
def get_retrospective(
    run_id: str,
    db: Session = Depends(get_session),
) -> dict[str, Any]:
    run = db.get(models.ValidationRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="ValidationRun not found")
    if run.status != "done":
        return {"status": run.status}
    return run.results or {}


# ---------------------------------------------------------------------------
# GET /admin/validation/bias-audit/{run_id}
# ---------------------------------------------------------------------------

@router.get("/validation/bias-audit/{run_id}", dependencies=[Depends(_require_admin)])
def bias_audit(run_id: str) -> dict[str, Any]:
    return {
        "status": "deferred",
        "note": (
            "Bias audit requires stratification data. "
            "Implement after design partner provides anonymized demographics."
        ),
    }


# ---------------------------------------------------------------------------
# GET /admin/logs/match/{match_id}
# ---------------------------------------------------------------------------

@router.get("/logs/match/{match_id}", dependencies=[Depends(_require_admin)])
def get_match_logs(
    match_id: str,
    db: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    rows = db.execute(
        select(models.RolloutLog)
        .where(models.RolloutLog.match_id == match_id)
        .order_by(models.RolloutLog.created_at)
    ).scalars().all()
    return [
        {
            "id": r.id,
            "match_id": r.match_id,
            "rollout_id": r.rollout_id,
            "event_type": r.event_type,
            "payload": r.payload,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# GET /admin/logs/training-export
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# GET /admin/sim-health
#
# Roadmap 2 / PR #1.11. Backtesting analytics: per-vacancy + per-prompt-version
# rollouts of fidelity scores, retry rates, and judge confidence. Lets the
# operator answer questions like "how many low-fidelity rollouts did we get
# for vacancy X this week?" or "did the latest prompt version actually
# improve fidelity vs the prior one?".
#
# All queries grouped by ``rollouts.prompt_version`` so analytics never mix
# rollouts produced by different prompt scaffolding.
# ---------------------------------------------------------------------------

@router.get("/sim-health", dependencies=[Depends(_require_admin)])
def sim_health(
    position_id: str | None = None,
    prompt_version: str | None = None,
    db: Session = Depends(get_session),
) -> dict[str, Any]:
    """Return aggregate health metrics across recent simulation activity.

    Query parameters
    ----------------
    position_id : optional — filter to a single vacancy.
    prompt_version : optional — filter to a single prompt version.

    Response shape
    --------------
    {
      "filters": {...},
      "totals": { "matches", "rollouts", "rollouts_superseded", ... },
      "fidelity": { "n", "mean", "low_count", "low_rate", "violation_kinds": {...} },
      "criteria_judge_confidence": { "n", "mean" },
      "by_company": [ { position_id, ..., metrics }, ... ],
      "by_prompt_version": [ { prompt_version, ..., metrics }, ... ]
    }
    """
    from collections import Counter

    rollout_q = select(models.Rollout)
    if position_id is not None:
        rollout_q = rollout_q.join(
            models.Match, models.Match.id == models.Rollout.match_id,
        ).where(models.Match.position_id == position_id)
    if prompt_version is not None:
        rollout_q = rollout_q.where(models.Rollout.prompt_version == prompt_version)
    rollouts = db.execute(rollout_q).scalars().all()
    rollout_ids = [r.id for r in rollouts]

    scores: list[models.RolloutScore] = []
    if rollout_ids:
        scores = db.execute(
            select(models.RolloutScore).where(
                models.RolloutScore.rollout_id.in_(rollout_ids),
            )
        ).scalars().all()

    # ---- Top-level metrics ---------------------------------------------------
    fidelity_scores = [
        s for s in scores
        if s.dimension_key == "persona_fidelity" and s.score is not None
    ]
    criterion_scores = [
        s for s in scores
        if s.dimension_key != "persona_fidelity" and s.score is not None
    ]

    fidelity_values = [float(s.score) for s in fidelity_scores]
    fidelity_low = [v for v in fidelity_values if v < 60]

    # Aggregate violation kinds across rollouts that exposed them in final_state.
    violation_kinds: Counter[str] = Counter()
    for r in rollouts:
        fs = (r.final_state or {}).get("persona_fidelity") or {}
        for v in fs.get("violations", []):
            kind = v.get("kind")
            if kind:
                violation_kinds[kind] += 1

    superseded = sum(1 for r in rollouts if r.status == "superseded")

    match_ids = {r.match_id for r in rollouts}

    fidelity_block = {
        "n": len(fidelity_values),
        "mean": round(_mean(fidelity_values), 1) if fidelity_values else None,
        "low_count": len(fidelity_low),
        "low_rate": round(len(fidelity_low) / len(fidelity_values), 3)
            if fidelity_values else None,
        "violation_kinds": dict(violation_kinds),
    }

    criteria_block = {
        "n": len(criterion_scores),
        "mean_confidence": round(
            _mean([float(s.confidence or 0.0) for s in criterion_scores]), 3
        ) if criterion_scores else None,
    }

    totals = {
        "matches": len(match_ids),
        "rollouts": len(rollouts),
        "rollouts_superseded": superseded,
        "retry_rate": round(superseded / len(rollouts), 3) if rollouts else None,
    }

    # ---- Group: by_company ---------------------------------------------------
    by_company: dict[str, dict[str, Any]] = {}
    if rollouts:
        match_company = dict(
            db.execute(
                select(models.Match.id, models.Match.position_id).where(
                    models.Match.id.in_(match_ids)
                )
            ).all()
        )
        scores_by_rollout: dict[str, list[models.RolloutScore]] = {}
        for s in scores:
            scores_by_rollout.setdefault(s.rollout_id, []).append(s)

        for r in rollouts:
            cid = match_company.get(r.match_id, "unknown")
            bucket = by_company.setdefault(cid, {
                "position_id": cid,
                "rollouts": 0,
                "superseded": 0,
                "fidelity_n": 0,
                "fidelity_low": 0,
                "fidelity_sum": 0.0,
            })
            bucket["rollouts"] += 1
            if r.status == "superseded":
                bucket["superseded"] += 1
            for s in scores_by_rollout.get(r.id, []):
                if s.dimension_key == "persona_fidelity" and s.score is not None:
                    bucket["fidelity_n"] += 1
                    bucket["fidelity_sum"] += float(s.score)
                    if s.score < 60:
                        bucket["fidelity_low"] += 1

    company_rows = []
    for c in by_company.values():
        n = c["fidelity_n"]
        company_rows.append({
            "position_id": c["position_id"],
            "rollouts": c["rollouts"],
            "superseded": c["superseded"],
            "fidelity_n": n,
            "fidelity_mean": round(c["fidelity_sum"] / n, 1) if n else None,
            "fidelity_low_count": c["fidelity_low"],
            "fidelity_low_rate": round(c["fidelity_low"] / n, 3) if n else None,
        })
    company_rows.sort(key=lambda x: -x["rollouts"])

    # ---- Group: by_prompt_version -------------------------------------------
    by_pv: dict[str, dict[str, Any]] = {}
    rollout_pv = {r.id: r.prompt_version for r in rollouts}
    for r in rollouts:
        pv = r.prompt_version or "legacy"
        bucket = by_pv.setdefault(pv, {
            "prompt_version": pv,
            "rollouts": 0,
            "superseded": 0,
            "fidelity_n": 0,
            "fidelity_low": 0,
            "fidelity_sum": 0.0,
        })
        bucket["rollouts"] += 1
        if r.status == "superseded":
            bucket["superseded"] += 1
    for s in fidelity_scores:
        pv = rollout_pv.get(s.rollout_id) or "legacy"
        bucket = by_pv.setdefault(pv, {
            "prompt_version": pv, "rollouts": 0, "superseded": 0,
            "fidelity_n": 0, "fidelity_low": 0, "fidelity_sum": 0.0,
        })
        bucket["fidelity_n"] += 1
        bucket["fidelity_sum"] += float(s.score)
        if s.score < 60:
            bucket["fidelity_low"] += 1

    pv_rows = []
    for c in by_pv.values():
        n = c["fidelity_n"]
        pv_rows.append({
            "prompt_version": c["prompt_version"],
            "rollouts": c["rollouts"],
            "superseded": c["superseded"],
            "fidelity_n": n,
            "fidelity_mean": round(c["fidelity_sum"] / n, 1) if n else None,
            "fidelity_low_count": c["fidelity_low"],
            "fidelity_low_rate": round(c["fidelity_low"] / n, 3) if n else None,
        })
    pv_rows.sort(key=lambda x: x["prompt_version"])

    return {
        "filters": {"position_id": position_id, "prompt_version": prompt_version},
        "totals": totals,
        "fidelity": fidelity_block,
        "criteria_judge_confidence": criteria_block,
        "by_company": company_rows,
        "by_prompt_version": pv_rows,
    }


@router.get("/logs/training-export", dependencies=[Depends(_require_admin)])
def training_export(db: Session = Depends(get_session)) -> StreamingResponse:
    """Stream all RolloutLog rows as NDJSON (one JSON object per line)."""

    def _generate():
        rows = db.execute(
            select(models.RolloutLog).order_by(models.RolloutLog.id)
        ).scalars().all()
        for r in rows:
            obj = {
                "id": r.id,
                "match_id": r.match_id,
                "rollout_id": r.rollout_id,
                "event_type": r.event_type,
                "payload": r.payload,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            yield json.dumps(obj) + "\n"

    return StreamingResponse(_generate(), media_type="application/x-ndjson")
