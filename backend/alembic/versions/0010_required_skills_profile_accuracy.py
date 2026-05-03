"""Roadmap 2 / PR #2a: required skills, skill_match_weight, profile_accuracy.

  * ``companies.required_skills`` — JSON list of {"skill": str, "level": str}
    used by FitProfile v3 to compute a skill-match sub-score and by
    persona_aggregator/skill_gap_briefing as a deterministic signal of which
    skills a vacancy actually probes.
  * ``companies.skill_match_weight`` — float in [0, 1]. Fraction of the
    overall fit score driven by skill/education/experience match (vs.
    behavioral simulation). Default 0.4 — edu/skills weighted alongside
    behavior. Configurable per company.
  * ``candidates.profile_accuracy_score`` — 0..100 single number powering
    the candidate Overview "How well we know you" ring. Default 0; PR #5
    (calibration loop) increments as evidence accumulates.

Revision ID: 0010
Revises: 0009
Create Date: 2026-05-03
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "companies",
        sa.Column("required_skills", sa.JSON, nullable=False, server_default="[]"),
    )
    op.add_column(
        "companies",
        sa.Column(
            "skill_match_weight",
            sa.Float,
            nullable=False,
            server_default="0.4",
        ),
    )
    op.add_column(
        "candidates",
        sa.Column(
            "profile_accuracy_score",
            sa.Integer,
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    op.drop_column("candidates", "profile_accuracy_score")
    op.drop_column("companies", "skill_match_weight")
    op.drop_column("companies", "required_skills")
