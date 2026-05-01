"""Role-family taxonomy — code-controlled slug enum.

New families require a code change. Acceptable v0 trade-off with two seed companies.
"""
from __future__ import annotations

ROLE_FAMILIES: list[str] = [
    "financial_analyst",
    "software_engineer",
    "product_manager",
    "data_scientist",
    "operations_manager",
    "marketing_manager",
    "sales_executive",
    "hr_business_partner",
    "legal_counsel",
    "strategy_consultant",
]

SENIORITY_LEVELS: list[str] = ["junior", "mid", "senior", "lead"]

_SENIORITY_INDEX: dict[str, int] = {s: i for i, s in enumerate(SENIORITY_LEVELS)}


def compatible_seniorities(target: str) -> set[str]:
    """Return the set of seniority levels compatible with target (±1 adjacency)."""
    idx = _SENIORITY_INDEX.get(target)
    if idx is None:
        return set()
    return {
        SENIORITY_LEVELS[i]
        for i in range(len(SENIORITY_LEVELS))
        if abs(i - idx) <= 1
    }
