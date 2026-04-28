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
    assessment_status: str = "pending"
    is_seed: bool = False
    created_at: datetime
    updated_at: datetime
    persona: PersonaSummary | None = None


class CandidateMePatchIn(BaseModel):
    display_name: str | None = None
    linkedin_url: str | None = None
    github_url: str | None = None
    cv_path: str | None = None


class AssessmentSubmitIn(BaseModel):
    bfi_responses: dict[str, int] = Field(default_factory=dict)
    sjt_responses: dict[str, str] = Field(default_factory=dict)


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


class CompanyIn(BaseModel):
    id: str | None = None  # caller may supply a slug; otherwise server generates one
    name: str
    tagline: str | None = None
    role: str
    artifact_values: str = ""
    artifact_role_spec: str = ""
    artifact_team_structure: str = ""
    artifact_sample_comms: str = ""
    criteria: list[CriterionIn] = Field(default_factory=list)


class CompanyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    tagline: str | None = None
    role: str
    artifact_values: str
    artifact_role_spec: str
    artifact_team_structure: str
    artifact_sample_comms: str
    criteria: list[CriterionOut]
    created_at: datetime
    updated_at: datetime


class CompanyListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    role: str
    tagline: str | None = None


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
    company_id: str


class CriterionScore(BaseModel):
    score: float
    justification: str


class FitReport(BaseModel):
    """The matcher's return shape, mirroring the JSX reference envelope."""
    company_id: str
    company_name: str
    role: str
    overall_score: int
    band: str
    band_note: str
    criterion_scores: dict[str, CriterionScore]
    inconsistency_flags: list[InconsistencyFlag]
    audit_trail: dict[str, Any]


class SearchMatchIn(BaseModel):
    company_id: str
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
    is_seed: bool = False


class SearchMatchOut(BaseModel):
    company_id: str
    company_name: str
    role: str
    pool_size: int
    results: list[SearchMatchResultItem]


class MatchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    candidate_id: str
    company_id: str
    overall_score: int
    band: str
    band_note: str
    report: dict[str, Any]
    candidate_opt_in: bool | None = None
    manager_opt_in: bool | None = None
    created_at: datetime


# ----------------------------------------------------------------------------
# Scenario library
# ----------------------------------------------------------------------------
class MomentOfTruthOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    company_id: str
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
    company_id: str
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
# Misc
# ----------------------------------------------------------------------------
class HealthOut(BaseModel):
    ok: bool = True
