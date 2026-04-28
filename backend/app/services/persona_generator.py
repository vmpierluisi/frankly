"""LLM-generated synthetic candidate responses for pool seeding.

One OpenRouter call per candidate using a cheap/fast model.  The output
matches the exact intake payload shape so it can be fed directly into
`synthesize_persona` and stored as a real Candidate row with is_seed=True.
"""
from __future__ import annotations

import random
from typing import Any

from .openrouter import chat_json

# ---------------------------------------------------------------------------
# Archetypes — the model picks a personality "seed" from this list so the 100
# generated profiles form a realistic distribution rather than a blob of
# median responses.
# ---------------------------------------------------------------------------
ARCHETYPES = [
    "The Meticulous IC — extreme conscientiousness, low extraversion, prefers exhaustive analysis over speed, uncomfortable with ambiguity, will dissent in writing",
    "The Impatient Founder Type — low conscientiousness, high extraversion, biased toward speed and conviction, dismisses excessive deliberation, charismatic but cuts corners on rigour",
    "The Contrarian Analyst — high openness and agreeableness but low, very low writtenDissent threshold — calls out bad reasoning publicly, intellectually honest to a fault",
    "The Consensus Builder — high agreeableness, high extraversion, excellent at lowEgoCollab, uncomfortable with confrontation, prefers private alignment over public dissent",
    "The Late Bloomer — middling scores across the board but high intellectualHonesty, acknowledges gaps openly, asks for help, steady under pressure",
    "The Principled Skeptic — high conscientiousness and neuroticism, risk-averse, flags every downside, high analyticalRigor, writes long memos, sometimes slows the team",
    "The Pragmatic Operator — medium conscientiousness, medium agreeableness, high ambiguityTolerance, gets things done with imperfect information, not precious about process",
    "The Visionary Generalist — high openness, low conscientiousness, connects disparate ideas quickly, easily bored by detail work, energizes rooms but misses deadlines",
]

_BFI_ITEM_LIST = """
BFI-10 items (respond 1=strongly disagree … 5=strongly agree):
  e1 — "I see myself as someone who is reserved"  [reverse-scored for Extraversion]
  a1 — "I see myself as someone who is generally trusting"
  c1 — "I see myself as someone who tends to be lazy"  [reverse-scored for Conscientiousness]
  n1 — "I see myself as someone who is relaxed, handles stress well"  [reverse-scored for Neuroticism]
  o1 — "I see myself as someone who has few artistic interests"  [reverse-scored for Openness]
  e2 — "I see myself as someone who is outgoing, sociable"
  a2 — "I see myself as someone who tends to find fault with others"  [reverse-scored for Agreeableness]
  c2 — "I see myself as someone who does a thorough job"
  n2 — "I see myself as someone who gets nervous easily"
  o2 — "I see myself as someone who has an active imagination"
"""

_SJT_OPTIONS = """
sjt1 (IRR below hurdle, MD excited, IC memo due tomorrow):
  a — Flag the gap prominently, send with 12% base case  [intellectualHonesty↑ writtenDissent↑]
  b — Revisit assumptions for legitimate upside, send whatever you find  [analyticalRigor↑]
  c — Adjust assumption upward to 15.5%, note the change  [dishonest, low all signals]
  d — Ask the MD directly before finalising  [lowEgoCollab↑]

sjt2 (VP publicly dismisses your risk memo, five people watching):
  a — Defend with data in the meeting  [writtenDissent↑ analyticalRigor↑]
  b — Note it, follow up privately  [lowEgoCollab↑]
  c — Invite the room to walk through the appendix  [lowEgoCollab↑ writtenDissent↑]
  d — Drop it — it's already in writing  [moderate all]

sjt3 (unfamiliar sector model, day one confidence low, three days total):
  a — Deliver on schedule with flagged caveats  [intellectualHonesty↑ ambiguityTolerance↑]
  b — Tell the lead on day two you need an extension  [intellectualHonesty↑]
  c — Push through and present as best estimate  [low intellectualHonesty]
  d — Find two sector experts, burn a day, build with citations  [ambiguityTolerance↑ analyticalRigor↑ lowEgoCollab↑]
"""

_SYSTEM = """You are generating a synthetic candidate for a private-equity analyst hiring simulation.
Your output is used for demo/testing and will never be shown to real users.

Guidelines:
- Embody the given archetype fully and consistently — internal consistency matters.
- BFI values must be integers 1–5. Do not use values outside this range.
- SJT option IDs must be exactly one of: a, b, c, d.
- The display_name should be a realistic-sounding full name (first + last), varied gender and ethnicity.
- Make choices that logically reflect the archetype's personality — don't randomise.
"""


_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "display_name": {"type": "string"},
        "bfi_responses": {
            "type": "object",
            "properties": {
                "e1": {"type": "integer"},
                "a1": {"type": "integer"},
                "c1": {"type": "integer"},
                "n1": {"type": "integer"},
                "o1": {"type": "integer"},
                "e2": {"type": "integer"},
                "a2": {"type": "integer"},
                "c2": {"type": "integer"},
                "n2": {"type": "integer"},
                "o2": {"type": "integer"},
            },
            "required": ["e1", "a1", "c1", "n1", "o1", "e2", "a2", "c2", "n2", "o2"],
            "additionalProperties": False,
        },
        "sjt_responses": {
            "type": "object",
            "properties": {
                "sjt1": {"type": "string"},
                "sjt2": {"type": "string"},
                "sjt3": {"type": "string"},
            },
            "required": ["sjt1", "sjt2", "sjt3"],
            "additionalProperties": False,
        },
    },
    "required": ["display_name", "bfi_responses", "sjt_responses"],
    "additionalProperties": False,
}


async def generate_synthetic_responses(archetype: str | None = None) -> dict[str, Any]:
    """Return `{display_name, bfi_responses, sjt_responses}` shaped like the intake payload."""
    chosen = archetype or random.choice(ARCHETYPES)

    user_msg = f"""Archetype: {chosen}

{_BFI_ITEM_LIST}

{_SJT_OPTIONS}

Generate a single synthetic candidate that fully embodies this archetype.
Remember: BFI values are integers 1–5; SJT options are exactly a/b/c/d."""

    raw = await chat_json(
        system=_SYSTEM,
        user=user_msg,
        schema=_RESPONSE_SCHEMA,
        schema_name="synthetic_candidate",
        model="anthropic/claude-haiku-4-5",
        temperature=0.9,
        max_tokens=400,
    )

    # Clamp BFI values defensively (model occasionally emits 0 or 6).
    bfi = {k: max(1, min(5, int(v))) for k, v in raw["bfi_responses"].items()}
    # Normalise SJT options to lowercase single char.
    sjt = {k: str(v).strip().lower()[0] for k, v in raw["sjt_responses"].items()}

    return {
        "display_name": raw["display_name"],
        "bfi_responses": bfi,
        "sjt_responses": sjt,
    }
