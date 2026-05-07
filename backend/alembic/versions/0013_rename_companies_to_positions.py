"""Rename ``companies`` table to ``positions`` and ``matches.company_id`` to
``position_id``.

Roadmap 2 / PR #2d.4.c — naming + cleanup pass. After PR #2d shipped the
three-tier hierarchy (Organization → Team → Position), the ``companies``
table was a Position in everything but name. This migration completes the
rename so the model + database are honest. Code-side rename happens in
the same PR.

Postgres auto-renames the column-backing index when a table is renamed,
but FK / PK constraint names are kept stable here (we don't touch them)
because nothing in the codebase references them by literal name.

Revision ID: 0013
Revises: 0012
Create Date: 2026-05-06
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.rename_table("companies", "positions")
    op.alter_column(
        "matches",
        "company_id",
        new_column_name="position_id",
    )
    op.alter_column(
        "criteria",
        "company_id",
        new_column_name="position_id",
    )


def downgrade() -> None:
    op.alter_column(
        "criteria",
        "position_id",
        new_column_name="company_id",
    )
    op.alter_column(
        "matches",
        "position_id",
        new_column_name="company_id",
    )
    op.rename_table("positions", "companies")
