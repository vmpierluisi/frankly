"""Roadmap 2 / PR #6 — reliability + fairness audit panel.

Two columns to power the recruiter-only audit surface:

  * ``organizations.reliability_audit_enabled`` — feature toggle exposed
    in Org Settings. Audit endpoints respect it.
  * ``candidates.demographics`` — opt-in, self-reported JSON bag the
    candidate fills at intake (gender, age_band, education_tier). The
    fairness panel reads from this column only; never inferred.

Revision ID: 0016
Revises: 0015
Create Date: 2026-05-11
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0016"
down_revision: Union[str, None] = "0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column(
            "reliability_audit_enabled",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "candidates",
        sa.Column("demographics", sa.JSON, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("candidates", "demographics")
    op.drop_column("organizations", "reliability_audit_enabled")
