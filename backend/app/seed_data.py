"""Seed content: BFI-10, SJTs, and two contrasting seed companies.

Meridian is ported VERBATIM from hiring-sim-demo.jsx per the brief. Do not
redesign — the psychometric content was already production-ready there.

Kestrel Growth Partners is the second, contrasting FA company written for this
build. It deliberately inverts Meridian's values (speed over patience, verbal
conviction over written dissent, pattern-matching over exhaustive rigor) so
the matcher visibly discriminates between environments for the same candidate.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from . import models


# ---------------------------------------------------------------------------
# BFI-10 — Rammstedt & John (2007). Ported verbatim from hiring-sim-demo.jsx.
# ---------------------------------------------------------------------------
BFI10 = [
    {"id": "e1", "text": "I see myself as someone who is reserved", "trait": "E", "reverse": True},
    {"id": "a1", "text": "I see myself as someone who is generally trusting", "trait": "A", "reverse": False},
    {"id": "c1", "text": "I see myself as someone who tends to be lazy", "trait": "C", "reverse": True},
    {"id": "n1", "text": "I see myself as someone who is relaxed, handles stress well", "trait": "N", "reverse": True},
    {"id": "o1", "text": "I see myself as someone who has few artistic interests", "trait": "O", "reverse": True},
    {"id": "e2", "text": "I see myself as someone who is outgoing, sociable", "trait": "E", "reverse": False},
    {"id": "a2", "text": "I see myself as someone who tends to find fault with others", "trait": "A", "reverse": True},
    {"id": "c2", "text": "I see myself as someone who does a thorough job", "trait": "C", "reverse": False},
    {"id": "n2", "text": "I see myself as someone who gets nervous easily", "trait": "N", "reverse": False},
    {"id": "o2", "text": "I see myself as someone who has an active imagination", "trait": "O", "reverse": False},
]


# ---------------------------------------------------------------------------
# Situational Judgment Tests — authored against Meridian artifacts.
# Ported verbatim; signal weights preserved exactly.
# ---------------------------------------------------------------------------
SJTS = [
    {
        "id": "sjt1",
        "scenario": (
            "You've spent six days modeling a deal the MD is clearly excited about. "
            "Your base case shows a 12% IRR — below the firm's 15% hurdle. The MD "
            "mentions in passing that 'there's always upside we haven't captured.' "
            "The IC memo is due tomorrow."
        ),
        "question": "What do you do?",
        "options": [
            {
                "id": "a",
                "text": "Send the memo with the 12% base case and three downside scenarios. Flag the gap to the hurdle prominently.",
                "signal": {"intellectualHonesty": 5, "writtenDissent": 5, "analyticalRigor": 4},
            },
            {
                "id": "b",
                "text": "Revisit assumptions to see if there's legitimate upside the MD might be pointing to, then send the memo reflecting whatever you find.",
                "signal": {"intellectualHonesty": 4, "analyticalRigor": 5, "writtenDissent": 3},
            },
            {
                "id": "c",
                "text": "Adjust the growth assumption upward to reflect the MD's implied confidence, bringing IRR to 15.5%. Note the change in the memo.",
                "signal": {"intellectualHonesty": 1, "writtenDissent": 1, "analyticalRigor": 2},
            },
            {
                "id": "d",
                "text": "Ask the MD directly what upside they see before finalizing the memo.",
                "signal": {"intellectualHonesty": 4, "lowEgoCollab": 4, "writtenDissent": 2},
            },
        ],
    },
    {
        "id": "sjt2",
        "scenario": (
            "In deal review, a VP publicly dismisses a risk you raised in your memo "
            "as 'theoretical.' You believe the risk is real and material. Five other "
            "people are in the room."
        ),
        "question": "What do you do?",
        "options": [
            {
                "id": "a",
                "text": "Defend your position in the meeting with the specific data points from your sensitivity analysis.",
                "signal": {"writtenDissent": 5, "analyticalRigor": 5, "lowEgoCollab": 3},
            },
            {
                "id": "b",
                "text": "Note it, move on, and follow up with the VP privately after the meeting.",
                "signal": {"writtenDissent": 2, "lowEgoCollab": 4},
            },
            {
                "id": "c",
                "text": "Acknowledge the VP's experience, but ask the room if anyone wants to walk through Appendix C before dismissing it.",
                "signal": {"writtenDissent": 4, "lowEgoCollab": 5, "analyticalRigor": 4},
            },
            {
                "id": "d",
                "text": "Drop it — you've already put it in writing in the memo, which is what matters.",
                "signal": {"writtenDissent": 3, "lowEgoCollab": 3},
            },
        ],
    },
    {
        "id": "sjt3",
        "scenario": (
            "You're asked to build a model for a sector you've never covered. You "
            "have three days. Your honest assessment after day one is that you "
            "don't understand the unit economics well enough to produce reliable "
            "numbers."
        ),
        "question": "What do you do?",
        "options": [
            {
                "id": "a",
                "text": "Produce the model on schedule with clearly-flagged assumptions and caveats about your confidence level.",
                "signal": {"intellectualHonesty": 4, "ambiguityTolerance": 4, "analyticalRigor": 3},
            },
            {
                "id": "b",
                "text": "Tell the deal lead on day two that you need a two-day extension and why.",
                "signal": {"intellectualHonesty": 5, "ambiguityTolerance": 3, "writtenDissent": 3},
            },
            {
                "id": "c",
                "text": "Push through, build the best model you can, and present it as your best estimate.",
                "signal": {"intellectualHonesty": 2, "ambiguityTolerance": 2},
            },
            {
                "id": "d",
                "text": "Find two sector experts in the firm's network, burn a day on calls, then build the model with citations.",
                "signal": {"intellectualHonesty": 4, "ambiguityTolerance": 5, "analyticalRigor": 5, "lowEgoCollab": 4},
            },
        ],
    },
]


# ---------------------------------------------------------------------------
# SEED COMPANIES
# ---------------------------------------------------------------------------
SEED_COMPANIES = [
    {
        "id": "meridian-capital",
        "name": "Meridian Capital Partners",
        "tagline": "Mid-market private credit. Amsterdam + NYC.",
        "role": "Financial Analyst — Credit Underwriting",
        "artifact_values": (
            "We write checks on companies our competitors don't understand. "
            "Our edge is patience and homework, not speed. Analysts are expected "
            "to disagree with deal teams in writing, early, and often. We reward "
            "being right over being first. We do not reward hustle theatre."
        ),
        "artifact_role_spec": (
            "Build and defend underwriting models for mid-market credit deals "
            "($25M–$150M). Produce memos that hold up under IC scrutiny. Own "
            "your numbers end-to-end. Comfort with ambiguity and ability to say "
            "\"I don't know yet\" are prerequisites."
        ),
        "artifact_team_structure": (
            "Flat team of 11. Two MDs, three VPs, four associates, two analysts. "
            "No hierarchy in credit debates — the model is the argument. Weekly "
            "deal review is the forum; memos circulate 48h prior. Red team rotates."
        ),
        "artifact_sample_comms": (
            "[IC memo excerpt] \"Recommend PASS. Sponsor's thesis depends on "
            "180bps of margin expansion driven by procurement synergies that have "
            "not been realized in any of their last four platforms. I've modeled "
            "three scenarios — see Appendix C — and none clear our 15% unlevered "
            "IRR hurdle without aggressive assumptions. Happy to walk through the "
            "sensitivity at Thursday's review.\""
        ),
        "criteria": [
            {"key": "analyticalRigor",     "label": "Analytical Rigor",      "description": "Depth over speed; defends numbers",                 "weight": 0.25, "ordering": 0},
            {"key": "intellectualHonesty", "label": "Intellectual Honesty",  "description": "Comfortable saying 'I don't know'",                 "weight": 0.25, "ordering": 1},
            {"key": "writtenDissent",      "label": "Written Dissent",       "description": "Disagrees in writing, early, constructively",       "weight": 0.20, "ordering": 2},
            {"key": "ambiguityTolerance",  "label": "Ambiguity Tolerance",   "description": "Operates without clear playbooks",                  "weight": 0.15, "ordering": 3},
            {"key": "lowEgoCollab",        "label": "Low-Ego Collaboration", "description": "Model-as-argument, not status-as-argument",         "weight": 0.15, "ordering": 4},
        ],
    },
    {
        # Kestrel is authored for this build to contrast Meridian. Deliberately
        # inverts the value set — demo value is that the same candidate scores
        # differently against the two environments.
        "id": "kestrel-growth",
        "name": "Kestrel Growth Partners",
        "tagline": "Late-stage growth equity. London + Singapore.",
        "role": "Financial Analyst — Growth Equity",
        "artifact_values": (
            "Conviction at speed. We back founders three weeks before our "
            "competitors notice the category. Our edge is pattern recognition "
            "across hundreds of deals and the willingness to commit before "
            "every question is answered. We prize analysts who can form a "
            "point of view in 48 hours and defend it in a room. We do not "
            "reward excess caution."
        ),
        "artifact_role_spec": (
            "Source and evaluate growth-stage equity investments ($20M–$80M "
            "checks). Own the first-pass memo within one week of initial call. "
            "Build market-sizing and cohort models that inform — not delay — "
            "partner decisions. Strong verbal communication is non-negotiable; "
            "partners decide in meetings, not via email threads."
        ),
        "artifact_team_structure": (
            "Pod model. Each of the four partners runs a pod of one VP plus "
            "two analysts. Decisions are partner-led; analysts contribute the "
            "numbers and the story. Monday IC runs 90 minutes, three deals, "
            "decision by end of room. No red team. Dissent is welcome but "
            "expected to resolve in the meeting."
        ),
        "artifact_sample_comms": (
            "[Partner note on an analyst memo] \"Good instincts on the "
            "category. Skip Appendix B — the sensitivity table doesn't change "
            "the decision and we're out of time. Lead with the founder call "
            "notes and the growth loop diagram on Monday. If your gut says "
            "this is a top-quartile team, say that on slide one and defend it.\""
        ),
        "criteria": [
            {"key": "speedOfConviction",      "label": "Speed of Conviction",      "description": "Forms a defensible view quickly under incomplete information", "weight": 0.25, "ordering": 0},
            {"key": "patternRecognition",     "label": "Pattern Recognition",      "description": "Draws signal from comparable deals and market shape",           "weight": 0.20, "ordering": 1},
            {"key": "verbalAgility",          "label": "Verbal Agility",           "description": "Argues persuasively in live rooms, not only on paper",          "weight": 0.20, "ordering": 2},
            {"key": "commercialInstinct",     "label": "Commercial Instinct",      "description": "Reads founder quality and market pull, not only spreadsheets",  "weight": 0.20, "ordering": 3},
            {"key": "resilienceUnderPressure","label": "Resilience Under Pressure","description": "Works cleanly against short deadlines and public debate",       "weight": 0.15, "ordering": 4},
        ],
    },
]


# ---------------------------------------------------------------------------
# Loader — idempotent; safe to call on every boot.
# ---------------------------------------------------------------------------
def seed_companies(db: Session) -> None:
    for spec in SEED_COMPANIES:
        existing = db.get(models.Company, spec["id"])
        if existing is not None:
            # Keep existing rows untouched so manager edits aren't overwritten.
            continue

        company = models.Company(
            id=spec["id"],
            name=spec["name"],
            tagline=spec.get("tagline"),
            role=spec["role"],
            artifact_values=spec.get("artifact_values", ""),
            artifact_role_spec=spec.get("artifact_role_spec", ""),
            artifact_team_structure=spec.get("artifact_team_structure", ""),
            artifact_sample_comms=spec.get("artifact_sample_comms", ""),
        )
        for crit in spec.get("criteria", []):
            company.criteria.append(
                models.Criterion(
                    key=crit["key"],
                    label=crit["label"],
                    description=crit.get("description", ""),
                    weight=crit.get("weight", 0.0),
                    ordering=crit.get("ordering", 0),
                )
            )
        db.add(company)
    db.commit()
