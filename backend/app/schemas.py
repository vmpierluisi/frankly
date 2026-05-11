"""Pydantic request/response schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# ----------------------------------------------------------------------------
# Psychometric instruments (read-only, served to the frontend quiz)
# ----------------------------------------------------------------------------
class BFIItem(BaseModel):
    id: str
    text: str
    trait: str  # one of O/C/E/A/N
    reverse: bool


class SJTOption(BaseModel):
    id: str
    text: str
    # signal mapping kept server-side ONLY — never leaked to the candidate.
    # The API shape omits it on the public endpoint.


class SJT(BaseModel):
    id: str
    scenario: str
    question: str
    options: list[SJTOption]


class Instruments(BaseModel):
    """Public payload served to /instruments for the quiz UI."""
    bfi: list[BFIItem]
    sjts: list[SJT]


# ----------------------------------------------------------------------------
# Candidates
# ----------------------------------------------------------------------------
class CandidateIntakeIn(BaseModel):
    display_name: str | None = None
    email: str | None = None
    bfi_responses: dict[str, int] = Field(default_factory=dict)
    sjt_responses: dict[str, str] = Field(default_factory=dict)


class InconsistencyFlag(BaseModel):
    type: str
    note: str


class PersonaSummary(BaseModel):
    """Cached persona, shown on profile page. NOT used for matching."""
    big_five: dict[str, float]
    sjt_signals: dict[str, float]
    inconsistencies: list[InconsistencyFlag]
    narrative: str


class CandidateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    display_name: str | None = None
    email: str | None = None
    created_at: datetime
    updated_at: datetime
    persona: PersonaSummary | None = None


class CandidateMeOut(BaseModel):
    """Full self-view for authenticated candidates."""
    model_config = ConfigDict(from_attributes=True)

    id: str
    auth_user_id: str | None = None
    display_name: str | None = None
    email: str | None = None
    cv_path: str | None = None
    linkedin_url: str | None = None
    github_url: str | None = None
    portfolio_url: str | None = None
    assessment_status: str = "pending"
    is_seed: bool = False
    # Roadmap 2 / PR #2a — 0..100 number for the Overview "how well we know
    # you" ring. Default 0; PR #5 calibration loop increments it.
    profile_accuracy_score: int = 0
    # Job targets — set during intake; editable from Settings tab.
    target_role_family: str | None = None
    target_seniority: str | None = None
    created_at: datetime
    updated_at: datetime
    persona: PersonaSummary | None = None


class CandidateMePatchIn(BaseModel):
    display_name: str | None = None
    linkedin_url: str | None = None
    github_url: str | None = None
    portfolio_url: str | None = None
    cv_path: str | None = None
    # Roadmap 2 / PR #2b.1 — let candidates change job targets after intake.
    target_role_family: str | None = None
    target_seniority: str | None = None


class VerifiedProfileOut(BaseModel):
    """Public fields of a verified profile.

    Internal scaffolding (capability_ledger, communication_ledger,
    voice_samples) is intentionally excluded — those drive the simulation
    agent prompt and are never returned to candidates or recruiters.
    """
    candidate_id: str
    experience: list[dict[str, Any]] = Field(default_factory=list)
    education: list[dict[str, Any]] = Field(default_factory=list)
    skills: list[dict[str, Any]] = Field(default_factory=list)
    github_repos: list[dict[str, Any]] = Field(default_factory=list)
    edited_fields: list[str] = Field(default_factory=list)
    extracted_at: datetime
    updated_at: datetime


class VerifiedProfilePatchIn(BaseModel):
    """Partial update to public verified-profile fields.

    Edited fields are tracked in ``edited_fields`` so subsequent
    re-extractions don't clobber the candidate's corrections.
    """
    experience: list[dict[str, Any]] | None = None
    education: list[dict[str, Any]] | None = None
    skills: list[dict[str, Any]] | None = None


class AssessmentSubmitIn(BaseModel):
    bfi_responses: dict[str, int] = Field(default_factory=dict)
    sjt_responses: dict[str, str] = Field(default_factory=dict)
    target_role_family: str | None = None
    target_seniority: str | None = None


class AggregatedPersonaOut(BaseModel):
    """Response for GET/POST /candidates/me/persona endpoints."""
    aggregated_persona: dict[str, Any]
    aggregation_audit: dict[str, Any] | None = None
    aggregated_at: datetime


class CandidateListItem(BaseModel):
    """Slim row for the manager's candidate list."""
    model_config = ConfigDict(from_attributes=True)

    id: str
    display_name: str | None = None
    email: str | None = None
    narrative: str | None = None
    assessment_status: str = "pending"
    is_seed: bool = False
    created_at: datetime


# ----------------------------------------------------------------------------
# Companies
# ----------------------------------------------------------------------------
class CriterionIn(BaseModel):
    key: str
    label: str
    description: str
    weight: float


class CriterionOut(CriterionIn):
    model_config = ConfigDict(from_attributes=True)
    id: int


class RequiredSkill(BaseModel):
    """One row of Company.required_skills.

    level: "junior" | "mid" | "senior" — required proficiency for the
    vacancy. Used by FitProfile v3 skill-match scoring and surfaced in the
    skill-gap briefing prompt for the candidate agent.
    """
    skill: str
    level: str = "mid"


# ----------------------------------------------------------------------------
# Roadmap 2 / PR #2d — Organization + Team schemas.
# ----------------------------------------------------------------------------
class OrganizationIn(BaseModel):
    name: str
    tagline: str | None = None
    mission: str = ""
    code_of_conduct: str = ""


class OrganizationPatch(BaseModel):
    name: str | None = None
    tagline: str | None = None
    mission: str | None = None
    code_of_conduct: str | None = None


class OrganizationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    tagline: str | None = None
    mission: str = ""
    code_of_conduct: str = ""
    created_at: datetime
    updated_at: datetime


class TeamIn(BaseModel):
    name: str
    artifact_team_structure: str = ""
    artifact_sample_comms: str = ""


class TeamPatch(BaseModel):
    name: str | None = None
    artifact_team_structure: str | None = None
    artifact_sample_comms: str | None = None


class TeamOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    organization_id: str
    name: str
    artifact_team_structure: str = ""
    artifact_sample_comms: str = ""
    created_at: datetime
    updated_at: datetime


class PositionOut(BaseModel):
    """Slim list-item view of a position (Company internally).

    Used by ``GET /teams/{team_id}/positions``.
    """
    model_config = ConfigDict(from_attributes=True)

    id: str
    team_id: str
    organization_id: str
    name: str
    role: str
    role_family: str | None = None
    target_seniority: str | None = None
    is_open: bool = True


class OrganizationDetailOut(OrganizationOut):
    teams: list[TeamOut] = Field(default_factory=list)


class TeamDetailOut(TeamOut):
    positions: list[PositionOut] = Field(default_factory=list)


class PositionIn(BaseModel):
    """Position create/update payload.

    PR #2d: Org-level fields (tagline, artifact_values) and team-level
    fields (artifact_team_structure, artifact_sample_comms) used to live
    here. They've moved to Organization / Team. ``team_id`` lets a caller
    create a position under an existing team. When absent, the route's
    legacy fallback auto-creates a fresh Org + Team (compat for the old
    TemplateSetup form).
    """
    id: str | None = None  # caller may supply a slug; otherwise server generates one
    team_id: str | None = None
    name: str
    role: str
    role_family: str | None = None
    target_seniority: str | None = None
    is_open: bool = True
    artifact_role_spec: str = ""
    criteria: list[CriterionIn] = Field(default_factory=list)
    required_skills: list[RequiredSkill] = Field(default_factory=list)

    # ⚠️ DEPRECATED legacy fields — accepted but ignored. PR #2d.4 removes.
    # The old TemplateSetup form still posts these; new flows should use the
    # Org / Team endpoints instead.
    tagline: str | None = None
    artifact_values: str | None = None
    artifact_team_structure: str | None = None
    artifact_sample_comms: str | None = None
    skill_match_weight: float | None = None


class PositionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    organization_id: str
    team_id: str
    name: str
    tagline: str | None = None
    role: str
    role_family: str | None = None
    target_seniority: str | None = None
    is_open: bool = True
    artifact_values: str = ""
    artifact_role_spec: str = ""
    artifact_team_structure: str = ""
    artifact_sample_comms: str = ""
    criteria: list[CriterionOut]
    required_skills: list[RequiredSkill] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class PositionListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    role: str
    tagline: str | None = None
    role_family: str | None = None
    target_seniority: str | None = None
    is_open: bool = True


# ----------------------------------------------------------------------------
# Criteria extraction
# ----------------------------------------------------------------------------
class ExtractCriteriaIn(BaseModel):
    """Free-form artifacts, either already-parsed text or pending parse."""
    artifact_values: str = ""
    artifact_role_spec: str = ""
    artifact_team_structure: str = ""
    artifact_sample_comms: str = ""


class ExtractedCriterion(BaseModel):
    key: str
    label: str
    description: str
    weight: float


class ExtractCriteriaOut(BaseModel):
    criteria: list[ExtractedCriterion]


# ----------------------------------------------------------------------------
# Matches
# ----------------------------------------------------------------------------
class TriggerMatchIn(BaseModel):
    candidate_id: str
    position_id: str


class CriterionScore(BaseModel):
    score: float
    justification: str


class FitReport(BaseModel):
    """The matcher's return shape, mirroring the JSX reference envelope."""
    position_id: str
    company_name: str
    role: str
    overall_score: int
    band: str
    band_note: str
    criterion_scores: dict[str, CriterionScore]
    inconsistency_flags: list[InconsistencyFlag]
    audit_trail: dict[str, Any]


class SearchMatchIn(BaseModel):
    position_id: str
    refresh: bool = False


class FitAxes(BaseModel):
    role: float
    culture: float
    growth: float


class SearchMatchResultItem(BaseModel):
    candidate_id: str
    display_name: str | None = None
    narrative: str | None = None
    overall_score: int
    band: str
    band_note: str
    report: dict[str, Any]
    fit_axes: FitAxes
    cached: bool
    match_id: str | None = None
    is_seed: bool = False


class SearchMatchOut(BaseModel):
    position_id: str
    company_name: str
    role: str
    pool_size: int
    results: list[SearchMatchResultItem]


class MatchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    candidate_id: str
    position_id: str
    overall_score: int
    band: str
    band_note: str
    report: dict[str, Any]
    status: str = "succeeded"
    error_message: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    candidate_opt_in: bool | None = None
    manager_opt_in: bool | None = None
    created_at: datetime


class LeaderboardRow(BaseModel):
    match_id: str
    candidate_id: str
    display_name: str | None = None
    candidate_seniority: str | None = None
    status: str
    overall_score: int
    band: str
    report: dict[str, Any]
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error_message: str | None = None
    # Roadmap 2 / PR #2c — surface profile links so FitProfile v3 can render
    # open-in-new-tab buttons. Hidden client-side when missing.
    cv_path: str | None = None
    linkedin_url: str | None = None
    github_url: str | None = None
    portfolio_url: str | None = None
    profile_accuracy_score: int = 0
    # Roadmap 2 / PR #2d.3 — dual-score columns. None if the position has
    # no required_skills configured (skills_fit can't be computed).
    behaviour_fit: int | None = None
    skills_fit: int | None = None


class LeaderboardOut(BaseModel):
    position_id: str
    company_name: str
    role: str
    role_family: str | None = None
    target_seniority: str | None = None
    is_open: bool
    results: list[LeaderboardRow]


# ----------------------------------------------------------------------------
# Scenario library
# ----------------------------------------------------------------------------
class MomentOfTruthOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    team_id: str
    title: str
    scenario_type: str
    prompt: str
    candidate_role: str
    expected_arc: str
    scoring_dims: list[str]
    participating_roles: list[str]
    max_turns: int
    grounding: str
    is_llm_drafted: bool
    ordering: int
    created_at: datetime
    updated_at: datetime


class MomentOfTruthIn(BaseModel):
    title: str
    scenario_type: str
    prompt: str
    candidate_role: str
    expected_arc: str
    scoring_dims: list[str] = Field(default_factory=list)
    participating_roles: list[str] = Field(default_factory=list)
    max_turns: int = 6
    grounding: str = ""


class MomentOfTruthPatch(BaseModel):
    title: str | None = None
    scenario_type: str | None = None
    prompt: str | None = None
    candidate_role: str | None = None
    expected_arc: str | None = None
    scoring_dims: list[str] | None = None
    participating_roles: list[str] | None = None
    max_turns: int | None = None
    grounding: str | None = None


# ----------------------------------------------------------------------------
# Synthetic team
# ----------------------------------------------------------------------------
class SyntheticTeammateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    team_id: str
    name: str
    role_on_team: str
    seniority: str
    trait_sheet: dict[str, Any]
    narrative: str
    private_goals: list[str]
    generated_from: dict[str, Any] | None = None
    is_edited: bool
    ordering: int
    created_at: datetime
    updated_at: datetime


class SyntheticTeammatePatch(BaseModel):
    name: str | None = None
    role_on_team: str | None = None
    seniority: str | None = None
    trait_sheet: dict[str, Any] | None = None
    narrative: str | None = None
    private_goals: list[str] | None = None


# ----------------------------------------------------------------------------
# Simulation pipeline — rollout read endpoints
# ----------------------------------------------------------------------------
class RolloutScoreOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    dimension_key: str
    score: int | None = None
    confidence: float
    justification: str
    evidence_turns: list[int]


class RolloutSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    match_id: str
    scenario_id: str | None = None
    rollout_index: int
    status: str
    failure_reason: str | None = None
    duration_turns: int
    headline: str
    scores: dict[str, Any]
    created_at: datetime


class RolloutDetailOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    match_id: str
    scenario_id: str | None = None
    rollout_index: int
    status: str
    failure_reason: str | None = None
    duration_turns: int
    transcript: list[Any]
    final_state: dict[str, Any]
    score_rows: list[RolloutScoreOut]
    created_at: datetime


class BaselineComparisonOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    match_id: str
    overall_score: int
    per_criterion: dict[str, Any]
    band: str
    band_note: str
    delta_vs_sim: dict[str, Any]
    robustness_summary: str
    created_at: datetime


# ----------------------------------------------------------------------------
# Roadmap 2 / PR #4 — interviews + notifications
# ----------------------------------------------------------------------------
class InterviewProposeIn(BaseModel):
    match_id: str
    proposed_slots: list[str] = Field(default_factory=list, min_length=1, max_length=5)


class InterviewAcceptIn(BaseModel):
    selected_slot: str
    message: str | None = None


class InterviewDeclineIn(BaseModel):
    message: str | None = None


class InterviewCounterIn(BaseModel):
    counter_slots: list[str] = Field(default_factory=list, min_length=1, max_length=5)
    message: str | None = None


class InterviewOut(BaseModel):
    """Recruiter-side view — vacancy details always visible."""
    model_config = ConfigDict(from_attributes=True)

    id: str
    match_id: str
    candidate_id: str
    position_id: str
    recruiter_email: str
    proposed_slots: list[str]
    selected_slot: str | None = None
    counter_slots: list[str]
    candidate_message: str
    status: str
    created_at: datetime
    updated_at: datetime
    candidate_display_name: str | None = None
    candidate_email: str | None = None
    position_name: str | None = None
    position_role: str | None = None
    organization_name: str | None = None


class CandidateInterviewOut(InterviewOut):
    """Candidate-side view — vacancy fields are the vacancy-reveal: this is
    the first surface where a candidate sees position_name / role / org."""


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_kind: str
    type: str
    payload: dict[str, Any]
    status: str
    created_at: datetime


# ----------------------------------------------------------------------------
# Roadmap 2 / PR #5 — calibration loop
# ----------------------------------------------------------------------------
class CalibrationOptionOut(BaseModel):
    text: str
    skill_level: str = ""
    # ``is_agent_answer`` is intentionally NOT exposed to the candidate.


class CalibrationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    candidate_id: str
    rollout_id: str | None
    scenario_id: str | None
    agent_response_text: str
    mcq_options: list[CalibrationOptionOut] = Field(default_factory=list)
    mode: str
    status: str
    divergence_score: float | None = None
    candidate_selection_index: int | None = None
    candidate_free_text: str | None = None
    accuracy_before: int | None = None
    accuracy_after: int | None = None
    created_at: datetime
    submitted_at: datetime | None = None


class CalibrationSubmitIn(BaseModel):
    selection_index: int | None = None
    free_text: str | None = None


class CalibrationTimelinePoint(BaseModel):
    calibration_id: str
    submitted_at: datetime | None
    accuracy_before: int | None
    accuracy_after: int | None
    divergence: float | None


class CalibrationTimelineOut(BaseModel):
    current_accuracy: int
    points: list[CalibrationTimelinePoint] = Field(default_factory=list)


# ----------------------------------------------------------------------------
# Misc
# ----------------------------------------------------------------------------
class HealthOut(BaseModel):
    ok: bool = True
