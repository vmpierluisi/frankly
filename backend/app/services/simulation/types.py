"""Shared TypedDicts for the simulation pipeline.

These types are the stable interface between simulation modules. Downstream
code (routes, aggregator, proof layer) depends only on these shapes, not on
module internals.
"""
from __future__ import annotations

from typing import Any, TypedDict


# ---------------------------------------------------------------------------
# Persona
# ---------------------------------------------------------------------------

class ProvenanceSource(TypedDict):
    source: str   # "bfi" | "sjt:<sjt_id>" | "cv" | "linkedin" | "github"
    evidence: str  # short quoted excerpt or item id


class ProvenanceEntry(TypedDict):
    claim: str
    sources: list[ProvenanceSource]
    confidence: float
    reliability_weight: str  # "high" | "moderate" | "low"


class Inconsistency(TypedDict):
    type: str
    note: str


class EvidenceCompleteness(TypedDict):
    bfi_present: bool
    sjt_present: bool
    cv_present: bool
    linkedin_present: bool
    github_present: bool
    notes: str


class BigFive(TypedDict):
    openness: float
    conscientiousness: float
    extraversion: float
    agreeableness: float
    neuroticism: float


class SjtSignals(TypedDict):
    analyticalRigor: float
    intellectualHonesty: float
    writtenDissent: float
    ambiguityTolerance: float
    lowEgoCollab: float


class StructuredTraits(TypedDict):
    big_five: BigFive
    sjt_signals: SjtSignals
    skill_inferences: dict[str, float]
    work_style: dict[str, float]


class AggregatedPersona(TypedDict):
    structured_traits: StructuredTraits
    narrative: str
    provenance_map: list[ProvenanceEntry]
    inconsistencies: list[Inconsistency]
    evidence_completeness: EvidenceCompleteness
    aggregator_version: str


# ---------------------------------------------------------------------------
# Rollout / agent runtime
# ---------------------------------------------------------------------------

class RolloutTurn(TypedDict):
    turn: int
    speaker_id: str
    speaker_role: str
    content: str
    intent: str
    internal_state: str


class AgentTurnOutput(TypedDict):
    utterance: str
    intent: str
    internal_state: str
    ends_turn: bool


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

class DimScore(TypedDict):
    score: int | None  # null when no evidence
    justification: str
    evidence_turns: list[int]
    confidence: float


class JudgeOutput(TypedDict):
    dimension_scores: dict[str, DimScore]
    transcript_summary: str
    judge_notes: str


# ---------------------------------------------------------------------------
# FitProfile (top-level match report for v2)
# ---------------------------------------------------------------------------

class DimensionalFitEntry(TypedDict):
    mean: float
    std: float
    n: int
    judgeAgreement: float | None


class RolloutSummary(TypedDict):
    rolloutId: str
    scenarioId: str
    scenarioTitle: str
    kIndex: int
    headline: str
    scores: dict[str, int]


class BaselineComparison(TypedDict):
    overallScore: int
    perCriterion: dict[str, Any]
    deltaVsSim: dict[str, int]
    robustnessSummary: str


class ConfidenceSignals(TypedDict):
    overallStd: float
    perCriterionStd: dict[str, float]
    minNRollouts: int
    judgeAgreementMean: float
