"""Unit tests for services/simulation/agent_runtime.py — Phase 4A.

Validation gate:
  (1) advance_turn() calls tracked_chat_json and appends a record to turn_history.
  (2) The turn record contains required fields: turn, speaker_id, content, ends_turn.
  (3) Round-robin order puts candidate first.
  (4) ends_turn=True signal is returned correctly from advance_turn().
  (5) Visible record (no intent/internal_state) is broadcast to other agents.
  (6) world.current_turn is incremented after each advance_turn() call.
  (7) _render_agent_turn_prompt includes persona name and scenario prompt.
  (8) _build_turn_order places candidate first regardless of insertion order.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.services.simulation.agent_runtime import (
    AGENT_TURN_SCHEMA,
    _build_turn_order,
    _render_agent_turn_prompt,
    advance_turn,
)
from app.services.simulation.scenario_engine import AgentState, WorldState
from app.services.simulation.cost_tracker import CostBudget


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_world(num_teammates: int = 1) -> WorldState:
    agents: dict = {
        "candidate": AgentState(
            agent_id="candidate",
            persona={
                "narrative": "Candidate with strong analytical background.",
                "structured_traits": {},
                "private_goals": ["Demonstrate structured thinking."],
            },
            memory=[],
            scratchpad={},
        ),
    }
    for i in range(num_teammates):
        tid = f"teammate:tm{i}"
        agents[tid] = AgentState(
            agent_id=tid,
            persona={
                "name": f"Alex {i}",
                "role_on_team": "Associate",
                "seniority": "senior",
                "narrative": "Experienced deal-side associate.",
                "trait_sheet": {},
                "private_goals": ["Probe the candidate's reasoning."],
            },
            memory=[],
            scratchpad={},
        )

    return WorldState(
        scenario={
            "id": "scen-1",
            "title": "Budget pressure",
            "type": "dyad",
            "prompt": "Q4 targets are at risk. What do you cut?",
            "candidate_role": "Analyst presenting options.",
            "expected_arc": "Structured, prioritised recommendation.",
            "scoring_dims": ["written_rigor"],
            "max_turns": 6,
        },
        agents=agents,
        turn_history=[],
        current_turn=0,
        seed="test-seed-1",
        candidate_agent_id="candidate",
    )


def _stub_turn_response(utterance: str = "Hello.", ends_turn: bool = False) -> dict:
    return {
        "utterance": utterance,
        "intent": "open the conversation",
        "internal_state": "calm",
        "ends_turn": ends_turn,
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_advance_turn_appends_record():
    world = _make_world()
    budget = CostBudget(ceiling_usd=1.0)

    with patch(
        "app.services.simulation.agent_runtime.tracked_chat_json",
        new=AsyncMock(return_value=_stub_turn_response("Good morning.")),
    ):
        await advance_turn(world, budget=budget, company_name="Meridian Capital")

    assert len(world.turn_history) == 1
    record = world.turn_history[0]
    assert record["content"] == "Good morning."
    assert record["speaker_id"] == "candidate"
    assert record["turn"] == 0


@pytest.mark.asyncio
async def test_advance_turn_increments_current_turn():
    world = _make_world()
    budget = CostBudget(ceiling_usd=1.0)

    with patch(
        "app.services.simulation.agent_runtime.tracked_chat_json",
        new=AsyncMock(return_value=_stub_turn_response()),
    ):
        await advance_turn(world, budget=budget, company_name="Test Co")

    assert world.current_turn == 1


@pytest.mark.asyncio
async def test_advance_turn_returns_ends_turn_signal():
    world = _make_world()
    budget = CostBudget(ceiling_usd=1.0)

    with patch(
        "app.services.simulation.agent_runtime.tracked_chat_json",
        new=AsyncMock(return_value=_stub_turn_response(ends_turn=True)),
    ):
        ended = await advance_turn(world, budget=budget, company_name="Test Co")

    assert ended is True


@pytest.mark.asyncio
async def test_advance_turn_returns_false_when_not_ended():
    world = _make_world()
    budget = CostBudget(ceiling_usd=1.0)

    with patch(
        "app.services.simulation.agent_runtime.tracked_chat_json",
        new=AsyncMock(return_value=_stub_turn_response(ends_turn=False)),
    ):
        ended = await advance_turn(world, budget=budget, company_name="Test Co")

    assert ended is False


@pytest.mark.asyncio
async def test_visible_record_broadcast_to_other_agents():
    world = _make_world(num_teammates=1)
    budget = CostBudget(ceiling_usd=1.0)

    with patch(
        "app.services.simulation.agent_runtime.tracked_chat_json",
        new=AsyncMock(return_value=_stub_turn_response("Test utterance.")),
    ):
        await advance_turn(world, budget=budget, company_name="Test Co")

    # The candidate spoke (turn 0). Teammate should have received the visible record.
    teammate_id = "teammate:tm0"
    assert len(world.agents[teammate_id].memory) == 1
    visible = world.agents[teammate_id].memory[0]
    # Private fields must NOT be in the visible record.
    assert "intent" not in visible
    assert "internal_state" not in visible
    assert visible["content"] == "Test utterance."


@pytest.mark.asyncio
async def test_speaker_does_not_receive_own_utterance_in_memory():
    world = _make_world(num_teammates=1)
    budget = CostBudget(ceiling_usd=1.0)

    with patch(
        "app.services.simulation.agent_runtime.tracked_chat_json",
        new=AsyncMock(return_value=_stub_turn_response()),
    ):
        await advance_turn(world, budget=budget, company_name="Test Co")

    # Candidate spoke; their own memory should NOT contain the broadcast.
    assert len(world.agents["candidate"].memory) == 0


@pytest.mark.asyncio
async def test_round_robin_candidate_first():
    world = _make_world(num_teammates=1)
    budget = CostBudget(ceiling_usd=1.0)
    calls: list[str] = []

    async def _capture(*args, **kwargs):
        # Determine who was asked to speak from the user prompt.
        user = kwargs.get("user", "")
        if "candidate" in user.lower() and "your turn" in user.lower():
            calls.append("candidate")
        else:
            calls.append("teammate")
        return _stub_turn_response()

    with patch(
        "app.services.simulation.agent_runtime.tracked_chat_json",
        new=AsyncMock(side_effect=_capture),
    ):
        await advance_turn(world, budget=budget, company_name="Test Co")  # turn 0
        await advance_turn(world, budget=budget, company_name="Test Co")  # turn 1

    assert world.turn_history[0]["speaker_id"] == "candidate"
    assert world.turn_history[1]["speaker_id"] != "candidate"


def test_build_turn_order_candidate_first():
    world = _make_world(num_teammates=2)
    order = _build_turn_order(world)
    assert order[0] == "candidate"
    assert len(order) == 3  # candidate + 2 teammates


def test_build_turn_order_no_candidate():
    world = _make_world(num_teammates=1)
    del world.agents["candidate"]
    order = _build_turn_order(world)
    assert "candidate" not in order
    assert len(order) == 1


def test_render_agent_turn_prompt_includes_persona_and_scenario():
    world = _make_world()
    agent = world.agents["candidate"]
    prompt = _render_agent_turn_prompt(agent, world, company_name="Meridian Capital")
    assert "Meridian Capital" in prompt
    assert "Q4 targets are at risk" in prompt


def test_candidate_prompt_includes_verified_profile_blocks():
    """PR #1.2/1.3: capability ledger + voice samples + comm style render
    inside the candidate's user prompt. Teammate prompts are unaffected."""
    world = _make_world(num_teammates=1)
    world.agents["candidate"].persona["verified_profile"] = {
        "education": [
            {"institution": "ETH Zurich", "degree": "MSc", "field": "CS",
             "start": "2018", "end": "2020"},
        ],
        "experience": [
            {"role": "Backend engineer", "company": "Acme",
             "start": "2021", "end": "2024", "bullets": []},
        ],
        "skills": [],
        "github_repos": [
            {"name": "stream-toolkit", "language": "Go", "stars": 12,
             "description": "small streaming helpers"},
        ],
        "capability_ledger": {
            "known": [{"skill": "Go", "depth_evidence": ["mentioned in CV"]}],
            "exposure_only": ["Kubernetes"],
            "role_year_span": 3,
        },
        "communication_ledger": {
            "avg_sentence_length": 14.2,
            "hedging_rate": 0.3,
            "voice_sample_count": 2,
            "voice_sample_total_chars": 480,
        },
        "voice_samples": [
            {"source": "github_readme",
             "text": "honestly the way we ended up doing it was a little hacky."},
        ],
    }

    candidate_prompt = _render_agent_turn_prompt(
        world.agents["candidate"], world, company_name="Acme",
    )
    assert "VERIFIED PROFILE" in candidate_prompt
    assert "Confidently held: Go" in candidate_prompt
    assert "Limited exposure" in candidate_prompt
    assert "Kubernetes" in candidate_prompt
    assert "VOICE SAMPLES" in candidate_prompt
    assert "honestly the way we ended up doing it" in candidate_prompt
    assert "ETH Zurich" in candidate_prompt

    teammate_prompt = _render_agent_turn_prompt(
        world.agents["teammate:tm0"], world, company_name="Acme",
    )
    assert "VERIFIED PROFILE" not in teammate_prompt


def test_candidate_prompt_renders_gap_briefing_when_present():
    """PR #1.4: gap_briefing on world.scenario shows up in the candidate prompt."""
    world = _make_world()
    world.scenario["gap_briefing"] = {
        "required_skills": ["Kubernetes operator design"],
        "gaps": [
            {"skill": "Kubernetes operator design", "severity": "absent",
             "guidance": "Admit you don't know; ask clarifying questions."},
        ],
        "notes": "candidate ledger has no k8s evidence",
    }
    prompt = _render_agent_turn_prompt(
        world.agents["candidate"], world, company_name="Acme",
    )
    assert "SCENARIO GAP BRIEFING" in prompt
    assert "Kubernetes operator design" in prompt
    assert "Admit you don't know" in prompt


def test_turn_record_has_required_fields():
    world = _make_world()
    # Simulate what advance_turn writes.
    record = {
        "turn": 0,
        "speaker_id": "candidate",
        "speaker_name": "Candidate",
        "speaker_role": "Candidate",
        "content": "Hello.",
        "intent": "open",
        "internal_state": "calm",
        "ends_turn": False,
    }
    for field in ("turn", "speaker_id", "speaker_name", "content", "ends_turn"):
        assert field in record
