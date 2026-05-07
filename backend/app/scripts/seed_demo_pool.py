"""Seed a 10-candidate demo pool with full VerifiedProfile rows.

Built for showcasing Roadmap 2 features — the candidates here are crafted
to exercise the new persona-faithful agent prompt (capability ledgers,
voice samples), the skills-vs-behaviour dual score, and the FitProfile v3
Background section.

What it does:
  1. Wipes existing is_seed=True candidates (and their cascades).
  2. Inserts 10 deterministic, internally consistent candidates spanning
     a realistic distribution of seniority + skill strength against
     financial-analyst vacancies.
  3. Each candidate gets a VerifiedProfile (skills, education, experience,
     github_repos, capability_ledger, communication_ledger, voice_samples).
  4. Optional: also sets ``required_skills`` on the seeded companies so
     the skills_fit score has something to compare against.

Usage:
    docker compose exec backend python -m app.scripts.seed_demo_pool
    docker compose exec backend python -m app.scripts.seed_demo_pool --add-required-skills

After seeding, run:
    docker compose exec backend python -m app.scripts.preseed_matches \\
        --per-company 10 --company meridian-capital --fast
"""
from __future__ import annotations

import argparse
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

try:
    from dotenv import load_dotenv
    _here = os.path.dirname(os.path.abspath(__file__))
    for _p in [
        os.path.join(_here, "../../.env"),
        os.path.join(_here, "../../../.env"),
    ]:
        if os.path.exists(_p):
            load_dotenv(_p)
            break
except ImportError:
    pass

from app.db import SessionLocal
from app import models
from app.services.persona import synthesize_persona


# ---------------------------------------------------------------------------
# Hand-crafted demo candidates.
#
# The skill-strength column is a hint — "strong" candidates have more
# capability_ledger entries with confidence >0.7 against typical
# financial-analyst skills (modeling, accounting, valuation). "weak"
# candidates have shallow ledgers so the skill-gap briefing kicks in
# during simulation.
# ---------------------------------------------------------------------------
DEMO_CANDIDATES = [
    # --- Strong analysts ----------------------------------------------------
    dict(
        display_name="Sofia Reyes",
        target_seniority="senior",
        skill_strength="strong",
        bfi=dict(e1=4, a1=4, c1=1, n1=4, o1=2, e2=2, a2=2, c2=5, n2=2, o2=4),
        sjt=dict(sjt1="a", sjt2="a", sjt3="d"),
        education=[
            dict(institution="London Business School", degree="MBA", field="Finance", start="2017", end="2019"),
            dict(institution="Imperial College London", degree="BSc", field="Mathematics", start="2010", end="2013"),
        ],
        experience=[
            dict(role="Senior Credit Analyst", company="Apollo Global Management", start="2019", end="present", bullets=[
                "Underwrote $4B in mid-market private credit across 18 deals; zero defaults to date.",
                "Built the team's three-statement model template now used by all four pods.",
                "Led monthly portfolio review cadence, flagging stress concentrations to risk committee.",
            ]),
            dict(role="Credit Analyst", company="Goldman Sachs", start="2013", end="2017", bullets=[
                "Modeled debt structures for leveraged buyouts ranging from $200M to $1.2B.",
                "Co-authored the 2016 healthcare-credit primer cited by ~30 internal teams.",
            ]),
        ],
        skills=["financial modeling", "credit analysis", "leveraged finance", "Python", "SQL", "Excel", "memo writing"],
        github_repos=[
            dict(name="leverage-tools", language="Python", description="LBO modeling helpers + sensitivity sweeps."),
        ],
        voice_samples=[
            "The IRR delta is sensitive to a 50bps rate move; flagging this in the memo before circulation.",
            "Pass on this one — coverage ratios collapse below hurdle in three of four downside scenarios.",
        ],
        github_url="https://github.com/sofia-reyes",
        linkedin_url="https://linkedin.com/in/sofia-reyes",
        portfolio_url=None,
    ),
    dict(
        display_name="Jordan Park",
        target_seniority="senior",
        skill_strength="strong",
        bfi=dict(e1=3, a1=4, c1=1, n1=3, o1=2, e2=3, a2=2, c2=5, n2=2, o2=5),
        sjt=dict(sjt1="a", sjt2="c", sjt3="d"),
        education=[
            dict(institution="University of Chicago Booth", degree="MBA", field="Finance + Statistics", start="2018", end="2020"),
            dict(institution="UCLA", degree="BA", field="Economics", start="2010", end="2014"),
        ],
        experience=[
            dict(role="Investment Associate", company="KKR", start="2020", end="present", bullets=[
                "Owned diligence on three platform investments, two completed.",
                "Reframed the team's sensitivity-analysis convention; saved ~3 days per memo cycle.",
            ]),
        ],
        skills=["valuation", "financial modeling", "due diligence", "Python", "tableau", "memo writing"],
        github_repos=[
            dict(name="dcf-toolkit", language="Python", description="DCF + comparables tooling, used internally."),
        ],
        voice_samples=[
            "Three things still bother me about this thesis. I'd push back before we sign.",
            "Tagging the synergy assumption as 'low confidence' in the model — won't paper over that.",
        ],
        github_url="https://github.com/jordan-park",
        linkedin_url="https://linkedin.com/in/jordan-park",
        portfolio_url=None,
    ),
    # --- Mid analysts -------------------------------------------------------
    dict(
        display_name="Amara Okonkwo",
        target_seniority="mid",
        skill_strength="strong",
        bfi=dict(e1=4, a1=5, c1=1, n1=4, o1=2, e2=2, a2=3, c2=5, n2=2, o2=3),
        sjt=dict(sjt1="a", sjt2="b", sjt3="d"),
        education=[
            dict(institution="Wharton", degree="BS", field="Finance", start="2016", end="2020"),
        ],
        experience=[
            dict(role="Credit Analyst", company="Blackstone", start="2020", end="present", bullets=[
                "Modeling lead on $850M direct-lending pipeline.",
                "Maintains the desk's covenant-tracker — flagged two early-warning breaches in 2024.",
            ]),
        ],
        skills=["financial modeling", "credit analysis", "covenant analysis", "Excel", "SQL", "memo writing"],
        github_repos=[],
        voice_samples=[
            "I've recut the model with the new debt schedule. Coverage drops to 1.4x — below our floor.",
        ],
        github_url=None,
        linkedin_url="https://linkedin.com/in/amara-okonkwo",
        portfolio_url="https://amaraokonkwo.com",
    ),
    dict(
        display_name="Theodora Volkov",
        target_seniority="mid",
        skill_strength="medium",
        bfi=dict(e1=4, a1=3, c1=2, n1=3, o1=3, e2=2, a2=3, c2=4, n2=3, o2=4),
        sjt=dict(sjt1="b", sjt2="b", sjt3="b"),
        education=[
            dict(institution="Bocconi University", degree="MSc", field="Finance", start="2018", end="2020"),
            dict(institution="Bocconi University", degree="BSc", field="Economics", start="2014", end="2018"),
        ],
        experience=[
            dict(role="Investment Analyst", company="EQT Partners", start="2020", end="present", bullets=[
                "Supports diligence across three sectors — mostly industrials and consumer.",
                "Built sector tear-sheet template for the EU mid-market team.",
            ]),
        ],
        skills=["financial modeling", "Excel", "Italian", "English", "valuation"],
        github_repos=[],
        voice_samples=[
            "Could we double-check the working-capital walk before the IC? Something feels off.",
        ],
        github_url=None,
        linkedin_url="https://linkedin.com/in/theodora-volkov",
        portfolio_url=None,
    ),
    dict(
        display_name="Kenji Tanaka",
        target_seniority="mid",
        skill_strength="strong",
        bfi=dict(e1=5, a1=4, c1=1, n1=4, o1=1, e2=1, a2=2, c2=5, n2=2, o2=5),
        sjt=dict(sjt1="a", sjt2="a", sjt3="d"),
        education=[
            dict(institution="University of Tokyo", degree="BA", field="Economics + CS minor", start="2014", end="2018"),
        ],
        experience=[
            dict(role="Quant Analyst", company="Two Sigma", start="2018", end="2022", bullets=[
                "Built credit factor model used by the systematic team.",
                "Open-sourced parts of the data-cleaning pipeline; ~2k stars.",
            ]),
            dict(role="Credit Analyst", company="Carlyle", start="2022", end="present", bullets=[
                "Translates quant signals into discretionary deal recommendations.",
            ]),
        ],
        skills=["Python", "SQL", "financial modeling", "credit analysis", "machine learning", "data engineering"],
        github_repos=[
            dict(name="credit-factor-toy", language="Python", description="Open-source credit factor research."),
            dict(name="rate-curves", language="Python", description="Yield-curve interpolation utilities."),
        ],
        voice_samples=[
            "The factor loading is unstable on the recent vintages — I'd discount the signal until we resample.",
        ],
        github_url="https://github.com/kenji-tanaka",
        linkedin_url="https://linkedin.com/in/kenji-tanaka",
        portfolio_url="https://kenjitanaka.dev",
    ),
    # --- Junior analysts -----------------------------------------------------
    dict(
        display_name="Priya Iyer",
        target_seniority="junior",
        skill_strength="medium",
        bfi=dict(e1=4, a1=4, c1=2, n1=3, o1=2, e2=2, a2=3, c2=4, n2=3, o2=4),
        sjt=dict(sjt1="a", sjt2="b", sjt3="d"),
        education=[
            dict(institution="UC Berkeley Haas", degree="BS", field="Business + Economics", start="2020", end="2024"),
        ],
        experience=[
            dict(role="Analyst Intern", company="Lazard", start="2023", end="2023", bullets=[
                "Modeling support on two M&A processes; built the comparable-companies set.",
            ]),
            dict(role="Analyst", company="Houlihan Lokey", start="2024", end="present", bullets=[
                "Builds DCFs and accretion/dilution templates; learning the desk conventions.",
            ]),
        ],
        skills=["Excel", "PowerPoint", "financial modeling", "valuation"],
        github_repos=[],
        voice_samples=[
            "Made the changes you flagged — let me know if the EBITDA bridge looks right now.",
        ],
        github_url=None,
        linkedin_url="https://linkedin.com/in/priya-iyer",
        portfolio_url=None,
    ),
    dict(
        display_name="Marcus Bell",
        target_seniority="junior",
        skill_strength="weak",
        bfi=dict(e1=2, a1=4, c1=2, n1=2, o1=3, e2=4, a2=4, c2=3, n2=4, o2=3),
        sjt=dict(sjt1="d", sjt2="d", sjt3="b"),
        education=[
            dict(institution="University of Michigan Ross", degree="BBA", field="Finance", start="2020", end="2024"),
        ],
        experience=[
            dict(role="Summer Analyst", company="Bank of America", start="2023", end="2023", bullets=[
                "Rotated across coverage groups; mostly industry primer work.",
            ]),
        ],
        skills=["Excel", "PowerPoint", "communication"],
        github_repos=[],
        voice_samples=[
            "Hey, just wanted to flag — I'm a bit out of my depth on the LBO mechanics. Could we walk through it together?",
        ],
        github_url=None,
        linkedin_url="https://linkedin.com/in/marcus-bell",
        portfolio_url=None,
    ),
    # --- Lead analysts ------------------------------------------------------
    dict(
        display_name="Ines Rivera",
        target_seniority="lead",
        skill_strength="strong",
        bfi=dict(e1=2, a1=4, c1=1, n1=4, o1=2, e2=4, a2=2, c2=5, n2=2, o2=4),
        sjt=dict(sjt1="a", sjt2="a", sjt3="d"),
        education=[
            dict(institution="Harvard Business School", degree="MBA", field="Finance", start="2009", end="2011"),
            dict(institution="Stanford", degree="BA", field="Economics", start="2002", end="2006"),
        ],
        experience=[
            dict(role="Principal", company="Bain Capital Credit", start="2017", end="present", bullets=[
                "Leads underwriting for the European special-situations book.",
                "Mentored four analysts to associate; two now run their own deals.",
            ]),
            dict(role="VP", company="Oaktree", start="2011", end="2017", bullets=[
                "Owned the European distressed energy book during the 2015-2016 oil cycle.",
            ]),
        ],
        skills=["financial modeling", "credit analysis", "leveraged finance", "team leadership", "Spanish", "memo writing"],
        github_repos=[],
        voice_samples=[
            "I want a one-page case-against memo before this hits IC. If we can't argue the pass, the buy is fragile.",
            "Slow down — coverage at the assumed margin doesn't survive a recession base case.",
        ],
        github_url=None,
        linkedin_url="https://linkedin.com/in/ines-rivera",
        portfolio_url=None,
    ),
    # --- Wildcard / weak ----------------------------------------------------
    dict(
        display_name="Rohan Mehta",
        target_seniority="mid",
        skill_strength="weak",
        bfi=dict(e1=2, a1=3, c1=3, n1=2, o1=4, e2=4, a2=4, c2=3, n2=4, o2=2),
        sjt=dict(sjt1="c", sjt2="d", sjt3="c"),
        education=[
            dict(institution="University of Manchester", degree="BSc", field="Marketing", start="2014", end="2018"),
        ],
        experience=[
            dict(role="Sales Associate", company="Stripe", start="2018", end="2023", bullets=[
                "Mid-market account exec; consistently 110-130% of quota.",
            ]),
            dict(role="Independent Consultant", company="Self", start="2023", end="present", bullets=[
                "Pivoting toward finance — taking the CFA L1 in 2025.",
            ]),
        ],
        skills=["sales", "communication", "stakeholder management", "Excel"],
        github_repos=[],
        voice_samples=[
            "I think the upside is bigger than your downside — I'd push the deal.",
        ],
        github_url=None,
        linkedin_url="https://linkedin.com/in/rohan-mehta",
        portfolio_url=None,
    ),
    dict(
        display_name="Eve Lindqvist",
        target_seniority="senior",
        skill_strength="medium",
        bfi=dict(e1=4, a1=3, c1=2, n1=3, o1=2, e2=2, a2=2, c2=4, n2=3, o2=5),
        sjt=dict(sjt1="b", sjt2="c", sjt3="a"),
        education=[
            dict(institution="Stockholm School of Economics", degree="MSc", field="Finance", start="2014", end="2016"),
        ],
        experience=[
            dict(role="Senior Analyst", company="Nordic Capital", start="2018", end="present", bullets=[
                "Cross-border deal experience across Nordics + DACH.",
                "Built the team's deal-tracking dashboard in Tableau.",
            ]),
            dict(role="Analyst", company="EY", start="2016", end="2018", bullets=[
                "Transaction services — quality of earnings work.",
            ]),
        ],
        skills=["financial modeling", "valuation", "Tableau", "Swedish", "German", "English"],
        github_repos=[],
        voice_samples=[
            "Quality-of-earnings adjustments wipe out about 15% of reported EBITDA. Updating the cover sheet.",
        ],
        github_url=None,
        linkedin_url="https://linkedin.com/in/eve-lindqvist",
        portfolio_url=None,
    ),
]


# Skill strength → capability_ledger templates.
#
# Canonical capability_ledger shape (consumed by skills_fit.compute_skills_fit
# and the agent prompt's behavioral contract):
#
#   {
#     "known": [{"skill": str, "depth_evidence": [str, ...]}, ...],
#     "exposure_only": [str, ...],
#   }
#
# `depth_evidence` is a list of provenance strings ("CV: 2 roles",
# "GitHub: <repo>"). Any string containing "github" upgrades the skill
# score from 75 → 100 in compute_skills_fit.
_LEDGER_BY_STRENGTH = {
    "strong": {
        "known": [
            {"skill": "financial modeling", "depth_evidence": ["CV: 2 roles", "GitHub: leverage-tools"]},
            {"skill": "credit analysis", "depth_evidence": ["CV: 6+ years"]},
            {"skill": "valuation", "depth_evidence": ["CV: DCF/comparables across 18 deals"]},
            {"skill": "memo writing", "depth_evidence": ["CV: IC memos owned end-to-end"]},
            {"skill": "Python", "depth_evidence": ["GitHub: dcf-toolkit"]},
            {"skill": "SQL", "depth_evidence": ["CV: queries production data"]},
        ],
        "exposure_only": ["Tableau", "machine learning"],
    },
    "medium": {
        "known": [
            {"skill": "financial modeling", "depth_evidence": ["CV: 2 roles"]},
            {"skill": "Excel", "depth_evidence": ["CV: daily use"]},
            {"skill": "valuation", "depth_evidence": ["CV: DCF on M&A deals"]},
        ],
        "exposure_only": ["Python", "SQL", "Tableau"],
    },
    "weak": {
        "known": [
            {"skill": "Excel", "depth_evidence": ["CV: daily use"]},
            {"skill": "communication", "depth_evidence": ["CV: customer-facing role"]},
        ],
        "exposure_only": ["financial modeling"],
    },
}

_DEFAULT_COMM_LEDGER = {
    "verbosity": 0.55,
    "formality": 0.65,
    "directness": 0.6,
    "tech_jargon": 0.5,
    "uses_examples": True,
}


def _profile_accuracy_for(strength: str) -> int:
    return {"strong": 78, "medium": 64, "weak": 48}.get(strength, 50)


def _build_candidate(spec: dict) -> tuple[models.Candidate, models.VerifiedProfile]:
    persona = synthesize_persona(spec["bfi"], spec["sjt"])
    candidate = models.Candidate(
        display_name=spec["display_name"],
        bfi_responses=spec["bfi"],
        sjt_responses=spec["sjt"],
        cached_big_five=persona["bigFive"],
        cached_sjt_signals=persona["sjtSignals"],
        cached_inconsistencies=persona["inconsistencies"],
        cached_narrative=persona["narrative"],
        assessment_status="completed",
        is_seed=True,
        target_role_family="financial_analyst",
        target_seniority=spec["target_seniority"],
        linkedin_url=spec.get("linkedin_url"),
        github_url=spec.get("github_url"),
        portfolio_url=spec.get("portfolio_url"),
        profile_accuracy_score=_profile_accuracy_for(spec["skill_strength"]),
    )
    profile = models.VerifiedProfile(
        education=spec["education"],
        experience=spec["experience"],
        skills=[{"name": s} for s in spec["skills"]],
        github_repos=spec["github_repos"],
        capability_ledger=_LEDGER_BY_STRENGTH[spec["skill_strength"]],
        communication_ledger=_DEFAULT_COMM_LEDGER,
        # Canonical voice_sample shape: {"text": str, "source": str}.
        voice_samples=[
            {"text": s, "source": "seed"} for s in spec["voice_samples"]
        ],
        edited_fields=[],
        source_versions={"seed_demo_pool": "1"},
    )
    candidate.verified_profile = profile
    return candidate, profile


# ---------------------------------------------------------------------------
# Optional: set required_skills + skill_match_weight on seeded companies.
# ---------------------------------------------------------------------------
COMPANY_REQUIRED_SKILLS = {
    "meridian-capital": [
        {"skill": "financial modeling", "level": "senior"},
        {"skill": "credit analysis", "level": "mid"},
        {"skill": "memo writing", "level": "mid"},
        {"skill": "valuation", "level": "mid"},
        {"skill": "Python", "level": "junior"},
    ],
    "kestrel-growth": [
        {"skill": "financial modeling", "level": "senior"},
        {"skill": "valuation", "level": "senior"},
        {"skill": "memo writing", "level": "senior"},
        {"skill": "Python", "level": "mid"},
        {"skill": "SQL", "level": "mid"},
    ],
}


def _set_required_skills(db) -> None:
    for position_id, skills in COMPANY_REQUIRED_SKILLS.items():
        company = db.get(models.Position, position_id)
        if company is None:
            continue
        company.required_skills = skills
    db.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed a 10-candidate demo pool with VerifiedProfiles.")
    parser.add_argument(
        "--add-required-skills",
        action="store_true",
        help="Also set required_skills on seeded companies so skills_fit has signal.",
    )
    parser.add_argument(
        "--keep-existing",
        action="store_true",
        help="Don't wipe existing seed candidates first.",
    )
    args = parser.parse_args()

    random.seed(42)

    with SessionLocal() as db:
        if not args.keep_existing:
            n = db.query(models.Candidate).filter(models.Candidate.is_seed == True).delete()
            db.commit()
            print(f"Deleted {n} existing seed candidates (and their cascades).")

        for spec in DEMO_CANDIDATES:
            candidate, _profile = _build_candidate(spec)
            db.add(candidate)
        db.commit()
        print(f"Inserted {len(DEMO_CANDIDATES)} demo candidates with VerifiedProfile rows.")

        if args.add_required_skills:
            _set_required_skills(db)
            print(
                "Set required_skills on companies: "
                + ", ".join(COMPANY_REQUIRED_SKILLS.keys())
            )

    print()
    print("Next: trigger matches for one company.")
    print("  docker compose exec backend python -m app.scripts.preseed_matches \\")
    print("      --per-company 10 --company meridian-capital --fast")


if __name__ == "__main__":
    main()
