"""Candidate persona aggregator.

MiroFish lineage: this module corresponds to MiroFish's PersonaDocument
aggregation pass. In MiroFish, a PersonaDocument is built from a trait_sheet +
provenance. Here we build the same artifact from heterogeneous evidence sources
with explicit reliability weighting.

v1 fine-tuning target: the prompt template + schema in this module are the
primary artifacts that will be improved via retrospective study output. Keep
the prompt constants isolated and easy to version-snapshot (see
tests/simulation/test_persona_aggregator.py for snapshot tests).
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ...seed_data import BFI10, SJTS
from ..artifact_parser import parse_upload
from .cost_tracker import CostBudget, tracked_chat_json
from .types import AggregatedPersona

if TYPE_CHECKING:
    from ...models import Candidate

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompt templates (verbatim from brief Appendix A.1 — do not paraphrase)
# ---------------------------------------------------------------------------

PERSONA_AGGREGATOR_SYSTEM = """\
You are the candidate persona aggregator inside a hiring-screening platform.
Your job is to synthesize a behavioral profile of a candidate from
heterogeneous evidence sources, with explicit reliability weighting per source.

YOU PRODUCE A SCREENING-LEVEL ARTIFACT, NOT A HIRING JUDGMENT.

SOURCE RELIABILITY PRIORS (apply rigorously):
  * BFI-10 self-report: HIGH reliability for self-perception, MODERATE for
    behavior. Use as trait anchors. Documented self-presentation bias.
  * Situational Judgment Tests: HIGH reliability for situational reasoning
    (well-validated psychometric instrument). Use as behavior anchors.
  * CV / resume text: MODERATE reliability for skill claims (presentation
    bias), LOW for personality. Treat skill claims as candidate-asserted.
  * LinkedIn URL or extracted summary (where available): LOW reliability for
    personality (heavy presentation bias), MODERATE for trajectory and role
    inference.
  * GitHub URL or extracted summary (where available): LOW reliability as
    personality signal, MODERATE for conscientiousness and skill proxies
    (commit cadence, code review behavior, documentation habits, languages).

HARD RULES:
  1. Every claim in structured_traits or narrative MUST appear in
     provenance_map with at least one cited source plus a reliability_weight
     tag of "high", "moderate", or "low".
  2. When sources conflict, surface the conflict in inconsistencies — do not
     silently average. Each inconsistency gets a type slug and a one-paragraph
     note framed for a human interviewer.
  3. Never reference protected characteristics (race, gender, age, national
     origin, religion, disability, sexual orientation, pregnancy, marital
     status) or proxies for them.
  4. Frame every claim as "self-reports", "behavioral evidence suggests",
     "trajectory indicates" — never as fixed personality verdicts.
  5. Output STRICT JSON matching the provided schema exactly. Do not invent
     fields. Do not omit required fields.
  6. If an evidence source is missing or empty, produce reduced-confidence
     claims rather than refusing — note the absence in
     evidence_completeness.

SCALES:
  * Big Five traits: 0.0 to 5.0 (BFI-10 native scale, two-decimal precision).
  * SJT signals: 0.0 to 5.0 (matches existing seed_data.SJTS signal weights).
  * Skill inferences: 0.0 to 1.0 (likelihood-to-demonstrate scale).
  * Work-style inferences: 0.0 to 1.0 (preference intensity scale).
  * provenance_map confidence: 0.0 to 1.0.

NARRATIVE REQUIREMENTS:
  * 800 to 1500 words. Plain prose. No headers, no bullets, no numbered
    lists.
  * Cite the structured anchors organically; do not number or label them.
  * Tone: clinical-but-humane, like a research note. Past-tense observations,
    present-tense inferences, conditional language for predictions.
  * Never address the candidate directly. Third-person throughout.
  * Surface uncertainty. A short narrative honestly acknowledging missing
    evidence is better than a long one filling gaps with confabulation.\
"""

PERSONA_AGGREGATOR_USER_TEMPLATE = """\
Synthesize the candidate's behavioral profile from the evidence below.

CANDIDATE METADATA
------------------
Display name: {display_name_or_anon}
Email present: {email_present}

BFI-10 RAW RESPONSES (1-5 Likert, item id : score)
--------------------------------------------------
{bfi_block}

BFI-10 ITEMS (for your reference)
{bfi_items_block}

SJT RESPONSES (situation : chosen option, with that option's signal weights)
----------------------------------------------------------------------------
{sjt_block}

CV / RESUME TEXT (parsed; may be empty)
\"\"\"
{cv_text}
\"\"\"

LINKEDIN
--------
URL provided: {linkedin_present}
Extracted summary (may be empty in v0; treat as URL-only when absent):
\"\"\"
{linkedin_summary}
\"\"\"

GITHUB
------
URL provided: {github_present}
Extracted summary (may be empty in v0; treat as URL-only when absent):
\"\"\"
{github_summary}
\"\"\"

TASK
----
Return a JSON object matching the AggregatedPersona schema. Specifically:

1. Compute big_five from the BFI-10 responses (items, reverse-scoring rules,
   averaging — see persona.py for the canonical algorithm; reproduce it
   inside your reasoning, do not call out to it).
2. Compute sjt_signals from the SJT responses (sum signal weights across
   selected options, divide by number of SJTs answered).
3. Infer skill_inferences and work_style from CV / LinkedIn / GitHub
   evidence. If a category has no supporting evidence, omit the key
   entirely rather than fabricating a midpoint score.
4. Build provenance_map: every non-trivial claim is one entry. Cite the
   specific source and quote a short evidence excerpt where possible.
5. Detect inconsistencies. The three rules from persona.py
   (agreeable-dissenter, low-c-high-rigor, neurotic-but-tolerant) are the
   floor — surface additional cross-source tensions you observe.
6. Write the narrative last, anchored in the structured claims and the
   provenance_map.
7. Set evidence_completeness to flag missing sources and any confidence
   degradation.
8. Set aggregator_version to "v0.1".\
"""

# ---------------------------------------------------------------------------
# JSON schema (verbatim from brief Appendix B.1)
# ---------------------------------------------------------------------------

AGGREGATED_PERSONA_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "structured_traits": {
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
                    "required": [
                        "openness", "conscientiousness", "extraversion",
                        "agreeableness", "neuroticism",
                    ],
                    "additionalProperties": False,
                },
                "sjt_signals": {
                    "type": "object",
                    "properties": {
                        "analyticalRigor":     {"type": "number"},
                        "intellectualHonesty": {"type": "number"},
                        "writtenDissent":      {"type": "number"},
                        "ambiguityTolerance":  {"type": "number"},
                        "lowEgoCollab":        {"type": "number"},
                    },
                    "required": [
                        "analyticalRigor", "intellectualHonesty",
                        "writtenDissent", "ambiguityTolerance", "lowEgoCollab",
                    ],
                    "additionalProperties": False,
                },
                "skill_inferences": {
                    "type": "object",
                    "additionalProperties": {"type": "number"},
                    "properties": {},
                    "required": [],
                    "description": (
                        "Free-form key/value map of skill -> 0.0-1.0. "
                        "Omit a skill entirely rather than inventing a midpoint. "
                        "Example keys: systems_thinking, written_communication, "
                        "domain_finance, code_review_discipline."
                    ),
                },
                "work_style": {
                    "type": "object",
                    "additionalProperties": {"type": "number"},
                    "properties": {},
                    "required": [],
                    "description": (
                        "Free-form key/value map of work-style preference -> 0.0-1.0. "
                        "Example keys: async_pref, written_first, conflict_comfort, "
                        "structure_seeking."
                    ),
                },
            },
            "required": ["big_five", "sjt_signals", "skill_inferences", "work_style"],
            "additionalProperties": False,
        },
        "narrative": {
            "type": "string",
            "description": (
                "800-1500 word prose synthesis. Plain prose, no headers, "
                "third-person, clinical-but-humane."
            ),
        },
        "provenance_map": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "claim": {"type": "string"},
                    "sources": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "source": {
                                    "type": "string",
                                    "description": (
                                        "One of: 'bfi', 'sjt:<sjt_id>', 'cv', "
                                        "'linkedin', 'github'."
                                    ),
                                },
                                "evidence": {
                                    "type": "string",
                                    "description": "Short quoted excerpt or item id.",
                                },
                            },
                            "required": ["source", "evidence"],
                            "additionalProperties": False,
                        },
                    },
                    "confidence": {"type": "number"},
                    "reliability_weight": {
                        "type": "string",
                        "description": "One of 'high', 'moderate', 'low'.",
                    },
                },
                "required": ["claim", "sources", "confidence", "reliability_weight"],
                "additionalProperties": False,
            },
        },
        "inconsistencies": {
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
        "evidence_completeness": {
            "type": "object",
            "properties": {
                "bfi_present":      {"type": "boolean"},
                "sjt_present":      {"type": "boolean"},
                "cv_present":       {"type": "boolean"},
                "linkedin_present": {"type": "boolean"},
                "github_present":   {"type": "boolean"},
                "notes":            {"type": "string"},
            },
            "required": [
                "bfi_present", "sjt_present", "cv_present",
                "linkedin_present", "github_present", "notes",
            ],
            "additionalProperties": False,
        },
        "aggregator_version": {"type": "string"},
    },
    "required": [
        "structured_traits", "narrative", "provenance_map",
        "inconsistencies", "evidence_completeness", "aggregator_version",
    ],
    "additionalProperties": False,
}


# ---------------------------------------------------------------------------
# Prompt rendering helpers
# ---------------------------------------------------------------------------

def _render_bfi_block(bfi_responses: dict[str, int]) -> str:
    return "\n".join(
        f"  {item['id']}: {bfi_responses.get(item['id'], '(not answered)')}"
        for item in BFI10
    )


def _render_bfi_items_block() -> str:
    return "\n".join(
        f"  {item['id']}: {item['text']} "
        f"(trait={item['trait']}, reverse={item['reverse']})"
        for item in BFI10
    )


def _render_sjt_block(sjt_responses: dict[str, str]) -> str:
    lines: list[str] = []
    for sjt in SJTS:
        chosen_id = sjt_responses.get(sjt["id"])
        if not chosen_id:
            lines.append(f"  {sjt['id']}: (not answered)")
            continue
        chosen = next((o for o in sjt["options"] if o["id"] == chosen_id), None)
        if not chosen:
            lines.append(f"  {sjt['id']}: (unknown option {chosen_id!r})")
            continue
        signals_str = ", ".join(f"{k}={v}" for k, v in chosen["signal"].items())
        lines.append(
            f"  {sjt['id']}: Option {chosen_id.upper()} — \"{chosen['text']}\"\n"
            f"    signal weights: {signals_str}"
        )
    return "\n".join(lines)


def _load_cv_text(candidate: "Candidate") -> str:
    cv_path = getattr(candidate, "cv_path", None)
    if not cv_path:
        return "(none provided)"
    try:
        p = Path(cv_path)
        if not p.exists():
            logger.warning("cv_path %s does not exist for candidate %s", cv_path, candidate.id)
            return "(none provided)"
        data = p.read_bytes()
        text = parse_upload(filename=p.name, data=data)
        return text or "(none provided)"
    except Exception as exc:
        logger.warning("Failed to parse CV for candidate %s: %s", candidate.id, exc)
        return "(none provided)"


def _render_user_prompt(candidate: "Candidate") -> str:
    """Render the user prompt template for a given candidate.

    Exposed as a public function so snapshot tests can capture the rendered
    prompt without making an LLM call.
    """
    bfi_responses: dict[str, int] = candidate.bfi_responses or {}
    sjt_responses: dict[str, str] = candidate.sjt_responses or {}
    cv_text = _load_cv_text(candidate)
    linkedin_url = getattr(candidate, "linkedin_url", None) or ""
    github_url = getattr(candidate, "github_url", None) or ""
    display_name = getattr(candidate, "display_name", None) or "anonymous"
    email = getattr(candidate, "email", None)

    return PERSONA_AGGREGATOR_USER_TEMPLATE.format(
        display_name_or_anon=display_name,
        email_present="yes" if email else "no",
        bfi_block=_render_bfi_block(bfi_responses),
        bfi_items_block=_render_bfi_items_block(),
        sjt_block=_render_sjt_block(sjt_responses),
        cv_text=cv_text,
        linkedin_present="yes" if linkedin_url else "no",
        linkedin_summary="(none provided)",
        github_present="yes" if github_url else "no",
        github_summary="(none provided)",
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def aggregate(candidate: "Candidate", *, budget: CostBudget) -> AggregatedPersona:
    """Aggregate all candidate evidence sources into an AggregatedPersona.

    Parameters
    ----------
    candidate : Candidate
        SQLAlchemy Candidate row. Must have bfi_responses and sjt_responses
        populated. cv_path, linkedin_url, github_url are optional.
    budget : CostBudget
        Per-match cost tracker. Raises CostCeilingExceeded if the ceiling
        is reached before this call completes.

    Returns
    -------
    AggregatedPersona dict — validated by the LLM against AGGREGATED_PERSONA_SCHEMA.
    No database writes are performed here; persistence is Phase 1B.
    """
    user_prompt = _render_user_prompt(candidate)
    result = await tracked_chat_json(
        budget,
        system=PERSONA_AGGREGATOR_SYSTEM,
        user=user_prompt,
        schema=AGGREGATED_PERSONA_SCHEMA,
        schema_name="aggregated_persona",
        temperature=0.2,
        max_tokens=4500,
    )
    return result  # type: ignore[return-value]
