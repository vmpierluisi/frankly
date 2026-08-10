"""Manager Shortlist V7 — triage decisions.

Adds the ``triage_decisions`` table backing the optional manual-swipe flow
(one row per manager × position × candidate). The default auto-shortlist does
not write here; only the Triage page persists rows. Blind matching is
untouched — a decision never notifies the candidate.

``manager_id`` is the Supabase auth identity string (no local users table to
FK against). RLS is enabled to match the rest of our tables (Postgres only).

Revision ID: 0017
Revises: 0016
Create Date: 2026-08-10
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: Union[str, None] = "0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "triage_decisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("manager_id", sa.String(64), nullable=False, index=True),
        sa.Column(
            "position_id",
            sa.String(64),
            sa.ForeignKey("positions.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "candidate_id",
            sa.String(36),
            sa.ForeignKey("candidates.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("decision", sa.String(16), nullable=False),  # "pass" | "shortlist"
        sa.Column(
            "decided_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "manager_id", "position_id", "candidate_id", name="uq_triage_one_per_trio"
        ),
    )

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # Same default-deny RLS posture as the rest of our tables (0012).
        op.execute('ALTER TABLE public."triage_decisions" ENABLE ROW LEVEL SECURITY')


def downgrade() -> None:
    op.drop_table("triage_decisions")
