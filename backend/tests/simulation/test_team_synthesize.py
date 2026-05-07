"""Unit tests for team_synthesizer.synthesize() — Phase 2B.

Validation gate:
  (1) synthesize() returns a list of SyntheticTeammate ORM objects.
  (2) Each teammate has all required fields set.
  (3) trait_sheet big_five values are clipped to [0, 5].
  (4) _sample_trait_sheet produces values within expected ranges.
  (5) synthesize() calls LLM N+1 times (1 centroid + N teammate calls).
  (6) Teammate ordering values are 0, 1, ..., N-1.
"""
from __future__ import annotations

import random
from unittest.mock import AsyncMock, call, patch

import pytest

from app.services.simulation.team_synthesizer import (
    DEFAULT_TEAM_SIZE,
    SYNTHETIC_TEAMMATE_SCHEMA,
    _render_centroid_tensions_block,
    _sample_trait_sheet,
    synthesize,
)
from app.services.simulation.cost_tracker import CostBudget


# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------

class _StubCriterion:
    def __init__(self, key, label, description, ordering=0):
        self.key = key
        self.label = label
        self.description = description
        self.ordering = ordering
        self.weight = 0.25


class _StubOrg:
    id = "org-meridian"
    name = "Meridian Capital"
    tagline = "Patience as a competitive edge."
    mission = "We value written rigor and intellectual honesty above all."


class _StubTeam:
    id = "team-meridian"
    organization_id = "org-meridian"
    name = "Meridian core team"
    artifact_team_structure = "Pod structure: 1 VP + 2 analysts per pod."
    artifact_sample_comms = "IRR below hurdle. Recommend pass."
    knowledge_graph = None
    teammates: list = []
    scenarios: list = []


class _StubCompany:
    id = "meridian-capital"
    organization_id = "org-meridian"
    team_id = "team-meridian"
    name = "Meridian Capital"
    role = "Associate, Private Credit"
    artifact_role_spec = "Analysts own deal memos end-to-end."
    organization = _StubOrg()
    team = _StubTeam()
    criteria = [
        _StubCriterion("analyticalRigor", "Analytical Rigor", "Depth of quant analysis.", ordering=0),
    ]


def _make_canned_centroid() -> dict:
    return {
        "big_five_centroid": {
            "openness":          {"value": 4.2, "provenance": "Role spec"},
            "conscientiousness": {"value": 4.8, "provenance": "Values doc"},
            "extraversion":      {"value": 2.5, "provenance": "Sample comms"},
            "agreeableness":     {"value": 2.8, "provenance": "Values"},
            "neuroticism":       {"value": 2.0, "provenance": "Role spec"},
        },
        "skill_centroid": {
            "financial_modeling": {"value": 4.5, "provenance": "Role spec"},
        },
        "work_style_centroid": {
            "async_pref": {"value": 0.8, "provenance": "Sample comms"},
        },
        "centroid_tensions": [
            {
                "id": "patience-vs-velocity",
                "description": "Tagline promotes patience; deal flow demands speed.",
                "evidence": "Tagline vs role spec",
            }
        ],
        "sigma_recommendations": {
            "big_five": 0.6,
            "skill": 0.6,
            "work_style": 0.3,
        },
    }


def _make_canned_teammate(index: int = 0) -> dict:
    return {
        "name": f"Alex Morgan {index}",
        "role_on_team": "Senior Credit Analyst",
        "seniority": "senior",
        "trait_sheet": {
            "big_five": {
                "openness": 4.1,
                "conscientiousness": 4.9,
                "extraversion": 2.3,
                "agreeableness": 2.7,
                "neuroticism": 1.9,
            },
            "skill_profile": {"financial_modeling": 4.4},
            "work_style": {"async_pref": 0.7},
        },
        "narrative": "A meticulous analyst who prefers written communication and deep analysis.",
        "private_goals": [
            "Assess the candidate's analytical rigor under pressure.",
            "Probe written dissent behavior.",
        ],
        "provenance_notes": "Narrative grounded in values doc: 'written rigor' and role spec: 'deal memos'.",
    }


# ---------------------------------------------------------------------------
# Tests for _sample_trait_sheet
# ---------------------------------------------------------------------------

def test_sample_trait_sheet_big_five_in_range():
    """(3) Big Five values from sampling are clipped to [0, 5]."""
    centroid = _make_canned_centroid()
    rng = random.Random(42)
    for _ in range(20):
        sheet = _sample_trait_sheet(centroid, rng)
        for trait, val in sheet["big_five"].items():
            assert 0.0 <= val <= 5.0, f"{trait}={val} out of [0,5]"


def test_sample_trait_sheet_work_style_in_range():
    """(4) Work-style values from sampling are clipped to [0, 1]."""
    centroid = _make_canned_centroid()
    rng = random.Random(99)
    for _ in range(20):
        sheet = _sample_trait_sheet(centroid, rng)
        for key, val in sheet["work_style"].items():
            assert 0.0 <= val <= 1.0, f"{key}={val} out of [0,1]"


def test_sample_trait_sheet_preserves_keys():
    """Sampled sheet has same keys as the centroid entries."""
    centroid = _make_canned_centroid()
    rng = random.Random(0)
    sheet = _sample_trait_sheet(centroid, rng)
    assert set(sheet["big_five"].keys()) == {"openness", "conscientiousness",
                                              "extraversion", "agreeableness", "neuroticism"}
    assert "financial_modeling" in sheet["skill_profile"]
    assert "async_pref" in sheet["work_style"]


# ---------------------------------------------------------------------------
# Tests for _render_centroid_tensions_block
# ---------------------------------------------------------------------------

def test_render_tensions_block_with_tensions():
    centroid = _make_canned_centroid()
    block = _render_centroid_tensions_block(centroid)
    assert "patience-vs-velocity" in block
    assert "patience" in block.lower()


def test_render_tensions_block_empty():
    centroid = dict(_make_canned_centroid())
    centroid["centroid_tensions"] = []
    block = _render_centroid_tensions_block(centroid)
    assert "(none" in block


# ---------------------------------------------------------------------------
# Tests for synthesize()
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_synthesize_returns_orm_objects():
    """(1) synthesize() returns a list of SyntheticTeammate ORM objects."""
    import app.models as m
    company = _StubCompany()
    budget = CostBudget(ceiling_usd=50.0)
    canned_centroid = _make_canned_centroid()
    canned_teammate = _make_canned_teammate()

    call_count = 0

    async def _fake_tracked(*args, schema_name="", **kwargs):
        nonlocal call_count
        call_count += 1
        if schema_name == "team_centroid":
            return canned_centroid
        return canned_teammate

    with patch(
        "app.services.simulation.team_synthesizer.tracked_chat_json",
        new=_fake_tracked,
    ):
        result = await synthesize(company, budget=budget, n=3)

    assert len(result) == 3
    for t in result:
        assert isinstance(t, m.SyntheticTeammate)


@pytest.mark.asyncio
async def test_synthesize_calls_llm_n_plus_one_times():
    """(5) synthesize() makes 1 centroid call + N teammate calls = N+1 total."""
    n = 4
    company = _StubCompany()
    budget = CostBudget(ceiling_usd=50.0)
    canned_centroid = _make_canned_centroid()

    call_count = 0

    async def _fake_tracked(*args, schema_name="", **kwargs):
        nonlocal call_count
        call_count += 1
        if schema_name == "team_centroid":
            return canned_centroid
        return _make_canned_teammate(call_count)

    with patch(
        "app.services.simulation.team_synthesizer.tracked_chat_json",
        new=_fake_tracked,
    ):
        await synthesize(company, budget=budget, n=n)

    assert call_count == n + 1


@pytest.mark.asyncio
async def test_synthesize_required_fields_set():
    """(2) Each returned teammate has all required model fields set."""
    company = _StubCompany()
    budget = CostBudget(ceiling_usd=50.0)
    canned_centroid = _make_canned_centroid()

    async def _fake_tracked(*args, schema_name="", **kwargs):
        if schema_name == "team_centroid":
            return canned_centroid
        return _make_canned_teammate()

    with patch(
        "app.services.simulation.team_synthesizer.tracked_chat_json",
        new=_fake_tracked,
    ):
        result = await synthesize(company, budget=budget, n=2)

    for t in result:
        assert t.team_id == company.team_id
        assert t.name != ""
        assert t.role_on_team != ""
        assert t.seniority in ("junior", "mid", "senior", "lead")
        assert isinstance(t.trait_sheet, dict)
        assert isinstance(t.private_goals, list)
        assert isinstance(t.narrative, str)
        assert t.is_edited is False


@pytest.mark.asyncio
async def test_synthesize_ordering_sequential():
    """(6) Teammate ordering values are 0, 1, ..., N-1."""
    company = _StubCompany()
    budget = CostBudget(ceiling_usd=50.0)
    canned_centroid = _make_canned_centroid()
    n = 5

    async def _fake_tracked(*args, schema_name="", **kwargs):
        if schema_name == "team_centroid":
            return canned_centroid
        return _make_canned_teammate()

    with patch(
        "app.services.simulation.team_synthesizer.tracked_chat_json",
        new=_fake_tracked,
    ):
        result = await synthesize(company, budget=budget, n=n)

    assert [t.ordering for t in result] == list(range(n))
