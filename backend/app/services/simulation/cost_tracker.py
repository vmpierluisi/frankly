"""Per-match cost tracking and circuit breaker.

Each simulation match constructs a CostBudget and passes it through every LLM
call via tracked_chat_json. If the ceiling is exceeded, CostCeilingExceeded is
raised, the match aborts, and whatever scoring is already complete is persisted
with auditTrailV2.aborted = "cost_ceiling".
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..openrouter import chat_json_with_retry
from ...config import settings

# Per-model price table (USD per 1K tokens). Update when model pricing changes.
_MODEL_PRICES: dict[str, dict[str, float]] = {
    "anthropic/claude-sonnet-4.6": {"in": 0.003, "out": 0.015},
    "anthropic/claude-haiku-4.5":  {"in": 0.0008, "out": 0.004},
}
_DEFAULT_PRICES = _MODEL_PRICES["anthropic/claude-sonnet-4.6"]


@dataclass
class CostBudget:
    ceiling_usd: float
    spent_usd: float = 0.0
    calls_made: int = 0
    tokens_in: int = 0
    tokens_out: int = 0


class CostCeilingExceeded(RuntimeError):
    pass


def estimate_call_cost(model: str, usage: dict[str, Any]) -> float:
    p = _MODEL_PRICES.get(model, _DEFAULT_PRICES)
    return (
        (usage.get("prompt_tokens", 0) / 1000) * p["in"]
        + (usage.get("completion_tokens", 0) / 1000) * p["out"]
    )


async def tracked_chat_json(budget: CostBudget, **kwargs: Any) -> dict[str, Any]:
    """Wrapper around chat_json_with_retry that records cost against a budget.

    Raises CostCeilingExceeded before making the call if the ceiling is already
    reached. Strips the internal ``_usage`` key from the returned dict so
    callers see a clean payload.
    """
    if budget.spent_usd >= budget.ceiling_usd:
        raise CostCeilingExceeded(
            f"Match exceeded ${budget.ceiling_usd:.2f} ceiling "
            f"after {budget.calls_made} LLM calls."
        )
    out = await chat_json_with_retry(**kwargs)
    usage = out.pop("_usage", {})
    model = kwargs.get("model") or settings.openrouter_model
    cost = estimate_call_cost(model, usage)
    budget.spent_usd += cost
    budget.calls_made += 1
    budget.tokens_in += usage.get("prompt_tokens", 0)
    budget.tokens_out += usage.get("completion_tokens", 0)
    return out
