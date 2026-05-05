"""Skill-fit scoring — Roadmap 2 / PR #2d.3.

Compares a position's ``required_skills`` against the candidate's
``capability_ledger`` (extracted by the verified-profile pipeline) and
produces a 0..100 score that's reported alongside ``behaviour_fit`` in
the FitProfile.

Scoring rubric (per required skill):

  required_level → candidate coverage           → score
  ───────────────────────────────────────────────────────
  any            → known + has GitHub depth     → 100
  any            → known (CV/skills only)       →  75
  any            → exposure_only                →  40
  any            → not in ledger                →   0

The seniority part of ``required_level`` (junior/mid/senior) is
informational for the agent's gap briefing; we don't currently grade
"known but at the wrong level" because the capability ledger doesn't
expose level. PR #2d.4 can refine if we add a level signal.

Returns ``None`` when no required_skills are configured — the caller
treats this as "skills_fit unavailable; use behaviour_fit alone".
"""
from __future__ import annotations

from typing import Any


def _normalise(s: str) -> str:
    return (s or "").strip().lower()


def _index_ledger(capability_ledger: dict | None) -> tuple[dict[str, dict], set[str]]:
    """Returns ({normalised_skill: known_entry}, {exposure_only set})."""
    ledger = capability_ledger or {}
    known_by_key: dict[str, dict] = {}
    for entry in ledger.get("known") or []:
        skill = _normalise(entry.get("skill", ""))
        if skill:
            known_by_key[skill] = entry
    exposure_set = {_normalise(s) for s in (ledger.get("exposure_only") or []) if s}
    return known_by_key, exposure_set


def _score_one(required_skill: str, known_by_key: dict, exposure_set: set[str]) -> int:
    key = _normalise(required_skill)
    if not key:
        return 0
    if key in known_by_key:
        evidence = known_by_key[key].get("depth_evidence") or []
        has_github = any("github" in (e or "").lower() for e in evidence)
        return 100 if has_github else 75
    if key in exposure_set:
        return 40
    return 0


def compute_skills_fit(
    required_skills: list[dict[str, Any]] | None,
    capability_ledger: dict | None,
) -> dict[str, Any] | None:
    """Compute a skills-fit summary for one (position, candidate) pair.

    Returns None when required_skills is empty — caller should fall back to
    behaviour-only scoring. Otherwise returns:

        {
          "score": 0..100,                # average of per-skill scores
          "n_required": int,
          "per_skill": [
            {"skill": str, "level": str, "score": 0..100,
             "coverage": "covered" | "limited" | "absent"}
          ],
        }
    """
    required = required_skills or []
    if not required:
        return None

    known_by_key, exposure_set = _index_ledger(capability_ledger)

    per_skill: list[dict[str, Any]] = []
    total = 0
    for entry in required:
        skill = entry.get("skill", "")
        level = entry.get("level", "mid")
        score = _score_one(skill, known_by_key, exposure_set)
        coverage = "covered" if score >= 75 else "limited" if score >= 40 else "absent"
        per_skill.append(
            {
                "skill": skill,
                "level": level,
                "score": score,
                "coverage": coverage,
            }
        )
        total += score

    avg = round(total / max(1, len(per_skill)))
    return {"score": avg, "n_required": len(per_skill), "per_skill": per_skill}
