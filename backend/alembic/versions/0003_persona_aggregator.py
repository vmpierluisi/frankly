"""Persona aggregator cache columns on candidates.

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-28
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("candidates", sa.Column("aggregated_persona", sa.JSON, nullable=True))
    op.add_column("candidates", sa.Column("aggregation_audit", sa.JSON, nullable=True))
    op.add_column("candidates", sa.Column("aggregated_at", sa.DateTime, nullable=True))


def downgrade() -> None:
    op.drop_column("candidates", "aggregated_at")
    op.drop_column("candidates", "aggregation_audit")
    op.drop_column("candidates", "aggregated_persona")
