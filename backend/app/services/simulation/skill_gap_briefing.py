"""Pre-flight scenario → candidate skill-gap briefing.

Roadmap 2 / PR #1.4.

Before each rollout, identify which skills the scenario probes and how the
candidate's verified-profile capability ledger maps onto them. Output is
attached to the WorldState scenario dict under ``gap_briefing`` and rendered
into the agent system prompt by ``agent_runtime._render_gap_briefing_block``.

Cached per (scenario_id, candidate_id) on the WorldState — repeated rollouts
of the same pair within a match reuse the briefing.

The briefing is intentionally small (max ~6 gaps) — the goal is concrete,
manifestable behavioral cues, not an exhaustive skills audit.
"""
from __future__ import annotations

import logging
from typing import Any

from ...config import settings
from .cost_tracker import CostBudget, PERSONA_PROVIDER, tracked_chat_json

logger = logging.getLogger(__name__)


GAP_BRIEFING_SYSTEM = """\
You decide how a candidate's documented skill gaps should manifest in a
specific workplace simulation scenario.

You receive:
  * The scenario prompt and what "good" looks like.
  * The candidate's capability ledger:
      - "known": skills they can confidently demonstrate.
      - "exposure_only": skills they recognize but can't execute fluently.
      - Anything not listed in either is treated as outside their background.

Your job:
  1. Identify which skills the scenario actually probes.
     Be concrete (e.g. "k8s operator design", "financial-modelling DCF",
     "incident command", "stakeholder negotiation"). Skip generic skills
     everyone has ("communication", "teamwork") unless the scenario
     specifically pressure-tests them.
  2. For each probed skill, classify the candidate's coverage:
       - "covered" — confidently held; no behavioral constraint.
       - "limited" — exposure_only; the candidate should hedge,
         partially attempt, ask for help, occasionally err.
       - "absent" — not in the ledger; the candidate must admit they
         don't know, redirect, or pivot. They CANNOT fake fluency.
  3. For each non-covered skill, write a one-sentence behavioral
     guidance for the agent ("Hedge when discussing X; ask
     clarifying questions; don't pattern-match to other domains").
  4. Output up to 6 gaps total. Prioritize the highest-stakes gaps.
  5. If the candidate covers everything the scenario probes, return an
     empty gap list with notes explaining why.

HARD RULES:
  * Do not invent skills not implied by the scenario.
  * Do not speculate about the candidate beyond what the ledger
    documents.
  * Strict JSON only.
"""


GAP_BRIEFING_USER_TEMPLATE = """\
SCENARIO TITLE: {scenario_title}

SCENARIO PROMPT
{scenario_prompt}

EXPECTED ARC (what "good" looks like)
{expected_arc}

CANDIDATE'S CAPABILITY LEDGER
Known (confident): {known_block}
Exposure only:     {exposure_block}
Documented experience years: {role_years}

Identify the skills this scenario probes, classify the candidate's
coverage, and write a short briefing per gap. Return JSON matching the
GapBriefing schema."""


GAP_BRIEFING_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "required_skills": {
            "type": "array",
            "items": {"type": "string"},
            "description": "All skills this scenario actually probes.",
        },
        "gaps": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "skill": {"type": "string"},
                    "severity": {
                        "type": "string",
                        "description": "One of: 'limited' (exposure-only), 'absent' (not in ledger).",
                    },
                    "guidance": {
                        "type": "string",
                        "description": "One short sentence on how this gap should manifest in the agent's behavior.",
                    },
                },
                "required": ["skill", "severity", "guidance"],
                "additionalProperties": False,
            },
        },
        "notes": {
            "type": "string",
            "description": "Optional one-line note (e.g. 'fully covered').",
        },
    },
    "required": ["required_skills", "gaps", "notes"],
    "additionalProperties": False,
}


def _format_known(known: list[dict]) -> str:
    if not known:
        return "(none)"
    return ", ".join(k.get("skill", "") for k in known if k.get("skill"))


def _format_exposure(exposure_only: list[str]) -> str:
    if not exposure_only:
        return "(none)"
    return ", ".join(exposure_only)


def _has_meaningful_ledger(capability_ledger: dict) -> bool:
    if not capability_ledger:
        return False
    return bool(capability_ledger.get("known")) or bool(capability_ledger.get("exposure_only"))


async def compute_gap_briefing(
    *,
    scenario: Any,
    capability_ledger: dict | None,
    budget: CostBudget,
) -> dict | None:
    """Compute a per-rollout gap briefing.

    Returns None when the candidate has no usable capability ledger (so the
    agent prompt skips the gap-briefing block entirely). Returns the briefing
    dict otherwise — even if no gaps are found, so the agent gets explicit
    confirmation that the scenario is within their range.
    """
    if not _has_meaningful_ledger(capability_ledger or {}):
        return None

    scenario_title = getattr(scenario, "title", scenario.get("title", "")) if not isinstance(scenario, dict) else scenario.get("title", "")
    scenario_prompt = getattr(scenario, "prompt", scenario.get("prompt", "")) if not isinstance(scenario, dict) else scenario.get("prompt", "")
    expected_arc = getattr(scenario, "expected_arc", scenario.get("expected_arc", "")) if not isinstance(scenario, dict) else scenario.get("expected_arc", "")

    user_prompt = GAP_BRIEFING_USER_TEMPLATE.format(
        scenario_title=scenario_title or "(untitled)",
        scenario_prompt=scenario_prompt or "(no prompt)",
        expected_arc=expected_arc or "(no expected arc provided)",
        known_block=_format_known(capability_ledger.get("known") or []),
        exposure_block=_format_exposure(capability_ledger.get("exposure_only") or []),
        role_years=capability_ledger.get("role_year_span", "(unknown)"),
    )

    try:
        result = await tracked_chat_json(
            budget,
            system=GAP_BRIEFING_SYSTEM,
            user=user_prompt,
            schema=GAP_BRIEFING_SCHEMA,
            schema_name="gap_briefing",
            temperature=0.2,
            max_tokens=900,
            model=settings.openrouter_persona_model,
            provider=PERSONA_PROVIDER,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("gap-briefing call failed: %s — proceeding without briefing", exc)
        return None

    # Defensive cap — schema allows unbounded list, but we only render 6.
    gaps = result.get("gaps") or []
    if len(gaps) > 6:
        result["gaps"] = gaps[:6]

    return result
