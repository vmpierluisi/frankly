"""Tests for the profile extraction pipeline (Phase 1).

Covers:
  * cv_parser returns the expected shape from a fixture CV (LLM mocked).
  * github_fetcher username parsing.
  * portfolio_fetcher rejects private/loopback URLs (SSRF guard).
  * merger aggregates skills cross-source and builds capability ledger.
  * POST /candidates/me/profile/extract writes a row, idempotent on re-run.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models
from app.auth import CurrentUser, require_candidate
from app.db import Base, get_session
from app.main import app as fastapi_app
from app.services.profile_extraction.cv_parser import extract_from_cv
from app.services.profile_extraction.github_fetcher import _parse_username
from app.services.profile_extraction.merger import merge
from app.services.profile_extraction.portfolio_fetcher import (
    UnsafeUrlError,
    _validate_url,
)
from app.services.simulation.cost_tracker import CostBudget


# ---------------------------------------------------------------------------
# CV parser
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cv_parser_returns_expected_shape():
    canned = {
        "education": [
            {"institution": "MIT", "degree": "BSc", "field": "CS",
             "start": "2018", "end": "2022"},
        ],
        "experience": [
            {"company": "Acme", "role": "Engineer", "start": "2022", "end": "2024",
             "bullets": ["Built X", "Shipped Y"]},
        ],
        "skills": ["Python", "Postgres"],
        "voice_samples": ["I led the redesign of the ingestion pipeline."],
    }
    with patch(
        "app.services.profile_extraction.cv_parser.tracked_chat_json",
        new=AsyncMock(return_value=canned),
    ):
        budget = CostBudget(ceiling_usd=1.0)
        out = await extract_from_cv("Some CV text\nwith content.", budget=budget)
    assert out["skills"] == ["Python", "Postgres"]
    assert out["experience"][0]["company"] == "Acme"
    assert out["voice_samples"]


@pytest.mark.asyncio
async def test_cv_parser_skips_when_empty():
    out = await extract_from_cv("", budget=CostBudget(ceiling_usd=1.0))
    assert out == {"education": [], "experience": [], "skills": [], "voice_samples": []}

    out2 = await extract_from_cv("(none provided)", budget=CostBudget(ceiling_usd=1.0))
    assert out2["skills"] == []


# ---------------------------------------------------------------------------
# Github fetcher — username parsing only (network call is mocked elsewhere)
# ---------------------------------------------------------------------------

def test_github_username_parser():
    assert _parse_username("https://github.com/octocat") == "octocat"
    assert _parse_username("github.com/octocat/") == "octocat"
    assert _parse_username("octocat") == "octocat"
    assert _parse_username("https://github.com/octocat/repo") == "octocat"
    assert _parse_username("") is None
    assert _parse_username("https://gitlab.com/octocat") is None


# ---------------------------------------------------------------------------
# Portfolio fetcher SSRF guard
# ---------------------------------------------------------------------------

def test_portfolio_rejects_private_ips():
    with pytest.raises(UnsafeUrlError):
        _validate_url("https://127.0.0.1/")
    with pytest.raises(UnsafeUrlError):
        _validate_url("https://10.0.0.1/")
    with pytest.raises(UnsafeUrlError):
        _validate_url("https://192.168.1.1/")
    with pytest.raises(UnsafeUrlError):
        _validate_url("https://169.254.169.254/")  # AWS metadata


def test_portfolio_rejects_non_https():
    with pytest.raises(UnsafeUrlError):
        _validate_url("http://example.com")
    with pytest.raises(UnsafeUrlError):
        _validate_url("file:///etc/passwd")


def test_portfolio_accepts_public_https():
    # Use a domain that resolves; this is just a static-validation check.
    out = _validate_url("https://example.com/")
    assert out.startswith("https://")


# ---------------------------------------------------------------------------
# Merger
# ---------------------------------------------------------------------------

def test_merger_aggregates_skills_cross_source():
    cv_data = {
        "education": [],
        "experience": [
            {"company": "Acme", "role": "Eng", "start": "2020", "end": "2024",
             "bullets": ["Wrote Python services"]},
        ],
        "skills": ["Python", "SQL"],
        "voice_samples": ["I prefer terse commit messages."],
    }
    github_data = {
        "repos": [
            {"name": "a", "language": "Python", "stars": 5, "last_commit_at": "2025-01-01"},
            {"name": "b", "language": "Python", "stars": 1, "last_commit_at": "2024-09-01"},
            {"name": "c", "language": "Go", "stars": 10, "last_commit_at": "2024-06-01"},
        ],
        "readme_samples": ["This repo implements a small consensus protocol in Go."],
    }
    portfolio_data = {"prose_samples": [], "pages_fetched": 0, "root": None}

    out = merge(
        cv_data=cv_data,
        github_data=github_data,
        portfolio_data=portfolio_data,
        intake_voice_samples=[],
    )

    skills_by_name = {s["name"].lower(): s for s in out["skills"]}
    assert "python" in skills_by_name
    assert skills_by_name["python"]["source_count"] >= 2
    assert any(e["source"] == "cv" for e in skills_by_name["python"]["evidence"])
    assert any(e["source"] == "github" for e in skills_by_name["python"]["evidence"])

    known_names = {k["skill"].lower() for k in out["capability_ledger"]["known"]}
    assert "python" in known_names
    assert out["voice_samples"], "expected voice samples merged in"
    assert out["communication_ledger"]["voice_sample_count"] == len(out["voice_samples"])


def test_merger_handles_empty_inputs():
    out = merge(
        cv_data={},
        github_data={},
        portfolio_data={},
        intake_voice_samples=None,
    )
    assert out["skills"] == []
    assert out["experience"] == []
    assert out["capability_ledger"]["known"] == []
    assert out["voice_samples"] == []


# ---------------------------------------------------------------------------
# Endpoint integration
# ---------------------------------------------------------------------------

def _make_engine_and_tables():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    return engine


@pytest.fixture()
def db_session():
    engine = _make_engine_and_tables()
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture()
def client(db_session):
    def _override_session():
        try:
            yield db_session
        finally:
            pass

    _TEST_USER = CurrentUser(
        auth_user_id="test-extract-001",
        email="extract@example.com",
        role="candidate",
    )

    def _override_candidate():
        return _TEST_USER

    fastapi_app.dependency_overrides[get_session] = _override_session
    fastapi_app.dependency_overrides[require_candidate] = _override_candidate

    with TestClient(fastapi_app, raise_server_exceptions=True) as c:
        yield c

    fastapi_app.dependency_overrides.clear()


def _seed_candidate(db_session) -> models.Candidate:
    c = models.Candidate(
        auth_user_id="test-extract-001",
        email="extract@example.com",
        display_name="Test",
        bfi_responses={},
        sjt_responses={},
        assessment_status="completed",
    )
    db_session.add(c)
    db_session.commit()
    db_session.refresh(c)
    return c


def test_extract_endpoint_writes_and_is_idempotent(client, db_session):
    _seed_candidate(db_session)

    fake_merged = {
        "experience": [{"company": "X", "role": "Y", "start": "", "end": "",
                        "bullets": ["b"], "source": "cv"}],
        "education": [],
        "skills": [{"name": "Python", "evidence": [{"source": "cv", "snippet": "Python"}],
                    "source_count": 1}],
        "github_repos": [],
        "capability_ledger": {"known": [], "exposure_only": ["Python"], "role_year_span": {}},
        "communication_ledger": {"avg_sentence_length": 0, "hedging_rate": 0,
                                 "voice_sample_count": 0, "voice_sample_total_chars": 0},
        "voice_samples": [],
        "source_versions": {"cv_hash": "abc", "github_fetched_at": None,
                            "github_username": None, "portfolio_fetched_at": None,
                            "portfolio_pages": 0},
    }

    with patch(
        "app.routes.candidates.extract_profile",
        new=AsyncMock(return_value=fake_merged),
    ):
        r1 = client.post("/candidates/me/profile/extract")
        assert r1.status_code == 200, r1.text
        body1 = r1.json()
        assert body1["candidate_id"]
        assert body1["skills"][0]["name"] == "Python"
        # Internal scaffolding must not leak to the response.
        assert "capability_ledger" not in body1
        assert "voice_samples" not in body1

        r2 = client.post("/candidates/me/profile/extract")
        assert r2.status_code == 200

    rows = db_session.query(models.VerifiedProfile).all()
    assert len(rows) == 1, "extract must be idempotent — single row per candidate"
