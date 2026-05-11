"""Unit tests for services/simulation/scenario_engine.py — Phase 3A.

Validation gate:
  (1) draft_scenarios() returns a list of MomentOfTruth ORM objects.
  (2) Each scenario has all required fields set.
  (3) scoring_dims in returned scenarios are filtered to valid criterion keys.
  (4) prepare_rollout() returns a WorldState with agents for candidate + teammates.
  (5) prepare_rollout() selects teammates by participating_roles.
  (6) prepare_rollout() falls back to first teammate when no roles match.
  (7) validate_scoring_dims() returns only invalid keys.
  (8) Prompt contains criteria keys and artifact text.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.services.simulation.scenario_engine import (
    SCENARIO_LIBRARY_SCHEMA,
    AgentState,
    WorldState,
    _render_drafter_user_prompt,
    draft_scenarios,
    prepare_rollout,
    validate_scoring_dims,
)
from app.services.simulation.cost_tracker import CostBudget


# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------

class _StubCriterion:
    def __init__(self, key, label="", description="", ordering=0):
        self.key = key
        self.label = label
        self.description = description
        self.ordering = ordering
        self.weight = 0.25


class _StubOrg:
    id = "org-meridian"
    name = "Meridian Capital"
    tagline = "Patience as a competitive edge."
    mission = "We value written rigor."


class _StubTeam:
    id = "team-meridian"
    organization_id = "org-meridian"
    name = "Meridian core team"
    artifact_team_structure = "Pod: 1 VP + 2 analysts."
    artifact_sample_comms = "IRR below hurdle. Recommend pass."
    knowledge_graph = None
    teammates: list = []
    scenarios: list = []


class _StubPosition:
    id = "meridian-capital"
    organization_id = "org-meridian"
    team_id = "team-meridian"
    name = "Meridian Capital"
    role = "Associate, Private Credit"
    artifact_role_spec = "Analysts own deal memos end-to-end."
    organization = _StubOrg()
    team = _StubTeam()
    criteria = [
        _StubCriterion("analyticalRigor", "Analytical Rigor", "Depth of quantitative analysis.", 0),
        _StubCriterion("writtenDissent", "Written Dissent", "Disagrees in writing.", 1),
    ]


def _make_canned_library() -> dict:
    return {
        "scenarios": [
            {
                "title": "IC Memo Under Pressure",
                "type": "dyad",
                "prompt": "You and a VP are reviewing a deal memo with a tight deadline.",
                "candidate_role": "Draft the IC recommendation section.",
                "expected_arc": "Candidate grounds recommendation in data, dissents if warranted.",
                "scoring_dims": ["analyticalRigor", "writtenDissent"],
                "participating_roles": ["Pod VP"],
                "max_turns": 6,
                "grounding": "Role spec: 'Analysts own deal memos end-to-end.'",
            },
            {
                "title": "Morning Deal Review",
                "type": "small_group",
                "prompt": "Pod weekly deal review. You present the model.",
                "candidate_role": "Present and defend your analysis.",
                "expected_arc": "Candidate defends quantitative positions clearly.",
                "scoring_dims": ["analyticalRigor"],
                "participating_roles": ["Senior Analyst", "Pod VP"],
                "max_turns": 10,
                "grounding": "Team structure: pod reviews weekly.",
            },
            {
                "title": "Written Dissent Memo",
                "type": "written",
                "prompt": "MD is bullish on a deal. You have concerns.",
                "candidate_role": "Write a dissent memo before IC.",
                "expected_arc": "Candidate writes clearly, cites data, proposes path forward.",
                "scoring_dims": ["writtenDissent"],
                "participating_roles": [],
                "max_turns": 4,
                "grounding": "Values: 'written rigor'.",
            },
        ]
    }


class _StubScenario:
    id = "scen-001"
    title = "IC Memo Under Pressure"
    scenario_type = "dyad"
    prompt = "You and a VP are reviewing a deal memo."
    candidate_role = "Draft the IC recommendation."
    expected_arc = "Candidate grounds recommendation in data."
    scoring_dims = ["analyticalRigor", "writtenDissent"]
    participating_roles = ["Pod VP"]
    max_turns = 6


# ---------------------------------------------------------------------------
# validate_scoring_dims tests
# ---------------------------------------------------------------------------

def test_validate_scoring_dims_all_valid():
    """(7) Returns empty list when all keys are valid."""
    position = _StubPosition()
    result = validate_scoring_dims(["analyticalRigor", "writtenDissent"], position)
    assert result == []


def test_validate_scoring_dims_invalid_keys():
    """(7) Returns the invalid keys."""
    position = _StubPosition()
    result = validate_scoring_dims(["analyticalRigor", "nonExistentKey"], position)
    assert "nonExistentKey" in result
    assert "analyticalRigor" not in result


def test_validate_scoring_dims_empty():
    position = _StubPosition()
    assert validate_scoring_dims([], position) == []


# ---------------------------------------------------------------------------
# Prompt rendering test
# ---------------------------------------------------------------------------

def test_render_prompt_includes_criteria_and_artifacts():
    """(8) Prompt includes criterion keys and artifact text."""
    position = _StubPosition()
    prompt = _render_drafter_user_prompt(position)
    assert "analyticalRigor" in prompt
    assert "writtenDissent" in prompt
    assert "written rigor" in prompt
    assert "deal memos" in prompt


# ---------------------------------------------------------------------------
# draft_scenarios tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_draft_scenarios_returns_orm_objects():
    """(1) draft_scenarios() returns a list of MomentOfTruth ORM objects."""
    import app.models as m
    position = _StubPosition()
    budget = CostBudget(ceiling_usd=10.0)
    canned = _make_canned_library()

    with patch(
        "app.services.simulation.scenario_engine.tracked_chat_json",
        new=AsyncMock(return_value=canned),
    ):
        result = await draft_scenarios(position, budget=budget)

    assert len(result) == 3
    for s in result:
        assert isinstance(s, m.MomentOfTruth)


@pytest.mark.asyncio
async def test_draft_scenarios_required_fields():
    """(2) Each scenario has all required fields set correctly."""
    position = _StubPosition()
    budget = CostBudget(ceiling_usd=10.0)
    canned = _make_canned_library()

    with patch(
        "app.services.simulation.scenario_engine.tracked_chat_json",
        new=AsyncMock(return_value=canned),
    ):
        result = await draft_scenarios(position, budget=budget)

    first = result[0]
    assert first.team_id == position.team_id
    assert first.title == "IC Memo Under Pressure"
    assert first.scenario_type == "dyad"
    assert first.is_llm_drafted is True
    assert first.ordering == 0
    assert isinstance(first.scoring_dims, list)
    assert isinstance(first.participating_roles, list)


@pytest.mark.asyncio
async def test_draft_scenarios_filters_invalid_scoring_dims():
    """(3) scoring_dims in returned scenarios are filtered to valid criterion keys."""
    position = _StubPosition()
    budget = CostBudget(ceiling_usd=10.0)
    canned = {
        "scenarios": [{
            **_make_canned_library()["scenarios"][0],
            "scoring_dims": ["analyticalRigor", "INVALID_KEY"],
        }]
    }

    with patch(
        "app.services.simulation.scenario_engine.tracked_chat_json",
        new=AsyncMock(return_value=canned),
    ):
        result = await draft_scenarios(position, budget=budget)

    assert "analyticalRigor" in result[0].scoring_dims
    assert "INVALID_KEY" not in result[0].scoring_dims


@pytest.mark.asyncio
async def test_draft_scenarios_ordering_sequential():
    """Ordering values are 0, 1, 2, ..."""
    position = _StubPosition()
    budget = CostBudget(ceiling_usd=10.0)
    canned = _make_canned_library()

    with patch(
        "app.services.simulation.scenario_engine.tracked_chat_json",
        new=AsyncMock(return_value=canned),
    ):
        result = await draft_scenarios(position, budget=budget)

    assert [s.ordering for s in result] == list(range(len(result)))


# ---------------------------------------------------------------------------
# prepare_rollout tests
# ---------------------------------------------------------------------------

def _make_candidate_persona() -> dict:
    return {
        "narrative": "A meticulous analyst who prefers written communication.",
        "structured_traits": {
            "big_five": {"openness": 4.5, "conscientiousness": 4.8,
                         "extraversion": 2.5, "agreeableness": 3.0, "neuroticism": 2.0},
            "sjt_signals": {},
            "skill_inferences": {},
            "work_style": {},
        },
    }


def _make_teammates() -> list[dict]:
    return [
        {
            "id": "tm-001",
            "name": "Alex Morgan",
            "role_on_team": "Pod VP",
            "seniority": "lead",
            "narrative": "A seasoned VP who values rigour.",
            "trait_sheet": {"big_five": {}, "skill_profile": {}, "work_style": {}},
            "private_goals": ["Probe analytical depth."],
        },
        {
            "id": "tm-002",
            "name": "Jordan Smith",
            "role_on_team": "Senior Analyst",
            "seniority": "senior",
            "narrative": "Meticulous analyst.",
            "trait_sheet": {"big_five": {}, "skill_profile": {}, "work_style": {}},
            "private_goals": ["Check written dissent."],
        },
    ]


def test_prepare_rollout_returns_world_state():
    """(4) prepare_rollout() returns a WorldState."""
    scenario = _StubScenario()
    persona = _make_candidate_persona()
    teammates = _make_teammates()

    world = prepare_rollout(scenario, persona, teammates)
    assert isinstance(world, WorldState)
    assert world.current_turn == 0
    assert world.scenario["title"] == scenario.title


def test_prepare_rollout_has_candidate_agent():
    """(4) WorldState includes a candidate agent."""
    world = prepare_rollout(_StubScenario(), _make_candidate_persona(), _make_teammates())
    assert "candidate" in world.agents
    assert isinstance(world.agents["candidate"], AgentState)


def test_prepare_rollout_selects_by_participating_roles():
    """(5) prepare_rollout selects teammates whose role matches participating_roles."""
    # Scenario wants "Pod VP" only.
    world = prepare_rollout(_StubScenario(), _make_candidate_persona(), _make_teammates())
    teammate_ids = [aid for aid in world.agents if aid != "candidate"]
    # Should include the Pod VP teammate.
    assert any("tm-001" in tid or "Alex Morgan" in tid for tid in teammate_ids)


def test_prepare_rollout_fallback_when_no_role_match():
    """(6) Falls back to first teammate when no participating_roles match."""
    class _NoRoleScenario(_StubScenario):
        participating_roles = ["Nonexistent Role"]
        scenario_type = "dyad"

    world = prepare_rollout(_NoRoleScenario(), _make_candidate_persona(), _make_teammates())
    # Should still have at least one teammate.
    assert len(world.agents) >= 2  # candidate + at least 1 teammate


def test_prepare_rollout_seed_generation():
    """prepare_rollout auto-generates a seed when none is supplied."""
    world = prepare_rollout(_StubScenario(), _make_candidate_persona(), _make_teammates())
    assert isinstance(world.seed, str)
    assert len(world.seed) > 0


def test_prepare_rollout_explicit_seed():
    """prepare_rollout uses the provided seed."""
    world = prepare_rollout(
        _StubScenario(), _make_candidate_persona(), _make_teammates(), seed="test-seed-42"
    )
    assert world.seed == "test-seed-42"
