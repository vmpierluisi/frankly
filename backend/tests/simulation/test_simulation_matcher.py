"""Integration tests for services/simulation/simulation_matcher.py — Phase 4C.

Validation gate:
  (1) run_match() returns a FitProfile v2 dict with overallScore, band, version.
  (2) Match aborts with 409 when company has no synthetic team.
  (3) Match aborts with 409 when company has no scenarios.
  (4) dimensionalFit keys match company criteria.
  (5) rolloutSummaries has one entry per K * scenario.
  (6) Baseline report is included in the profile when baseline_matcher succeeds.
  (7) baselineComparison is absent when baseline_matcher fails.
  (8) RolloutLog events are written to the session.
  (9) BaselineComparison row is persisted when baseline succeeds.
  (10) run_match uses legacy persona when aggregated_persona is missing.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import BaselineComparison, RolloutLog
from app.services.simulation.simulation_matcher import run_match


# ---------------------------------------------------------------------------
# Sync DB fixture
# ---------------------------------------------------------------------------

@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


# ---------------------------------------------------------------------------
# Stub objects
# ---------------------------------------------------------------------------

class _StubCriterion:
    def __init__(self, key, label="Label", description="Desc", weight=0.5, ordering=0):
        self.key = key
        self.label = label
        self.description = description
        self.weight = weight
        self.ordering = ordering


class _StubTeammate:
    def __init__(self, i=0):
        self.id = f"tm-{i}"
        self.name = f"Alex {i}"
        self.role_on_team = "Associate"
        self.seniority = "senior"
        self.narrative = "Experienced associate."
        self.trait_sheet = {}
        self.private_goals = []


class _StubScenario:
    def __init__(self, i=0):
        self.id = f"scen-{i}"
        self.title = f"Scenario {i}"
        self.scenario_type = "dyad"
        self.prompt = "What would you do?"
        self.candidate_role = "Lead the discussion."
        self.expected_arc = "Structured answer."
        self.scoring_dims = ["written_rigor"]
        self.participating_roles = ["Associate"]
        self.max_turns = 2
        self.grounding = ""
        self.is_llm_drafted = True


class _StubCompany:
    id = "meridian"
    name = "Meridian Capital"
    role = "Associate"
    tagline = "Patient capital."
    artifact_values = "Intellectual honesty."
    artifact_role_spec = "Analysts own memos."
    artifact_team_structure = "Pod structure."
    artifact_sample_comms = "IRR below hurdle."
    knowledge_graph = None

    def __init__(self, *, has_team=True, has_scenarios=True):
        self.criteria = [_StubCriterion("written_rigor", "Written Rigor", "Clear writing.", 1.0)]
        self.teammates = [_StubTeammate()] if has_team else []
        self.scenarios = [_StubScenario()] if has_scenarios else []


class _StubCandidate:
    id = "cand-001"
    display_name = "Jane Doe"
    email = "jane@example.com"
    bfi_responses = {}
    sjt_responses = {}
    aggregated_persona = {
        "narrative": "Strong analyst.",
        "structured_traits": {"big_five": {"openness": 4.0}},
        "_legacy": {
            "bigFive": {"openness": 4.0, "conscientiousness": 4.0,
                        "extraversion": 3.0, "agreeableness": 3.5, "neuroticism": 2.0},
            "sjtSignals": {"analyticalRigor": 4.0, "intellectualHonesty": 4.5,
                           "writtenDissent": 3.5, "ambiguityTolerance": 4.0, "lowEgoCollab": 3.8},
            "inconsistencies": [],
            "narrative": "Strong analyst.",
        },
    }


_STUB_AGENT_TURN = {"utterance": "Hello.", "intent": "open", "internal_state": "calm", "ends_turn": True}

_JUDGE_RESP = {
    "dimension_scores": {
        "written_rigor": {"score": 78, "justification": "Clear.", "evidence_turns": [0], "confidence": 0.8},
    },
    "transcript_summary": "Candidate was clear.",
    "judge_notes": "",
}

_BASELINE_RESP = {
    "companyId": "meridian",
    "companyName": "Meridian Capital",
    "role": "Associate",
    "overallScore": 72,
    "band": "Plausible fit",
    "bandNote": "Worth a conversation.",
    "criterionScores": {"written_rigor": {"score": 72, "justification": "Solid."}},
    "inconsistencyFlags": [],
    "auditTrail": {"model": "test", "timestamp": "2026-01-01", "note": ""},
}


def _patch_llm():
    """Patch both agent runtime and judge LLM calls."""
    return (
        patch("app.services.simulation.agent_runtime.tracked_chat_json",
              new=AsyncMock(return_value=_STUB_AGENT_TURN)),
        patch("app.services.simulation.judge.tracked_chat_json",
              new=AsyncMock(return_value=_JUDGE_RESP)),
        patch("app.services.simulation.simulation_matcher.baseline_run_match",
              new=AsyncMock(return_value=_BASELINE_RESP)),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_match_returns_fit_profile(db_session):
    with _patch_llm()[0], _patch_llm()[1], _patch_llm()[2]:
        profile = await run_match(
            match_id="match-001",
            candidate=_StubCandidate(),
            company=_StubCompany(),
            db=db_session,
            k_per_scenario=1,
        )

    assert isinstance(profile, dict)
    assert "overallScore" in profile
    assert profile["version"] == "v2"
    assert "band" in profile


@pytest.mark.asyncio
async def test_run_match_dimensional_fit_keys(db_session):
    with _patch_llm()[0], _patch_llm()[1], _patch_llm()[2]:
        profile = await run_match(
            match_id="match-001",
            candidate=_StubCandidate(),
            company=_StubCompany(),
            db=db_session,
            k_per_scenario=1,
        )

    assert "written_rigor" in profile["dimensionalFit"]


@pytest.mark.asyncio
async def test_run_match_rollout_summaries(db_session):
    with _patch_llm()[0], _patch_llm()[1], _patch_llm()[2]:
        profile = await run_match(
            match_id="match-001",
            candidate=_StubCandidate(),
            company=_StubCompany(),
            db=db_session,
            k_per_scenario=1,
        )

    # 1 scenario × 1 k = 1 rollout summary
    assert len(profile["rolloutSummaries"]) == 1


@pytest.mark.asyncio
async def test_run_match_no_team_raises_409(db_session):
    with pytest.raises(HTTPException) as exc_info:
        await run_match(
            match_id="match-001",
            candidate=_StubCandidate(),
            company=_StubCompany(has_team=False),
            db=db_session,
        )
    assert exc_info.value.status_code == 409
    assert "team" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_run_match_no_scenarios_raises_409(db_session):
    with pytest.raises(HTTPException) as exc_info:
        await run_match(
            match_id="match-001",
            candidate=_StubCandidate(),
            company=_StubCompany(has_scenarios=False),
            db=db_session,
        )
    assert exc_info.value.status_code == 409
    assert "scenario" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_run_match_includes_baseline_comparison(db_session):
    with _patch_llm()[0], _patch_llm()[1], _patch_llm()[2]:
        profile = await run_match(
            match_id="match-001",
            candidate=_StubCandidate(),
            company=_StubCompany(),
            db=db_session,
            k_per_scenario=1,
        )

    assert "baselineComparison" in profile
    assert profile["baselineComparison"]["overallScore"] == 72


@pytest.mark.asyncio
async def test_run_match_baseline_failure_omits_comparison(db_session):
    with patch("app.services.simulation.agent_runtime.tracked_chat_json",
               new=AsyncMock(return_value=_STUB_AGENT_TURN)), \
         patch("app.services.simulation.judge.tracked_chat_json",
               new=AsyncMock(return_value=_JUDGE_RESP)), \
         patch("app.services.simulation.simulation_matcher.baseline_run_match",
               new=AsyncMock(side_effect=Exception("baseline failed"))):
        profile = await run_match(
            match_id="match-001",
            candidate=_StubCandidate(),
            company=_StubCompany(),
            db=db_session,
            k_per_scenario=1,
        )

    assert "baselineComparison" not in profile


@pytest.mark.asyncio
async def test_run_match_log_events_written(db_session):
    with _patch_llm()[0], _patch_llm()[1], _patch_llm()[2]:
        await run_match(
            match_id="match-001",
            candidate=_StubCandidate(),
            company=_StubCompany(),
            db=db_session,
            k_per_scenario=1,
        )
        db_session.commit()

    logs = db_session.execute(
        select(RolloutLog).where(RolloutLog.match_id == "match-001")
    ).scalars().all()
    event_types = {r.event_type for r in logs}

    assert "persona_aggregated" in event_types
    assert "rollout_started" in event_types
    assert "fit_aggregated" in event_types


@pytest.mark.asyncio
async def test_run_match_persists_baseline_comparison_row(db_session):
    with _patch_llm()[0], _patch_llm()[1], _patch_llm()[2]:
        await run_match(
            match_id="match-001",
            candidate=_StubCandidate(),
            company=_StubCompany(),
            db=db_session,
            k_per_scenario=1,
        )
        db_session.commit()

    row = db_session.get(BaselineComparison, "match-001")
    assert row is not None
    assert row.overall_score == 72


@pytest.mark.asyncio
async def test_run_match_falls_back_to_legacy_persona(db_session):
    """When aggregated_persona is None, the legacy synthesize_persona path is used."""
    candidate = _StubCandidate()
    candidate.aggregated_persona = None
    candidate.bfi_responses = {}
    candidate.sjt_responses = {}

    with _patch_llm()[0], _patch_llm()[1], _patch_llm()[2]:
        profile = await run_match(
            match_id="match-002",
            candidate=candidate,
            company=_StubCompany(),
            db=db_session,
            k_per_scenario=1,
        )

    assert profile["version"] == "v2"
