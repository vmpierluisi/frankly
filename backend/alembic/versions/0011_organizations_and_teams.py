"""Roadmap 2 / PR #2d: split companies into organizations + teams + positions.

Architectural rename. Each existing ``companies`` row becomes a Position
under a new Organization → Team. The org owns culture (mission,
code_of_conduct, tagline). The team owns the people/artefacts the
simulation actually uses (team_structure, sample_comms, knowledge_graph,
synthetic teammates, scenarios). The position keeps role-specific config
(role, role_family, seniority, criteria, required_skills, role_spec).

Internal note: we do NOT rename the ``companies`` table to ``positions`` in
this migration to keep code blast radius small. The Python class stays
``Company`` and the table stays ``companies`` — it's effectively a
position now. UI surfaces the new naming.

Migration steps:
  1. Create ``organizations`` and ``teams`` tables.
  2. For every existing company, create one Organization + one Team and
     wire FKs.
  3. Move SyntheticTeammates and MomentsOfTruth from ``company_id`` to
     ``team_id`` (rename column, backfill).
  4. Drop the migrated columns from ``companies`` (artifact_values,
     artifact_team_structure, artifact_sample_comms, knowledge_graph,
     tagline, skill_match_weight).

Revision ID: 0011
Revises: 0010
Create Date: 2026-05-04
"""
from __future__ import annotations

from typing import Sequence, Union
import uuid

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    # ---- 1. New tables ----------------------------------------------------
    op.create_table(
        "organizations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("tagline", sa.String(500), nullable=True),
        sa.Column("mission", sa.Text, nullable=False, server_default=""),
        sa.Column("code_of_conduct", sa.Text, nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "teams",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "organization_id",
            sa.String(36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("artifact_team_structure", sa.Text, nullable=False, server_default=""),
        sa.Column("artifact_sample_comms", sa.Text, nullable=False, server_default=""),
        sa.Column("knowledge_graph", sa.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )

    # ---- 2. Add FK columns to companies + dependents -----------------------
    op.add_column(
        "companies",
        sa.Column("organization_id", sa.String(36), nullable=True, index=True),
    )
    op.add_column(
        "companies",
        sa.Column("team_id", sa.String(36), nullable=True, index=True),
    )

    op.add_column(
        "synthetic_teammates",
        sa.Column("team_id", sa.String(36), nullable=True, index=True),
    )
    op.add_column(
        "moments_of_truth",
        sa.Column("team_id", sa.String(36), nullable=True, index=True),
    )

    # ---- 3. Backfill ------------------------------------------------------
    companies_t = sa.table(
        "companies",
        sa.column("id", sa.String),
        sa.column("name", sa.String),
        sa.column("tagline", sa.String),
        sa.column("artifact_values", sa.Text),
        sa.column("artifact_team_structure", sa.Text),
        sa.column("artifact_sample_comms", sa.Text),
        sa.column("knowledge_graph", sa.JSON),
        sa.column("organization_id", sa.String),
        sa.column("team_id", sa.String),
    )
    organizations_t = sa.table(
        "organizations",
        sa.column("id", sa.String),
        sa.column("name", sa.String),
        sa.column("tagline", sa.String),
        sa.column("mission", sa.Text),
        sa.column("code_of_conduct", sa.Text),
    )
    teams_t = sa.table(
        "teams",
        sa.column("id", sa.String),
        sa.column("organization_id", sa.String),
        sa.column("name", sa.String),
        sa.column("artifact_team_structure", sa.Text),
        sa.column("artifact_sample_comms", sa.Text),
        sa.column("knowledge_graph", sa.JSON),
    )
    teammates_t = sa.table(
        "synthetic_teammates",
        sa.column("id", sa.String),
        sa.column("company_id", sa.String),
        sa.column("team_id", sa.String),
    )
    moments_t = sa.table(
        "moments_of_truth",
        sa.column("id", sa.String),
        sa.column("company_id", sa.String),
        sa.column("team_id", sa.String),
    )

    rows = bind.execute(
        sa.select(
            companies_t.c.id,
            companies_t.c.name,
            companies_t.c.tagline,
            companies_t.c.artifact_values,
            companies_t.c.artifact_team_structure,
            companies_t.c.artifact_sample_comms,
            companies_t.c.knowledge_graph,
        )
    ).fetchall()

    for r in rows:
        org_id = str(uuid.uuid4())
        team_id = str(uuid.uuid4())

        bind.execute(
            organizations_t.insert().values(
                id=org_id,
                name=r.name,
                tagline=r.tagline,
                mission=r.artifact_values or "",
                code_of_conduct="",
            )
        )
        bind.execute(
            teams_t.insert().values(
                id=team_id,
                organization_id=org_id,
                name=f"{r.name} core team",
                artifact_team_structure=r.artifact_team_structure or "",
                artifact_sample_comms=r.artifact_sample_comms or "",
                knowledge_graph=r.knowledge_graph,
            )
        )
        bind.execute(
            companies_t.update()
            .where(companies_t.c.id == r.id)
            .values(organization_id=org_id, team_id=team_id)
        )
        bind.execute(
            teammates_t.update()
            .where(teammates_t.c.company_id == r.id)
            .values(team_id=team_id)
        )
        bind.execute(
            moments_t.update()
            .where(moments_t.c.company_id == r.id)
            .values(team_id=team_id)
        )

    # ---- 4. Lock down FKs + drop migrated columns -------------------------
    # SQLite drops + alters are limited; we wrap in batch ops so it works on
    # both Postgres and SQLite (tests use SQLite in-memory via create_all so
    # this branch is mostly relevant for production Postgres).
    with op.batch_alter_table("companies") as batch:
        batch.alter_column("organization_id", existing_type=sa.String(36), nullable=False)
        batch.alter_column("team_id", existing_type=sa.String(36), nullable=False)
        batch.create_foreign_key(
            "fk_companies_organization_id",
            "organizations",
            ["organization_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch.create_foreign_key(
            "fk_companies_team_id",
            "teams",
            ["team_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch.drop_column("tagline")
        batch.drop_column("artifact_values")
        batch.drop_column("artifact_team_structure")
        batch.drop_column("artifact_sample_comms")
        batch.drop_column("knowledge_graph")
        batch.drop_column("skill_match_weight")

    # Drop legacy FKs tolerantly (name may not exist on partial-upgrade DBs).
    op.execute(
        "ALTER TABLE synthetic_teammates "
        "DROP CONSTRAINT IF EXISTS synthetic_teammates_company_id_fkey"
    )
    op.execute(
        "ALTER TABLE moments_of_truth "
        "DROP CONSTRAINT IF EXISTS moments_of_truth_company_id_fkey"
    )

    with op.batch_alter_table("synthetic_teammates") as batch:
        batch.alter_column("team_id", existing_type=sa.String(36), nullable=False)
        batch.create_foreign_key(
            "fk_synthetic_teammates_team_id",
            "teams",
            ["team_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch.drop_column("company_id")

    with op.batch_alter_table("moments_of_truth") as batch:
        batch.alter_column("team_id", existing_type=sa.String(36), nullable=False)
        batch.create_foreign_key(
            "fk_moments_of_truth_team_id",
            "teams",
            ["team_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch.drop_column("company_id")


def downgrade() -> None:
    # Best-effort downgrade: re-add migrated columns and copy data back.
    bind = op.get_bind()

    op.add_column("companies", sa.Column("tagline", sa.String(500), nullable=True))
    op.add_column("companies", sa.Column("artifact_values", sa.Text, nullable=False, server_default=""))
    op.add_column("companies", sa.Column("artifact_team_structure", sa.Text, nullable=False, server_default=""))
    op.add_column("companies", sa.Column("artifact_sample_comms", sa.Text, nullable=False, server_default=""))
    op.add_column("companies", sa.Column("knowledge_graph", sa.JSON, nullable=True))
    op.add_column("companies", sa.Column("skill_match_weight", sa.Float, nullable=False, server_default="0.4"))

    op.add_column("synthetic_teammates", sa.Column("company_id", sa.String(36), nullable=True))
    op.add_column("moments_of_truth", sa.Column("company_id", sa.String(36), nullable=True))

    bind.execute(
        sa.text(
            "UPDATE companies AS c SET "
            " tagline = (SELECT o.tagline FROM organizations o WHERE o.id = c.organization_id), "
            " artifact_values = COALESCE((SELECT o.mission FROM organizations o WHERE o.id = c.organization_id), ''), "
            " artifact_team_structure = COALESCE((SELECT t.artifact_team_structure FROM teams t WHERE t.id = c.team_id), ''), "
            " artifact_sample_comms = COALESCE((SELECT t.artifact_sample_comms FROM teams t WHERE t.id = c.team_id), ''), "
            " knowledge_graph = (SELECT t.knowledge_graph FROM teams t WHERE t.id = c.team_id)"
        )
    )
    bind.execute(
        sa.text(
            "UPDATE synthetic_teammates AS s SET company_id = "
            " (SELECT c.id FROM companies c WHERE c.team_id = s.team_id LIMIT 1)"
        )
    )
    bind.execute(
        sa.text(
            "UPDATE moments_of_truth AS m SET company_id = "
            " (SELECT c.id FROM companies c WHERE c.team_id = m.team_id LIMIT 1)"
        )
    )

    op.execute(
        "ALTER TABLE synthetic_teammates DROP CONSTRAINT IF EXISTS fk_synthetic_teammates_team_id"
    )
    op.execute(
        "ALTER TABLE moments_of_truth DROP CONSTRAINT IF EXISTS fk_moments_of_truth_team_id"
    )
    op.execute("ALTER TABLE companies DROP CONSTRAINT IF EXISTS fk_companies_team_id")
    op.execute("ALTER TABLE companies DROP CONSTRAINT IF EXISTS fk_companies_organization_id")

    with op.batch_alter_table("synthetic_teammates") as batch:
        batch.drop_column("team_id")
    with op.batch_alter_table("moments_of_truth") as batch:
        batch.drop_column("team_id")
    with op.batch_alter_table("companies") as batch:
        batch.drop_column("team_id")
        batch.drop_column("organization_id")

    op.drop_table("teams")
    op.drop_table("organizations")
