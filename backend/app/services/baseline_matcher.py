"""Matcher — one of the two real LLM calls.

Takes a persona (BFI Big Five + SJT signals + cross-validation flags) plus a
company (four artifacts + criteria with weights) and returns a fit report.

Output must:
  * Include a 0-100 weighted overall score and a qualitative band.
  * Include a per-criterion score in [0, 100] with a one-sentence justification
    that cites artifact text directly.
  * Include the cross-validation flags verbatim (so the manager can probe in
    interview).
  * Frame itself as a screening signal — not a hiring decision.
  * Never reference protected characteristics.

The matcher issues ONE OpenRouter call with a strict JSON schema. On top of the
LLM's per-criterion scores we compute the weighted overall ourselves in Python
so the arithmetic is deterministic even if the LLM rounds.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from . import openrouter
from ..config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Prompt (evolved from MATCHING_PROMPT in hiring-sim-demo.jsx).
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """You are the matching engine inside a hiring-screening \
platform. Your job is to assess how a candidate persona would behave inside a \
specific company environment, using the company's own artifacts as ground \
truth.

YOU ARE A SCREENING SIGNAL, NOT A HIRING DECISION TOOL.

Hard rules:
  1. Ground every per-criterion justification in direct quotations or close \
paraphrases of the company's artifact text. If you cannot ground a score, \
lower your confidence — do not invent evidence.
  2. Never reference protected characteristics (race, gender, age, national \
origin, religion, disability, sexual orientation, pregnancy, marital status, \
etc.) or proxies for them.
  3. Frame output as "would likely behave" / "signals suggest" — never as \
hiring prescriptions.
  4. If the persona's cross-validation flags indicate tension, surface them \
in the report verbatim so a human interviewer can probe them.
  5. Output strict JSON only, matching the provided schema exactly.

Scoring guidance:
  * Scores are 0–100 per criterion: 0 = strong misfit, 50 = uncertain, \
100 = strong fit. Anchor to evidence, not aesthetics.
  * One-sentence justifications per criterion. Quote artifact text in \
quotation marks when you cite it.
"""


USER_PROMPT_TEMPLATE = """COMPANY
-------
Name: {company_name}
Role: {role}
Tagline: {tagline}

Values document:
\"\"\"
{artifact_values}
\"\"\"

Role specification:
\"\"\"
{artifact_role_spec}
\"\"\"

Team structure:
\"\"\"
{artifact_team_structure}
\"\"\"

Sample communication:
\"\"\"
{artifact_sample_comms}
\"\"\"

FORMAL CRITERIA (score each 0-100)
----------------------------------
{criteria_block}

CANDIDATE PERSONA
-----------------
Big Five (0-5 scale):
{big_five_block}

SJT behavioral signals (0-5 scale, aggregated across scenarios):
{sjt_signals_block}

Cross-validation flags raised during intake:
{flags_block}

Narrative summary (from intake):
{narrative}

TASK
----
Return a JSON object with:
  * criterionScores: object keyed by criterion key (listed above). Each value \
is {{score: 0-100 integer, justification: one-sentence string that quotes the \
artifact text it relies on}}.
  * bandNote: one sentence explaining the overall fit, pitched to the hiring \
manager. Screening framing only.
  * inconsistencyFlags: the exact cross-validation flag list you were given, \
passed through unchanged (same shape: [{{"type": str, "note": str}}]).
"""


# ---------------------------------------------------------------------------
# JSON schema for the structured response.
# ---------------------------------------------------------------------------
def _schema_for_criteria(criterion_keys: list[str]) -> dict[str, Any]:
    criterion_score_schema = {
        "type": "object",
        "properties": {
            "score": {
                "type": "integer",
                "description": "0-100 fit score for this criterion.",
            },
            "justification": {
                "type": "string",
                "description": (
                    "One sentence citing artifact text. Screening framing; "
                    "no hiring prescriptions; no protected characteristics."
                ),
            },
        },
        "required": ["score", "justification"],
        "additionalProperties": False,
    }
    criterion_scores = {
        "type": "object",
        "properties": {k: criterion_score_schema for k in criterion_keys},
        "required": criterion_keys,
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {
            "criterionScores": criterion_scores,
            "bandNote": {"type": "string"},
            "inconsistencyFlags": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string"},
                        "note": {"type": "string"},
                    },
                    "required": ["type", "note"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["criterionScores", "bandNote", "inconsistencyFlags"],
        "additionalProperties": False,
    }


# ---------------------------------------------------------------------------
# Band derivation — same thresholds as the JSX reference.
# ---------------------------------------------------------------------------
def _band_for(score: float, company_name: str) -> tuple[str, str]:
    if score >= 88:
        return (
            "Exceptional fit",
            "Strong recommendation to surface to hiring manager for mutual opt-in.",
        )
    if score >= 75:
        return (
            "Strong fit",
            "Recommend surfacing to hiring manager for mutual opt-in.",
        )
    if score >= 62:
        return (
            "Good fit",
            "Worth a conversation; specific tensions worth probing in interview.",
        )
    if score >= 48:
        return (
            "Moderate fit",
            "Environmental fit is uncertain. Not recommended for surfacing without additional signal.",
        )
    if score >= 35:
        return (
            "Weak fit",
            f"Candidate strengths likely lie in environments structurally different from {company_name}'s.",
        )
    return (
        "Poor fit",
        f"Significant environmental mismatch with {company_name}. Not recommended.",
    )


# ---------------------------------------------------------------------------
# Main entry point.
# ---------------------------------------------------------------------------
async def run_match(*, persona: dict[str, Any], company: dict[str, Any]) -> dict[str, Any]:
    """Match one persona against one company. Returns a FitReport dict."""

    criteria: list[dict[str, Any]] = company["criteria"]
    criterion_keys = [c["key"] for c in criteria]
    weights: dict[str, float] = {c["key"]: float(c["weight"]) for c in criteria}

    user_prompt = USER_PROMPT_TEMPLATE.format(
        company_name=company["name"],
        role=company["role"],
        tagline=company.get("tagline") or "",
        artifact_values=company["artifact_values"],
        artifact_role_spec=company["artifact_role_spec"],
        artifact_team_structure=company["artifact_team_structure"],
        artifact_sample_comms=company["artifact_sample_comms"],
        criteria_block="\n".join(
            f"  - {c['key']} ({c['label']}, weight {c['weight']:.2f}): {c['description']}"
            for c in criteria
        ),
        big_five_block="\n".join(
            f"  - {k}: {v:.2f}" for k, v in persona["bigFive"].items()
        ),
        sjt_signals_block="\n".join(
            f"  - {k}: {v:.2f}" for k, v in persona["sjtSignals"].items()
        ),
        flags_block=(
            "\n".join(
                f"  - [{f['type']}] {f['note']}"
                for f in persona["inconsistencies"]
            )
            if persona["inconsistencies"]
            else "  (none raised)"
        ),
        narrative=persona.get("narrative", ""),
    )

    schema = _schema_for_criteria(criterion_keys)

    llm_out = await openrouter.chat_json(
        system=SYSTEM_PROMPT,
        user=user_prompt,
        schema=schema,
        schema_name="fit_report",
        temperature=0.15,
        max_tokens=2000,
    )

    # Compute the weighted overall ourselves — deterministic arithmetic on top
    # of the LLM's per-criterion scores.
    criterion_scores: dict[str, dict[str, Any]] = llm_out["criterionScores"]
    weighted_sum = 0.0
    for key, cs in criterion_scores.items():
        weighted_sum += float(cs["score"]) * weights.get(key, 0.0)
    overall = int(round(max(0.0, min(100.0, weighted_sum))))

    band, band_note_fallback = _band_for(overall, company["name"])
    band_note = (llm_out.get("bandNote") or band_note_fallback).strip()

    return {
        "companyId": company["id"],
        "companyName": company["name"],
        "role": company["role"],
        "overallScore": overall,
        "band": band,
        "bandNote": band_note,
        "criterionScores": criterion_scores,
        "inconsistencyFlags": llm_out.get("inconsistencyFlags", persona["inconsistencies"]),
        "auditTrail": {
            "model": settings.openrouter_model,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "note": (
                "v0 matcher: single LLM call with strict JSON schema and "
                "response-healing. Weighted overall computed deterministically "
                "from per-criterion scores. ReasoningLayer audit trail is the "
                "Week 16+ upgrade path."
            ),
        },
    }


# ---------------------------------------------------------------------------
# Fit-axis projection — abstract role / culture / growth axes for the 3D map.
# Placeholder until the mirofish adaptation provides real embedding coords.
# ---------------------------------------------------------------------------
_AXIS_KEYWORDS = {
    "culture": ("culture", "value", "communication", "comms", "collaborat", "team", "trust", "feedback", "dissent"),
    "growth": ("growth", "learn", "ambition", "curios", "adapt", "develop", "potential", "openness"),
}


def _bucket_for(criterion: dict[str, Any]) -> str:
    """Classify a criterion into one of role / culture / growth by keyword."""
    haystack = f"{criterion.get('key','')} {criterion.get('label','')} {criterion.get('description','')}".lower()
    for axis, keywords in _AXIS_KEYWORDS.items():
        if any(kw in haystack for kw in keywords):
            return axis
    return "role"


def project_fit_axes(
    report: dict[str, Any], criteria: list[dict[str, Any]]
) -> dict[str, float]:
    """Project per-criterion scores onto three abstract axes.

    Each axis = weighted mean of its bucketed criteria scores (0-100). Empty
    axes fall back to the overall score so nodes aren't pinned to the origin.
    """
    buckets: dict[str, list[tuple[float, float]]] = {"role": [], "culture": [], "growth": []}
    by_key = {c["key"]: c for c in criteria}
    scores = report.get("criterionScores", {})
    for key, val in scores.items():
        crit = by_key.get(key)
        if not crit:
            continue
        axis = _bucket_for(crit)
        buckets[axis].append((float(val.get("score", 0)), float(crit.get("weight", 0))))

    fallback = float(report.get("overallScore", 50))
    out: dict[str, float] = {}
    for axis, entries in buckets.items():
        total_w = sum(w for _, w in entries)
        if total_w <= 0:
            out[axis] = fallback
        else:
            out[axis] = round(sum(s * w for s, w in entries) / total_w, 1)
    return out
