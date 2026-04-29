"""Simulation judge — scores a rollout transcript on company criteria.

MiroFish lineage: corresponds to MiroFish's RolloutJudge.
Phase 4B ships score_rollout() with two judge calls per rollout (different
temperature seeds) for inter-judge confidence estimation. Falls back to
single-judge when one call fails (Appendix D.2).

Public API:
  score_rollout(rollout, scenario, criteria, *, budget, company_name, role,
                candidate_label)
      → list[RolloutScore]   (unsaved; caller adds + commits)
"""
from __future__ import annotations

import logging
from typing import NamedTuple, TYPE_CHECKING, Any

from .cost_tracker import CostBudget, tracked_chat_json
from .rollout_logger import log_event

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from ...models import Rollout, RolloutScore


class JudgeResult(NamedTuple):
    rows: "list[RolloutScore]"
    transcript_summary: str

logger = logging.getLogger(__name__)

# Judge temperature seeds per Appendix A.7 / D.4.
_JUDGE_TEMPERATURES = (0.15, 0.25)
_JUDGE_MODEL_TAG = "judge-v1"   # embedded in judge_model field for audit


# ---------------------------------------------------------------------------
# Prompt templates (verbatim from brief Appendix A.7)
# ---------------------------------------------------------------------------

JUDGE_SYSTEM = """\
You are a workplace-simulation judge. You score a transcript on specific
behavioral dimensions, citing the exact turns that justify each score.

YOU PRODUCE A SCREENING-LEVEL SIGNAL, NOT A HIRING JUDGMENT.

HARD RULES:
  1. Score ONLY the candidate's behavior. Teammate behavior is context.
  2. Every score MUST cite specific turn indices in evidence_turns. A
     score with no cited turns is invalid — return null and explain in
     justification why no evidence was available.
  3. Score on the 0-100 scale: 0 = strong misfit, 50 = ambiguous /
     insufficient evidence, 100 = strong fit.
  4. Self-report your confidence (0.0-1.0) per dimension. Lower
     confidence when: candidate had few turns, evidence is thin, the
     scenario didn't strongly probe this dimension.
  5. Justifications quote transcript text in quotation marks where
     possible. One to two sentences per justification.
  6. Never reference protected characteristics or proxies.
  7. Strict JSON only.

DIMENSION ANCHORING:
  Use the dimension's description (provided per dimension) as the rubric
  anchor. If a dimension is "Written Dissent: disagrees in writing,
  early, constructively", a score of 90 means the candidate did so
  visibly in this transcript; a score of 50 means insufficient signal;
  a score of 20 means the candidate avoided dissent or did so
  destructively.\
"""

JUDGE_USER_TEMPLATE = """\
Score the candidate's behavior in this transcript on the dimensions
listed below.

COMPANY: {company_name}
ROLE: {role}

SCENARIO
{scenario_block}

EXPECTED ARC (for the judge's reference; what does "good" look like on
this team)
{expected_arc}

DIMENSIONS TO SCORE (use these exact keys)
{dimensions_block}

CANDIDATE: {candidate_label}

TRANSCRIPT (turns are indexed; you cite indices in evidence_turns)
{indexed_transcript}

Return a JSON object matching the JudgeOutput schema. dimension_scores
keys match the dimension keys above exactly.\
"""


# ---------------------------------------------------------------------------
# JSON schema (verbatim from brief Appendix B.7)
# ---------------------------------------------------------------------------

def judge_output_schema(dimension_keys: list[str]) -> dict[str, Any]:
    """Build the per-call schema bound to the specific dimension keys."""
    dim_score_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "score": {
                "type": "integer",
                "description": "0-100; null only when no evidence is available.",
            },
            "justification": {
                "type": "string",
                "description": "1-2 sentences quoting transcript text.",
            },
            "evidence_turns": {
                "type": "array",
                "items": {
                    "type": "integer",
                    "description": (
                        "Index into the indexed_transcript. "
                        "Required to be non-empty unless score is null."
                    ),
                },
            },
            "confidence": {
                "type": "number",
                "description": "0.0-1.0 self-reported confidence.",
            },
        },
        "required": ["score", "justification", "evidence_turns", "confidence"],
        "additionalProperties": False,
    }
    dimension_scores: dict[str, Any] = {
        "type": "object",
        "properties": {k: dim_score_schema for k in dimension_keys},
        "required": list(dimension_keys),
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {
            "dimension_scores": dimension_scores,
            "transcript_summary": {
                "type": "string",
                "description": (
                    "1-2 sentence headline summary of what the candidate did. "
                    "Surfaced in rollout summaries."
                ),
            },
            "judge_notes": {
                "type": "string",
                "description": "Optional notes from the judge for the audit trail.",
            },
        },
        "required": ["dimension_scores", "transcript_summary", "judge_notes"],
        "additionalProperties": False,
    }


# ---------------------------------------------------------------------------
# Prompt rendering helpers
# ---------------------------------------------------------------------------

def _render_dimensions_block(criteria: list[dict[str, Any]]) -> str:
    """Each line: '  * {key} ({label}): {description}'"""
    return "\n".join(
        f"  * {c['key']} ({c.get('label', c['key'])}): {c.get('description', '')}"
        for c in criteria
    )


def _render_indexed_transcript(turn_history: list[dict[str, Any]]) -> str:
    """'[#{i} · {speaker}] {utterance}' — no intents or internal states."""
    lines = []
    for i, turn in enumerate(turn_history):
        speaker = turn.get("speaker_name", turn.get("speaker_id", "?"))
        utterance = turn.get("content", "")
        lines.append(f"[#{i} · {speaker}] {utterance}")
    return "\n".join(lines) if lines else "(empty transcript)"


def _render_judge_user_prompt(
    rollout: "Rollout",
    scenario: dict[str, Any],
    criteria: list[dict[str, Any]],
    *,
    company_name: str,
    role: str,
    candidate_label: str,
) -> str:
    return JUDGE_USER_TEMPLATE.format(
        company_name=company_name,
        role=role,
        scenario_block=scenario.get("prompt", ""),
        expected_arc=scenario.get("expected_arc", ""),
        dimensions_block=_render_dimensions_block(criteria),
        candidate_label=candidate_label,
        indexed_transcript=_render_indexed_transcript(rollout.transcript or []),
    )


# ---------------------------------------------------------------------------
# Confidence estimation (Appendix D.4)
# ---------------------------------------------------------------------------

def _compute_confidence(scores_a: dict, scores_b: dict, dim_key: str) -> float:
    """Inter-judge confidence: 1 - |score_a - score_b| / 100.

    Returns the mean of the two self-reported confidences when only one
    judge produced a result.
    """
    da = scores_a.get(dim_key, {})
    db = scores_b.get(dim_key, {})
    sa = da.get("score")
    sb = db.get("score")
    if sa is None or sb is None:
        # One judge had no evidence — use the available judge's confidence halved.
        conf = (da.get("confidence") or db.get("confidence") or 0.0)
        return conf * 0.5
    agreement = 1.0 - abs(sa - sb) / 100.0
    # Weight agreement equally with the mean self-reported confidence.
    mean_self_conf = ((da.get("confidence") or 0.0) + (db.get("confidence") or 0.0)) / 2.0
    return (agreement + mean_self_conf) / 2.0


def _merge_scores(
    scores_a: dict,
    scores_b: dict | None,
    dim_key: str,
) -> tuple[int | None, float]:
    """Return (mean_score, confidence) merging two judge outputs.

    If scores_b is None (single-judge fallback), confidence is halved.
    """
    da = scores_a.get(dim_key, {})
    sa = da.get("score")

    if scores_b is None:
        return sa, (da.get("confidence") or 0.0) * 0.5

    db = scores_b.get(dim_key, {})
    sb = db.get("score")

    if sa is None and sb is None:
        return None, 0.0
    if sa is None:
        return sb, (db.get("confidence") or 0.0) * 0.5
    if sb is None:
        return sa, (da.get("confidence") or 0.0) * 0.5

    mean_score = round((sa + sb) / 2)
    confidence = _compute_confidence(scores_a, scores_b, dim_key)
    return mean_score, confidence


# ---------------------------------------------------------------------------
# Phase 4B public API
# ---------------------------------------------------------------------------

async def score_rollout(
    rollout: "Rollout",
    scenario: dict[str, Any],
    criteria: list[dict[str, Any]],
    *,
    budget: CostBudget,
    db: "Session",
    match_id: str,
    company_name: str = "",
    role: str = "",
    candidate_label: str = "Candidate",
) -> JudgeResult:
    """Score a completed rollout and return a JudgeResult(rows, transcript_summary).

    Makes two LLM calls (temperature seeds 0.15 and 0.25). Falls back to
    single-judge if the second call fails. If both calls fail, returns null-
    score stubs so the aggregator can treat them as no-signal.

    Caller adds result.rows to the session and commits.
    """
    from ...models import RolloutScore  # deferred to avoid circular import

    dim_keys = [c["key"] for c in criteria]
    if not dim_keys:
        return JudgeResult(rows=[], transcript_summary="")

    schema = judge_output_schema(dim_keys)
    user_prompt = _render_judge_user_prompt(
        rollout, scenario, criteria,
        company_name=company_name, role=role, candidate_label=candidate_label,
    )

    # --- Judge call A (seed index 0) ----------------------------------------
    raw_a: dict | None = None
    try:
        raw_a = await tracked_chat_json(
            budget,
            system=JUDGE_SYSTEM,
            user=user_prompt,
            schema=schema,
            schema_name="judge_output",
            temperature=_JUDGE_TEMPERATURES[0],
            max_tokens=2500,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("judge call A failed for rollout %s: %s", rollout.id, exc)

    # --- Judge call B (seed index 1) ----------------------------------------
    raw_b: dict | None = None
    try:
        raw_b = await tracked_chat_json(
            budget,
            system=JUDGE_SYSTEM,
            user=user_prompt,
            schema=schema,
            schema_name="judge_output",
            temperature=_JUDGE_TEMPERATURES[1],
            max_tokens=2500,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("judge call B failed for rollout %s: %s", rollout.id, exc)

    # --- Determine fallback mode --------------------------------------------
    if raw_a is None and raw_b is None:
        await log_event(match_id, rollout.id, "rollout_unscored", {"reason": "both judges failed"}, db=db)
        # Return null stubs so aggregator reduces effective N.
        return JudgeResult(
            rows=[
                RolloutScore(
                    rollout_id=rollout.id,
                    dimension_key=c["key"],
                    score=None,
                    justification="(both judge calls failed)",
                    evidence_turns=[],
                    judge_model=_JUDGE_MODEL_TAG,
                    judge_seed_index=0,
                    confidence=0.0,
                )
                for c in criteria
            ],
            transcript_summary="",
        )

    if raw_a is None or raw_b is None:
        await log_event(match_id, rollout.id, "judge_fallback", {"failed_seed": 0 if raw_a is None else 1}, db=db)

    # Use whichever succeeded as primary; None means single-judge fallback.
    scores_a = (raw_a or raw_b)["dimension_scores"]
    scores_b = raw_b["dimension_scores"] if (raw_a is not None and raw_b is not None) else None
    summary = (raw_a or raw_b).get("transcript_summary", "")

    # --- Build merged RolloutScore rows ------------------------------------
    result: list[RolloutScore] = []
    dim_scores_out: dict[str, int | None] = {}

    for c in criteria:
        key = c["key"]
        primary = (raw_a or raw_b)["dimension_scores"].get(key, {})

        score, confidence = _merge_scores(scores_a, scores_b, key)
        justification = primary.get("justification", "")
        evidence_turns = primary.get("evidence_turns", [])

        dim_scores_out[key] = score

        row = RolloutScore(
            rollout_id=rollout.id,
            dimension_key=key,
            score=score,
            justification=justification,
            evidence_turns=evidence_turns,
            judge_model=_JUDGE_MODEL_TAG,
            judge_seed_index=0,
            confidence=confidence,
        )
        result.append(row)

    await log_event(
        match_id,
        rollout.id,
        "judge_scored",
        {
            "mock": False,
            "dims": dim_scores_out,
            "transcript_summary": summary,
            "single_judge_fallback": scores_b is None,
        },
        db=db,
    )

    logger.info(
        "score_rollout: rollout=%s dims=%s single_fallback=%s",
        rollout.id, list(dim_scores_out.keys()), scores_b is None,
    )
    return JudgeResult(rows=result, transcript_summary=summary)
