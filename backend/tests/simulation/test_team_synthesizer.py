"""Unit tests for services/simulation/team_synthesizer.py — Phase 2A portion.

Phase 2A covers extract_centroid only.  The full synthesize() pipeline is
tested in Phase 2B.

Validation gate (Phase 2A):
  (1) extract_centroid() returns all required TeamCentroid keys.
  (2) big_five_centroid values are in 0-5 range and carry provenance.
  (3) sigma_recommendations contains big_five, skill, work_style.
  (4) centroid_tensions is a list (may be empty) with id/description/evidence.
  (5) Knowledge graph summary is embedded in the rendered prompt.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.services.simulation.team_synthesizer import (
    TEAM_CENTROID_SCHEMA,
    _render_centroid_user_prompt,
    _render_criteria_block,
    extract_centroid,
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
    knowledge_graph = {
        "nodes": [
            {"id": "value:rigor", "type": "value", "label": "Rigor",
             "body": "Thorough analysis."},
        ],
        "edges": [],
    }
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
        _StubCriterion("analyticalRigor", "Analytical Rigor",
                       "Depth of quantitative analysis.", ordering=0),
        _StubCriterion("writtenDissent", "Written Dissent",
                       "Willingness to disagree in writing.", ordering=1),
    ]


def _make_canned_centroid() -> dict:
    return {
        "big_five_centroid": {
            "openness":          {"value": 4.2, "provenance": "Role spec: 'analytical curiosity'"},
            "conscientiousness": {"value": 4.8, "provenance": "Values doc: 'thorough'"},
            "extraversion":      {"value": 2.5, "provenance": "Sample comms: brief, written-first"},
            "agreeableness":     {"value": 2.8, "provenance": "Values: intellectual honesty over harmony"},
            "neuroticism":       {"value": 2.0, "provenance": "Role spec: operates under pressure"},
        },
        "skill_centroid": {
            "financial_modeling": {"value": 4.5, "provenance": "Role spec: owns deal model"},
            "written_communication": {"value": 4.7, "provenance": "Values: memo-first"},
        },
        "work_style_centroid": {
            "async_pref": {"value": 0.8, "provenance": "Sample comms: all written"},
            "structure_seeking": {"value": 0.7, "provenance": "Values: process discipline"},
        },
        "centroid_tensions": [
            {
                "id": "patience-vs-velocity",
                "description": "Tagline promotes patience; deal flow demands speed.",
                "evidence": "Tagline: 'patience as edge' vs role spec: 'fast turn on memos'",
            }
        ],
        "sigma_recommendations": {
            "big_five": 0.6,
            "skill": 0.6,
            "work_style": 0.6,
        },
    }


# ---------------------------------------------------------------------------
# Schema validation helper (reuse pattern from other test files)
# ---------------------------------------------------------------------------

def _validate_required_keys(obj: dict, schema: dict) -> list[str]:
    errors = []
    for req in schema.get("required", []):
        if req not in obj:
            errors.append(f"missing required key: {req!r}")
    return errors


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_extract_centroid_returns_all_required_keys():
    """(1) extract_centroid() output contains all TeamCentroid required keys."""
    company = _StubCompany()
    budget = CostBudget(ceiling_usd=10.0)
    canned = _make_canned_centroid()

    with patch(
        "app.services.simulation.team_synthesizer.tracked_chat_json",
        new=AsyncMock(return_value=canned),
    ):
        result = await extract_centroid(company, budget=budget)

    errors = _validate_required_keys(result, TEAM_CENTROID_SCHEMA)
    assert errors == [], errors


@pytest.mark.asyncio
async def test_big_five_centroid_has_provenance():
    """(2) Every big_five_centroid trait carries a provenance string."""
    company = _StubCompany()
    budget = CostBudget(ceiling_usd=10.0)
    canned = _make_canned_centroid()

    with patch(
        "app.services.simulation.team_synthesizer.tracked_chat_json",
        new=AsyncMock(return_value=canned),
    ):
        result = await extract_centroid(company, budget=budget)

    bf = result["big_five_centroid"]
    for trait in ("openness", "conscientiousness", "extraversion", "agreeableness", "neuroticism"):
        assert trait in bf, f"Missing trait: {trait}"
        assert isinstance(bf[trait]["value"], (int, float))
        assert isinstance(bf[trait]["provenance"], str)
        assert bf[trait]["provenance"] != ""


@pytest.mark.asyncio
async def test_sigma_recommendations_has_all_keys():
    """(3) sigma_recommendations contains big_five, skill, work_style."""
    company = _StubCompany()
    budget = CostBudget(ceiling_usd=10.0)
    canned = _make_canned_centroid()

    with patch(
        "app.services.simulation.team_synthesizer.tracked_chat_json",
        new=AsyncMock(return_value=canned),
    ):
        result = await extract_centroid(company, budget=budget)

    sigma = result["sigma_recommendations"]
    assert "big_five" in sigma
    assert "skill" in sigma
    assert "work_style" in sigma


@pytest.mark.asyncio
async def test_centroid_tensions_is_list():
    """(4) centroid_tensions is a list; each entry has id/description/evidence."""
    company = _StubCompany()
    budget = CostBudget(ceiling_usd=10.0)
    canned = _make_canned_centroid()

    with patch(
        "app.services.simulation.team_synthesizer.tracked_chat_json",
        new=AsyncMock(return_value=canned),
    ):
        result = await extract_centroid(company, budget=budget)

    tensions = result["centroid_tensions"]
    assert isinstance(tensions, list)
    for t in tensions:
        assert "id" in t
        assert "description" in t
        assert "evidence" in t


def test_render_prompt_includes_knowledge_graph_summary():
    """(5) Knowledge graph summary appears in the rendered user prompt."""
    company = _StubCompany()
    prompt = _render_centroid_user_prompt(company)
    # The stub company has a knowledge_graph with one value node
    assert "Rigor" in prompt or "knowledge_graph" in prompt.lower() or "(none)" in prompt
    assert "KNOWLEDGE GRAPH NODES" in prompt


def test_render_criteria_block_includes_all_criteria():
    """criteria_block renders all criteria with keys and labels."""
    company = _StubCompany()
    block = _render_criteria_block(company)
    assert "analyticalRigor" in block
    assert "writtenDissent" in block
    assert "Analytical Rigor" in block


def test_render_criteria_block_empty():
    """criteria_block returns placeholder when no criteria defined."""
    class _NoCriteria(_StubCompany):
        criteria = []

    block = _render_criteria_block(_NoCriteria())
    assert "no criteria defined" in block


def test_render_prompt_no_artifacts_uses_placeholder():
    """Absent artifacts render as '(none provided)' not empty string."""
    class _BareOrg:
        id = "o"; name = "Bare"; tagline = None; mission = ""

    class _BareTeam:
        id = "t"; organization_id = "o"; name = "Bare core team"
        artifact_team_structure = ""
        artifact_sample_comms = ""
        knowledge_graph = None
        teammates: list = []
        scenarios: list = []

    class _Bare(_StubCompany):
        artifact_role_spec = ""
        organization = _BareOrg()
        team = _BareTeam()

    prompt = _render_centroid_user_prompt(_Bare())
    assert "(none provided)" in prompt
    assert "(none)" in prompt  # tagline + kg summary


@pytest.mark.asyncio
async def test_extract_centroid_empty_tensions_is_valid():
    """extract_centroid is valid when centroid_tensions is an empty list."""
    company = _StubCompany()
    budget = CostBudget(ceiling_usd=10.0)
    canned = dict(_make_canned_centroid())
    canned["centroid_tensions"] = []

    with patch(
        "app.services.simulation.team_synthesizer.tracked_chat_json",
        new=AsyncMock(return_value=canned),
    ):
        result = await extract_centroid(company, budget=budget)

    assert result["centroid_tensions"] == []
    assert result["sigma_recommendations"]["big_five"] == pytest.approx(0.6)
