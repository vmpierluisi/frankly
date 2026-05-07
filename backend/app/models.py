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
    portfolio_url: Mapped[str | None] = mapped_column(String(500), default=None)
    # "pending" until BFI+SJT submitted; seeded profiles start as "completed".
    assessment_status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False
    )
    is_seed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Candidate-driven matching — declared job target set at intake completion.
    target_role_family: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True, default=None
    )
    target_seniority: Mapped[str | None] = mapped_column(
        String(20), nullable=True, index=True, default=None
    )

    # Roadmap 2 / PR #2a — single 0..100 number powering the candidate
    # Overview "How well we know you" ring. Default 0; PR #5 calibration loop
    # increments as evidence accumulates.
    profile_accuracy_score: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow
    )

    matches: Mapped[list["Match"]] = relationship(
        "Match", back_populates="candidate", cascade="all, delete-orphan"
    )
    verified_profile: Mapped["VerifiedProfile | None"] = relationship(
        "VerifiedProfile",
        back_populates="candidate",
        cascade="all, delete-orphan",
        uselist=False,
    )


# ----------------------------------------------------------------------------
# Verified profile — structured extraction from CV / Github / portfolio.
# Public fields (experience, skills, education, github_repos) are exposed to
# both candidate and recruiter. Internal fields (capability_ledger,
# communication_ledger, voice_samples) are scaffolding for the agent prompt
# and never returned to candidates or recruiters.
# ----------------------------------------------------------------------------
class VerifiedProfile(Base):
    __tablename__ = "verified_profiles"

    candidate_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("candidates.id", ondelete="CASCADE"),
        primary_key=True,
    )

    education: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    experience: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    skills: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    github_repos: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    # Internal scaffolding for the simulation agent. NEVER returned via public API.
    capability_ledger: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    communication_ledger: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    voice_samples: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    # Audit / provenance.
    edited_fields: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    source_versions: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    extracted_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow
    )

    candidate: Mapped[Candidate] = relationship(
        "Candidate", back_populates="verified_profile"
    )


# ----------------------------------------------------------------------------
# Roadmap 2 / PR #2d — three-tier hierarchy:
#   Organization  → owns culture (mission, code_of_conduct, tagline).
#   Team          → owns the people + scenarios the simulation uses
#                   (synthetic teammates, scenarios, team_structure,
#                   sample_comms, knowledge_graph).
#   Company (Position internally) → owns role-specific config
#                   (role title, role_family, seniority, criteria,
#                   required_skills, role_spec).
#
# Note: the table is still named ``companies`` and the class still ``Company``
# to keep the diff small. UI surfaces this entity as "Position" everywhere.
# ----------------------------------------------------------------------------
class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    tagline: Mapped[str | None] = mapped_column(String(500), default=None)
    mission: Mapped[str] = mapped_column(Text, nullable=False, default="")
    code_of_conduct: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow
    )

    teams: Mapped[list["Team"]] = relationship(
        "Team",
        back_populates="organization",
        cascade="all, delete-orphan",
        order_by="Team.created_at",
    )


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organization_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    artifact_team_structure: Mapped[str] = mapped_column(Text, nullable=False, default="")
    artifact_sample_comms: Mapped[str] = mapped_column(Text, nullable=False, default="")
    knowledge_graph: Mapped[dict | None] = mapped_column(JSON, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow
    )

    organization: Mapped[Organization] = relationship(
        "Organization", back_populates="teams"
    )
    positions: Mapped[list["Company"]] = relationship(
        "Company",
        back_populates="team",
        cascade="all, delete-orphan",
        order_by="Company.created_at",
    )
    teammates: Mapped[list["SyntheticTeammate"]] = relationship(
        "SyntheticTeammate",
        back_populates="team",
        cascade="all, delete-orphan",
        order_by="SyntheticTeammate.ordering",
    )
    scenarios: Mapped[list["MomentOfTruth"]] = relationship(
        "MomentOfTruth",
        back_populates="team",
        cascade="all, delete-orphan",
        order_by="MomentOfTruth.ordering",
    )


class Company(Base):
    """⚠️ NAMING DEBT: this class is a *Position*, not a company.

    Kept the legacy name (``Company`` / ``companies`` table) to bound the
    blast radius of the PR #2d schema split. Conceptually:

        Organization → Team → Company (= Position / vacancy)

    Owns role-specific config only — culture/team-structure/teammates
    bubble up via ``self.team`` and ``self.team.organization``.

    Cleanup: ROADMAP_2 PR #2d.4 renames the class + table to ``Position``
    once dual-score (#2d.3) is validated through real usage.
    """
    __tablename__ = "companies"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    organization_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    team_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("teams.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[str] = mapped_column(String(200), nullable=False)

    role_family: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True, default=None
    )
    target_seniority: Mapped[str | None] = mapped_column(
        String(20), nullable=True, index=True, default=None
    )
    is_open: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Roadmap 2 / PR #2a — required skills (list of {skill, level}).
    # PR #2d removed skill_match_weight (we now compute skills_fit and
    # behaviour_fit independently and average them).
    required_skills: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    # Position-only artefact: the role spec text. Other artefacts live on
    # Organization (mission, code_of_conduct) and Team (team_structure,
    # sample_comms).
    artifact_role_spec: Mapped[str] = mapped_column(Text, default="")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow
    )

    organization: Mapped[Organization] = relationship("Organization")
    team: Mapped[Team] = relationship("Team", back_populates="positions")
    criteria: Mapped[list["Criterion"]] = relationship(
        "Criterion",
        back_populates="company",
        cascade="all, delete-orphan",
        order_by="Criterion.ordering",
    )
    matches: Mapped[list["Match"]] = relationship(
        "Match", back_populates="company", cascade="all, delete-orphan"
    )

    def __init__(self, **kwargs):
        """Auto-provision a default Organization + Team when neither is given.

        New callers should explicitly pass ``organization_id`` + ``team_id``
        (or ``organization`` / ``team`` relationship objects). This shim
        only covers the case of building a Position from scratch with no
        prior Org/Team context — used by seed scripts and a small handful
        of test fixtures that don't bring their own hierarchy.
        """
        has_org = ("organization_id" in kwargs) or (kwargs.get("organization") is not None)
        has_team = ("team_id" in kwargs) or (kwargs.get("team") is not None)

        if not has_org:
            kwargs["organization"] = Organization(
                name=kwargs.get("name", "Untitled"),
            )
        if not has_team:
            kwargs["team"] = Team(
                organization=kwargs.get("organization"),
                name=f"{kwargs.get('name', 'team')} core team",
            )
        super().__init__(**kwargs)


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
    # ⚠️ NAMING DEBT: this references a Position (see Company class note).
    # Renames to ``position_id`` in ROADMAP_2 PR #2d.4.
    company_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )

    overall_score: Mapped[int] = mapped_column(Integer, default=0)
    band: Mapped[str] = mapped_column(String(40), default="")
    band_note: Mapped[str] = mapped_column(Text, default="")

    # Full report JSON as returned by the matcher — criterionScores,
    # inconsistencyFlags, auditTrail, the whole envelope.
    report: Mapped[dict] = mapped_column(JSON, default=dict)

    # Candidate-driven matching — lifecycle tracking.
    # Default 'succeeded' keeps backward-compat with rows created before this column.
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="succeeded", index=True
    )
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True, default=None)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=None)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=None)

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
    team_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("teams.id", ondelete="CASCADE"), index=True, nullable=False
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

    team: Mapped["Team"] = relationship("Team", back_populates="teammates")


# ----------------------------------------------------------------------------
# Simulation pipeline — scenario library (stub; Phase 3A wires the service)
# ----------------------------------------------------------------------------
class MomentOfTruth(Base):
    __tablename__ = "moments_of_truth"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    team_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("teams.id", ondelete="CASCADE"), index=True, nullable=False
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

    team: Mapped["Team"] = relationship("Team", back_populates="scenarios")


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
    # Tagged from simulation.PROMPT_VERSION at write time so analytics can
    # group rollouts by the prompt scaffolding that produced them.
    prompt_version: Mapped[str] = mapped_column(
        String(40), nullable=False, default="legacy", index=True
    )
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
    prompt_version: Mapped[str] = mapped_column(
        String(40), nullable=False, default="legacy", index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


# ----------------------------------------------------------------------------
# Calibration responses — schema-only scaffold. Behavior (sampling, MCQ
# generation, candidate UX) lands in PR #5. Adding the table now means
# historical rollouts (tagged with prompt_version) can be paired against
# future calibration data without a migration.
# ----------------------------------------------------------------------------
class CalibrationResponse(Base):
    __tablename__ = "calibration_responses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    candidate_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("candidates.id", ondelete="CASCADE"),
        index=True, nullable=False,
    )
    rollout_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("rollouts.id", ondelete="SET NULL"),
        nullable=True, index=True, default=None,
    )
    scenario_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("moments_of_truth.id", ondelete="SET NULL"),
        nullable=True, index=True, default=None,
    )
    agent_response_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # Each item: {"text": str, "is_agent_answer": bool, "skill_level": str}.
    mcq_options: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    candidate_selection_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    candidate_free_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 0.0 = matched agent; 1.0 = total mismatch. Computed on submission.
    divergence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    # "mcq_plus_text" (default) or "free_text_only" when the rollout had low
    # judge confidence and we chose not to bias the candidate with options.
    mode: Mapped[str] = mapped_column(String(40), nullable=False, default="mcq_plus_text")
    prompt_version: Mapped[str] = mapped_column(
        String(40), nullable=False, default="legacy"
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=None)


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


# ----------------------------------------------------------------------------
# Admin — validation runs
# ----------------------------------------------------------------------------
class ValidationRun(Base):
    __tablename__ = "validation_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(200), default="")
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending | running | done | failed
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    rows: Mapped[dict | None] = mapped_column(JSON, nullable=True)   # uploaded CSV rows as list of dicts
    results: Mapped[dict | None] = mapped_column(JSON, nullable=True) # correlation report
    error: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)
