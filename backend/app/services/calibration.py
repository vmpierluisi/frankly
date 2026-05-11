"""Calibration loop — Roadmap 2 / PR #5.

Closes the persona-accuracy feedback loop:

    sample_after_match()          → picks rollouts worth asking about,
                                    creates pending CalibrationResponse rows,
                                    fires notification + email nudge.
    generate_mcq_options()        → 4 shuffled options (1 agent paraphrase,
                                    3 plausible alternates) via LLM, with a
                                    deterministic fallback for tests / when
                                    OPENROUTER_API_KEY is absent.
    submit_response()             → records candidate answer, computes
                                    divergence, increments profile accuracy,
                                    appends to persona evidence ledger.

Sampling policy (per spec):
  * Eligible: any candidate whose match just succeeded and who has not been
    asked in the last 7 days. (Frequency cap.)
  * Bias toward low-confidence rollouts (judge confidence < 0.6 OR persona
    fidelity score < 60) — those are scheduled deterministically.
  * Remaining candidates are sampled at 15% probability.
"""
from __future__ import annotations

import logging
import random
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from .email import send_calibration_nudge
from .openrouter import OpenRouterError, chat_json_with_retry

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------
RANDOM_SAMPLE_PROB = 0.15
LOW_CONFIDENCE_THRESHOLD = 0.6   # judge confidence
LOW_FIDELITY_THRESHOLD = 60       # persona_fidelity score (0..100)
FREQUENCY_CAP_DAYS = 7
ACCURACY_BUMP_BASE = 4            # base points per submission
ACCURACY_BUMP_HIGH_DIVERGENCE = 1 # bonus when divergence is large
ACCURACY_MAX = 100


# ---------------------------------------------------------------------------
# Sampling
# ---------------------------------------------------------------------------
def _last_calibration_at(db: Session, candidate_id: str) -> datetime | None:
    row = (
        db.execute(
            select(models.CalibrationResponse.created_at)
            .where(models.CalibrationResponse.candidate_id == candidate_id)
            .order_by(models.CalibrationResponse.created_at.desc())
            .limit(1)
        )
        .scalars()
        .first()
    )
    return row


def _within_frequency_cap(db: Session, candidate_id: str) -> bool:
    last = _last_calibration_at(db, candidate_id)
    if last is None:
        return False
    # Treat naive datetimes (SQLite) as UTC.
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - last) < timedelta(days=FREQUENCY_CAP_DAYS)


def _pick_target_rollout(
    db: Session, match_id: str
) -> tuple[models.Rollout | None, str]:
    """Return (rollout, mode). Mode is "free_text_only" when the rollout's
    judge confidence was low and we shouldn't bias the candidate with MCQ
    options; otherwise "mcq_plus_text"."""
    rollouts = (
        db.execute(
            select(models.Rollout)
            .where(models.Rollout.match_id == match_id)
            .where(models.Rollout.status == "completed")
        )
        .scalars()
        .all()
    )
    if not rollouts:
        return None, "mcq_plus_text"

    # Rank: prefer low fidelity, then low judge confidence, then most recent.
    def _confidence_for(r: models.Rollout) -> float:
        scores = (
            db.execute(
                select(models.RolloutScore.confidence).where(
                    models.RolloutScore.rollout_id == r.id,
                    models.RolloutScore.dimension_key != "persona_fidelity",
                )
            )
            .scalars()
            .all()
        )
        if not scores:
            return 1.0
        return sum(scores) / len(scores)

    def _fidelity_for(r: models.Rollout) -> int:
        fs = (r.final_state or {}).get("persona_fidelity") or {}
        return int(fs.get("score") or 100)

    ranked = sorted(
        rollouts,
        key=lambda r: (_fidelity_for(r), _confidence_for(r), -r.duration_turns),
    )
    target = ranked[0]
    mode = (
        "free_text_only"
        if _confidence_for(target) < LOW_CONFIDENCE_THRESHOLD
        else "mcq_plus_text"
    )
    return target, mode


def _last_agent_turn(rollout: models.Rollout) -> dict | None:
    """The most recent turn the candidate-agent spoke in. We calibrate
    against this turn — it's the simulation's most concrete commitment."""
    for turn in reversed(rollout.transcript or []):
        if turn.get("speaker_id") == "candidate":
            return turn
    return None


def _should_sample(
    *,
    rng: random.Random,
    rollout: models.Rollout,
    rollouts: list[models.Rollout] | None = None,
) -> bool:
    """Bias toward low-confidence / low-fidelity rollouts; otherwise 15%."""
    fs = (rollout.final_state or {}).get("persona_fidelity") or {}
    if fs.get("score") is not None and int(fs["score"]) < LOW_FIDELITY_THRESHOLD:
        return True
    return rng.random() < RANDOM_SAMPLE_PROB


async def sample_after_match(
    *,
    db: Session,
    match_id: str,
    rng: random.Random | None = None,
) -> models.CalibrationResponse | None:
    """Decide whether to ask this candidate to calibrate based on the just-
    completed match. If yes, create a pending CalibrationResponse row,
    notification, and email nudge. Returns the row (or ``None`` skipped).

    The function is best-effort — any internal error is logged and
    swallowed so a transient LLM failure doesn't crash the simulation
    pipeline. The match itself has already succeeded by the time we run.
    """
    rng = rng or random.Random()
    match = db.get(models.Match, match_id)
    if match is None:
        return None
    candidate = db.get(models.Candidate, match.candidate_id)
    if candidate is None:
        return None

    if _within_frequency_cap(db, candidate.id):
        logger.info("calibration.skip frequency_cap candidate=%s", candidate.id)
        return None

    rollout, mode = _pick_target_rollout(db, match_id)
    if rollout is None:
        return None
    agent_turn = _last_agent_turn(rollout)
    if agent_turn is None:
        return None

    if not _should_sample(rng=rng, rollout=rollout):
        logger.info("calibration.skip sampling candidate=%s", candidate.id)
        return None

    options: list[dict[str, Any]] = []
    if mode == "mcq_plus_text":
        try:
            options = await generate_mcq_options(
                agent_response=agent_turn.get("content", ""),
                scenario_brief=(rollout.final_state or {}).get("scenario_brief")
                or _scenario_brief(db, rollout.scenario_id),
                candidate_persona=candidate.aggregated_persona or {},
                rng=rng,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("calibration.mcq_failed match=%s: %s", match_id, exc)
            options = _fallback_options(agent_turn.get("content", ""), rng)

    row = models.CalibrationResponse(
        candidate_id=candidate.id,
        rollout_id=rollout.id,
        scenario_id=rollout.scenario_id,
        agent_response_text=agent_turn.get("content", ""),
        mcq_options=options,
        mode=mode,
        prompt_version=rollout.prompt_version,
        status="pending",
    )
    db.add(row)
    db.flush()

    db.add(
        models.Notification(
            user_kind="candidate",
            candidate_id=candidate.id,
            recipient_email=None,
            type="calibration_request",
            payload={
                "calibration_id": row.id,
                "mode": mode,
            },
            status="unread",
        )
    )
    db.commit()
    db.refresh(row)

    # Best-effort email nudge.
    try:
        send_calibration_nudge(
            to=candidate.email or "",
            display_name=candidate.display_name,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("calibration.email_failed candidate=%s: %s", candidate.id, exc)

    return row


def _scenario_brief(db: Session, scenario_id: str | None) -> str:
    if not scenario_id:
        return ""
    sc = db.get(models.MomentOfTruth, scenario_id)
    if sc is None:
        return ""
    return getattr(sc, "context", "") or getattr(sc, "title", "") or ""


# ---------------------------------------------------------------------------
# MCQ generation
# ---------------------------------------------------------------------------
_MCQ_SYSTEM = """\
You generate calibration multiple-choice options for a hiring-screening
simulation. You will be given the agent's actual response in a scenario,
plus a brief description of that scenario. Produce exactly FOUR options:

  * One option that is a faithful paraphrase of the agent's response.
  * Three options that are plausible alternatives at DIFFERENT style or
    skill levels (e.g. more terse, more verbose, more technical, less
    confident, more confident).

Hard constraints:
  * Every option must be 12-50 words.
  * No option may begin with "Option N" or any label.
  * Do not signal which option is the agent's — the candidate must not be
    able to tell.

Return STRICT JSON matching the supplied schema.
"""

_MCQ_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["options"],
    "properties": {
        "options": {
            "type": "array",
            "minItems": 4,
            "maxItems": 4,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["text", "is_agent_answer", "skill_level"],
                "properties": {
                    "text": {"type": "string"},
                    "is_agent_answer": {"type": "boolean"},
                    "skill_level": {"type": "string"},
                },
            },
        }
    },
}


async def generate_mcq_options(
    *,
    agent_response: str,
    scenario_brief: str,
    candidate_persona: dict[str, Any],
    rng: random.Random | None = None,
) -> list[dict[str, Any]]:
    """LLM call → list[{text, is_agent_answer, skill_level}], shuffled.

    Falls back to deterministic templates when the API key is missing or
    the call fails — the calibration prompt is still useful then, just
    less varied.
    """
    rng = rng or random.Random()
    try:
        user = (
            f"SCENARIO\n{scenario_brief or '(none)'}\n\n"
            f"AGENT RESPONSE\n{agent_response}\n\n"
            "Produce exactly 4 calibration options as described."
        )
        result = await chat_json_with_retry(
            system=_MCQ_SYSTEM,
            user=user,
            schema=_MCQ_SCHEMA,
            schema_name="calibration_mcq",
            temperature=0.7,
            max_tokens=900,
        )
        options = list(result.get("options") or [])
        if len(options) != 4:
            raise OpenRouterError("MCQ generator returned wrong option count")
    except Exception as exc:  # noqa: BLE001
        logger.info("calibration.mcq.fallback reason=%s", exc)
        options = _fallback_options(agent_response, rng)

    rng.shuffle(options)
    return options


def _fallback_options(agent_response: str, rng: random.Random) -> list[dict[str, Any]]:
    """Deterministic 4-option set when the LLM call isn't available.

    The agent option is a verbatim copy; the three alternates are simple
    transforms expressing different style/skill levels.
    """
    text = agent_response.strip() or "I would address the situation directly."
    short = text.split(".")[0][:160].strip() or text[:160]
    longer = (
        f"{text} I would also pull in additional context, check assumptions "
        "with the team, and document the reasoning before moving forward."
    )
    cautious = (
        f"Honestly, I am not fully sure here. {short} — but I would want to "
        "talk it through with someone closer to the problem first."
    )
    return [
        {"text": text, "is_agent_answer": True, "skill_level": "match"},
        {"text": short, "is_agent_answer": False, "skill_level": "terse"},
        {"text": longer, "is_agent_answer": False, "skill_level": "verbose"},
        {"text": cautious, "is_agent_answer": False, "skill_level": "cautious"},
    ]


# ---------------------------------------------------------------------------
# Submission + persona update
# ---------------------------------------------------------------------------
def submit_response(
    *,
    db: Session,
    calibration: models.CalibrationResponse,
    candidate: models.Candidate,
    selection_index: int | None,
    free_text: str | None,
) -> models.CalibrationResponse:
    """Record the candidate's answer, compute divergence, increment the
    profile-accuracy score, and append evidence to the persona's audit
    trail.

    Persona re-derivation is intentionally lazy here. The aggregator runs
    on demand at match time and reads ``aggregation_audit['evidence']`` —
    we append the calibration row's id + verdict there; the next match
    will pick it up when ``aggregated_persona`` is rebuilt.
    """
    if calibration.status != "pending":
        return calibration

    accuracy_before = candidate.profile_accuracy_score or 0

    divergence: float | None = None
    if selection_index is not None and calibration.mcq_options:
        try:
            chose_agent = bool(
                calibration.mcq_options[selection_index].get("is_agent_answer")
            )
            divergence = 0.0 if chose_agent else 1.0
        except (IndexError, AttributeError, TypeError):
            divergence = None

    bump = ACCURACY_BUMP_BASE
    if divergence is not None and divergence >= 0.5:
        # Surfaces a real mismatch → more learning value.
        bump += ACCURACY_BUMP_HIGH_DIVERGENCE
    if free_text and free_text.strip():
        bump += 1

    accuracy_after = min(ACCURACY_MAX, accuracy_before + bump)
    candidate.profile_accuracy_score = accuracy_after

    # Append to the persona's evidence audit trail (append-only).
    audit = dict(candidate.aggregation_audit or {})
    evidence = list(audit.get("evidence") or [])
    evidence.append(
        {
            "kind": "calibration_response",
            "calibration_id": calibration.id,
            "rollout_id": calibration.rollout_id,
            "scenario_id": calibration.scenario_id,
            "divergence": divergence,
            "selection_index": selection_index,
            "free_text": (free_text or "").strip()[:2000] or None,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    audit["evidence"] = evidence
    audit["last_calibration_id"] = calibration.id
    candidate.aggregation_audit = audit

    calibration.candidate_selection_index = selection_index
    calibration.candidate_free_text = (free_text or "").strip() or None
    calibration.divergence_score = divergence
    calibration.accuracy_before = accuracy_before
    calibration.accuracy_after = accuracy_after
    calibration.status = "submitted"
    calibration.submitted_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(calibration)
    return calibration


# ---------------------------------------------------------------------------
# Convenience wrappers for routes
# ---------------------------------------------------------------------------
def list_for_candidate(
    db: Session, candidate_id: str
) -> list[models.CalibrationResponse]:
    return (
        db.execute(
            select(models.CalibrationResponse)
            .where(models.CalibrationResponse.candidate_id == candidate_id)
            .order_by(models.CalibrationResponse.created_at.desc())
        )
        .scalars()
        .all()
    )


def timeline_for_candidate(
    db: Session, candidate: models.Candidate
) -> list[dict[str, Any]]:
    """Render the "how the number sharpened over weeks" view. Returns
    one row per submitted calibration plus a synthetic 'today' entry at
    the candidate's current score.
    """
    rows = (
        db.execute(
            select(models.CalibrationResponse)
            .where(models.CalibrationResponse.candidate_id == candidate.id)
            .where(models.CalibrationResponse.status == "submitted")
            .order_by(models.CalibrationResponse.submitted_at.asc())
        )
        .scalars()
        .all()
    )
    out: list[dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "calibration_id": r.id,
                "submitted_at": r.submitted_at,
                "accuracy_before": r.accuracy_before,
                "accuracy_after": r.accuracy_after,
                "divergence": r.divergence_score,
            }
        )
    return out


