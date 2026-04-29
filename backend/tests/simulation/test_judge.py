"""Unit tests for services/simulation/judge.py — Phase 4B.

Validation gate:
  (1) score_rollout() returns one RolloutScore per criterion.
  (2) Scores are merged means of two judge calls.
  (3) evidence_turns are forwarded from the primary judge's response.
  (4) Single-judge fallback fires when judge B fails; confidence halved.
  (5) Both-judges-fail returns null-score stubs and logs rollout_unscored.
  (6) judge_fallback event is logged when one call fails.
  (7) judge_scored event is logged with mock=False on success.
  (8) _merge_scores returns None when both judges return null score.
  (9) _render_indexed_transcript formats turns correctly.
  (10) judge_output_schema generates correct required keys.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import RolloutLog, RolloutScore
from app.services.simulation.judge import (
    JudgeResult,
    _merge_scores,
    _render_dimensions_block,
    _render_indexed_transcript,
    judge_output_schema,
    score_rollout,
)
from app.services.simulation.cost_tracker import CostBudget


# ---------------------------------------------------------------------------
# Sync DB fixture
# ---------------------------------------------------------------------------

@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------

class _StubRollout:
    id = "rollout-001"
    transcript = [
        {"turn": 0, "speaker_id": "candidate", "speaker_name": "Candidate", "content": "I'd cut marketing first."},
        {"turn": 1, "speaker_id": "teammate:tm0", "speaker_name": "Alex", "content": "Why marketing?"},
        {"turn": 2, "speaker_id": "candidate", "speaker_name": "Candidate", "content": "Lowest near-term ROI."},
    ]


_CRITERIA = [
    {"key": "written_rigor", "label": "Written Rigor", "description": "Structures arguments clearly."},
    {"key": "decisiveness", "label": "Decisiveness", "description": "Makes calls without endless hedging."},
]

_SCENARIO = {
    "id": "scen-001",
    "prompt": "Q4 targets at risk. What do you cut?",
    "expected_arc": "Structured, prioritised recommendation.",
}

_MATCH_ID = "match-001"


def _judge_response(score_a: int = 75, score_b: int = 85) -> dict:
    return {
        "dimension_scores": {
            "written_rigor": {
                "score": score_a,
                "justification": '"I\'d cut marketing first" shows clear prioritisation.',
                "evidence_turns": [0, 2],
                "confidence": 0.8,
            },
            "decisiveness": {
                "score": score_b,
                "justification": "Candidate gave a direct recommendation.",
                "evidence_turns": [0],
                "confidence": 0.7,
            },
        },
        "transcript_summary": "Candidate prioritised clearly under pressure.",
        "judge_notes": "",
    }


def _make_budget() -> CostBudget:
    return CostBudget(ceiling_usd=2.0)


# ---------------------------------------------------------------------------
# Tests — score_rollout()
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_score_rollout_returns_one_row_per_criterion(db_session):
    resp = _judge_response()
    with patch("app.services.simulation.judge.tracked_chat_json", new=AsyncMock(return_value=resp)):
        result = await score_rollout(
            _StubRollout(), _SCENARIO, _CRITERIA,
            budget=_make_budget(), db=db_session, match_id=_MATCH_ID,
        )

    assert isinstance(result, JudgeResult)
    assert len(result.rows) == 2
    keys = {r.dimension_key for r in result.rows}
    assert keys == {"written_rigor", "decisiveness"}


@pytest.mark.asyncio
async def test_score_rollout_merges_two_judge_calls(db_session):
    resp_a = _judge_response(score_a=70, score_b=80)
    resp_b = _judge_response(score_a=90, score_b=100)

    with patch("app.services.simulation.judge.tracked_chat_json",
               new=AsyncMock(side_effect=[resp_a, resp_b])):
        result = await score_rollout(
            _StubRollout(), _SCENARIO, _CRITERIA,
            budget=_make_budget(), db=db_session, match_id=_MATCH_ID,
        )

    scores = {r.dimension_key: r.score for r in result.rows}
    # (70+90)//2 = 80, (80+100)//2 = 90
    assert scores["written_rigor"] == 80
    assert scores["decisiveness"] == 90


@pytest.mark.asyncio
async def test_score_rollout_transcript_summary_returned(db_session):
    with patch("app.services.simulation.judge.tracked_chat_json",
               new=AsyncMock(return_value=_judge_response())):
        result = await score_rollout(
            _StubRollout(), _SCENARIO, _CRITERIA,
            budget=_make_budget(), db=db_session, match_id=_MATCH_ID,
        )

    assert result.transcript_summary == "Candidate prioritised clearly under pressure."


@pytest.mark.asyncio
async def test_score_rollout_evidence_turns_forwarded(db_session):
    with patch("app.services.simulation.judge.tracked_chat_json",
               new=AsyncMock(return_value=_judge_response())):
        result = await score_rollout(
            _StubRollout(), _SCENARIO, _CRITERIA,
            budget=_make_budget(), db=db_session, match_id=_MATCH_ID,
        )

    wr = next(r for r in result.rows if r.dimension_key == "written_rigor")
    assert wr.evidence_turns == [0, 2]


@pytest.mark.asyncio
async def test_score_rollout_single_judge_fallback_on_second_failure(db_session):
    resp_a = _judge_response()

    with patch("app.services.simulation.judge.tracked_chat_json",
               new=AsyncMock(side_effect=[resp_a, Exception("timeout")])):
        result = await score_rollout(
            _StubRollout(), _SCENARIO, _CRITERIA,
            budget=_make_budget(), db=db_session, match_id=_MATCH_ID,
        )

    wr = next(r for r in result.rows if r.dimension_key == "written_rigor")
    assert wr.score == 75
    assert wr.confidence == pytest.approx(0.4)  # 0.8 * 0.5


@pytest.mark.asyncio
async def test_score_rollout_single_judge_fallback_logs_event(db_session):
    resp_a = _judge_response()

    with patch("app.services.simulation.judge.tracked_chat_json",
               new=AsyncMock(side_effect=[resp_a, Exception("timeout")])):
        await score_rollout(
            _StubRollout(), _SCENARIO, _CRITERIA,
            budget=_make_budget(), db=db_session, match_id=_MATCH_ID,
        )
        db_session.commit()

    logs = db_session.execute(select(RolloutLog).where(RolloutLog.match_id == _MATCH_ID)).scalars().all()
    event_types = {r.event_type for r in logs}
    assert "judge_fallback" in event_types


@pytest.mark.asyncio
async def test_score_rollout_both_fail_returns_null_stubs(db_session):
    with patch("app.services.simulation.judge.tracked_chat_json",
               new=AsyncMock(side_effect=Exception("network error"))):
        result = await score_rollout(
            _StubRollout(), _SCENARIO, _CRITERIA,
            budget=_make_budget(), db=db_session, match_id=_MATCH_ID,
        )

    assert len(result.rows) == 2
    assert all(r.score is None for r in result.rows)
    assert all(r.confidence == 0.0 for r in result.rows)
    assert result.transcript_summary == ""


@pytest.mark.asyncio
async def test_score_rollout_both_fail_logs_rollout_unscored(db_session):
    with patch("app.services.simulation.judge.tracked_chat_json",
               new=AsyncMock(side_effect=Exception("network error"))):
        await score_rollout(
            _StubRollout(), _SCENARIO, _CRITERIA,
            budget=_make_budget(), db=db_session, match_id=_MATCH_ID,
        )
        db_session.commit()

    logs = db_session.execute(select(RolloutLog).where(RolloutLog.match_id == _MATCH_ID)).scalars().all()
    event_types = {r.event_type for r in logs}
    assert "rollout_unscored" in event_types


@pytest.mark.asyncio
async def test_score_rollout_logs_judge_scored_on_success(db_session):
    with patch("app.services.simulation.judge.tracked_chat_json",
               new=AsyncMock(return_value=_judge_response())):
        await score_rollout(
            _StubRollout(), _SCENARIO, _CRITERIA,
            budget=_make_budget(), db=db_session, match_id=_MATCH_ID,
        )
        db_session.commit()

    logs = db_session.execute(select(RolloutLog).where(RolloutLog.match_id == _MATCH_ID)).scalars().all()
    scored = [r for r in logs if r.event_type == "judge_scored"]
    assert len(scored) == 1
    assert scored[0].payload["mock"] is False


@pytest.mark.asyncio
async def test_score_rollout_empty_criteria_returns_empty(db_session):
    with patch("app.services.simulation.judge.tracked_chat_json", new=AsyncMock()) as mock_llm:
        result = await score_rollout(
            _StubRollout(), _SCENARIO, [],
            budget=_make_budget(), db=db_session, match_id=_MATCH_ID,
        )
    assert result.rows == []
    assert result.transcript_summary == ""
    mock_llm.assert_not_called()


# ---------------------------------------------------------------------------
# Tests — helpers
# ---------------------------------------------------------------------------

def test_merge_scores_mean_of_two():
    scores_a = {"key": {"score": 60, "confidence": 0.8}}
    scores_b = {"key": {"score": 80, "confidence": 0.9}}
    score, conf = _merge_scores(scores_a, scores_b, "key")
    assert score == 70
    assert 0.0 < conf <= 1.0


def test_merge_scores_null_a_uses_b():
    scores_a = {"key": {"score": None, "confidence": 0.0}}
    scores_b = {"key": {"score": 75, "confidence": 0.7}}
    score, conf = _merge_scores(scores_a, scores_b, "key")
    assert score == 75
    assert conf == pytest.approx(0.35)


def test_merge_scores_both_null_returns_none():
    scores_a = {"key": {"score": None, "confidence": 0.0}}
    scores_b = {"key": {"score": None, "confidence": 0.0}}
    score, conf = _merge_scores(scores_a, scores_b, "key")
    assert score is None
    assert conf == 0.0


def test_merge_scores_single_judge_halves_confidence():
    scores_a = {"key": {"score": 80, "confidence": 0.9}}
    score, conf = _merge_scores(scores_a, None, "key")
    assert score == 80
    assert conf == pytest.approx(0.45)


def test_render_indexed_transcript_format():
    turns = [
        {"speaker_name": "Candidate", "content": "Hello."},
        {"speaker_name": "Alex", "content": "Why?"},
    ]
    result = _render_indexed_transcript(turns)
    assert "[#0 · Candidate] Hello." in result
    assert "[#1 · Alex] Why?" in result


def test_render_indexed_transcript_empty():
    result = _render_indexed_transcript([])
    assert "empty" in result.lower()


def test_render_dimensions_block():
    criteria = [
        {"key": "written_rigor", "label": "Written Rigor", "description": "Clear arguments."},
    ]
    result = _render_dimensions_block(criteria)
    assert "written_rigor" in result
    assert "Written Rigor" in result
    assert "Clear arguments." in result


def test_judge_output_schema_required_keys():
    schema = judge_output_schema(["dim_a", "dim_b"])
    dim_scores = schema["properties"]["dimension_scores"]
    assert "dim_a" in dim_scores["properties"]
    assert "dim_b" in dim_scores["properties"]
    assert dim_scores["required"] == ["dim_a", "dim_b"]


def test_judge_output_schema_top_level_required():
    schema = judge_output_schema(["x"])
    assert set(schema["required"]) == {"dimension_scores", "transcript_summary", "judge_notes"}
