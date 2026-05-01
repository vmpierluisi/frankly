"""Agent turn-execution runtime for multi-agent rollouts.

MiroFish lineage: corresponds to MiroFish's RolloutExecutor turn loop.
Phase 4A ships advance_turn() (round-robin) with verbatim prompts from
Appendix A.6 / B.6. The speaker-selector LLM is deferred to a follow-up.
"""
from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from ...config import settings
from .cost_tracker import CostBudget, PERSONA_PROVIDER, tracked_chat_json
from .scenario_engine import AgentState, WorldState

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

_AGENT_MODEL = settings.openrouter_persona_model
_AGENT_PROVIDER = PERSONA_PROVIDER

# ---------------------------------------------------------------------------
# Prompt templates (verbatim from brief Appendix A.6)
# ---------------------------------------------------------------------------

AGENT_TURN_SYSTEM = """\
You are participating in a workplace simulation as a specific person with
a specific role and specific private goals. Your task is to produce one
turn of dialogue or action that this person would plausibly take given
the situation, the conversation so far, and your private goals.

HARD RULES:
  1. STAY IN CHARACTER. Your persona's traits, goals, and seniority are
     fixed — do not drift.
  2. Produce ONE turn. Not the whole scene. Other agents will respond.
  3. Your private_goals are private. Do not narrate them. Other agents
     do not see them. Your behavior should pursue them, but your
     utterance should not announce them.
  4. Express intent in the structured intent field — this is metadata
     visible only to the simulation system. The intent should describe
     what you are trying to accomplish with this turn (e.g. "probe the
     candidate's reasoning", "concede the analytical point but push back
     on tone", "redirect to a tactical decision").
  5. internal_state is a brief note for your own continuity across turns
     (e.g. "growing concerned about the candidate's deadline framing",
     "satisfied with the analytical depth"). Other agents do not see it.
  6. Never reference protected characteristics or proxies.
  7. Output strict JSON matching the AgentTurn schema.
  8. Set ends_turn=true ONLY when the conversation has reached a natural
     stopping point that this character would recognize (a partner has
     decided; the IC has voted; you have explicitly excused yourself; the
     written deliverable is complete). Do not set it as a way to shorten
     a difficult conversation. The runtime may end the rollout early on
     this signal — use it sparingly.

LENGTH GUIDANCE:
  * utterance: 1 short paragraph for verbal turns (60-200 words);
    1-3 sentences for terse roles (e.g. a partner who decides quickly).
  * intent: one short sentence.
  * internal_state: one short sentence.\
"""

AGENT_TURN_USER_TEMPLATE = """\
You are: {agent_name}, {role_on_team} ({seniority}) at {company_name}.

YOUR PERSONA
{persona_narrative}

YOUR STRUCTURED TRAITS (for reference)
{trait_sheet_json}

YOUR PRIVATE GOALS IN THIS SCENARIO
{private_goals_block}

YOUR INTERNAL STATE FROM PRIOR TURNS (may be empty on turn 1)
{internal_state_history}

SCENARIO (visible to all participants)
{scenario_prompt}

PARTICIPANTS
{participants_block}

CONVERSATION SO FAR (turn-by-turn)
{conversation_so_far}

It is now your turn ({agent_name}'s turn, turn #{turn_number}). Produce
your turn as JSON matching the AgentTurn schema.\
"""

# ---------------------------------------------------------------------------
# JSON schema (verbatim from brief Appendix B.6)
# ---------------------------------------------------------------------------

AGENT_TURN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "utterance": {
            "type": "string",
            "description": "The agent's spoken / written contribution this turn. 1-200 words.",
        },
        "intent": {
            "type": "string",
            "description": "One short sentence describing what the agent is trying to accomplish. NOT visible to other agents.",
        },
        "internal_state": {
            "type": "string",
            "description": "One short sentence note for this agent's continuity across turns. NOT visible to other agents.",
        },
        "ends_turn": {
            "type": "boolean",
            "description": "True if the agent considers the conversation naturally complete after this turn.",
        },
    },
    "required": ["utterance", "intent", "internal_state", "ends_turn"],
    "additionalProperties": False,
}


# ---------------------------------------------------------------------------
# Prompt rendering helpers
# ---------------------------------------------------------------------------

def _agent_name(agent: AgentState) -> str:
    return agent.persona.get("name", "Candidate" if agent.agent_id == "candidate" else agent.agent_id)


def _render_private_goals_block(goals: list[str]) -> str:
    if not goals:
        return "  (none specified)"
    return "\n".join(f"  * {g}" for g in goals)


def _render_internal_state_history(agent: AgentState, turn_history: list[dict]) -> str:
    """Collect this agent's internal_state notes from prior turns."""
    notes = [
        f"[turn {t['turn']}] {t['internal_state']}"
        for t in turn_history
        if t.get("speaker_id") == agent.agent_id and t.get("internal_state")
    ]
    return "\n".join(notes) if notes else "(none — first turn)"


def _render_participants_block(world: WorldState) -> str:
    lines: list[str] = []
    for agent in world.agents.values():
        name = _agent_name(agent)
        role = agent.persona.get("role_on_team", "Candidate" if agent.agent_id == "candidate" else "—")
        seniority = agent.persona.get("seniority", "—")
        lines.append(f"  * {name} — {role} ({seniority})")
    return "\n".join(lines)


def _render_conversation_so_far(turn_history: list[dict]) -> str:
    if not turn_history:
        return "(no turns yet — you are opening the conversation)"
    return "\n".join(
        f"[turn {t['turn']} · {t.get('speaker_name', t['speaker_id'])}] {t['content']}"
        for t in turn_history
    )


def _render_agent_turn_prompt(
    agent: AgentState,
    world: WorldState,
    company_name: str,
) -> str:
    persona = agent.persona
    name = _agent_name(agent)
    role = persona.get("role_on_team", "Candidate" if agent.agent_id == "candidate" else "—")
    seniority = persona.get("seniority", "—")
    narrative = persona.get("narrative", "(no narrative provided)")
    trait_sheet = persona.get("trait_sheet") or persona.get("structured_traits") or {}
    goals = persona.get("private_goals", [])

    return AGENT_TURN_USER_TEMPLATE.format(
        agent_name=name,
        role_on_team=role,
        seniority=seniority,
        company_name=company_name,
        persona_narrative=narrative,
        trait_sheet_json=json.dumps(trait_sheet, indent=2),
        private_goals_block=_render_private_goals_block(goals),
        internal_state_history=_render_internal_state_history(agent, world.turn_history),
        scenario_prompt=world.scenario.get("prompt", ""),
        participants_block=_render_participants_block(world),
        conversation_so_far=_render_conversation_so_far(world.turn_history),
        turn_number=world.current_turn + 1,
    )


# ---------------------------------------------------------------------------
# Round-robin speaker selection
# ---------------------------------------------------------------------------

def _build_turn_order(world: WorldState) -> list[str]:
    """Canonical agent turn order: candidate first, then teammates in insertion order."""
    ids = list(world.agents.keys())
    # Ensure candidate is always first.
    if "candidate" in ids:
        ids.remove("candidate")
        ids.insert(0, "candidate")
    return ids


# ---------------------------------------------------------------------------
# Phase 4A public API
# ---------------------------------------------------------------------------

async def advance_turn(
    world: WorldState,
    *,
    budget: CostBudget,
    company_name: str = "",
    turn_order: list[str] | None = None,
) -> bool:
    """Execute one turn in the rollout, mutating world in place.

    Returns True if the rollout should end early (ends_turn signal or
    max_turns reached). Caller is responsible for the loop condition.

    Round-robin speaker selection (v0). Speaker-selector LLM is Phase 4A+.
    """
    if turn_order is None:
        turn_order = _build_turn_order(world)

    speaker_id = turn_order[world.current_turn % len(turn_order)]
    agent = world.agents[speaker_id]

    user_prompt = _render_agent_turn_prompt(agent, world, company_name)

    raw = await tracked_chat_json(
        budget,
        system=AGENT_TURN_SYSTEM,
        user=user_prompt,
        schema=AGENT_TURN_SCHEMA,
        schema_name="agent_turn",
        temperature=0.7,
        max_tokens=600,
        model=_AGENT_MODEL,
        provider=_AGENT_PROVIDER,
    )

    turn_record: dict[str, Any] = {
        "turn": world.current_turn,
        "speaker_id": speaker_id,
        "speaker_name": _agent_name(agent),
        "speaker_role": agent.persona.get("role_on_team", "Candidate"),
        "content": raw["utterance"],
        "intent": raw["intent"],
        "internal_state": raw["internal_state"],
        "ends_turn": raw.get("ends_turn", False),
    }

    world.turn_history.append(turn_record)

    # Broadcast utterance to all agents' memory (no private fields).
    visible_record = {k: v for k, v in turn_record.items() if k not in ("intent", "internal_state")}
    for aid, other_agent in world.agents.items():
        if aid != speaker_id:
            other_agent.memory.append(visible_record)

    world.current_turn += 1

    logger.debug(
        "advance_turn: turn=%d speaker=%s ends_turn=%s",
        turn_record["turn"], speaker_id, raw.get("ends_turn"),
    )

    return bool(raw.get("ends_turn", False))
