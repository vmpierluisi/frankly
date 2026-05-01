"""Unit tests for services/simulation/aggregator.py — Phase 4C.

Validation gate:
  (1) aggregate_fit_profile() returns a dict with all required legacy fields.
  (2) version == "v2" is set.
  (3) dimensionalFit keys match the criteria keys.
  (4) dimensionalFit.mean is the weighted mean of rollout scores for that dim.
  (5) dimensionalFit.n counts only rollouts with non-null scores.
  (6) overallScore is clipped to [0, 100].
  (7) band is derived from overallScore correctly.
  (8) rolloutSummaries has one entry per rollout, sorted by rollout_index.
  (9) baselineComparison is included when baseline_report is provided.
  (10) baselineComparison is absent when baseline_report is None.
  (11) confidenceSignals includes overallStd and judgeAgreementMean.
  (12) Rollouts with status="failed" are excluded from dimensional means.
  (13) transcript_summary is surfaced in rolloutSummaries headline.
"""
from __future__ import annotations

import pytest

from app.services.simulation.aggregator import aggregate_fit_profile, _band_for


# ---------------------------------------------------------------------------
# Stub helpers
# ---------------------------------------------------------------------------

class _StubRollout:
    def __init__(self, *, id, rollout_index=0, scenario_id="scen-001",
                 status="completed", final_state=None):
        self.id = id
        self.rollout_index = rollout_index
        self.scenario_id = scenario_id
        self.status = status
        self.final_state = final_state or {}


class _StubScore:
    def __init__(self, *, rollout_id, dimension_key, score, confidence=0.8,
                 justification="Good.", evidence_turns=None):
        self.rollout_id = rollout_id
        self.dimension_key = dimension_key
        self.score = score
        self.confidence = confidence
        self.justification = justification
        self.evidence_turns = evidence_turns or []


_CRITERIA = [
    {"key": "analytical_rigor", "label": "Analytical Rigor", "description": "Rigorous.", "weight": 0.6},
    {"key": "decisiveness",     "label": "Decisiveness",     "description": "Decisive.", "weight": 0.4},
]

_BASELINE_REPORT = {
    "overallScore": 65,
    "band": "Plausible fit",
    "bandNote": "Worth a call.",
    "criterionScores": {
        "analytical_rigor": {"score": 70, "justification": "Decent."},
        "decisiveness":     {"score": 58, "justification": "Hesitant."},
    },
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_aggregate_returns_legacy_fields():
    rollout = _StubRollout(id="r1")
    scores = [
        _StubScore(rollout_id="r1", dimension_key="analytical_rigor", score=80),
        _StubScore(rollout_id="r1", dimension_key="decisiveness", score=70),
    ]
    profile = aggregate_fit_profile([rollout], scores, _CRITERIA)

    for field in ("companyId", "companyName", "role", "overallScore", "band",
                  "bandNote", "criterionScores", "inconsistencyFlags", "auditTrail"):
        assert field in profile, f"missing legacy field: {field}"


def test_aggregate_version_is_v2():
    profile = aggregate_fit_profile([], [], _CRITERIA)
    assert profile["version"] == "v2"


def test_aggregate_dimensional_fit_keys_match_criteria():
    profile = aggregate_fit_profile([], [], _CRITERIA)
    assert set(profile["dimensionalFit"].keys()) == {"analytical_rigor", "decisiveness"}


def test_aggregate_dimensional_fit_mean():
    rollouts = [
        _StubRollout(id="r1", rollout_index=0),
        _StubRollout(id="r2", rollout_index=1),
    ]
    scores = [
        _StubScore(rollout_id="r1", dimension_key="analytical_rigor", score=80),
        _StubScore(rollout_id="r2", dimension_key="analytical_rigor", score=60),
        _StubScore(rollout_id="r1", dimension_key="decisiveness", score=90),
        _StubScore(rollout_id="r2", dimension_key="decisiveness", score=70),
    ]
    profile = aggregate_fit_profile(rollouts, scores, _CRITERIA)

    assert profile["dimensionalFit"]["analytical_rigor"]["mean"] == 70.0
    assert profile["dimensionalFit"]["decisiveness"]["mean"] == 80.0


def test_aggregate_dimensional_fit_n_counts():
    rollouts = [_StubRollout(id="r1"), _StubRollout(id="r2")]
    scores = [
        _StubScore(rollout_id="r1", dimension_key="analytical_rigor", score=80),
        # r2 has no score for analytical_rigor
        _StubScore(rollout_id="r1", dimension_key="decisiveness", score=90),
        _StubScore(rollout_id="r2", dimension_key="decisiveness", score=70),
    ]
    profile = aggregate_fit_profile(rollouts, scores, _CRITERIA)

    assert profile["dimensionalFit"]["analytical_rigor"]["n"] == 1
    assert profile["dimensionalFit"]["decisiveness"]["n"] == 2


def test_aggregate_overall_score_weighted():
    rollouts = [_StubRollout(id="r1")]
    scores = [
        _StubScore(rollout_id="r1", dimension_key="analytical_rigor", score=100),
        _StubScore(rollout_id="r1", dimension_key="decisiveness", score=0),
    ]
    # weight 0.6 * 100 + 0.4 * 0 = 60 / (0.6+0.4) = 60
    profile = aggregate_fit_profile(rollouts, scores, _CRITERIA)
    assert profile["overallScore"] == 60


def test_aggregate_overall_score_clipped():
    rollouts = [_StubRollout(id="r1")]
    scores = [
        _StubScore(rollout_id="r1", dimension_key="analytical_rigor", score=100),
        _StubScore(rollout_id="r1", dimension_key="decisiveness", score=100),
    ]
    profile = aggregate_fit_profile(rollouts, scores, _CRITERIA)
    assert 0 <= profile["overallScore"] <= 100


def test_aggregate_band_strong_fit():
    rollouts = [_StubRollout(id="r1")]
    scores = [
        _StubScore(rollout_id="r1", dimension_key="analytical_rigor", score=80),
        _StubScore(rollout_id="r1", dimension_key="decisiveness", score=80),
    ]
    profile = aggregate_fit_profile(rollouts, scores, _CRITERIA)
    assert profile["band"] == "Strong fit"


def test_aggregate_band_low_fit():
    rollouts = [_StubRollout(id="r1")]
    scores = [
        _StubScore(rollout_id="r1", dimension_key="analytical_rigor", score=20),
        _StubScore(rollout_id="r1", dimension_key="decisiveness", score=20),
    ]
    profile = aggregate_fit_profile(rollouts, scores, _CRITERIA)
    assert profile["band"] == "Poor fit"


def test_aggregate_rollout_summaries_sorted_by_index():
    rollouts = [
        _StubRollout(id="r2", rollout_index=1),
        _StubRollout(id="r1", rollout_index=0),
    ]
    profile = aggregate_fit_profile(rollouts, [], _CRITERIA)

    summaries = profile["rolloutSummaries"]
    assert len(summaries) == 2
    assert summaries[0]["kIndex"] == 0
    assert summaries[1]["kIndex"] == 1


def test_aggregate_rollout_summaries_headline_from_final_state():
    rollouts = [
        _StubRollout(id="r1", final_state={"transcript_summary": "Candidate showed strong reasoning."})
    ]
    profile = aggregate_fit_profile(rollouts, [], _CRITERIA)
    assert profile["rolloutSummaries"][0]["headline"] == "Candidate showed strong reasoning."


def test_aggregate_rollout_summaries_scores():
    rollouts = [_StubRollout(id="r1")]
    scores = [
        _StubScore(rollout_id="r1", dimension_key="analytical_rigor", score=75),
        _StubScore(rollout_id="r1", dimension_key="decisiveness", score=85),
    ]
    profile = aggregate_fit_profile(rollouts, scores, _CRITERIA)
    summary_scores = profile["rolloutSummaries"][0]["scores"]
    assert summary_scores["analytical_rigor"] == 75
    assert summary_scores["decisiveness"] == 85


def test_aggregate_failed_rollout_excluded_from_means():
    rollouts = [
        _StubRollout(id="r1", rollout_index=0, status="completed"),
        _StubRollout(id="r2", rollout_index=1, status="failed"),
    ]
    scores = [
        _StubScore(rollout_id="r1", dimension_key="analytical_rigor", score=80),
        # r2 has a score row but rollout is failed — still excluded (status check)
        _StubScore(rollout_id="r2", dimension_key="analytical_rigor", score=10),
    ]
    profile = aggregate_fit_profile(rollouts, scores, _CRITERIA)
    # Only r1 should contribute (status="completed")
    assert profile["dimensionalFit"]["analytical_rigor"]["mean"] == 80.0
    assert profile["dimensionalFit"]["analytical_rigor"]["n"] == 1


def test_aggregate_baseline_comparison_included():
    profile = aggregate_fit_profile([], [], _CRITERIA, baseline_report=_BASELINE_REPORT)
    assert "baselineComparison" in profile
    bc = profile["baselineComparison"]
    assert bc["overallScore"] == 65
    assert "deltaVsSim" in bc
    assert "robustnessSummary" in bc


def test_aggregate_baseline_comparison_absent_when_none():
    profile = aggregate_fit_profile([], [], _CRITERIA, baseline_report=None)
    assert "baselineComparison" not in profile


def test_aggregate_confidence_signals_present():
    rollouts = [_StubRollout(id="r1"), _StubRollout(id="r2")]
    scores = [
        _StubScore(rollout_id="r1", dimension_key="analytical_rigor", score=80, confidence=0.9),
        _StubScore(rollout_id="r2", dimension_key="analytical_rigor", score=70, confidence=0.7),
    ]
    profile = aggregate_fit_profile(rollouts, scores, _CRITERIA)
    cs = profile["confidenceSignals"]
    assert "overallStd" in cs
    assert "judgeAgreementMean" in cs
    assert "minNRollouts" in cs
    assert "perCriterionStd" in cs


def test_aggregate_no_rollouts_returns_zero_overall():
    profile = aggregate_fit_profile([], [], _CRITERIA)
    assert profile["overallScore"] == 0


def test_band_for_thresholds():
    assert _band_for(95)[0] == "Exceptional fit"
    assert _band_for(88)[0] == "Exceptional fit"
    assert _band_for(87)[0] == "Strong fit"
    assert _band_for(75)[0] == "Strong fit"
    assert _band_for(74)[0] == "Good fit"
    assert _band_for(62)[0] == "Good fit"
    assert _band_for(61)[0] == "Moderate fit"
    assert _band_for(48)[0] == "Moderate fit"
    assert _band_for(47)[0] == "Weak fit"
    assert _band_for(35)[0] == "Weak fit"
    assert _band_for(34)[0] == "Poor fit"
