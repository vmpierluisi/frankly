"""SQLAlchemy ORM models.

Design notes
------------
* Candidates have PERSISTENT profiles. Raw BFI/SJT responses are stored so that
  future behavioral-residue inputs (portfolio, LinkedIn, etc.) can be layered on
  without re-running the quiz.
* Persona is NOT stored. It is synthesized server-side at match time because it
  depends on the company being matched against (the criteria surface matters).
* Company artifacts are always stored as text regardless of upload source
  (paste vs PDF vs DOCX); the parser normalizes before persistence.
* Criteria live in their own table so template setup can edit weights
  individually without rewriting the company row.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, JSON, event
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ----------------------------------------------------------------------------
# Candidates
# ----------------------------------------------------------------------------
class Candidate(Base):
    __tablename__ = "candidates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)

    # Supabase auth identity (null for anonymous / seeded candidates).
    auth_user_id: Mapped[str | None] = mapped_column(
        String(64), unique=True, nullable=True, index=True, default=None
    )

    display_name: Mapped[str | None] = mapped_column(String(200), default=None)
    email: Mapped[str | None] = mapped_column(String(320), default=None)

    # Raw responses — stored so we can re-synthesize later with different logic.
    # bfi_responses: {item_id: 1..5}
    # sjt_responses: {sjt_id: option_id}
    bfi_responses: Mapped[dict] = mapped_column(JSON, default=dict)
    sjt_responses: Mapped[dict] = mapped_column(JSON, default=dict)

    # Cached persona fields purely for the profile-view UX. NOT used for matching —
    # matching re-synthesizes from raw responses in the context of the target
    # company. Stored here so the candidate can revisit the profile page without
    # paying to re-run an LLM call.
    cached_big_five: Mapped[dict | None] = mapped_column(JSON, default=None)
    cached_sjt_signals: Mapped[dict | None] = mapped_column(JSON, default=None)
    cached_inconsistencies: Mapped[list | None] = mapped_column(JSON, default=None)
    cached_narrative: Mapped[str | None] = mapped_column(Text, default=None)

    # Simulation pipeline — aggregated persona cache (Phase 1B+).
    # aggregated_persona: full AggregatedPersona dict consumed by the simulation.
    # aggregation_audit:  slim audit record {evidence_completeness, aggregator_version, ...}.
    # aggregated_at:      timestamp of the last successful aggregation run.
    aggregated_persona: Mapped[dict | None] = mapped_column(JSON, default=None)
    aggregation_audit: Mapped[dict | None] = mapped_column(JSON, default=None)
    aggregated_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)

    # Phase B — profile artefacts
    cv_path: Mapped[str | None] = mapped_column(String(512), default=None)
    linkedin_url: Mapped[str | None] = mapped_column(String(500), default=None)
    github_url: Mapped[str | None] = mapped_column(String(500), default=None)
    # "pending" until BFI+SJT submitted; seeded profiles start as "completed".
    assessment_status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False
    )
    is_seed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow
    )

    matches: Mapped[list["Match"]] = relationship(
        "Match", back_populates="candidate", cascade="all, delete-orphan"
    )


# ----------------------------------------------------------------------------
# Companies + criteria
# ----------------------------------------------------------------------------
class Company(Base):
    __tablename__ = "companies"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    tagline: Mapped[str | None] = mapped_column(String(500), default=None)
    role: Mapped[str] = mapped_column(String(200), nullable=False)

    # Simulation pipeline — extracted knowledge graph (Phase 2A+).
    knowledge_graph: Mapped[dict | None] = mapped_column(JSON, default=None)

    # Four sanctioned artifacts — text form, already parsed.
    artifact_values: Mapped[str] = mapped_column(Text, default="")
    artifact_role_spec: Mapped[str] = mapped_column(Text, default="")
    artifact_team_structure: Mapped[str] = mapped_column(Text, default="")
    artifact_sample_comms: Mapped[str] = mapped_column(Text, default="")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow
    )

    criteria: Mapped[list["Criterion"]] = relationship(
        "Criterion",
        back_populates="company",
        cascade="all, delete-orphan",
        order_by="Criterion.ordering",
    )
    matches: Mapped[list["Match"]] = relationship(
        "Match", back_populates="company", cascade="all, delete-orphan"
    )
    teammates: Mapped[list["SyntheticTeammate"]] = relationship(
        "SyntheticTeammate",
        back_populates="company",
        cascade="all, delete-orphan",
        order_by="SyntheticTeammate.ordering",
    )
    scenarios: Mapped[list["MomentOfTruth"]] = relationship(
        "MomentOfTruth",
        back_populates="company",
        cascade="all, delete-orphan",
        order_by="MomentOfTruth.ordering",
    )


class Criterion(Base):
    __tablename__ = "criteria"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )

    # camelCase key used in scoring/signals aggregation (e.g. "analyticalRigor").
    key: Mapped[str] = mapped_column(String(80), nullable=False)
    # Human label shown in UI (e.g. "Analytical Rigor").
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    weight: Mapped[float] = mapped_column(Float, default=0.0)
    ordering: Mapped[int] = mapped_column(Integer, default=0)

    company: Mapped[Company] = relationship("Company", back_populates="criteria")


# ----------------------------------------------------------------------------
# Matches
# ----------------------------------------------------------------------------
class Match(Base):
    __tablename__ = "matches"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    candidate_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("candidates.id", ondelete="CASCADE"), index=True
    )
    company_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )

    overall_score: Mapped[int] = mapped_column(Integer, default=0)
    band: Mapped[str] = mapped_column(String(40), default="")
    band_note: Mapped[str] = mapped_column(Text, default="")

    # Full report JSON as returned by the matcher — criterionScores,
    # inconsistencyFlags, auditTrail, the whole envelope.
    report: Mapped[dict] = mapped_column(JSON, default=dict)

    # Mutual opt-in bookkeeping (stubs in v0).
    candidate_opt_in: Mapped[bool | None] = mapped_column(default=None)
    manager_opt_in: Mapped[bool | None] = mapped_column(default=None)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    candidate: Mapped[Candidate] = relationship("Candidate", back_populates="matches")
    company: Mapped[Company] = relationship("Company", back_populates="matches")


# ----------------------------------------------------------------------------
# Simulation pipeline — synthetic team
# ----------------------------------------------------------------------------
class SyntheticTeammate(Base):
    __tablename__ = "synthetic_teammates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    company_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("companies.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    role_on_team: Mapped[str] = mapped_column(String(200), nullable=False)
    seniority: Mapped[str] = mapped_column(String(20), nullable=False)
    trait_sheet: Mapped[dict] = mapped_column(JSON, nullable=False)
    narrative: Mapped[str] = mapped_column(Text, nullable=False, default="")
    private_goals: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    generated_from: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=None)
    is_edited: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    ordering: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)

    company: Mapped["Company"] = relationship("Company", back_populates="teammates")


# ----------------------------------------------------------------------------
# Simulation pipeline — scenario library (stub; Phase 3A wires the service)
# ----------------------------------------------------------------------------
class MomentOfTruth(Base):
    __tablename__ = "moments_of_truth"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    company_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("companies.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    scenario_type: Mapped[str] = mapped_column(String(20), nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    candidate_role: Mapped[str] = mapped_column(Text, nullable=False)
    expected_arc: Mapped[str] = mapped_column(Text, nullable=False)
    scoring_dims: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    participating_roles: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    max_turns: Mapped[int] = mapped_column(Integer, nullable=False, default=6)
    grounding: Mapped[str] = mapped_column(Text, nullable=False, default="")
    is_llm_drafted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    ordering: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)

    company: Mapped["Company"] = relationship("Company", back_populates="scenarios")


# ----------------------------------------------------------------------------
# Simulation pipeline — rollout execution (stub; Phase 4A wires the service)
# ----------------------------------------------------------------------------
class Rollout(Base):
    __tablename__ = "rollouts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    match_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("matches.id", ondelete="CASCADE"), index=True, nullable=False
    )
    scenario_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("moments_of_truth.id", ondelete="SET NULL"), index=True, nullable=True
    )
    rollout_index: Mapped[int] = mapped_column(Integer, nullable=False)
    transcript: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    final_state: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    duration_turns: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    seed: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="completed")
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class RolloutScore(Base):
    __tablename__ = "rollout_scores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rollout_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("rollouts.id", ondelete="CASCADE"), index=True, nullable=False
    )
    dimension_key: Mapped[str] = mapped_column(String(80), nullable=False)
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    justification: Mapped[str] = mapped_column(Text, nullable=False, default="")
    evidence_turns: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    judge_model: Mapped[str] = mapped_column(String(120), nullable=False)
    judge_seed_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


# ----------------------------------------------------------------------------
# Simulation pipeline — baseline coexistence (stub; Phase 4C wires the service)
# ----------------------------------------------------------------------------
class BaselineComparison(Base):
    __tablename__ = "baseline_comparisons"

    match_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("matches.id", ondelete="CASCADE"), primary_key=True
    )
    overall_score: Mapped[int] = mapped_column(Integer, nullable=False)
    per_criterion: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    band: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    band_note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    delta_vs_sim: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    robustness_summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


# ----------------------------------------------------------------------------
# Simulation pipeline — append-only event log
# ----------------------------------------------------------------------------
class RolloutLog(Base):
    __tablename__ = "rollout_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    match_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("matches.id", ondelete="CASCADE"), index=True, nullable=False
    )
    rollout_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("rollouts.id", ondelete="CASCADE"), index=True, nullable=True
    )
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


@event.listens_for(RolloutLog, "before_update")
def _block_rollout_log_update(mapper, connection, target):
    raise RuntimeError("RolloutLog rows are append-only — updates are not permitted.")


@event.listens_for(RolloutLog, "before_delete")
def _block_rollout_log_delete(mapper, connection, target):
    raise RuntimeError("RolloutLog rows are append-only — deletes are not permitted.")
