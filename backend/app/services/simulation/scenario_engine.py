"""Scenario library management and rollout data preparation.

MiroFish lineage: corresponds to MiroFish's ScenarioLibrary / draft_moments().
Phase 3A ships draft_scenarios() and prepare_rollout() (data prep only).
Phase 4A wires prepare_rollout() into the live rollout executor.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .cost_tracker import CostBudget, tracked_chat_json
from .knowledge_graph import summarize_for_prompt
from .team_synthesizer import _render_criteria_block

if TYPE_CHECKING:
    from ...models import Company, MomentOfTruth

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompt templates (verbatim from brief Appendix A.5)
# ---------------------------------------------------------------------------

SCENARIO_DRAFTER_SYSTEM = """\
You draft a library of "moments of truth" — concrete situations the role
actually encounters that probe whether a candidate would thrive in this
specific environment.

A good scenario:
  * Is grounded in the role spec, sample comms, or a knowledge_graph
    decision node — not a generic case.
  * Probes 1-3 specific company criteria (named in scoring_dims).
  * Has a clear candidate_role: what does the candidate need to do here?
  * Has a clear expected_arc: what does "good" look like for this team?
    (Used by the judge later. Do not write a single right answer — write
    the kinds of behaviors that would land well.)
  * Is one of three types:
      - dyad: candidate and one teammate (e.g. 1:1 escalation)
      - small_group: candidate and 2-3 teammates (e.g. deal review)
      - written: candidate produces written artifact, teammates respond async

HARD RULES:
  1. Produce 5-8 scenarios per call. Avoid repetition — each scenario
     should probe a distinct combination of criteria or a distinct social
     mode (dyad / small_group / written).
  2. Each scenario.scoring_dims uses the exact keys from the company's
     criteria — do not invent new dimension keys.
  3. Cite the artifact passages that motivated each scenario in
     scenario.grounding.
  4. Difficulty calibration: roughly half the scenarios should be hard
     (genuine value tensions, real stakes); roughly half should be normal
     workdays. Avoid trick questions.
  5. Strict JSON only.\
"""

SCENARIO_DRAFTER_USER_TEMPLATE = """\
Draft the scenario library for this company.

COMPANY: {company_name}
ROLE: {role}

CRITERIA (use exact keys for scoring_dims)
{criteria_block}

VALUES:
\"\"\"
{artifact_values}
\"\"\"
ROLE SPEC:
\"\"\"
{artifact_role_spec}
\"\"\"
TEAM STRUCTURE:
\"\"\"
{artifact_team_structure}
\"\"\"
SAMPLE COMMS:
\"\"\"
{artifact_sample_comms}
\"\"\"

KNOWLEDGE GRAPH (decision nodes are particularly useful seeds)
{knowledge_graph_summary}

Return a JSON object with `scenarios: [...]` matching the ScenarioLibrary
schema.\
"""

# ---------------------------------------------------------------------------
# JSON schema (verbatim from brief Appendix B.5)
# ---------------------------------------------------------------------------

SCENARIO_LIBRARY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "scenarios": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title":          {"type": "string"},
                    "type":           {"type": "string", "description": "One of: dyad, small_group, written."},
                    "prompt":         {"type": "string", "description": "The scenario setup, visible to all agents."},
                    "candidate_role": {"type": "string", "description": "What the candidate needs to do."},
                    "expected_arc":   {"type": "string", "description": "What 'good' looks like on this team."},
                    "scoring_dims": {
                        "type": "array",
                        "items": {"type": "string", "description": "Exact criterion key from the company."},
                    },
                    "participating_roles": {
                        "type": "array",
                        "items": {"type": "string", "description": "Role descriptions of teammates needed."},
                    },
                    "max_turns": {"type": "integer", "description": "Suggested max turns for the rollout."},
                    "grounding":  {"type": "string", "description": "Artifact lines that motivated this scenario."},
                },
                "required": [
                    "title", "type", "prompt", "candidate_role", "expected_arc",
                    "scoring_dims", "participating_roles", "max_turns", "grounding",
                ],
                "additionalProperties": False,
            },
        },
    },
    "required": ["scenarios"],
    "additionalProperties": False,
}

# ---------------------------------------------------------------------------
# WorldState / AgentState dataclasses (used by prepare_rollout; executed in 4A)
# ---------------------------------------------------------------------------

@dataclass
class AgentState:
    """State container for one agent in a rollout."""
    agent_id: str
    persona: dict        # SyntheticTeammate.trait_sheet + narrative + private_goals
    memory: list[dict]   # turn history visible to this agent
    scratchpad: dict     # per-agent internal state


@dataclass
class WorldState:
    """Full state of one rollout at a point in time."""
    scenario: dict
    agents: dict[str, AgentState]
    turn_history: list[dict]
    current_turn: int
    seed: str
    candidate_agent_id: str = "candidate"


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_scoring_dims(
    scoring_dims: list[str],
    company: "Company",
) -> list[str]:
    """Return list of scoring_dims keys that do NOT match any company criterion."""
    valid_keys = {c.key for c in getattr(company, "criteria", [])}
    return [k for k in scoring_dims if k not in valid_keys]


# ---------------------------------------------------------------------------
# Prompt rendering helpers
# ---------------------------------------------------------------------------

def _render_drafter_user_prompt(company: "Company") -> str:
    org = getattr(company, "organization", None)
    team = getattr(company, "team", None)
    return SCENARIO_DRAFTER_USER_TEMPLATE.format(
        company_name=company.name,
        role=company.role,
        criteria_block=_render_criteria_block(company),
        artifact_values=(org.mission if org is not None else None) or "(none provided)",
        artifact_role_spec=company.artifact_role_spec or "(none provided)",
        artifact_team_structure=(team.artifact_team_structure if team is not None else None) or "(none provided)",
        artifact_sample_comms=(team.artifact_sample_comms if team is not None else None) or "(none provided)",
        knowledge_graph_summary=summarize_for_prompt(
            (team.knowledge_graph if team is not None else None)
        ),
    )


# ---------------------------------------------------------------------------
# Phase 3A public API
# ---------------------------------------------------------------------------

async def draft_scenarios(
    company: "Company",
    *,
    budget: CostBudget,
) -> "list[MomentOfTruth]":
    """Draft a scenario library for a company from its artifacts.

    Returns a list of unsaved MomentOfTruth ORM objects.
    Caller is responsible for adding and committing them.

    MiroFish lineage: corresponds to ScenarioLibrary.draft_moments().
    """
    from ...models import MomentOfTruth  # deferred to avoid circular import

    user_prompt = _render_drafter_user_prompt(company)
    result = await tracked_chat_json(
        budget,
        system=SCENARIO_DRAFTER_SYSTEM,
        user=user_prompt,
        schema=SCENARIO_LIBRARY_SCHEMA,
        schema_name="scenario_library",
        temperature=0.6,
        max_tokens=4500,
    )

    scenarios_raw = result.get("scenarios", [])
    criterion_keys = {c.key for c in getattr(company, "criteria", [])}
    scenarios: list[MomentOfTruth] = []

    for i, raw in enumerate(scenarios_raw):
        # Filter scoring_dims to only valid criterion keys (soft guard).
        valid_dims = [k for k in raw.get("scoring_dims", []) if k in criterion_keys]
        mot = MomentOfTruth(
            team_id=company.team_id,
            title=raw["title"],
            scenario_type=raw["type"],
            prompt=raw["prompt"],
            candidate_role=raw["candidate_role"],
            expected_arc=raw["expected_arc"],
            scoring_dims=valid_dims,
            participating_roles=raw.get("participating_roles", []),
            max_turns=raw.get("max_turns", 6),
            grounding=raw.get("grounding", ""),
            is_llm_drafted=True,
            ordering=i,
        )
        scenarios.append(mot)

    logger.info(
        "draft_scenarios[%s]: drafted %d scenarios (budget spent=%.4f usd)",
        company.id, len(scenarios), budget.spent_usd,
    )
    return scenarios


def prepare_rollout(
    scenario: "MomentOfTruth",
    candidate_persona: dict,
    teammates: list[dict],
    *,
    seed: str | None = None,
) -> WorldState:
    """Prepare a WorldState for one rollout execution.

    Selects which teammates participate based on the scenario's
    participating_roles, constructs per-agent state, and initialises the
    world. Does NOT execute any turns — Phase 4A wires this into the live
    rollout executor.

    Args:
        scenario: MomentOfTruth ORM object or equivalent dict.
        candidate_persona: AggregatedPersona dict (structured_traits + narrative).
        teammates: list of SyntheticTeammate dicts (trait_sheet + narrative + private_goals).
        seed: reproducibility seed; auto-generated if None.
    """
    seed = seed or str(uuid.uuid4())

    # Build participating set: select teammates whose role_on_team matches
    # one of the scenario's participating_roles (case-insensitive substring).
    participating_roles = [r.lower() for r in (scenario.participating_roles or [])]
    selected: list[dict] = []
    if participating_roles:
        for tm in teammates:
            role_lower = tm.get("role_on_team", "").lower()
            if any(pr in role_lower or role_lower in pr for pr in participating_roles):
                selected.append(tm)
    # Fallback: if no matches, include all teammates (up to 3 for small_group).
    if not selected:
        selected = teammates[:3] if scenario.scenario_type == "small_group" else teammates[:1]

    agents: dict[str, AgentState] = {}

    # Candidate agent
    candidate_persona_block: dict[str, Any] = {
        "narrative": candidate_persona.get("narrative", ""),
        "structured_traits": candidate_persona.get("structured_traits", {}),
        "private_goals": ["Engage authentically with the scenario."],
    }
    # Verified profile ledgers feed the behavioral contract block in
    # agent_runtime. Public profile fields (education, experience, skills) are
    # also kept here so the agent can ground its self-references in real
    # background, while capability/communication ledgers + voice samples drive
    # skill-gap fidelity.
    verified_profile = candidate_persona.get("verified_profile")
    if verified_profile:
        candidate_persona_block["verified_profile"] = verified_profile
    agents["candidate"] = AgentState(
        agent_id="candidate",
        persona=candidate_persona_block,
        memory=[],
        scratchpad={},
    )

    # Teammate agents
    for tm in selected:
        agent_id = f"teammate:{tm.get('id', tm.get('name', 'unknown'))}"
        agents[agent_id] = AgentState(
            agent_id=agent_id,
            persona={
                "name": tm.get("name", "Teammate"),
                "role_on_team": tm.get("role_on_team", ""),
                "seniority": tm.get("seniority", "mid"),
                "narrative": tm.get("narrative", ""),
                "trait_sheet": tm.get("trait_sheet", {}),
                "private_goals": tm.get("private_goals", []),
            },
            memory=[],
            scratchpad={},
        )

    scenario_dict = {
        "id": str(getattr(scenario, "id", "")),
        "title": scenario.title,
        "type": scenario.scenario_type,
        "prompt": scenario.prompt,
        "candidate_role": scenario.candidate_role,
        "expected_arc": scenario.expected_arc,
        "scoring_dims": list(scenario.scoring_dims or []),
        "max_turns": scenario.max_turns,
    }

    return WorldState(
        scenario=scenario_dict,
        agents=agents,
        turn_history=[],
        current_turn=0,
        seed=seed,
        candidate_agent_id="candidate",
    )
