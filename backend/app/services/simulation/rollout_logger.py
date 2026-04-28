"""Append-only event log writer for rollout execution.

All simulation events (rollout_started, turn_completed, rollout_ended,
judge_scored, cost_exceeded) are persisted as RolloutLog rows.  The table has
SQLAlchemy-level guards that prevent updates and deletes.
"""
from __future__ import annotations

from typing import Any, TYPE_CHECKING

from ...models import RolloutLog

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def log_event(
    match_id: str,
    rollout_id: str | None,
    event_type: str,
    payload: dict[str, Any],
    *,
    db: "AsyncSession",
) -> None:
    """Append a single event row to rollout_logs.

    Deliberately fire-and-forget from the caller's perspective — the caller
    should not depend on the returned row.  Uses the session's own transaction;
    the caller is responsible for committing.
    """
    row = RolloutLog(
        match_id=match_id,
        rollout_id=rollout_id,
        event_type=event_type,
        payload=payload,
    )
    db.add(row)
