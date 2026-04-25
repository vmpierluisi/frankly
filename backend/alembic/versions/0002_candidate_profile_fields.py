"""Add candidate profile fields for auth + artefacts.

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-25
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("candidates", sa.Column("auth_user_id", sa.String(64), nullable=True))
    op.create_unique_constraint("uq_candidates_auth_user_id", "candidates", ["auth_user_id"])
    op.create_index("ix_candidates_auth_user_id", "candidates", ["auth_user_id"], unique=True)

    op.add_column("candidates", sa.Column("cv_path", sa.String(512), nullable=True))
    op.add_column("candidates", sa.Column("linkedin_url", sa.String(500), nullable=True))
    op.add_column("candidates", sa.Column("github_url", sa.String(500), nullable=True))
    op.add_column(
        "candidates",
        sa.Column(
            "assessment_status",
            sa.String(20),
            nullable=False,
            server_default="pending",
        ),
    )
    op.add_column(
        "candidates",
        sa.Column("is_seed", sa.Boolean, nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_column("candidates", "is_seed")
    op.drop_column("candidates", "assessment_status")
    op.drop_column("candidates", "github_url")
    op.drop_column("candidates", "linkedin_url")
    op.drop_column("candidates", "cv_path")
    op.drop_index("ix_candidates_auth_user_id", "candidates")
    op.drop_constraint("uq_candidates_auth_user_id", "candidates")
    op.drop_column("candidates", "auth_user_id")
