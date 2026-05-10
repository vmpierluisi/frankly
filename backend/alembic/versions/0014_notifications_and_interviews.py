"""Roadmap 2 / PR #4 — notifications + interview scheduling.

Adds two tables that wire up the end-to-end "recruiter wants to interview
this candidate → candidate sees vacancy + responds → recruiter is notified"
flow.

  * ``interviews`` — one row per scheduling thread between a manager and a
    candidate for a specific match. Tracks proposed time slots, the slot
    the candidate eventually picks, an optional counter-proposal, and a
    lightweight free-text message from the candidate.
  * ``notifications`` — bell-icon feed. Holds one row per event the user
    needs to see (invite arrived / response received / counter-proposed).
    ``user_kind`` discriminates candidate vs. manager notifications;
    ``candidate_id`` routes the row when the recipient is a candidate, and
    ``recipient_email`` routes it when the recipient is a manager (managers
    are identified by their Supabase email — there is no ``managers`` table).

The vacancy-reveal rule (candidate sees company/role only after the invite
arrives) is enforced at read time, not at the schema level: the candidate
``Matches`` tab fetches interviews and joins the position's public fields
inline.

Revision ID: 0014
Revises: 0013
Create Date: 2026-05-10
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "interviews",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "match_id",
            sa.String(length=36),
            sa.ForeignKey("matches.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "candidate_id",
            sa.String(length=36),
            sa.ForeignKey("candidates.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "position_id",
            sa.String(length=64),
            sa.ForeignKey("positions.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("recruiter_email", sa.String(length=320), nullable=False, index=True),
        sa.Column("proposed_slots", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("selected_slot", sa.String(length=64), nullable=True),
        sa.Column("counter_slots", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("candidate_message", sa.Text, nullable=False, server_default=""),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="proposed"),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )

    op.create_table(
        "notifications",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_kind", sa.String(length=20), nullable=False, index=True),
        sa.Column(
            "candidate_id",
            sa.String(length=36),
            sa.ForeignKey("candidates.id", ondelete="CASCADE"),
            nullable=True,
            index=True,
        ),
        sa.Column("recipient_email", sa.String(length=320), nullable=True, index=True),
        sa.Column("type", sa.String(length=40), nullable=False),
        sa.Column("payload", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="unread"),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute('ALTER TABLE public."interviews" ENABLE ROW LEVEL SECURITY')
        op.execute('ALTER TABLE public."notifications" ENABLE ROW LEVEL SECURITY')


def downgrade() -> None:
    op.drop_table("notifications")
    op.drop_table("interviews")
