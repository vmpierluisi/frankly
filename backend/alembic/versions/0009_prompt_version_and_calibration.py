"""Roadmap 2 / PR #1: prompt versioning + calibration responses scaffold.

Adds infrastructure for backtesting + the future calibration loop (PR #5):

  * ``rollouts.prompt_version`` and ``rollout_scores.prompt_version`` —
    populated from a constant in code (``simulation.PROMPT_VERSION``).
    Bumped per material prompt change so analytics can group by version
    and avoid mixing pre/post-tuning rollouts.

  * ``calibration_responses`` — schema only. PR #5 fills in the sampling
    job, MCQ generation, and candidate-side UX. Adding the table now
    means historical rollouts (tagged by prompt_version) can be paired
    against future calibrations without schema churn.

Revision ID: 0009
Revises: 0008
Create Date: 2026-05-03
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---- Prompt version tagging on rollouts + scores -----------------------
    op.add_column(
        "rollouts",
        sa.Column(
            "prompt_version",
            sa.String(40),
            nullable=False,
            server_default="legacy",
        ),
    )
    op.add_column(
        "rollout_scores",
        sa.Column(
            "prompt_version",
            sa.String(40),
            nullable=False,
            server_default="legacy",
        ),
    )
    op.create_index(
        "ix_rollouts_prompt_version",
        "rollouts",
        ["prompt_version"],
    )
    op.create_index(
        "ix_rollout_scores_prompt_version",
        "rollout_scores",
        ["prompt_version"],
    )

    # ---- Calibration responses (PR #5 fills in behavior) -------------------
    op.create_table(
        "calibration_responses",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "candidate_id",
            sa.String(36),
            sa.ForeignKey("candidates.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "rollout_id",
            sa.String(36),
            sa.ForeignKey("rollouts.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "scenario_id",
            sa.String(36),
            sa.ForeignKey("moments_of_truth.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        # The agent response we're calibrating against (paraphrased / verbatim).
        sa.Column("agent_response_text", sa.Text, nullable=False, server_default=""),
        # The 4 MCQ options shown to the candidate, with order randomized.
        # Each item: { "text": str, "is_agent_answer": bool, "skill_level": str }.
        sa.Column("mcq_options", sa.JSON, nullable=False, server_default="[]"),
        # Index into mcq_options the candidate selected (nullable when free-
        # text-only mode was used because the rollout had low confidence).
        sa.Column("candidate_selection_index", sa.Integer, nullable=True),
        sa.Column("candidate_free_text", sa.Text, nullable=True),
        # 0.0-1.0 divergence: 0 = candidate matched the agent's choice,
        # 1 = total mismatch. Computed at submission.
        sa.Column("divergence_score", sa.Float, nullable=True),
        # Mode the candidate was sampled into: "mcq_plus_text" or "free_text_only".
        sa.Column("mode", sa.String(40), nullable=False, server_default="mcq_plus_text"),
        # Prompt version of the rollout being calibrated against — lets us
        # exclude calibrations whose underlying rollout used outdated prompts.
        sa.Column("prompt_version", sa.String(40), nullable=False, server_default="legacy"),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column(
            "created_at", sa.DateTime, nullable=False, server_default=sa.func.now()
        ),
        sa.Column("submitted_at", sa.DateTime, nullable=True),
    )


def downgrade() -> None:
    op.drop_table("calibration_responses")
    op.drop_index("ix_rollout_scores_prompt_version", table_name="rollout_scores")
    op.drop_index("ix_rollouts_prompt_version", table_name="rollouts")
    op.drop_column("rollout_scores", "prompt_version")
    op.drop_column("rollouts", "prompt_version")
