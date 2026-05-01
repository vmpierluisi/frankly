"""LLM-based structured extraction from CV / resume text.

Pulls verbatim experience bullets, education, and skill mentions out of raw CV
text. Voice samples (long-form prose excerpts) are also collected so the
persona aggregator can quote the candidate's own writing register.
"""
from __future__ import annotations

import logging
from typing import Any

from ..simulation.cost_tracker import CostBudget, tracked_chat_json

logger = logging.getLogger(__name__)


CV_EXTRACTOR_SYSTEM = """\
You extract structured profile data from candidate CVs / resumes.

HARD RULES:
  1. Extract VERBATIM where possible. Do not paraphrase role bullets.
  2. If a field is absent in the CV, omit it (do not invent dates, companies,
     or skills).
  3. Skills must appear in the CV text. Do not infer skills the CV does not
     explicitly mention.
  4. Voice samples are 2-5 short verbatim excerpts (1-3 sentences each) of
     the candidate's own writing — pick passages with personal voice
     (e.g. summary statements, longer bullets), not boilerplate.
  5. Output STRICT JSON matching the schema. No commentary.
"""

CV_EXTRACTOR_USER_TEMPLATE = """\
Extract structured profile data from this CV. Be conservative — do not invent.

CV TEXT
\"\"\"
{cv_text}
\"\"\"
"""

CV_EXTRACTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "education": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "institution": {"type": "string"},
                    "degree": {"type": "string"},
                    "field": {"type": "string"},
                    "start": {"type": "string"},
                    "end": {"type": "string"},
                },
                "required": ["institution"],
                "additionalProperties": False,
            },
        },
        "experience": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "company": {"type": "string"},
                    "role": {"type": "string"},
                    "start": {"type": "string"},
                    "end": {"type": "string"},
                    "bullets": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": ["company", "role", "bullets"],
                "additionalProperties": False,
            },
        },
        "skills": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Skill names mentioned verbatim in the CV.",
        },
        "voice_samples": {
            "type": "array",
            "items": {"type": "string"},
            "description": "2-5 short verbatim excerpts of the candidate's writing.",
        },
    },
    "required": ["education", "experience", "skills", "voice_samples"],
    "additionalProperties": False,
}


async def extract_from_cv(cv_text: str, *, budget: CostBudget) -> dict[str, Any]:
    """Run the LLM extractor over CV text.

    Returns a dict with keys: education, experience, skills, voice_samples.
    Returns an empty-default dict if cv_text is empty / placeholder.
    """
    if not cv_text or cv_text == "(none provided)":
        return {"education": [], "experience": [], "skills": [], "voice_samples": []}

    user_prompt = CV_EXTRACTOR_USER_TEMPLATE.format(cv_text=cv_text)
    result = await tracked_chat_json(
        budget,
        system=CV_EXTRACTOR_SYSTEM,
        user=user_prompt,
        schema=CV_EXTRACTION_SCHEMA,
        schema_name="cv_extraction",
        temperature=0.1,
        max_tokens=2500,
    )
    return result
