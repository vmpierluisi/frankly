"""Enable Row-Level Security on every public application table.

Roadmap 2 / hardening pass — addresses the Supabase advisor warning
"RLS Disabled in Public" on all our tables.

Architecture context:
  * The FastAPI backend connects to Postgres using the Supabase
    *service role* secret. Service role bypasses RLS entirely, so
    backend reads/writes work unchanged.
  * The frontend never talks to Postgres directly — every read/write
    goes through the backend's HTTP API, which enforces app-level
    auth (Supabase JWT verification + role gating).
  * Therefore enabling RLS without explicit policies is safe: it
    *adds* defense-in-depth (anyone with the anon key gets nothing)
    without breaking any current code path.

This migration enables RLS on every public table we own. No policies
are added — that's intentional default-deny. If we later expose a
table to authenticated frontend reads, we'll add CREATE POLICY
statements then.

Idempotent: ALTER TABLE ... ENABLE ROW LEVEL SECURITY is safe to run
on a table that already has it enabled.

Revision ID: 0012
Revises: 0011
Create Date: 2026-05-06
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Every application table we own. Keep alphabetised.
_TABLES: tuple[str, ...] = (
    "baseline_comparisons",
    "calibration_responses",
    "candidates",
    "companies",
    "criteria",
    "matches",
    "moments_of_truth",
    "organizations",
    "rollout_logs",
    "rollout_scores",
    "rollouts",
    "synthetic_teammates",
    "teams",
    "validation_runs",
    "verified_profiles",
)


def upgrade() -> None:
    bind = op.get_bind()
    # No-op on SQLite — RLS is a Postgres feature; tests run against in-memory
    # SQLite via Base.metadata.create_all so they never hit this path.
    if bind.dialect.name != "postgresql":
        return
    for tbl in _TABLES:
        op.execute(f'ALTER TABLE public."{tbl}" ENABLE ROW LEVEL SECURITY')


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    for tbl in _TABLES:
        op.execute(f'ALTER TABLE public."{tbl}" DISABLE ROW LEVEL SECURITY')
