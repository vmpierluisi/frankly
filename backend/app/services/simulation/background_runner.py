"""Background task runner for simulation matches.

Single-worker uvicorn only. All coordination is in-process asyncio.
For multi-worker/multi-process deployments, replace with RQ/Redis.

Usage:
    background_runner.schedule(match_id)   # non-blocking, returns immediately
    await background_runner.shutdown()     # graceful drain (call from lifespan)
    await background_runner.sweep_pending() # re-spawn stale pending rows on startup
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone, timedelta

from ...db import SessionLocal
from ... import models

logger = logging.getLogger(__name__)

_tasks: dict[str, asyncio.Task] = {}


def schedule(match_id: str) -> None:
    """Enqueue a background simulation for match_id. Non-blocking."""
    if match_id in _tasks and not _tasks[match_id].done():
        return
    task = asyncio.create_task(_run_match_background(match_id), name=f"sim-{match_id[:8]}")
    _tasks[match_id] = task
    task.add_done_callback(lambda t: _tasks.pop(match_id, None))


async def _run_match_background(match_id: str) -> None:
    from ..simulation import simulation_matcher

    with SessionLocal() as db:
        match = db.get(models.Match, match_id)
        if match is None:
            logger.warning("background_runner: match %s not found", match_id)
            return

        candidate = db.get(models.Candidate, match.candidate_id)
        company = db.get(models.Position, match.position_id)

        if candidate is None or company is None:
            logger.error("background_runner: missing candidate/company for match %s", match_id)
            _mark_failed(db, match, "candidate or company not found")
            return

        match.status = "running"
        match.started_at = datetime.now(timezone.utc)
        db.commit()

    with SessionLocal() as db:
        match = db.get(models.Match, match_id)
        candidate = db.get(models.Candidate, match.candidate_id)
        company = db.get(models.Position, match.position_id)

        try:
            from ...config import settings
            k = 1 if settings.sim_fast_mode else None  # None → use default

            kwargs = dict(match_id=match.id, candidate=candidate, company=company, db=db)
            if k is not None:
                kwargs["k_per_scenario"] = k

            report = await asyncio.wait_for(
                simulation_matcher.run_match(**kwargs),
                timeout=settings.sim_match_wall_timeout_s,
            )
            match.report = report
            match.overall_score = int(report.get("overallScore", 0))
            match.band = report.get("band", "")
            match.band_note = report.get("bandNote", "")
            match.status = "succeeded"
            match.finished_at = datetime.now(timezone.utc)
            db.commit()
            logger.info("background_runner: match %s succeeded (score=%d)", match_id, match.overall_score)

            # PR #5 — fire-and-forget calibration sampling. Best-effort: any
            # failure is logged inside the helper and never crashes the match.
            asyncio.create_task(_run_calibration_sample(match_id))
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            with SessionLocal() as err_db:
                err_match = err_db.get(models.Match, match_id)
                if err_match:
                    _mark_failed(err_db, err_match, str(exc))
            logger.error("background_runner: match %s failed — %s", match_id, exc)


async def _run_calibration_sample(match_id: str) -> None:
    """PR #5 — sample calibration prompts after a match succeeds.

    Runs in its own session so it doesn't ride on the match's transaction.
    Best-effort: failures are logged, never re-raised.
    """
    try:
        from ..calibration import sample_after_match
    except Exception as exc:  # noqa: BLE001
        logger.warning("calibration import failed: %s", exc)
        return
    with SessionLocal() as db:
        try:
            await sample_after_match(db=db, match_id=match_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("calibration sample failed for match %s: %s", match_id, exc)


def _mark_failed(db, match: models.Match, reason: str) -> None:
    match.status = "failed"
    match.error_message = reason[:500]
    match.finished_at = datetime.now(timezone.utc)
    db.commit()


async def shutdown() -> None:
    """Gracefully drain in-flight tasks (call from FastAPI lifespan on shutdown)."""
    if not _tasks:
        return
    logger.info("background_runner: waiting for %d in-flight tasks…", len(_tasks))
    await asyncio.wait(list(_tasks.values()), timeout=30)


async def sweep_pending(stale_after_seconds: int = 60) -> None:
    """Re-spawn Match rows stuck in 'pending' (crash recovery on startup)."""
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=stale_after_seconds)
    with SessionLocal() as db:
        from sqlalchemy import select
        rows = db.execute(
            select(models.Match).where(
                models.Match.status == "pending",
                models.Match.created_at < cutoff,
            )
        ).scalars().all()
        ids = [r.id for r in rows]

    for match_id in ids:
        logger.info("background_runner: re-spawning stale pending match %s", match_id)
        schedule(match_id)
