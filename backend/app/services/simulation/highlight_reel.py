"""Auto-generate a recruiter-readable "highlight reel" for a rollout.

Roadmap 2 / PR #3.

Why this exists: judge ``transcript_summary`` is written for QA — terse,
audit-flavoured. Recruiters and investors want a short marketable narrative
("Sofia argued the case-against in two paragraphs, citing 2018 vintage data,
then proposed a path forward.") plus a pointer to the 2-3 turns that
crystallised the moment. This module produces that.

Cost: one extra Gemma (persona-model) call per rollout. K × scenarios per
match. At ~$0.001 / call this is well below 5% of the per-match cost.

Output shape:

    {
      "one_liner": "Sofia held the case-against under VP pressure, twice.",
      "summary":   "Two-paragraph narrative ...",
      "key_turn_indices": [1, 3]
    }

Failures degrade gracefully — if the LLM call fails or returns malformed
JSON, the caller just sees no highlight_reel field on the rollout's
final_state. The judge's transcript_summary is still there as a fallback.
"""
from __future__ import annotations

import logging
from typing import Any

from ...config import settings
from .cost_tracker import CostBudget, PERSONA_PROVIDER, tracked_chat_json

logger = logging.getLogger(__name__)


_HIGHLIGHT_SYSTEM = """\
You write a short, recruiter-readable highlight reel for one simulation
rollout. Treat it like a 30-second TV cut-down: the most informative or
characterful moment, named participants, no jargon.

HARD RULES:
  1. ``one_liner`` — single sentence, ≤ 18 words, names the candidate by
     first name (or "the candidate" if unknown), focuses on a specific
     action they took.
  2. ``summary`` — 2-3 sentences, concrete, in past tense, citing
     observable behaviour. No vague claims like "showed strong rigor";
     instead "ran a sensitivity sweep on the IRR".
  3. ``key_turn_indices`` — 2-3 zero-based indices into the transcript
     pointing at the turns that crystallise the moment. Skip turns
     where the candidate said nothing of substance.
  4. Strict JSON output.
  5. Never invent details — if the transcript is bland, say so plainly
     ("Candidate stayed quiet, deferred to the VP throughout.").\
"""


_HIGHLIGHT_USER_TEMPLATE = """\
SCENARIO: {scenario_title}
ROLE: {candidate_role}

TRANSCRIPT (each turn prefixed [N] speaker · role):
{transcript_block}

CANDIDATE SCORES (per criterion):
{scores_block}

Produce the highlight reel.\
"""


_HIGHLIGHT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "one_liner": {"type": "string"},
        "summary": {"type": "string"},
        "key_turn_indices": {
            "type": "array",
            "items": {"type": "integer", "minimum": 0},
            "minItems": 1,
            "maxItems": 4,
        },
    },
    "required": ["one_liner", "summary", "key_turn_indices"],
    "additionalProperties": False,
}


def _render_transcript(turns: list[dict[str, Any]], max_chars: int = 3000) -> str:
    lines: list[str] = []
    used = 0
    for i, t in enumerate(turns):
        speaker = t.get("speaker_name") or t.get("speaker_id") or "?"
        role = t.get("speaker_role") or ""
        content = (t.get("content") or "").strip()
        if not content:
            continue
        prefix = f"[{i}] {speaker} · {role}: "
        chunk = prefix + content
        if used + len(chunk) > max_chars:
            lines.append("[...]")
            break
        lines.append(chunk)
        used += len(chunk)
    return "\n".join(lines) if lines else "(empty transcript)"


def _render_scores(score_rows: list[Any]) -> str:
    if not score_rows:
        return "(no scores recorded)"
    return "\n".join(
        f"  * {s.dimension_key}: {s.score if s.score is not None else '—'}"
        for s in score_rows
        if getattr(s, "dimension_key", "") != "persona_fidelity"
    ) or "(no criteria scores)"


async def generate_highlight_reel(
    *,
    scenario: dict[str, Any] | Any,
    transcript: list[dict[str, Any]],
    score_rows: list[Any],
    budget: CostBudget,
) -> dict[str, Any] | None:
    """Generate a recruiter-readable highlight reel for one rollout.

    Returns ``None`` on any failure (caller drops the field silently). The
    judge's existing transcript_summary remains as a fallback.
    """
    if not transcript:
        return None

    scenario_title = (
        scenario.get("title")
        if isinstance(scenario, dict)
        else getattr(scenario, "title", "")
    ) or "(untitled)"
    candidate_role = (
        scenario.get("candidate_role")
        if isinstance(scenario, dict)
        else getattr(scenario, "candidate_role", "")
    ) or "(unspecified)"

    user_prompt = _HIGHLIGHT_USER_TEMPLATE.format(
        scenario_title=scenario_title,
        candidate_role=candidate_role,
        transcript_block=_render_transcript(transcript),
        scores_block=_render_scores(score_rows),
    )

    try:
        result = await tracked_chat_json(
            budget,
            system=_HIGHLIGHT_SYSTEM,
            user=user_prompt,
            schema=_HIGHLIGHT_SCHEMA,
            schema_name="rollout_highlight",
            temperature=0.5,
            max_tokens=400,
            model=settings.openrouter_persona_model,
            provider=PERSONA_PROVIDER,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("highlight_reel generation failed: %s", exc)
        return None

    # Sanity-check turn indices.
    n_turns = len(transcript)
    indices = [
        i for i in (result.get("key_turn_indices") or []) if 0 <= int(i) < n_turns
    ]
    return {
        "one_liner": (result.get("one_liner") or "").strip(),
        "summary": (result.get("summary") or "").strip(),
        "key_turn_indices": indices,
    }
