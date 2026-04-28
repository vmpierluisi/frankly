"""Simulation pipeline tables: teammates, scenarios, rollouts, scoring, logs.

Revision ID: 0005
Revises: 0004
Create Date: 2026-04-28
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---- synthetic_teammates ----
    op.create_table(
        "synthetic_teammates",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("company_id", sa.String(64), sa.ForeignKey("companies.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("role_on_team", sa.String(200), nullable=False),
        sa.Column("seniority", sa.String(20), nullable=False),
        sa.Column("trait_sheet", sa.JSON, nullable=False),
        sa.Column("narrative", sa.Text, nullable=False, server_default=""),
        sa.Column("private_goals", sa.JSON, nullable=False),
        sa.Column("generated_from", sa.JSON, nullable=True),
        sa.Column("is_edited", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("ordering", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )

    # ---- moments_of_truth ----
    op.create_table(
        "moments_of_truth",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("company_id", sa.String(64), sa.ForeignKey("companies.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("scenario_type", sa.String(20), nullable=False),  # dyad | small_group | written
        sa.Column("prompt", sa.Text, nullable=False),
        sa.Column("candidate_role", sa.Text, nullable=False),
        sa.Column("expected_arc", sa.Text, nullable=False),
        sa.Column("scoring_dims", sa.JSON, nullable=False),
        sa.Column("participating_roles", sa.JSON, nullable=False),
        sa.Column("max_turns", sa.Integer, nullable=False, server_default="6"),
        sa.Column("grounding", sa.Text, nullable=False, server_default=""),
        sa.Column("is_llm_drafted", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("ordering", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )

    # ---- rollouts ----
    op.create_table(
        "rollouts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("match_id", sa.String(36), sa.ForeignKey("matches.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("scenario_id", sa.String(36), sa.ForeignKey("moments_of_truth.id", ondelete="SET NULL"), index=True, nullable=True),
        sa.Column("rollout_index", sa.Integer, nullable=False),
        sa.Column("transcript", sa.JSON, nullable=False),
        sa.Column("final_state", sa.JSON, nullable=False),
        sa.Column("duration_turns", sa.Integer, nullable=False, server_default="0"),
        sa.Column("seed", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="completed"),
        sa.Column("failure_reason", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )

    # ---- rollout_scores ----
    op.create_table(
        "rollout_scores",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("rollout_id", sa.String(36), sa.ForeignKey("rollouts.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("dimension_key", sa.String(80), nullable=False),
        sa.Column("score", sa.Integer, nullable=True),
        sa.Column("justification", sa.Text, nullable=False, server_default=""),
        sa.Column("evidence_turns", sa.JSON, nullable=False),
        sa.Column("judge_model", sa.String(120), nullable=False),
        sa.Column("judge_seed_index", sa.Integer, nullable=False, server_default="0"),
        sa.Column("confidence", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_rollout_scores_dim", "rollout_scores", ["rollout_id", "dimension_key"])

    # ---- baseline_comparisons ----
    op.create_table(
        "baseline_comparisons",
        sa.Column("match_id", sa.String(36), sa.ForeignKey("matches.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("overall_score", sa.Integer, nullable=False),
        sa.Column("per_criterion", sa.JSON, nullable=False),
        sa.Column("band", sa.String(40), nullable=False, server_default=""),
        sa.Column("band_note", sa.Text, nullable=False, server_default=""),
        sa.Column("delta_vs_sim", sa.JSON, nullable=False),
        sa.Column("robustness_summary", sa.Text, nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )

    # ---- rollout_logs (append-only event store) ----
    op.create_table(
        "rollout_logs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("match_id", sa.String(36), sa.ForeignKey("matches.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("rollout_id", sa.String(36), sa.ForeignKey("rollouts.id", ondelete="CASCADE"), index=True, nullable=True),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("payload", sa.JSON, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now(), index=True),
    )


def downgrade() -> None:
    op.drop_table("rollout_logs")
    op.drop_table("baseline_comparisons")
    op.drop_index("ix_rollout_scores_dim", table_name="rollout_scores")
    op.drop_table("rollout_scores")
    op.drop_table("rollouts")
    op.drop_table("moments_of_truth")
    op.drop_table("synthetic_teammates")
