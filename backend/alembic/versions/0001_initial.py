"""Initial schema — candidates, companies, criteria, matches.

Revision ID: 0001
Revises: None
Create Date: 2026-04-25
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "candidates",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("display_name", sa.String(200), nullable=True),
        sa.Column("email", sa.String(320), nullable=True),
        sa.Column("bfi_responses", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("sjt_responses", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("cached_big_five", sa.JSON, nullable=True),
        sa.Column("cached_sjt_signals", sa.JSON, nullable=True),
        sa.Column("cached_inconsistencies", sa.JSON, nullable=True),
        sa.Column("cached_narrative", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "companies",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("tagline", sa.String(500), nullable=True),
        sa.Column("role", sa.String(200), nullable=False),
        sa.Column("artifact_values", sa.Text, nullable=False, server_default=""),
        sa.Column("artifact_role_spec", sa.Text, nullable=False, server_default=""),
        sa.Column("artifact_team_structure", sa.Text, nullable=False, server_default=""),
        sa.Column("artifact_sample_comms", sa.Text, nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "criteria",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "company_id",
            sa.String(64),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("key", sa.String(80), nullable=False),
        sa.Column("label", sa.String(200), nullable=False),
        sa.Column("description", sa.Text, nullable=False, server_default=""),
        sa.Column("weight", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("ordering", sa.Integer, nullable=False, server_default="0"),
    )
    op.create_index("ix_criteria_company_id", "criteria", ["company_id"])

    op.create_table(
        "matches",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "candidate_id",
            sa.String(36),
            sa.ForeignKey("candidates.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "company_id",
            sa.String(64),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("overall_score", sa.Integer, nullable=False, server_default="0"),
        sa.Column("band", sa.String(40), nullable=False, server_default=""),
        sa.Column("band_note", sa.Text, nullable=False, server_default=""),
        sa.Column("report", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("candidate_opt_in", sa.Boolean, nullable=True),
        sa.Column("manager_opt_in", sa.Boolean, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_matches_candidate_id", "matches", ["candidate_id"])
    op.create_index("ix_matches_company_id", "matches", ["company_id"])


def downgrade() -> None:
    op.drop_table("matches")
    op.drop_table("criteria")
    op.drop_table("companies")
    op.drop_table("candidates")
