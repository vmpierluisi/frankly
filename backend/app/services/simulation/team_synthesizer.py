"""Synthetic team synthesizer.

MiroFish lineage: corresponds to MiroFish's generate_population_from_documents().
Phase 2A ships extract_centroid only. Phase 2B adds the full synthesize() pipeline
(centroid → Gaussian sample → teammate generation → persistence).
"""
from __future__ import annotations

import json
import logging
import random
from typing import TYPE_CHECKING, Any

from ...config import settings
from .cost_tracker import CostBudget, PERSONA_PROVIDER, tracked_chat_json
from .knowledge_graph import summarize_for_prompt

if TYPE_CHECKING:
    from ...models import Company, SyntheticTeammate

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompt templates (verbatim from brief Appendix A.2)
# ---------------------------------------------------------------------------

TEAM_CENTROID_SYSTEM = """\
You extract the implicit centroid trait sheet of a high-functioning teammate
inside a specific company, from that company's sanctioned artifacts.

You do NOT design an aspirational ideal. You describe what the artifacts
collectively imply about who actually thrives on this team today.

HARD RULES:
  1. Ground every trait inference in cited artifact text. The provenance
     field on each trait is non-optional.
  2. Surface tensions inside the company's stated values and observed
     behaviors (sample comms). Tensions go in centroid_tensions and
     should NOT be averaged away.
  3. Big Five and skill scales match the persona aggregator (Appendix A.1).
  4. Never reference protected characteristics or proxies.
  5. Strict JSON only.

This is the centroid only. Variance around it is sampled later — do not
inject artificial diversity here.\
"""

TEAM_CENTROID_USER_TEMPLATE = """\
Extract the centroid trait sheet for this company's team.

COMPANY: {company_name}
ROLE: {role}
TAGLINE: {tagline}

VALUES DOCUMENT
\"\"\"
{artifact_values}
\"\"\"

ROLE SPECIFICATION
\"\"\"
{artifact_role_spec}
\"\"\"

TEAM STRUCTURE
\"\"\"
{artifact_team_structure}
\"\"\"

SAMPLE COMMUNICATIONS
\"\"\"
{artifact_sample_comms}
\"\"\"

CRITERIA (what the company formally evaluates against)
{criteria_block}

KNOWLEDGE GRAPH NODES (extracted previously; may be empty)
{knowledge_graph_summary}

TASK
----
Return a JSON object matching the TeamCentroid schema. Specifically:

1. Compute big_five_centroid: the mean trait profile of a person who would
   thrive on this team. Cite artifact evidence.
2. Compute skill_centroid: the mean role-relevant skill profile.
3. Compute work_style_centroid: collaboration, communication, decision-style
   defaults.
4. List centroid_tensions: places where the company's stated values and
   observed behavior pull in different directions. Each tension has an
   id, a description, and the artifact lines it draws from. These tensions
   later inform variance — teammates may sit at different points along
   them.
5. Set sigma_recommendations: per-trait recommended Gaussian σ for sampling
   teammates around the centroid. Default σ = 0.6 unless centroid_tensions
   suggest a wider spread (then up to 1.0).\
"""

# ---------------------------------------------------------------------------
# JSON schema (verbatim from brief Appendix B.2)
# ---------------------------------------------------------------------------

_TRAIT_WITH_PROVENANCE = {
    "type": "object",
    "properties": {
        "value":      {"type": "number"},
        "provenance": {"type": "string"},
    },
    "required": ["value", "provenance"],
    "additionalProperties": False,
}

TEAM_CENTROID_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "big_five_centroid": {
            "type": "object",
            "properties": {
                "openness":          _TRAIT_WITH_PROVENANCE,
                "conscientiousness": _TRAIT_WITH_PROVENANCE,
                "extraversion":      _TRAIT_WITH_PROVENANCE,
                "agreeableness":     _TRAIT_WITH_PROVENANCE,
                "neuroticism":       _TRAIT_WITH_PROVENANCE,
            },
            "required": ["openness", "conscientiousness", "extraversion",
                         "agreeableness", "neuroticism"],
            "additionalProperties": False,
        },
        "skill_centroid": {
            "type": "object",
            "additionalProperties": _TRAIT_WITH_PROVENANCE,
            "properties": {},
            "required": [],
        },
        "work_style_centroid": {
            "type": "object",
            "additionalProperties": _TRAIT_WITH_PROVENANCE,
            "properties": {},
            "required": [],
        },
        "centroid_tensions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id":          {"type": "string"},
                    "description": {"type": "string"},
                    "evidence":    {"type": "string",
                                   "description": "Cited artifact lines that surface the tension."},
                },
                "required": ["id", "description", "evidence"],
                "additionalProperties": False,
            },
        },
        "sigma_recommendations": {
            "type": "object",
            "properties": {
                "big_five":   {"type": "number"},
                "skill":      {"type": "number"},
                "work_style": {"type": "number"},
            },
            "required": ["big_five", "skill", "work_style"],
            "additionalProperties": False,
        },
    },
    "required": [
        "big_five_centroid", "skill_centroid", "work_style_centroid",
        "centroid_tensions", "sigma_recommendations",
    ],
    "additionalProperties": False,
}


# ---------------------------------------------------------------------------
# Prompt rendering helpers
# ---------------------------------------------------------------------------

def _render_criteria_block(company: "Company") -> str:
    criteria = getattr(company, "criteria", []) or []
    if not criteria:
        return "  (no criteria defined)"
    return "\n".join(
        f"  * {c.key} ({c.label}): {c.description}"
        for c in sorted(criteria, key=lambda c: c.ordering)
    )


def _render_centroid_user_prompt(company: "Company") -> str:
    return TEAM_CENTROID_USER_TEMPLATE.format(
        company_name=company.name,
        role=company.role,
        tagline=company.tagline or "(none)",
        artifact_values=company.artifact_values or "(none provided)",
        artifact_role_spec=company.artifact_role_spec or "(none provided)",
        artifact_team_structure=company.artifact_team_structure or "(none provided)",
        artifact_sample_comms=company.artifact_sample_comms or "(none provided)",
        criteria_block=_render_criteria_block(company),
        knowledge_graph_summary=summarize_for_prompt(
            getattr(company, "knowledge_graph", None)
        ),
    )


# ---------------------------------------------------------------------------
# Phase 2A public API
# ---------------------------------------------------------------------------

async def extract_centroid(company: "Company", *, budget: CostBudget) -> dict[str, Any]:
    """Extract the team centroid trait sheet from company artifacts.

    Returns the TeamCentroid dict. Does not persist to DB — caller decides
    whether to cache.  Consumed by synthesize() in Phase 2B.
    """
    user_prompt = _render_centroid_user_prompt(company)
    result = await tracked_chat_json(
        budget,
        model=settings.openrouter_persona_model,
        provider=PERSONA_PROVIDER,
        system=TEAM_CENTROID_SYSTEM,
        user=user_prompt,
        schema=TEAM_CENTROID_SCHEMA,
        schema_name="team_centroid",
        temperature=0.2,
        max_tokens=2500,
    )
    return result


# ---------------------------------------------------------------------------
# Phase 2B: teammate generator prompts + schema
# ---------------------------------------------------------------------------

TEAMMATE_GENERATOR_SYSTEM = """\
You generate a single fully-realized teammate persona for a hiring
simulation. The teammate's traits have been pre-sampled — your job is to
write the rest of the persona consistent with those traits and grounded in
the company's environment.

HARD RULES:
  1. The structured trait_sheet you receive is FIXED. Do not alter values.
     Generate the narrative, name, role_on_team, seniority, and
     private_goals consistent with those values.
  2. Names: anglophone-neutral, varied across calls. Avoid culturally-
     coded names that could carry stereotype freight. Surnames common.
     Do not generate names of real public figures.
  3. private_goals are the teammate's typical goals when interacting with
     a candidate during a simulated workday. They are private to the
     teammate (the candidate does not see them) and drive how the
     teammate behaves in rollouts. Each goal is one sentence; produce
     2-4 goals.
  4. Seniority must be one of: junior, mid, senior, lead.
  5. role_on_team is a short specific job title (e.g. "Senior Credit
     Analyst", "Pod VP — Healthcare", "Founding Operator").
  6. Narrative is 300-600 words, third-person, plain prose, no headers,
     no bullets. Same clinical tone as persona aggregator.
  7. provenance_notes field cites which artifact lines you drew from
     when grounding behavior — the structured trait values came from
     centroid+noise, but the narrative behaviors should be cited.
  8. Strict JSON only. Never reference protected characteristics or proxies.\
"""

TEAMMATE_GENERATOR_USER_TEMPLATE = """\
Generate one teammate persona consistent with the trait sheet and grounded
in the company environment.

COMPANY: {company_name}
ROLE: {role}
TAGLINE: {tagline}

CENTROID TENSIONS (this teammate may sit at any point along these)
{centroid_tensions_block}

PRE-SAMPLED TRAIT SHEET (FIXED — do not alter)
{sampled_trait_sheet_json}

ARTIFACT EXCERPTS (for grounding the narrative and goals)
\"\"\"
{artifact_excerpts}
\"\"\"

INSTRUCTIONS
------------
Return a JSON object matching the SyntheticTeammate schema (single object,
not a list). Fill all fields. Make the teammate feel specific and
internally consistent — a reader should believe this person works at this
company at this seniority.\
"""

SYNTHETIC_TEAMMATE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "name":         {"type": "string"},
        "role_on_team": {"type": "string"},
        "seniority":    {"type": "string", "description": "One of: junior, mid, senior, lead."},
        "trait_sheet": {
            "type": "object",
            "properties": {
                "big_five": {
                    "type": "object",
                    "properties": {
                        "openness":          {"type": "number"},
                        "conscientiousness": {"type": "number"},
                        "extraversion":      {"type": "number"},
                        "agreeableness":     {"type": "number"},
                        "neuroticism":       {"type": "number"},
                    },
                    "required": ["openness", "conscientiousness", "extraversion",
                                 "agreeableness", "neuroticism"],
                    "additionalProperties": False,
                },
                "skill_profile": {
                    "type": "object",
                    "additionalProperties": {"type": "number"},
                    "properties": {},
                    "required": [],
                },
                "work_style": {
                    "type": "object",
                    "additionalProperties": {"type": "number"},
                    "properties": {},
                    "required": [],
                },
            },
            "required": ["big_five", "skill_profile", "work_style"],
            "additionalProperties": False,
        },
        "narrative":     {"type": "string", "description": "300-600 words, third-person, plain prose."},
        "private_goals": {
            "type": "array",
            "items": {"type": "string", "description": "One sentence per goal."},
        },
        "provenance_notes": {
            "type": "string",
            "description": "Cites which artifact passages grounded the narrative behaviors.",
        },
    },
    "required": ["name", "role_on_team", "seniority", "trait_sheet",
                 "narrative", "private_goals", "provenance_notes"],
    "additionalProperties": False,
}


# ---------------------------------------------------------------------------
# Phase 2B helpers
# ---------------------------------------------------------------------------

def _sample_trait_sheet(centroid: dict[str, Any], rng: random.Random) -> dict[str, Any]:
    """Sample one trait sheet around the centroid using Gaussian noise.

    Big Five values: 0-5 scale, σ from sigma_recommendations["big_five"].
    Skill values:    0-5 scale, σ from sigma_recommendations["skill"].
    Work-style:      0-1 scale, σ from sigma_recommendations["work_style"].
    All values clipped to their respective ranges.
    """
    sigma = centroid.get("sigma_recommendations", {})
    bf_sigma = float(sigma.get("big_five", 0.6))
    skill_sigma = float(sigma.get("skill", 0.6))
    ws_sigma = float(sigma.get("work_style", 0.6))

    big_five: dict[str, float] = {}
    for trait, entry in centroid.get("big_five_centroid", {}).items():
        val = float(entry["value"]) + rng.gauss(0.0, bf_sigma)
        big_five[trait] = max(0.0, min(5.0, val))

    skill_profile: dict[str, float] = {}
    for key, entry in centroid.get("skill_centroid", {}).items():
        val = float(entry["value"]) + rng.gauss(0.0, skill_sigma)
        skill_profile[key] = max(0.0, min(5.0, val))

    work_style: dict[str, float] = {}
    for key, entry in centroid.get("work_style_centroid", {}).items():
        val = float(entry["value"]) + rng.gauss(0.0, ws_sigma)
        work_style[key] = max(0.0, min(1.0, val))

    return {"big_five": big_five, "skill_profile": skill_profile, "work_style": work_style}


def _render_centroid_tensions_block(centroid: dict[str, Any]) -> str:
    tensions = centroid.get("centroid_tensions", [])
    if not tensions:
        return "  (none identified)"
    return "\n".join(
        f"  * [{t['id']}] {t['description']}"
        for t in tensions
    )


def _render_artifact_excerpts(company: "Company") -> str:
    parts: list[str] = []
    if getattr(company, "artifact_values", ""):
        parts.append(company.artifact_values[:400])
    if getattr(company, "artifact_role_spec", ""):
        parts.append(company.artifact_role_spec[:400])
    if getattr(company, "artifact_team_structure", ""):
        parts.append(company.artifact_team_structure[:300])
    if getattr(company, "artifact_sample_comms", ""):
        parts.append(company.artifact_sample_comms[:200])
    return "\n---\n".join(parts) if parts else "(none provided)"


async def _generate_one_teammate(
    company: "Company",
    centroid: dict[str, Any],
    sampled_sheet: dict[str, Any],
    *,
    budget: CostBudget,
) -> dict[str, Any]:
    """Second LLM call: given pre-sampled trait values, produce one teammate."""
    user_prompt = TEAMMATE_GENERATOR_USER_TEMPLATE.format(
        company_name=company.name,
        role=company.role,
        tagline=getattr(company, "tagline", None) or "(none)",
        centroid_tensions_block=_render_centroid_tensions_block(centroid),
        sampled_trait_sheet_json=json.dumps(sampled_sheet, indent=2),
        artifact_excerpts=_render_artifact_excerpts(company),
    )
    return await tracked_chat_json(
        budget,
        model=settings.openrouter_persona_model,
        provider=PERSONA_PROVIDER,
        system=TEAMMATE_GENERATOR_SYSTEM,
        user=user_prompt,
        schema=SYNTHETIC_TEAMMATE_SCHEMA,
        schema_name="synthetic_teammate",
        temperature=0.7,
        max_tokens=2000,
    )


# ---------------------------------------------------------------------------
# Phase 2B public API
# ---------------------------------------------------------------------------

DEFAULT_TEAM_SIZE = 5


async def synthesize(
    company: "Company",
    *,
    budget: CostBudget,
    n: int = DEFAULT_TEAM_SIZE,
) -> "list[SyntheticTeammate]":
    """Generate N synthetic teammates for a company.

    Algorithm (per brief §4.2):
      1. Extract centroid from artifacts (one LLM call).
      2. Sample N trait sheets around the centroid via Gaussian noise.
      3. For each sampled sheet, generate one teammate (N LLM calls).
      4. Return list of unsaved SyntheticTeammate ORM objects.
         Caller is responsible for adding and committing them.

    MiroFish lineage: reimplements generate_population_from_documents().
    """
    from ...models import SyntheticTeammate  # deferred to avoid circular import

    centroid = await extract_centroid(company, budget=budget)

    rng = random.Random()
    teammates: list[SyntheticTeammate] = []

    for i in range(n):
        sampled_sheet = _sample_trait_sheet(centroid, rng)
        raw = await _generate_one_teammate(company, centroid, sampled_sheet, budget=budget)

        teammate = SyntheticTeammate(
            company_id=company.id,
            name=raw["name"],
            role_on_team=raw["role_on_team"],
            seniority=raw["seniority"],
            trait_sheet=raw["trait_sheet"],
            narrative=raw["narrative"],
            private_goals=raw["private_goals"],
            generated_from={
                "provenance_notes": raw["provenance_notes"],
                "sampled_from_centroid": True,
            },
            is_edited=False,
            ordering=i,
        )
        teammates.append(teammate)

    logger.info(
        "synthesize[%s]: generated %d teammates (budget spent=%.4f usd)",
        company.id, len(teammates), budget.spent_usd,
    )
    return teammates
