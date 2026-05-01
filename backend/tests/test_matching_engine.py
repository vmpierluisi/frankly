"""Tests for matching_engine: compatible_seniorities + find_open_companies."""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app import models
from app.lib.role_families import compatible_seniorities
from app.services.matching_engine import (
    find_open_companies_for_candidate,
    enqueue_matches_for_candidate,
)


# ---------------------------------------------------------------------------
# compatible_seniorities
# ---------------------------------------------------------------------------

def test_compatible_junior():
    assert compatible_seniorities("junior") == {"junior", "mid"}


def test_compatible_mid():
    assert compatible_seniorities("mid") == {"junior", "mid", "senior"}


def test_compatible_senior():
    assert compatible_seniorities("senior") == {"mid", "senior", "lead"}


def test_compatible_lead():
    assert compatible_seniorities("lead") == {"senior", "lead"}


def test_compatible_unknown():
    assert compatible_seniorities("intern") == set()


# ---------------------------------------------------------------------------
# DB fixture
# ---------------------------------------------------------------------------

@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def _make_company(db, company_id, role_family, target_seniority, is_open=True):
    c = models.Company(
        id=company_id,
        name=company_id,
        role="Analyst",
        role_family=role_family,
        target_seniority=target_seniority,
        is_open=is_open,
    )
    db.add(c)
    db.flush()
    return c


def _make_candidate(db, target_role_family, target_seniority):
    c = models.Candidate(
        target_role_family=target_role_family,
        target_seniority=target_seniority,
        assessment_status="completed",
        bfi_responses={},
        sjt_responses={},
    )
    db.add(c)
    db.flush()
    return c


# ---------------------------------------------------------------------------
# find_open_companies_for_candidate
# ---------------------------------------------------------------------------

def test_finds_matching_company(db):
    _make_company(db, "meridian", "financial_analyst", "mid")
    candidate = _make_candidate(db, "financial_analyst", "mid")
    companies = find_open_companies_for_candidate(db, candidate)
    assert len(companies) == 1
    assert companies[0].id == "meridian"


def test_adjacency_mid_matches_senior_company(db):
    _make_company(db, "kestrel", "financial_analyst", "senior")
    candidate = _make_candidate(db, "financial_analyst", "mid")
    companies = find_open_companies_for_candidate(db, candidate)
    assert len(companies) == 1


def test_adjacency_junior_does_not_match_senior(db):
    _make_company(db, "senior-co", "financial_analyst", "senior")
    candidate = _make_candidate(db, "financial_analyst", "junior")
    assert find_open_companies_for_candidate(db, candidate) == []


def test_closed_company_excluded(db):
    _make_company(db, "closed-co", "financial_analyst", "mid", is_open=False)
    candidate = _make_candidate(db, "financial_analyst", "mid")
    assert find_open_companies_for_candidate(db, candidate) == []


def test_wrong_role_family_excluded(db):
    _make_company(db, "eng-co", "software_engineer", "mid")
    candidate = _make_candidate(db, "financial_analyst", "mid")
    assert find_open_companies_for_candidate(db, candidate) == []


def test_no_target_role_family_returns_empty(db):
    _make_company(db, "meridian", "financial_analyst", "mid")
    candidate = _make_candidate(db, None, "mid")
    assert find_open_companies_for_candidate(db, candidate) == []


# ---------------------------------------------------------------------------
# enqueue_matches_for_candidate
# ---------------------------------------------------------------------------

def test_enqueue_creates_pending_match(db):
    _make_company(db, "meridian", "financial_analyst", "mid")
    candidate = _make_candidate(db, "financial_analyst", "mid")
    db.flush()

    matches = enqueue_matches_for_candidate(db, candidate)
    assert len(matches) == 1
    assert matches[0].status == "pending"
    assert matches[0].candidate_id == candidate.id


def test_enqueue_skips_succeeded_match(db):
    company = _make_company(db, "meridian", "financial_analyst", "mid")
    candidate = _make_candidate(db, "financial_analyst", "mid")
    existing = models.Match(
        candidate_id=candidate.id,
        company_id=company.id,
        status="succeeded",
        overall_score=75,
        band="Strong fit",
        band_note="",
        report={},
    )
    db.add(existing)
    db.flush()

    matches = enqueue_matches_for_candidate(db, candidate)
    assert matches == []


def test_enqueue_resets_failed_match(db):
    company = _make_company(db, "meridian", "financial_analyst", "mid")
    candidate = _make_candidate(db, "financial_analyst", "mid")
    existing = models.Match(
        candidate_id=candidate.id,
        company_id=company.id,
        status="failed",
        overall_score=0,
        band="",
        band_note="",
        report={},
        error_message="timeout",
    )
    db.add(existing)
    db.flush()

    matches = enqueue_matches_for_candidate(db, candidate)
    assert len(matches) == 1
    assert matches[0].status == "pending"
    assert matches[0].error_message is None


def test_enqueue_skips_running_match(db):
    company = _make_company(db, "meridian", "financial_analyst", "mid")
    candidate = _make_candidate(db, "financial_analyst", "mid")
    existing = models.Match(
        candidate_id=candidate.id,
        company_id=company.id,
        status="running",
        overall_score=0,
        band="",
        band_note="",
        report={},
    )
    db.add(existing)
    db.flush()

    matches = enqueue_matches_for_candidate(db, candidate)
    assert matches == []
