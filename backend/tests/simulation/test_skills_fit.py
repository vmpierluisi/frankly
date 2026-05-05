"""Unit tests for skills_fit.compute_skills_fit — Roadmap 2 / PR #2d.3."""
from __future__ import annotations

from app.services.simulation.skills_fit import compute_skills_fit


def test_returns_none_when_no_required_skills():
    out = compute_skills_fit([], {"known": [{"skill": "Python"}]})
    assert out is None


def test_returns_none_when_required_is_none():
    assert compute_skills_fit(None, {}) is None


def test_known_with_github_evidence_scores_100():
    required = [{"skill": "Go", "level": "mid"}]
    ledger = {"known": [{"skill": "Go", "depth_evidence": ["used in 3 github repos"]}]}
    out = compute_skills_fit(required, ledger)
    assert out["score"] == 100
    assert out["per_skill"][0]["coverage"] == "covered"


def test_known_without_github_scores_75():
    required = [{"skill": "Excel", "level": "mid"}]
    ledger = {"known": [{"skill": "Excel", "depth_evidence": ["mentioned in CV"]}]}
    out = compute_skills_fit(required, ledger)
    assert out["score"] == 75
    assert out["per_skill"][0]["coverage"] == "covered"


def test_exposure_only_scores_40():
    required = [{"skill": "Kubernetes", "level": "senior"}]
    ledger = {"known": [], "exposure_only": ["Kubernetes"]}
    out = compute_skills_fit(required, ledger)
    assert out["score"] == 40
    assert out["per_skill"][0]["coverage"] == "limited"


def test_absent_scores_0():
    required = [{"skill": "Rust", "level": "mid"}]
    ledger = {"known": [{"skill": "Python"}], "exposure_only": []}
    out = compute_skills_fit(required, ledger)
    assert out["score"] == 0
    assert out["per_skill"][0]["coverage"] == "absent"


def test_average_across_required_skills():
    required = [
        {"skill": "Go", "level": "mid"},
        {"skill": "Kubernetes", "level": "senior"},
        {"skill": "Rust", "level": "junior"},
    ]
    ledger = {
        "known": [{"skill": "Go", "depth_evidence": ["used in 2 github repos"]}],
        "exposure_only": ["Kubernetes"],
    }
    # 100 + 40 + 0 = 140 / 3 → 47 (rounded)
    out = compute_skills_fit(required, ledger)
    assert out["score"] == 47
    assert out["n_required"] == 3
    coverages = [r["coverage"] for r in out["per_skill"]]
    assert coverages == ["covered", "limited", "absent"]


def test_handles_missing_capability_ledger():
    required = [{"skill": "Anything"}]
    out = compute_skills_fit(required, None)
    assert out["score"] == 0
    assert out["per_skill"][0]["coverage"] == "absent"


def test_skill_matching_is_case_insensitive():
    required = [{"skill": "PYTHON", "level": "mid"}]
    ledger = {"known": [{"skill": "python", "depth_evidence": ["github 5 repos"]}]}
    out = compute_skills_fit(required, ledger)
    assert out["score"] == 100
