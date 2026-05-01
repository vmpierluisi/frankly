"""Add verified_profile table + candidates.portfolio_url.

Phase 1 of verified-profile + persona-fidelity workstream:
structured extraction from CV + Github + portfolio into a sidecar table.

Revision ID: 0008
Revises: 0007
Create Date: 2026-05-01
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("candidates", sa.Column("portfolio_url", sa.String(500), nullable=True))

    op.create_table(
        "verified_profiles",
        sa.Column(
            "candidate_id",
            sa.String(36),
            sa.ForeignKey("candidates.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("education", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("experience", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("skills", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("github_repos", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("capability_ledger", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("communication_ledger", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("voice_samples", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("edited_fields", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("source_versions", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("extracted_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("verified_profiles")
    op.drop_column("candidates", "portfolio_url")
