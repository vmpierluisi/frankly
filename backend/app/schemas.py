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


class CandidateListItem(BaseModel):
    """Slim row for the manager's candidate list."""
    model_config = ConfigDict(from_attributes=True)

    id: str
    display_name: str | None = None
    narrative: str | None = None
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
    narrative: str | None = None
    overall_score: int
    band: str
    band_note: str
    report: dict[str, Any]
    fit_axes: FitAxes
    cached: bool


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
# Misc
# ----------------------------------------------------------------------------
class HealthOut(BaseModel):
    ok: bool = True
