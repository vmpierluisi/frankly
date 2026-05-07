"""Unit tests for services/simulation/knowledge_graph.py.

Validation gate (Phase 2A / F.1):
  (1) Every value/behavior/anti_behavior/role/decision node has at least one
      cites edge to an artifact_quote node.
  (2) conflicts_with edges reference valid node ids on both endpoints.
  (3) Non-quote node count is between 8 and 30 (enforced in code).
  (4) extract() returns a dict that passes validate_graph() with no warnings.
  (5) summarize_for_prompt() returns a non-empty string for a real graph.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.services.simulation.knowledge_graph import (
    KNOWLEDGE_GRAPH_SCHEMA,
    extract,
    summarize_for_prompt,
    validate_graph,
)
from app.services.simulation.cost_tracker import CostBudget


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def _make_canned_graph(
    extra_nodes: list | None = None,
    extra_edges: list | None = None,
    omit_cites: bool = False,
) -> dict:
    """Build a minimal valid knowledge graph for testing."""
    nodes = [
        {"id": "value:rigor", "type": "value", "label": "Analytical Rigor",
         "body": "We expect thorough analysis before any recommendation."},
        {"id": "value:honesty", "type": "value", "label": "Intellectual Honesty",
         "body": "Admit uncertainty; never oversell a thesis."},
        {"id": "behavior:written-dissent", "type": "behavior",
         "label": "Written Dissent", "body": "Disagree in writing, early, constructively."},
        {"id": "behavior:memo-first", "type": "behavior",
         "label": "Memo-First Communication", "body": "Produce a memo before any meeting."},
        {"id": "anti_behavior:politeness-over-truth", "type": "anti_behavior",
         "label": "Silence for Social Comfort",
         "body": "Staying quiet to preserve harmony is penalized."},
        {"id": "role:analyst", "type": "role", "label": "Analyst",
         "body": "Junior IC; owns deal modeling and memo authorship."},
        {"id": "role:pod-vp", "type": "role", "label": "Pod VP",
         "body": "Approves IC recommendation; coaches analysts."},
        {"id": "decision:ic-vote", "type": "decision", "label": "IC Vote",
         "body": "Weekly committee vote; every IC member votes independently."},
        # artifact quotes
        {"id": "quote:1", "type": "artifact_quote", "label": "Quote 1",
         "body": "We expect written disagreement before the IC memo is circulated."},
        {"id": "quote:2", "type": "artifact_quote", "label": "Quote 2",
         "body": "Analysis must stand on its own; verbal conviction is insufficient."},
        {"id": "quote:3", "type": "artifact_quote", "label": "Quote 3",
         "body": "The analyst owns the first draft and the final model."},
    ]
    if extra_nodes:
        nodes.extend(extra_nodes)

    edges = [
        {"source": "value:rigor", "target": "behavior:memo-first",
         "type": "demands", "note": "Rigor implies written-first work."},
        {"source": "value:honesty", "target": "behavior:written-dissent",
         "type": "demands", "note": "Honesty demands explicit dissent."},
        {"source": "value:honesty", "target": "anti_behavior:politeness-over-truth",
         "type": "forbids", "note": "Honesty forbids silence for comfort."},
        {"source": "decision:ic-vote", "target": "behavior:written-dissent",
         "type": "informs", "note": "IC vote requires all analysts to dissent in writing first."},
        {"source": "role:analyst", "target": "behavior:memo-first",
         "type": "demands", "note": "Analysts produce memos as primary output."},
    ]
    if not omit_cites:
        edges += [
            {"source": "value:rigor", "target": "quote:2", "type": "cites",
             "note": "Artifact grounds rigor value."},
            {"source": "value:honesty", "target": "quote:1", "type": "cites",
             "note": "Artifact grounds honesty value."},
            {"source": "behavior:written-dissent", "target": "quote:1",
             "type": "cites", "note": "Artifact grounds written dissent behavior."},
            {"source": "behavior:memo-first", "target": "quote:2", "type": "cites",
             "note": "Artifact grounds memo-first behavior."},
            {"source": "anti_behavior:politeness-over-truth", "target": "quote:1",
             "type": "cites", "note": "Artifact grounds anti-behavior."},
            {"source": "role:analyst", "target": "quote:3", "type": "cites",
             "note": "Artifact grounds analyst role."},
            {"source": "role:pod-vp", "target": "quote:3", "type": "cites",
             "note": "Artifact grounds pod-vp role."},
            {"source": "decision:ic-vote", "target": "quote:1", "type": "cites",
             "note": "Artifact grounds ic-vote decision."},
        ]
    if extra_edges:
        edges.extend(extra_edges)

    return {"nodes": nodes, "edges": edges}


class _StubOrg:
    id = "org-meridian"
    name = "Meridian Capital"
    tagline = "Patience as a competitive edge."
    mission = "We value written rigor and intellectual honesty."


class _StubTeam:
    id = "team-meridian"
    organization_id = "org-meridian"
    name = "Meridian core team"
    artifact_team_structure = "Pod structure: 1 VP + 2 analysts per pod."
    artifact_sample_comms = "Example memo: 'IRR below hurdle; recommend pass.'"
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
    criteria = []


# ---------------------------------------------------------------------------
# validate_graph tests
# ---------------------------------------------------------------------------

def test_valid_graph_produces_no_warnings():
    """(4) A well-formed graph has zero validate_graph() warnings."""
    graph = _make_canned_graph()
    warnings = validate_graph(graph)
    assert warnings == [], warnings


def test_missing_cites_edge_produces_warning():
    """(1) A non-quote node without a cites edge → warning."""
    graph = _make_canned_graph(omit_cites=True)
    warnings = validate_graph(graph)
    # Every non-quote node (8 of them) should flag
    types_warned = {w for w in warnings if "no cites edge" in w}
    assert len(types_warned) > 0


def test_conflicts_with_invalid_endpoint_warns():
    """(2) conflicts_with edge pointing to unknown node → warning."""
    graph = _make_canned_graph(
        extra_edges=[
            {"source": "value:rigor", "target": "value:nonexistent",
             "type": "conflicts_with", "note": "tension"}
        ]
    )
    warnings = validate_graph(graph)
    assert any("unknown node" in w for w in warnings)


def test_valid_conflicts_with_edge_no_warning():
    """(2) conflicts_with edge between existing nodes does not warn."""
    graph = _make_canned_graph(
        extra_edges=[
            {"source": "value:rigor", "target": "value:honesty",
             "type": "conflicts_with", "note": "tension between rigor and honesty"}
        ]
    )
    warnings = validate_graph(graph)
    # No 'unknown node' warning for a valid conflicts_with edge
    assert not any("unknown node" in w for w in warnings)


def test_node_count_too_low_warns():
    """(3) Fewer than 8 non-quote nodes → warning."""
    graph = {
        "nodes": [
            {"id": "value:x", "type": "value", "label": "X", "body": "x"},
            {"id": "quote:1", "type": "artifact_quote", "label": "Q1", "body": "q1"},
        ],
        "edges": [
            {"source": "value:x", "target": "quote:1", "type": "cites", "note": ""},
        ],
    }
    warnings = validate_graph(graph)
    assert any("non-quote nodes" in w and "at least 8" in w for w in warnings)


def test_node_count_too_high_warns():
    """(3) More than 25 non-quote nodes → warning."""
    extra = [
        {"id": f"value:extra{i}", "type": "value", "label": f"E{i}", "body": "b"}
        for i in range(20)
    ]
    graph = _make_canned_graph(extra_nodes=extra)
    warnings = validate_graph(graph)
    assert any("≤25" in w for w in warnings)


# ---------------------------------------------------------------------------
# extract() tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_extract_returns_valid_graph():
    """extract() passes the canned response through and validates it."""
    company = _StubCompany()
    budget = CostBudget(ceiling_usd=10.0)
    canned = _make_canned_graph()

    with patch(
        "app.services.simulation.knowledge_graph.tracked_chat_json",
        new=AsyncMock(return_value=canned),
    ):
        result = await extract(company, budget=budget)

    assert "nodes" in result
    assert "edges" in result
    assert len(result["nodes"]) > 0
    warnings = validate_graph(result)
    assert warnings == [], warnings


@pytest.mark.asyncio
async def test_extract_logs_warnings_but_does_not_raise(caplog):
    """extract() logs validate_graph warnings but returns the result anyway."""
    import logging
    company = _StubCompany()
    budget = CostBudget(ceiling_usd=10.0)
    bad_graph = _make_canned_graph(omit_cites=True)  # will produce warnings

    with patch(
        "app.services.simulation.knowledge_graph.tracked_chat_json",
        new=AsyncMock(return_value=bad_graph),
    ):
        with caplog.at_level(logging.WARNING):
            result = await extract(company, budget=budget)

    assert result is not None
    assert any("no cites edge" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# summarize_for_prompt tests
# ---------------------------------------------------------------------------

def test_summarize_returns_non_empty_for_valid_graph():
    """(5) summarize_for_prompt() returns a non-empty string for a real graph."""
    graph = _make_canned_graph()
    summary = summarize_for_prompt(graph)
    assert summary != "(none)"
    assert len(summary) > 10


def test_summarize_returns_none_string_for_empty():
    """summarize_for_prompt() returns '(none)' for None input."""
    assert summarize_for_prompt(None) == "(none)"
    assert summarize_for_prompt({}) == "(none)"
    assert summarize_for_prompt({"nodes": [], "edges": []}) == "(none)"


def test_summarize_excludes_artifact_quotes():
    """summarize_for_prompt() does not include artifact_quote nodes."""
    graph = _make_canned_graph()
    summary = summarize_for_prompt(graph)
    assert "artifact_quote" not in summary


def test_summarize_includes_conflicts():
    """summarize_for_prompt() surfaces conflicts_with edges as TENSIONS."""
    graph = _make_canned_graph(
        extra_edges=[
            {"source": "value:rigor", "target": "value:honesty",
             "type": "conflicts_with", "note": "speed vs depth"}
        ]
    )
    summary = summarize_for_prompt(graph)
    assert "TENSIONS" in summary
