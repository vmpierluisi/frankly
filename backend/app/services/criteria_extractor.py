"""Criteria extractor — the other real LLM call.

Takes the four company artifacts and returns 5–7 criteria, each with:
  * key     — camelCase identifier used for matching (e.g. "analyticalRigor")
  * label   — human-readable name for the UI
  * description — grounded in artifact text (the prompt forces the model to
                  cite the artifact it drew from)
  * weight  — suggested weight; weights sum to 1.0 across the returned set

Manager reviews / edits / approves before the criteria are saved on the
company. Weight re-normalization happens server-side so the manager doesn't
have to sum to 1.0 manually.
"""
from __future__ import annotations

from typing import Any

from . import openrouter


SYSTEM_PROMPT = """You extract formal hiring criteria from a company's \
sanctioned artifacts (values document, role specification, team structure, \
sample communications).

Rules:
  1. Produce 5 to 7 criteria that are specific to the role and company, not \
generic "teamwork / communication / ownership" filler.
  2. Each description must cite the artifact text that justifies it. Use short \
direct quotations inside the description.
  3. Each criterion's `key` is camelCase (e.g. "analyticalRigor", "speedOfConviction").
  4. Weights are in [0, 1] and sum to 1.0 across the returned criteria.
  5. Never include criteria that proxy for protected characteristics (age, \
nationality, disability, etc.) or for social background.
  6. Output strict JSON only, matching the schema.
"""

USER_TEMPLATE = """Extract the formal criteria this company uses to evaluate \
candidates for the role below. Cite artifact text in each description.

ROLE: {role}

VALUES DOCUMENT:
\"\"\"
{artifact_values}
\"\"\"

ROLE SPECIFICATION:
\"\"\"
{artifact_role_spec}
\"\"\"

TEAM STRUCTURE:
\"\"\"
{artifact_team_structure}
\"\"\"

SAMPLE COMMUNICATIONS:
\"\"\"
{artifact_sample_comms}
\"\"\"
"""


SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "criteria": {
            "type": "array",
            "minItems": 5,
            "maxItems": 7,
            "items": {
                "type": "object",
                "properties": {
                    "key": {
                        "type": "string",
                        "description": "camelCase identifier",
                        "pattern": "^[a-z][a-zA-Z0-9]*$",
                    },
                    "label": {"type": "string"},
                    "description": {
                        "type": "string",
                        "description": "One to two sentences, cites artifact text.",
                    },
                    "weight": {
                        "type": "number",
                        "minimum": 0,
                        "maximum": 1,
                    },
                },
                "required": ["key", "label", "description", "weight"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["criteria"],
    "additionalProperties": False,
}


async def extract_criteria(
    *,
    role: str,
    artifact_values: str,
    artifact_role_spec: str,
    artifact_team_structure: str,
    artifact_sample_comms: str,
) -> list[dict[str, Any]]:
    user = USER_TEMPLATE.format(
        role=role,
        artifact_values=artifact_values,
        artifact_role_spec=artifact_role_spec,
        artifact_team_structure=artifact_team_structure,
        artifact_sample_comms=artifact_sample_comms,
    )
    out = await openrouter.chat_json(
        system=SYSTEM_PROMPT,
        user=user,
        schema=SCHEMA,
        schema_name="criteria_extraction",
        temperature=0.3,
        max_tokens=1800,
    )
    criteria: list[dict[str, Any]] = out["criteria"]

    # Re-normalize weights in case the model didn't quite sum to 1.0.
    total = sum(c.get("weight", 0.0) for c in criteria)
    if total > 0:
        for c in criteria:
            c["weight"] = round(c["weight"] / total, 3)

    return criteria
