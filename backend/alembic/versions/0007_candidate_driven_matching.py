"""Add candidate-driven matching columns.

Adds target_role_family + target_seniority to candidates;
role_family, target_seniority, is_open to companies;
status, error_message, started_at, finished_at to matches.

Revision ID: 0007
Revises: 0006
Create Date: 2026-04-30
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("candidates", sa.Column("target_role_family", sa.String(64), nullable=True))
    op.add_column("candidates", sa.Column("target_seniority", sa.String(20), nullable=True))
    op.create_index("ix_candidates_target_role_family", "candidates", ["target_role_family"])
    op.create_index("ix_candidates_target_seniority", "candidates", ["target_seniority"])

    op.add_column("companies", sa.Column("role_family", sa.String(64), nullable=True))
    op.add_column("companies", sa.Column("target_seniority", sa.String(20), nullable=True))
    op.add_column("companies", sa.Column("is_open", sa.Boolean, nullable=False, server_default="1"))
    op.create_index("ix_companies_role_family", "companies", ["role_family"])
    op.create_index("ix_companies_target_seniority", "companies", ["target_seniority"])

    op.add_column("matches", sa.Column("status", sa.String(20), nullable=False, server_default="succeeded"))
    op.add_column("matches", sa.Column("error_message", sa.String(500), nullable=True))
    op.add_column("matches", sa.Column("started_at", sa.DateTime, nullable=True))
    op.add_column("matches", sa.Column("finished_at", sa.DateTime, nullable=True))
    op.create_index("ix_matches_status", "matches", ["status"])


def downgrade() -> None:
    op.drop_index("ix_matches_status", "matches")
    op.drop_column("matches", "finished_at")
    op.drop_column("matches", "started_at")
    op.drop_column("matches", "error_message")
    op.drop_column("matches", "status")

    op.drop_index("ix_companies_target_seniority", "companies")
    op.drop_index("ix_companies_role_family", "companies")
    op.drop_column("companies", "is_open")
    op.drop_column("companies", "target_seniority")
    op.drop_column("companies", "role_family")

    op.drop_index("ix_candidates_target_seniority", "candidates")
    op.drop_index("ix_candidates_target_role_family", "candidates")
    op.drop_column("candidates", "target_seniority")
    op.drop_column("candidates", "target_role_family")
