"""Structured profile extraction pipeline.

Public entry point: ``extract_profile(candidate, *, budget) -> dict``. The
return value is the merged VerifiedProfile payload (public + internal fields)
ready to be persisted via the verified_profiles table.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from ..simulation.cost_tracker import CostBudget
from ..simulation.persona_aggregator import _load_cv_text
from .cv_parser import extract_from_cv
from .github_fetcher import fetch_github_profile
from .merger import merge
from .portfolio_fetcher import fetch_portfolio

if TYPE_CHECKING:
    from ...models import Candidate

logger = logging.getLogger(__name__)


def _cv_hash(cv_text: str) -> str:
    return hashlib.sha256(cv_text.encode("utf-8", errors="ignore")).hexdigest()[:16]


async def extract_profile(
    candidate: "Candidate",
    *,
    budget: CostBudget,
) -> dict[str, Any]:
    """Run the full extraction pipeline for a candidate.

    Failures in any single source (no CV, broken github URL, unreachable
    portfolio) degrade gracefully — the merger receives empty defaults and
    returns whatever data did extract successfully.
    """
    cv_text = _load_cv_text(candidate)
    cv_data = await extract_from_cv(cv_text, budget=budget)

    github_url = getattr(candidate, "github_url", None) or ""
    github_data = await fetch_github_profile(github_url) if github_url else {
        "repos": [], "readme_samples": [], "username": None,
    }

    portfolio_url = getattr(candidate, "portfolio_url", None) or ""
    portfolio_data = await fetch_portfolio(portfolio_url) if portfolio_url else {
        "prose_samples": [], "pages_fetched": 0, "root": None,
    }

    intake_samples: list[str] = []
    sjt_responses = getattr(candidate, "sjt_responses", None) or {}
    for v in sjt_responses.values():
        if isinstance(v, str) and len(v) > 40:
            intake_samples.append(v)

    merged = merge(
        cv_data=cv_data,
        github_data=github_data,
        portfolio_data=portfolio_data,
        intake_voice_samples=intake_samples,
    )

    now = datetime.now(timezone.utc)
    merged["source_versions"] = {
        "cv_hash": _cv_hash(cv_text) if cv_text and cv_text != "(none provided)" else None,
        "github_fetched_at": now.isoformat() if github_url else None,
        "github_username": github_data.get("username"),
        "portfolio_fetched_at": now.isoformat() if portfolio_url else None,
        "portfolio_pages": portfolio_data.get("pages_fetched", 0),
    }
    return merged


__all__ = ["extract_profile"]
