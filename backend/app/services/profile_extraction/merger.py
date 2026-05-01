"""Merge CV / GitHub / portfolio extraction outputs into a VerifiedProfile shape.

Produces:
  * Public fields: experience, education, skills (with evidence), github_repos.
  * Internal scaffolding: capability_ledger, communication_ledger, voice_samples.

Skills are aggregated cross-source. Each skill carries an evidence array — no
level label, since inference is unreliable. The capability_ledger is the
internal projection used by the agent prompt: known vs exposure-only.
"""
from __future__ import annotations

import re
import statistics
from typing import Any


_HEDGE_WORDS = {
    "maybe", "perhaps", "possibly", "might", "could", "i think", "i guess",
    "kind of", "sort of", "probably", "likely", "i suppose",
}


def _tokens(text: str) -> list[str]:
    return [t for t in re.split(r"\s+", text.lower()) if t]


def _avg_sentence_length(text: str) -> float:
    if not text:
        return 0.0
    sentences = [s for s in re.split(r"[.!?]+", text) if s.strip()]
    if not sentences:
        return 0.0
    return statistics.mean(len(_tokens(s)) for s in sentences)


def _hedging_rate(text: str) -> float:
    if not text:
        return 0.0
    tokens = _tokens(text)
    if not tokens:
        return 0.0
    lowered = text.lower()
    hits = sum(lowered.count(h) for h in _HEDGE_WORDS)
    return round(hits / max(len(tokens), 1), 4)


def _normalize_skill(name: str) -> str:
    return name.strip().lower()


def _experience_year_span(experience: list[dict]) -> dict[str, float]:
    """Cheap heuristic: count distinct year tokens in start/end fields per role."""
    out: dict[str, float] = {}
    year_re = re.compile(r"(19|20)\d{2}")
    for exp in experience:
        years = set()
        for field in ("start", "end"):
            val = (exp.get(field) or "").strip()
            for m in year_re.findall(val):
                years.add(m)
        if years:
            out[exp.get("role", "")] = float(len(years))
    return out


def merge(
    *,
    cv_data: dict[str, Any],
    github_data: dict[str, Any],
    portfolio_data: dict[str, Any],
    intake_voice_samples: list[str] | None = None,
) -> dict[str, Any]:
    """Merge extraction results into a verified-profile dict.

    Inputs are tolerant of missing keys; defaults to empty containers.
    """
    cv_skills: list[str] = cv_data.get("skills") or []
    cv_experience: list[dict] = cv_data.get("experience") or []
    cv_education: list[dict] = cv_data.get("education") or []
    cv_voice: list[str] = cv_data.get("voice_samples") or []

    gh_repos: list[dict] = github_data.get("repos") or []
    gh_readmes: list[str] = github_data.get("readme_samples") or []

    pf_samples: list[str] = portfolio_data.get("prose_samples") or []

    intake_voice_samples = intake_voice_samples or []

    # ---------- skills ----------
    skill_map: dict[str, dict[str, Any]] = {}

    def _bump_skill(name: str, source: str, snippet: str = "") -> None:
        key = _normalize_skill(name)
        if not key:
            return
        entry = skill_map.setdefault(
            key,
            {"name": name.strip(), "evidence": [], "source_count": 0},
        )
        entry["evidence"].append({"source": source, "snippet": snippet[:240]})
        entry["source_count"] = len(entry["evidence"])

    for s in cv_skills:
        _bump_skill(s, "cv", s)
    for repo in gh_repos:
        lang = (repo.get("language") or "").strip()
        if lang:
            _bump_skill(lang, "github", f"{repo.get('name', '')} ({lang})")

    skills = sorted(
        skill_map.values(),
        key=lambda e: (-e["source_count"], e["name"].lower()),
    )

    # ---------- capability ledger (internal) ----------
    role_years = _experience_year_span(cv_experience)
    known: list[dict[str, Any]] = []
    exposure_only: list[str] = []

    cv_skill_keys = {_normalize_skill(s) for s in cv_skills}
    gh_lang_keys = {
        _normalize_skill(r.get("language", "")) for r in gh_repos if r.get("language")
    }

    for entry in skills:
        key = _normalize_skill(entry["name"])
        in_cv = key in cv_skill_keys
        in_github = key in gh_lang_keys
        if entry["source_count"] >= 2 or (in_github and entry["source_count"] >= 1):
            depth_evidence: list[str] = []
            if in_cv:
                depth_evidence.append("mentioned in CV")
            if in_github:
                gh_for_skill = [
                    r for r in gh_repos
                    if _normalize_skill(r.get("language", "")) == key
                ]
                if gh_for_skill:
                    depth_evidence.append(
                        f"used in {len(gh_for_skill)} github repo"
                        + ("s" if len(gh_for_skill) != 1 else "")
                    )
            known.append({"skill": entry["name"], "depth_evidence": depth_evidence})
        else:
            exposure_only.append(entry["name"])

    capability_ledger = {
        "known": known,
        "exposure_only": exposure_only,
        "role_year_span": role_years,
    }

    # ---------- voice samples ----------
    voice_samples: list[dict[str, str]] = []
    for v in intake_voice_samples:
        if v and v.strip():
            voice_samples.append({"source": "intake", "text": v.strip()[:1500]})
    for v in cv_voice:
        if v and v.strip():
            voice_samples.append({"source": "cv", "text": v.strip()[:1500]})
    for v in gh_readmes:
        if v and v.strip():
            voice_samples.append({"source": "github_readme", "text": v.strip()[:1500]})
    for v in pf_samples:
        if v and v.strip():
            voice_samples.append({"source": "portfolio", "text": v.strip()[:1500]})

    # ---------- communication ledger (internal) ----------
    all_prose = " ".join(s["text"] for s in voice_samples)
    communication_ledger = {
        "avg_sentence_length": round(_avg_sentence_length(all_prose), 2),
        "hedging_rate": _hedging_rate(all_prose),
        "voice_sample_count": len(voice_samples),
        "voice_sample_total_chars": len(all_prose),
    }

    # ---------- experience / education / repos passthrough ----------
    experience = [
        {
            "company": e.get("company", ""),
            "role": e.get("role", ""),
            "start": e.get("start", ""),
            "end": e.get("end", ""),
            "bullets": e.get("bullets", []),
            "source": "cv",
        }
        for e in cv_experience
    ]
    education = [
        {
            "institution": e.get("institution", ""),
            "degree": e.get("degree", ""),
            "field": e.get("field", ""),
            "start": e.get("start", ""),
            "end": e.get("end", ""),
        }
        for e in cv_education
    ]
    github_repos = [
        {
            "name": r.get("name", ""),
            "description": r.get("description", ""),
            "language": r.get("language", ""),
            "stars": r.get("stars", 0),
            "last_commit_at": r.get("last_commit_at", ""),
            "readme_excerpt": r.get("readme_excerpt", ""),
        }
        for r in gh_repos
    ]

    return {
        "experience": experience,
        "education": education,
        "skills": skills,
        "github_repos": github_repos,
        "capability_ledger": capability_ledger,
        "communication_ledger": communication_ledger,
        "voice_samples": voice_samples,
    }
