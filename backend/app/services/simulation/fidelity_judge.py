"""Persona-fidelity judge.

Roadmap 2 / PR #1.6.

Scores how faithfully the agent stayed within the candidate's verified
profile (capability ledger, communication style, voice samples). This is a
*quality gate* on the simulation, not a signal about the candidate, so its
score is intentionally stored under the non-criterion key ``persona_fidelity``
in ``rollout_scores`` — the FitProfile aggregator iterates criteria only,
so this row is excluded from ``overall_fit`` while remaining available for
audit, retry decisions, and the manager-side health dashboard.

When the fidelity score falls below ``FIDELITY_RERUN_THRESHOLD``, the rollout
executor re-runs the rollout once with a fresh seed and marks the prior
rollout as ``superseded`` so it is excluded from aggregation.
"""
from __future__ import annotations

import logging
from typing import Any

from ...config import settings
from .cost_tracker import CostBudget, tracked_chat_json

logger = logging.getLogger(__name__)


FIDELITY_JUDGE_TAG = "fidelity-v1"
FIDELITY_DIMENSION_KEY = "persona_fidelity"
FIDELITY_RERUN_THRESHOLD = 60
FIDELITY_MAX_RETRIES = 1


FIDELITY_JUDGE_SYSTEM = """\
You are a persona-fidelity auditor for a workplace simulation. You receive
a candidate's documented real-world profile (skills, communication style,
voice samples) and the transcript of an agent role-playing as that
candidate.

Your job: score 0-100 how faithfully the agent stayed within what the
ledger documents. This is NOT a judgement of the candidate. It is a
judgement of whether the agent simulated them honestly.

Scoring rubric (anchor):
  * 90-100: Voice patterns mirror samples; skill claims fit the ledger;
    skill gaps surface naturally; no fabricated experience.
  * 70-89: Mostly faithful with minor drift (slightly polished phrasing
    or a marginal claim).
  * 50-69: Visible drift — fluency on a "limited exposure" skill,
    invented credentials, voice clearly off.
  * 30-49: Major violations — fluent execution on absent skills,
    fabricated experience, voice unrelated to samples.
  * 0-29: Persona ignored.

HARD RULES:
  1. Score ONLY the candidate-agent's lines. Teammate behavior is
     context.
  2. Cite specific turn indices in violations[].turn_index when you
     dock points. A violation without a cited turn is invalid.
  3. Self-report your confidence (0.0-1.0). Lower confidence when the
     candidate had few turns, the ledger is sparse, or the scenario
     didn't pressure-test the documented gaps.
  4. Do NOT penalise the agent for things the ledger doesn't cover.
     Absence of evidence is not evidence of fabrication.
  5. Never reference protected characteristics or proxies.
  6. Strict JSON only.
"""


FIDELITY_JUDGE_USER_TEMPLATE = """\
CANDIDATE'S DOCUMENTED PROFILE
==============================
Capability ledger (known = confident; exposure_only = limited; absent = NOT in ledger):
{capability_block}

Communication style metrics:
{communication_block}

Voice samples (verbatim — how this person actually writes):
{voice_samples_block}

Education / experience (real background — agent must not invent more):
{background_block}

SCENARIO GAP BRIEFING (gaps the agent was expected to manifest)
{gap_briefing_block}

CANDIDATE-AGENT TRANSCRIPT (turns are indexed; cite indices in violations)
{indexed_candidate_transcript}

Score persona fidelity. Return JSON matching the FidelityScore schema."""


FIDELITY_JUDGE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "score": {
            "type": "integer",
            "description": "0-100 fidelity score.",
        },
        "confidence": {
            "type": "number",
            "description": "0.0-1.0 self-reported confidence.",
        },
        "justification": {
            "type": "string",
            "description": "1-2 sentences. Quote transcript text where relevant.",
        },
        "violations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "turn_index": {"type": "integer"},
                    "kind": {
                        "type": "string",
                        "description": "One of: 'skill_overreach', 'voice_drift', 'invented_credential', 'missed_gap', 'other'.",
                    },
                    "note": {"type": "string"},
                },
                "required": ["turn_index", "kind", "note"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["score", "confidence", "justification", "violations"],
    "additionalProperties": False,
}


# ---------------------------------------------------------------------------
# Render helpers
# ---------------------------------------------------------------------------

def _render_capability_block(ledger: dict | None) -> str:
    if not ledger:
        return "  (no capability ledger available — fidelity will rely on voice samples + background only)"
    known = ledger.get("known") or []
    exposure = ledger.get("exposure_only") or []
    lines = []
    if known:
        lines.append("  known: " + ", ".join(k.get("skill", "") for k in known))
    else:
        lines.append("  known: (none)")
    if exposure:
        lines.append("  exposure_only: " + ", ".join(exposure))
    else:
        lines.append("  exposure_only: (none)")
    if ledger.get("role_year_span") is not None:
        lines.append(f"  role_year_span: {ledger['role_year_span']}")
    return "\n".join(lines)


def _render_communication_block(ledger: dict | None) -> str:
    if not ledger:
        return "  (no communication ledger)"
    bits: list[str] = []
    if ledger.get("avg_sentence_length") is not None:
        bits.append(f"avg_sentence_length={ledger['avg_sentence_length']}")
    if ledger.get("hedging_rate") is not None:
        bits.append(f"hedging_rate={ledger['hedging_rate']}")
    bits.append(f"voice_sample_count={ledger.get('voice_sample_count', 0)}")
    return "  " + ", ".join(bits)


def _render_voice_samples_block(samples: list[dict] | None) -> str:
    if not samples:
        return "  (no voice samples available)"
    lines = []
    for s in samples[:5]:
        text = (s.get("text") or "").strip()[:600]
        if text:
            lines.append(f"  [{s.get('source', '?')}] {text}")
    return "\n".join(lines) or "  (samples present but empty)"


def _render_background_block(verified_profile: dict | None) -> str:
    if not verified_profile:
        return "  (no verified profile)"
    lines = []
    edu = verified_profile.get("education") or []
    if edu:
        lines.append("  Education:")
        for e in edu[:4]:
            lines.append(
                f"    - {e.get('institution', '?')} — "
                f"{(e.get('degree') or '').strip()} {(e.get('field') or '').strip()} "
                f"({e.get('start', '')}–{e.get('end', '')})"
            )
    exp = verified_profile.get("experience") or []
    if exp:
        lines.append("  Experience:")
        for x in exp[:5]:
            lines.append(
                f"    - {x.get('role', '?')} @ {x.get('company', '?')} "
                f"({x.get('start', '')}–{x.get('end', '')})"
            )
    return "\n".join(lines) or "  (no documented background)"


def _render_gap_briefing_block(briefing: dict | None) -> str:
    if not briefing:
        return "  (no gap briefing for this scenario)"
    lines = []
    required = briefing.get("required_skills") or []
    if required:
        lines.append("  required_skills: " + ", ".join(required))
    gaps = briefing.get("gaps") or []
    if gaps:
        lines.append("  gaps:")
        for g in gaps:
            lines.append(
                f"    - {g.get('skill', '?')} [{g.get('severity', '?')}]: {g.get('guidance', '')}"
            )
    if briefing.get("notes"):
        lines.append(f"  notes: {briefing['notes']}")
    return "\n".join(lines) or "  (briefing present but empty)"


def _render_candidate_transcript(transcript: list[dict] | None) -> str:
    if not transcript:
        return "(empty transcript)"
    lines = []
    for i, turn in enumerate(transcript):
        if turn.get("speaker_id") != "candidate":
            continue
        utterance = (turn.get("content") or "").strip()
        lines.append(f"[#{i}] {utterance}")
    return "\n".join(lines) if lines else "(candidate produced no turns)"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def score_persona_fidelity(
    *,
    transcript: list[dict],
    verified_profile: dict | None,
    gap_briefing: dict | None,
    budget: CostBudget,
) -> dict | None:
    """Score persona fidelity for one rollout.

    Returns a dict with keys: score, confidence, justification, violations.
    Returns ``None`` when the candidate has no verified profile (no ground
    truth to score against — skipping the call saves tokens).
    """
    if not verified_profile:
        return None

    # Skip if the candidate produced zero turns — nothing to judge.
    has_candidate_turns = any(
        (t.get("speaker_id") == "candidate") for t in (transcript or [])
    )
    if not has_candidate_turns:
        return None

    user_prompt = FIDELITY_JUDGE_USER_TEMPLATE.format(
        capability_block=_render_capability_block(verified_profile.get("capability_ledger")),
        communication_block=_render_communication_block(verified_profile.get("communication_ledger")),
        voice_samples_block=_render_voice_samples_block(verified_profile.get("voice_samples")),
        background_block=_render_background_block(verified_profile),
        gap_briefing_block=_render_gap_briefing_block(gap_briefing),
        indexed_candidate_transcript=_render_candidate_transcript(transcript),
    )

    try:
        result = await tracked_chat_json(
            budget,
            system=FIDELITY_JUDGE_SYSTEM,
            user=user_prompt,
            schema=FIDELITY_JUDGE_SCHEMA,
            schema_name="persona_fidelity",
            temperature=0.15,
            max_tokens=1200,
            model=settings.openrouter_model,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("fidelity judge failed: %s — proceeding without fidelity score", exc)
        return None

    return result
