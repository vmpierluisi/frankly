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

BEHAVIORAL CONTRACT (when a verified profile is provided, ABSOLUTE):
  * The "VERIFIED PROFILE" section below documents the real person's
    actual skills and communication style. Treat it as a hard ceiling
    on what this person can demonstrate.
  * Confidently held skills (capability_ledger.known) → unconstrained.
  * Limited-exposure skills (capability_ledger.exposure_only) → you may
    recognize the term and attempt, but you should hedge, ask for help,
    or admit gaps when pressed for specifics. Probabilistic — you can
    sometimes get the gist right, sometimes fumble. Do NOT produce
    fluent, idiomatic, expert-level execution on these.
  * Skills NOT in the ledger at all → deterministic. Admit you don't
    know, ask clarifying questions, or pivot. Never fake fluency.
  * Communication style — match the patterns in
    "VOICE SAMPLES" (verbatim few-shot). Mirror sentence length,
    hedging frequency, formality, and idiosyncrasies. The samples are
    how this person ACTUALLY writes. Do not produce polished prose if
    the samples are casual; do not produce casual prose if the samples
    are formal.
  * Education and experience listed in the profile are this person's
    real background. Do not invent credentials, projects, or roles
    that aren't there.
  * If the SCENARIO GAP BRIEFING block is present, it lists the
    specific gaps for this scenario — make those gaps visible in your
    behavior in a natural, in-character way.
  * Producing skill, vocabulary, or style beyond what is documented
    breaks the simulation. Faithfulness > polish.

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
{verified_profile_block}{gap_briefing_block}
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


# ---------------------------------------------------------------------------
# Verified profile rendering (PR #1: persona faithfulness)
# ---------------------------------------------------------------------------

_MAX_VOICE_SAMPLES_RENDERED = 5
_MAX_VOICE_SAMPLE_CHARS = 600
_MAX_REPOS_RENDERED = 6
_MAX_EXPERIENCE_RENDERED = 6


def _render_education_lines(education: list[dict]) -> list[str]:
    lines: list[str] = []
    for e in education:
        institution = e.get("institution") or "(unknown)"
        degree = e.get("degree") or ""
        field = e.get("field") or ""
        years = " ".join(filter(None, [e.get("start", ""), e.get("end", "")]))
        bits = [institution]
        if degree or field:
            bits.append(f"{degree} {field}".strip())
        if years.strip():
            bits.append(years.strip())
        lines.append("  * " + " — ".join(bits))
    return lines


def _render_experience_lines(experience: list[dict]) -> list[str]:
    lines: list[str] = []
    for e in experience[:_MAX_EXPERIENCE_RENDERED]:
        company = e.get("company") or "(unknown)"
        role = e.get("role") or ""
        years = "–".join(filter(None, [e.get("start", ""), e.get("end", "")]))
        head = f"  * {role} @ {company}"
        if years:
            head += f" ({years})"
        lines.append(head)
    return lines


def _render_capability_ledger(ledger: dict) -> list[str]:
    if not ledger:
        return ["  (no capability ledger available)"]
    lines: list[str] = []
    known = ledger.get("known") or []
    exposure = ledger.get("exposure_only") or []
    role_years = ledger.get("role_year_span")
    if known:
        named = ", ".join(
            f"{k.get('skill')}"
            + (f" [{'; '.join(k.get('depth_evidence', []))}]" if k.get("depth_evidence") else "")
            for k in known
        )
        lines.append(f"  Confidently held: {named}")
    else:
        lines.append("  Confidently held: (none)")
    if exposure:
        lines.append(f"  Limited exposure (recognize, can't execute fluently): {', '.join(exposure)}")
    else:
        lines.append("  Limited exposure: (none)")
    if role_years is not None:
        lines.append(f"  Total documented professional years: {role_years}")
    return lines


def _render_communication_ledger(ledger: dict) -> list[str]:
    if not ledger:
        return ["  (no communication ledger available)"]
    avg_len = ledger.get("avg_sentence_length")
    hedging = ledger.get("hedging_rate")
    sample_count = ledger.get("voice_sample_count", 0)
    lines: list[str] = []
    if avg_len is not None:
        lines.append(f"  Average sentence length: {avg_len} words")
    if hedging is not None:
        try:
            lines.append(f"  Hedging frequency: {float(hedging) * 100:.0f}% of clauses")
        except (TypeError, ValueError):
            pass
    lines.append(f"  Voice sample evidence: {sample_count} samples extracted")
    return lines


def _render_voice_samples(samples: list) -> list[str]:
    """Render voice samples for the agent prompt.

    Accepts heterogeneous shapes:
      - {"text": str, "source": str}    — canonical, from extractors
      - plain str                        — used by demo seeds and CV-only flows
    """
    if not samples:
        return ["  (no voice samples available — fall back to neutral but plain phrasing)"]
    lines: list[str] = []
    for s in samples[:_MAX_VOICE_SAMPLES_RENDERED]:
        if isinstance(s, str):
            text = s.strip()
            source = "?"
        elif isinstance(s, dict):
            text = (s.get("text") or "").strip()
            source = s.get("source", "?")
        else:
            continue
        if not text:
            continue
        text = text[:_MAX_VOICE_SAMPLE_CHARS]
        lines.append(f"  [{source}] {text}")
    return lines or ["  (samples present but empty — use neutral plain phrasing)"]


def _render_github_repos(repos: list[dict]) -> list[str]:
    if not repos:
        return []
    lines: list[str] = ["  GitHub repos (top):"]
    for r in repos[:_MAX_REPOS_RENDERED]:
        name = r.get("name") or "(unnamed)"
        lang = r.get("language") or "?"
        stars = r.get("stars", 0)
        desc = (r.get("description") or "").strip()
        head = f"    - {name} ({lang}, ★{stars})"
        if desc:
            head += f" — {desc[:160]}"
        lines.append(head)
    return lines


def _render_verified_profile_block(persona: dict) -> str:
    """Render the candidate's verified profile + voice samples for the prompt.

    Returns an empty string for non-candidate agents or when no verified
    profile is attached (so teammates retain their existing prompt shape).
    """
    vp = persona.get("verified_profile")
    if not vp:
        return ""

    blocks: list[str] = []
    blocks.append("\nVERIFIED PROFILE — REAL-WORLD BACKGROUND (treat as ground truth)")

    education = vp.get("education") or []
    if education:
        blocks.append("Education:")
        blocks.extend(_render_education_lines(education))

    experience = vp.get("experience") or []
    if experience:
        blocks.append("Experience (most recent first):")
        blocks.extend(_render_experience_lines(experience))

    capability = vp.get("capability_ledger") or {}
    blocks.append("Capability ledger:")
    blocks.extend(_render_capability_ledger(capability))

    repo_lines = _render_github_repos(vp.get("github_repos") or [])
    if repo_lines:
        blocks.extend(repo_lines)

    comm = vp.get("communication_ledger") or {}
    blocks.append("Communication style metrics:")
    blocks.extend(_render_communication_ledger(comm))

    samples = vp.get("voice_samples") or []
    blocks.append("VOICE SAMPLES (mirror this voice — verbatim excerpts of how this person actually writes):")
    blocks.extend(_render_voice_samples(samples))

    return "\n".join(blocks) + "\n"


def _render_gap_briefing_block(scenario: dict) -> str:
    """Render the per-rollout scenario→skill gap briefing if available."""
    briefing = scenario.get("gap_briefing")
    if not briefing:
        return ""
    lines = ["\nSCENARIO GAP BRIEFING (how your real-world gaps should manifest here)"]

    required = briefing.get("required_skills") or []
    if required:
        lines.append("  Skills the scenario probes: " + ", ".join(required))

    gaps = briefing.get("gaps") or []
    if gaps:
        lines.append("  Specific gaps to manifest:")
        for g in gaps:
            skill = g.get("skill", "?")
            severity = g.get("severity", "limited")
            guidance = g.get("guidance") or ""
            lines.append(f"    * {skill} [{severity}] — {guidance}")
    else:
        lines.append("  No explicit skill gaps for this scenario; play to your strengths.")

    notes = briefing.get("notes")
    if notes:
        lines.append(f"  Notes: {notes}")

    return "\n".join(lines) + "\n"


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

    # Verified-profile + gap-briefing blocks render only for the candidate
    # (teammate personas have no VerifiedProfile attached).
    verified_block = _render_verified_profile_block(persona)
    gap_block = (
        _render_gap_briefing_block(world.scenario) if agent.agent_id == "candidate" else ""
    )

    return AGENT_TURN_USER_TEMPLATE.format(
        agent_name=name,
        role_on_team=role,
        seniority=seniority,
        company_name=company_name,
        persona_narrative=narrative,
        trait_sheet_json=json.dumps(trait_sheet, indent=2),
        verified_profile_block=verified_block,
        gap_briefing_block=gap_block,
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

    # Lower temperature when the candidate is operating under a skill-gap
    # briefing — keeps the model closer to the deterministic/probabilistic
    # rules in the behavioral contract instead of inventing fluent execution
    # for skills the candidate doesn't have.
    temperature = 0.7
    if speaker_id == "candidate":
        gaps = (world.scenario.get("gap_briefing") or {}).get("gaps") or []
        if gaps:
            temperature = 0.4

    raw = await tracked_chat_json(
        budget,
        system=AGENT_TURN_SYSTEM,
        user=user_prompt,
        schema=AGENT_TURN_SCHEMA,
        schema_name="agent_turn",
        temperature=temperature,
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
