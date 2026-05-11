"""Roadmap 2 / PR #5 — calibration loop bookkeeping.

The ``calibration_responses`` table itself was scaffolded back in 0009.
This migration tacks on the two columns the PR #5 timeline view needs:

  * ``accuracy_before`` / ``accuracy_after`` — captured at submission so
    the candidate-side "How well we know you" ring can render its
    timeline directly from these rows (no separate audit table required).

Revision ID: 0015
Revises: 0014
Create Date: 2026-05-11
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: Union[str, None] = "0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "calibration_responses",
        sa.Column("accuracy_before", sa.Integer, nullable=True),
    )
    op.add_column(
        "calibration_responses",
        sa.Column("accuracy_after", sa.Integer, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("calibration_responses", "accuracy_after")
    op.drop_column("calibration_responses", "accuracy_before")
