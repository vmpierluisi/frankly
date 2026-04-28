"""Unit tests for services/simulation/cost_tracker.py.

Validation gate (Phase 0):
  (1) tracked_chat_json raises CostCeilingExceeded when budget exhausted.
  (2) Cost estimation matches _MODEL_PRICES for known models.
  (3) Unknown model defaults to Sonnet pricing without crashing.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.services.simulation.cost_tracker import (
    CostBudget,
    CostCeilingExceeded,
    _MODEL_PRICES,
    estimate_call_cost,
    tracked_chat_json,
)


def test_estimate_call_cost_known_model():
    """(2) Cost matches _MODEL_PRICES table for known model."""
    model = "anthropic/claude-sonnet-4.6"
    usage = {"prompt_tokens": 1000, "completion_tokens": 500}
    p = _MODEL_PRICES[model]
    expected = (1000 / 1000) * p["in"] + (500 / 1000) * p["out"]
    assert estimate_call_cost(model, usage) == pytest.approx(expected)


def test_estimate_call_cost_unknown_model_uses_sonnet_pricing():
    """(3) Unknown model defaults to Sonnet pricing without crashing."""
    usage = {"prompt_tokens": 1000, "completion_tokens": 500}
    default_p = _MODEL_PRICES["anthropic/claude-sonnet-4.6"]
    expected = (1000 / 1000) * default_p["in"] + (500 / 1000) * default_p["out"]
    assert estimate_call_cost("some/unknown-model-xyz", usage) == pytest.approx(expected)


def test_estimate_call_cost_zero_tokens():
    """Zero usage → zero cost."""
    assert estimate_call_cost("anthropic/claude-sonnet-4.6", {}) == 0.0


@pytest.mark.asyncio
async def test_tracked_chat_json_raises_when_ceiling_exhausted():
    """(1) CostCeilingExceeded raised immediately when spent >= ceiling."""
    budget = CostBudget(ceiling_usd=0.01, spent_usd=0.01)
    with pytest.raises(CostCeilingExceeded):
        await tracked_chat_json(budget, system="s", user="u", schema={}, schema_name="x")


@pytest.mark.asyncio
async def test_tracked_chat_json_updates_budget():
    """Budget fields are updated after a successful call."""
    budget = CostBudget(ceiling_usd=10.0)
    canned = {"result": "ok"}

    mock_usage = {"prompt_tokens": 100, "completion_tokens": 50}

    async def _fake_chat_json_with_retry(**kwargs):
        return {**canned, "_usage": mock_usage}

    with patch(
        "app.services.simulation.cost_tracker.chat_json_with_retry",
        new=_fake_chat_json_with_retry,
    ):
        result = await tracked_chat_json(
            budget,
            system="s",
            user="u",
            schema={},
            schema_name="x",
            model="anthropic/claude-sonnet-4.6",
        )

    assert result == canned
    assert budget.calls_made == 1
    assert budget.tokens_in == 100
    assert budget.tokens_out == 50
    assert budget.spent_usd > 0.0


@pytest.mark.asyncio
async def test_tracked_chat_json_strips_usage_key():
    """_usage key is removed from the returned dict."""
    budget = CostBudget(ceiling_usd=10.0)

    async def _fake(**kwargs):
        return {"answer": 42, "_usage": {"prompt_tokens": 10, "completion_tokens": 5}}

    with patch("app.services.simulation.cost_tracker.chat_json_with_retry", new=_fake):
        result = await tracked_chat_json(budget, system="", user="", schema={}, schema_name="")

    assert "_usage" not in result
    assert result["answer"] == 42
