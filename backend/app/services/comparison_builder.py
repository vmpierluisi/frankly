"""Manager Shortlist V7 — comparison report composer.

Assembles the ``ShortlistComparisonReport`` served by
``GET /positions/{id}/shortlist``. Two selection modes:

  * explicit   — caller passes ``candidate_ids``; those exact candidates form
                 the active set, everyone else becomes ``available_candidates``.
  * auto_top_n — caller passes only ``top_n``; the top-N completed matches by
                 ``Match.overall_score`` form the active set.

Everything is derived at request time from existing Match / Rollout /
RolloutScore / Position data. The only new persistence is ``TriageDecision``,
read here to stamp each candidate's manual decision (default "undecided").
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from statistics import mean
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .. import models
from .composite_fit import compute_overall_fit, compute_team_fit
from .hero_quote import pick_hero_quote


@dataclass
class _Prefetch:
    """Rollouts + scores for a set of matches, loaded in two queries up front.

    The report builds a full CandidateInReport for every candidate in the
    active set *and* the ~20 available candidates. Each candidate's team_fit,
    overall_fit, hero_quote, and responses all read the same rollouts/scores, so
    loading them once here (rather than per-candidate, per-function) collapses
    what was an N+1 storm — ~8 queries × ~23 candidates against a remote
    Postgres — down to two queries total for the whole request.
    """

    rollouts_by_match: dict[str, list[models.Rollout]] = field(default_factory=dict)
    scores_by_rollout: dict[str, list[models.RolloutScore]] = field(default_factory=dict)

    def rollouts(self, match_id: str) -> list[models.Rollout]:
        return self.rollouts_by_match.get(match_id, [])

    def scores_for(self, match_id: str) -> list[models.RolloutScore]:
        out: list[models.RolloutScore] = []
        for r in self.rollouts(match_id):
            out.extend(self.scores_by_rollout.get(r.id, []))
        return out


def _prefetch(match_ids: list[str], db: Session) -> _Prefetch:
    if not match_ids:
        return _Prefetch()
    rollouts = list(
        db.execute(
            select(models.Rollout).where(models.Rollout.match_id.in_(match_ids))
        ).scalars()
    )
    rollouts_by_match: dict[str, list[models.Rollout]] = defaultdict(list)
    rollout_ids: list[str] = []
    for r in rollouts:
        rollouts_by_match[r.match_id].append(r)
        rollout_ids.append(r.id)

    scores_by_rollout: dict[str, list[models.RolloutScore]] = defaultdict(list)
    if rollout_ids:
        for s in db.execute(
            select(models.RolloutScore).where(
                models.RolloutScore.rollout_id.in_(rollout_ids)
            )
        ).scalars():
            scores_by_rollout[s.rollout_id].append(s)

    return _Prefetch(dict(rollouts_by_match), dict(scores_by_rollout))

# Palette slots assigned in ranked order (mirrors design.js CANDIDATE_PALETTE).
_PALETTE_VARS = ["--c-slot1", "--c-slot2", "--c-slot3", "--c-slot4", "--c-slot5"]

# The six composite axes (plan §5 / §12 #1). Kept in sync with
# composite_fit.compute_overall_fit keys.
_OVERALL_AXES = [
    ("role_fit", "Role fit", "Weighted fit across the role's behavioral criteria and hard skills."),
    ("team_chem", "Team chemistry", "How productively the candidate worked with the synthetic team."),
    ("memo_culture", "Memo culture", "Written-dissent and IC-memo signal — comfort putting a view on paper."),
    ("conflict_prod", "Conflict productivity", "Share of disagreements that stayed constructive."),
    ("ramp_speed", "Ramp speed", "v0 proxy on skills coverage — how ready to contribute on day one."),
    ("long_cycle", "Long-cycle stamina", "Patience plus CV tenure — comfort with long feedback loops."),
]

_FIDELITY_DIM = "persona_fidelity"

# Number of also-considered candidates returned alongside the active set. Keeps
# chip-toggling instant without a refetch (plan §4 note).
_AVAILABLE_CAP = 20


# ---------------------------------------------------------------------------
# Verdict / level labels
# ---------------------------------------------------------------------------
def _verdict_label(score: int | None) -> str:
    """Short human verdict for an Overview behavioral cell."""
    if score is None:
        return "No signal"
    if score >= 85:
        return "Exceptional"
    if score >= 70:
        return "Strong"
    if score >= 55:
        return "Solid"
    if score >= 40:
        return "Mixed"
    return "Weak"


def _skill_level_label(score: int | None) -> str:
    if score is None:
        return "Absent"
    if score >= 100:
        return "Expert"
    if score >= 75:
        return "Strong"
    if score >= 40:
        return "Working"
    if score > 0:
        return "Limited"
    return "Absent"


def _delta_str(value: int | float) -> str:
    n = int(round(value))
    return f"+{n}" if n >= 0 else str(n)


# ---------------------------------------------------------------------------
# Position context
# ---------------------------------------------------------------------------
def _skill_id(skill_name: str) -> str:
    return "skill_" + "".join(
        ch if ch.isalnum() else "_" for ch in (skill_name or "").strip().lower()
    ).strip("_")


def _scenario_by_dim(position: models.Position) -> dict[str, str]:
    """{criterion/skill key -> primary scenario id} from scenario scoring_dims.

    A criterion's "primary" scenario is the first (by ordering) scenario whose
    ``scoring_dims`` lists that criterion key. Powers the CellPopover's
    "See in scenario" affordance.
    """
    team = getattr(position, "team", None)
    scenarios = sorted(getattr(team, "scenarios", []) or [], key=lambda s: s.ordering)
    mapping: dict[str, str] = {}
    for sc in scenarios:
        for dim in sc.scoring_dims or []:
            mapping.setdefault(dim, sc.id)
    return mapping


def _build_position_context(position: models.Position) -> dict[str, Any]:
    dim_scenario = _scenario_by_dim(position)

    criteria = [
        {
            "id": c.key,
            "label": c.label,
            "why": c.description or "",
            "weight": float(c.weight or 0.0),
            "scenario_id": dim_scenario.get(c.key),
        }
        for c in sorted(position.criteria, key=lambda c: c.ordering)
    ]

    skills = [
        {
            "id": _skill_id(s.get("skill", "")),
            "label": s.get("skill", ""),
            "reason": f"Required at {s.get('level', 'mid')} level",
            "scenario_id": dim_scenario.get(s.get("skill", "")),
        }
        for s in (position.required_skills or [])
        if s.get("skill")
    ]

    team = getattr(position, "team", None)
    teammates = getattr(team, "teammates", []) or []
    team_meta = [
        {
            "id": tm.id,
            "name": tm.name,
            "short": _teammate_short(tm),
            "role": tm.role_on_team or "",
            "voice": (tm.narrative or "").split(".")[0][:120],
        }
        for tm in sorted(teammates, key=lambda t: t.ordering)
    ]

    overall_axes = [{"id": a, "label": lbl, "tip": tip} for a, lbl, tip in _OVERALL_AXES]

    return {
        "id": position.id,
        "title": position.role or position.name,
        "company_name": getattr(getattr(position, "organization", None), "name", None)
        or position.name,
        "role_short": position.role or position.name,
        "criteria": criteria,
        "skills": skills,
        "team": team_meta,
        "overall_axes": overall_axes,
        "default_top_n": 3,
        "available_sizes": [3, 5, 10],
    }


def _teammate_short(tm: models.SyntheticTeammate) -> str:
    """Axis-label form, e.g. 'Maya, MD'."""
    first = (tm.name or "").split(" ")[0]
    role = tm.role_on_team or ""
    return f"{first}, {role}" if role else first


def _build_scenarios(position: models.Position) -> list[dict[str, Any]]:
    team = getattr(position, "team", None)
    scenarios = getattr(team, "scenarios", []) or []
    out: list[dict[str, Any]] = []
    for sc in sorted(scenarios, key=lambda s: s.ordering):
        out.append(
            {
                "id": sc.id,
                "eyebrow": sc.scenario_type or "",
                "title": sc.title,
                "prompt": sc.prompt or "",
                "who": (sc.participating_roles or [None])[0] or "",
            }
        )
    return out


# ---------------------------------------------------------------------------
# Candidate report
# ---------------------------------------------------------------------------
def _dim_mean_map(report: dict) -> dict[str, int]:
    """{criterion_key: rounded mean} from dimensionalFit, skipping fidelity."""
    out: dict[str, int] = {}
    for key, entry in (report.get("dimensionalFit") or {}).items():
        if key == _FIDELITY_DIM:
            continue
        mval = entry.get("mean")
        if mval is not None:
            out[key] = int(round(mval))
    return out


def _build_candidate(
    match: models.Match,
    candidate: models.Candidate,
    position: models.Position,
    db: Session,
    palette_var: str,
    population_mean: float,
    triage_decision: str,
    prefetch: "_Prefetch",
) -> dict[str, Any]:
    report = match.report or {}
    dim_means = _dim_mean_map(report)
    criterion_scores = report.get("criterionScores") or {}

    # Overview cells by criterion id.
    overview: dict[str, dict[str, Any]] = {}
    for c in position.criteria:
        score = dim_means.get(c.key)
        cs = criterion_scores.get(c.key) or {}
        overview[c.key] = {
            "v": _verdict_label(score),
            "d": (cs.get("justification") or "")[:200] or None,
            "top": False,
            "weak": False,
        }

    # Skill cells by skill id.
    skills_details = report.get("skillsFitDetails") or {}
    per_skill = {ps["skill"]: ps for ps in (skills_details.get("per_skill") or [])}
    skills: dict[str, dict[str, Any]] = {}
    role_fit_skills: dict[str, int] = {}
    for s in position.required_skills or []:
        name = s.get("skill", "")
        if not name:
            continue
        sid = _skill_id(name)
        ps = per_skill.get(name) or {}
        score = ps.get("score")
        skills[sid] = {
            "lev": _skill_level_label(score),
            "evid": None,
            "src": None,
            "top": False,
            "weak": False,
        }
        if score is not None:
            role_fit_skills[sid] = int(score)

    # role_fit axes = criteria means + per-skill scores.
    role_fit = {**dim_means, **role_fit_skills}

    # All rollout/score reads below come from the request-level prefetch —
    # no per-candidate queries.
    roll = prefetch.rollouts(match.id)
    scores_by_rollout = prefetch.scores_by_rollout
    team_fit = compute_team_fit(match, rollouts=roll, scores_by_rollout=scores_by_rollout)
    overall_fit = compute_overall_fit(
        match, rollouts=roll, scores_by_rollout=scores_by_rollout, team_fit=team_fit
    )

    # Signals — 4 tiles from the strongest / weakest criteria.
    signals = _build_signals(position, dim_means)

    # Tell — one-line watch-out from the weakest criterion.
    tell = _build_tell(position, dim_means)

    # Per-scenario responses.
    responses = _build_responses(match, position, rollouts=roll)

    score = int(match.overall_score or report.get("overallScore") or 0)
    return {
        "id": candidate.id,
        "match_id": match.id,
        "name": candidate.display_name or "Candidate",
        "anchor": candidate.display_name or "Candidate",
        "anchor_short": candidate.display_name or "Candidate",
        "palette_color_var": palette_var,
        "score": score,
        "band": match.band or report.get("band") or "",
        "delta": _delta_str(score - population_mean),
        "linkedin_url": candidate.linkedin_url,
        "cv_available": bool(candidate.cv_path),
        "hero_quote": pick_hero_quote(match, rollouts=roll, scores=prefetch.scores_for(match.id)),
        "signals": signals,
        "overview": overview,
        "tell": tell,
        "skills": skills,
        "role_fit": role_fit,
        "team_fit": team_fit,
        "overall_fit": overall_fit,
        "responses": responses,
        "triage_decision": triage_decision,
    }


def _build_signals(position: models.Position, dim_means: dict[str, int]) -> list[dict[str, Any]]:
    """Up to four signal tiles: the strongest criteria first, with the single
    weakest flagged as a "tell". Each criterion appears at most once — with few
    criteria we simply show fewer tiles rather than duplicating one."""
    label_by_key = {c.key: c.label for c in position.criteria}
    if not dim_means:
        return []
    ranked = sorted(dim_means.items(), key=lambda kv: kv[1], reverse=True)
    weak_key = ranked[-1][0]
    # Show the top criteria (cap 4), flagging the weakest as the tell.
    tiles: list[dict[str, Any]] = []
    for key, val in ranked[:4]:
        tiles.append(
            {
                "lab": label_by_key.get(key, key),
                "v": _verdict_label(val),
                "e": f"{val}/100",
                "tell": key == weak_key and len(ranked) > 1,
            }
        )
    return tiles


def _build_tell(position: models.Position, dim_means: dict[str, int]) -> str:
    if not dim_means:
        return ""
    label_by_key = {c.key: c.label for c in position.criteria}
    weak_key, weak_val = min(dim_means.items(), key=lambda kv: kv[1])
    if weak_val >= 70:
        return ""
    return f"Watch: {label_by_key.get(weak_key, weak_key)} ({weak_val}/100) is the softest signal."


def _build_responses(
    match: models.Match,
    position: models.Position,
    db: Session | None = None,
    *,
    rollouts: list[models.Rollout] | None = None,
) -> dict[str, dict[str, Any]]:
    """Per-scenario response: the candidate's most substantive turn + score."""
    scenario_aggs = {
        sa["scenarioId"]: sa for sa in (match.report or {}).get("scenarioAggregates") or []
    }
    if rollouts is None:
        rollouts = list(
            db.execute(
                select(models.Rollout).where(models.Rollout.match_id == match.id)
            ).scalars()
        )
    # Group rollouts by scenario; pick the first completed rollout per scenario.
    by_scenario: dict[str, list[models.Rollout]] = {}
    for r in rollouts:
        if r.scenario_id:
            by_scenario.setdefault(r.scenario_id, []).append(r)

    out: dict[str, dict[str, Any]] = {}
    for sid, scenario_rollouts in by_scenario.items():
        rollout = scenario_rollouts[0]
        text, evidence_turns = _longest_candidate_turn(rollout)
        agg = scenario_aggs.get(sid) or {}
        out[sid] = {
            "score": int(agg.get("score") or 0),
            "text": text,
            "skills_shown": [],
            "evidence_turns": evidence_turns,
        }
    return out


def _longest_candidate_turn(rollout: models.Rollout) -> tuple[str, list[int]]:
    best_text = ""
    best_turn: int | None = None
    for turn in rollout.transcript or []:
        if (turn or {}).get("speaker_id") != "candidate":
            continue
        content = (turn or {}).get("content", "") or ""
        if len(content) > len(best_text):
            best_text = content
            best_turn = (turn or {}).get("turn")
    return best_text, ([best_turn] if best_turn is not None else [])


# ---------------------------------------------------------------------------
# Top / weak markers across the active set
# ---------------------------------------------------------------------------
def _mark_top_weak(active: list[dict[str, Any]], position: models.Position) -> None:
    """Set top/weak on overview + skill cells, row-wise across the active set.

    Top = strict max of the row (only when it beats the rest); weak = strict min
    (only when there is spread). A single-candidate set gets no markers.
    """
    if len(active) < 2:
        return

    def mark(field: str, row_ids: list[str], score_fn) -> None:
        for rid in row_ids:
            scored = [(cand, score_fn(cand, rid)) for cand in active]
            scored = [(c, v) for c, v in scored if v is not None]
            if len(scored) < 2:
                continue
            values = [v for _, v in scored]
            hi, lo = max(values), min(values)
            if hi == lo:
                continue
            for cand, v in scored:
                cell = cand[field].get(rid)
                if cell is None:
                    continue
                if v == hi:
                    cell["top"] = True
                elif v == lo:
                    cell["weak"] = True

    crit_ids = [c.key for c in position.criteria]
    mark("overview", crit_ids, lambda c, rid: c["role_fit"].get(rid))

    skill_ids = [_skill_id(s.get("skill", "")) for s in (position.required_skills or []) if s.get("skill")]
    mark("skills", skill_ids, lambda c, rid: c["role_fit"].get(rid))


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------
def _completed_matches(position_id: str, db: Session) -> list[tuple[models.Match, models.Candidate]]:
    """(match, candidate) for succeeded matches, ranked by score DESC.

    Only the latest succeeded match per candidate is kept.
    """
    rows = db.execute(
        select(models.Match, models.Candidate)
        .join(models.Candidate, models.Match.candidate_id == models.Candidate.id)
        # Eager-load the profile so the long-cycle tenure heuristic doesn't
        # lazy-load verified_profile once per candidate.
        .options(selectinload(models.Candidate.verified_profile))
        .where(
            models.Match.position_id == position_id,
            models.Match.status == "succeeded",
        )
        .order_by(
            models.Match.overall_score.desc(),
            models.Match.finished_at.desc(),
        )
    ).all()

    seen: set[str] = set()
    deduped: list[tuple[models.Match, models.Candidate]] = []
    for match, candidate in rows:
        if candidate.id in seen:
            continue
        seen.add(candidate.id)
        deduped.append((match, candidate))
    return deduped


def _triage_map(position_id: str, manager_id: str | None, db: Session) -> dict[str, str]:
    if not manager_id:
        return {}
    rows = db.execute(
        select(models.TriageDecision).where(
            models.TriageDecision.position_id == position_id,
            models.TriageDecision.manager_id == manager_id,
        )
    ).scalars()
    return {r.candidate_id: r.decision for r in rows}


def build_shortlist_report(
    position_id: str,
    candidate_ids: list[str] | None = None,
    top_n: int = 3,
    session: Session | None = None,
    manager_id: str | None = None,
) -> dict[str, Any]:
    """Compose the ShortlistComparisonReport (as a dict). See module docstring.

    Raises LookupError if the position does not exist.
    """
    db = session
    if db is None:  # pragma: no cover - always injected by the route
        raise ValueError("session is required")

    position = db.get(models.Position, position_id)
    if position is None:
        raise LookupError(f"Position {position_id!r} not found")

    ranked = _completed_matches(position_id, db)
    by_candidate = {c.id: (m, c) for m, c in ranked}
    population_scores = [m.overall_score or 0 for m, _ in ranked]
    population_mean = mean(population_scores) if population_scores else 0.0

    triage = _triage_map(position_id, manager_id, db)

    if candidate_ids:
        selection_mode = "explicit"
        top_n_applied = None
        active_pairs = [by_candidate[cid] for cid in candidate_ids if cid in by_candidate]
        active_ids = {cid for cid in candidate_ids if cid in by_candidate}
        available_pairs = [(m, c) for m, c in ranked if c.id not in active_ids][:_AVAILABLE_CAP]
    else:
        selection_mode = "auto_top_n"
        top_n_applied = top_n
        active_pairs = ranked[:top_n]
        available_pairs = ranked[top_n : top_n + _AVAILABLE_CAP]

    # Load every candidate's rollouts + scores in two queries up front, so the
    # per-candidate builders below issue zero further queries.
    all_match_ids = [m.id for m, _ in active_pairs] + [m.id for m, _ in available_pairs]
    prefetch = _prefetch(all_match_ids, db)

    def to_reports(pairs: list[tuple[models.Match, models.Candidate]]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for idx, (match, candidate) in enumerate(pairs):
            out.append(
                _build_candidate(
                    match=match,
                    candidate=candidate,
                    position=position,
                    db=db,
                    palette_var=_PALETTE_VARS[idx % len(_PALETTE_VARS)],
                    population_mean=population_mean,
                    triage_decision=triage.get(candidate.id, "undecided"),
                    prefetch=prefetch,
                )
            )
        return out

    active = to_reports(active_pairs)
    available = to_reports(available_pairs)
    _mark_top_weak(active, position)

    return {
        "position": _build_position_context(position),
        "scenarios": _build_scenarios(position),
        "candidates": active,
        "available_candidates": available,
        "selection_mode": selection_mode,
        "top_n_applied": top_n_applied,
    }


def build_triage_queue(
    position_id: str,
    manager_id: str | None,
    session: Session,
) -> dict[str, Any]:
    """Compose the TriageQueue payload — undecided candidates for this manager."""
    position = session.get(models.Position, position_id)
    if position is None:
        raise LookupError(f"Position {position_id!r} not found")

    ranked = _completed_matches(position_id, session)
    triage = _triage_map(position_id, manager_id, session)
    population_scores = [m.overall_score or 0 for m, _ in ranked]
    population_mean = mean(population_scores) if population_scores else 0.0

    prefetch = _prefetch([m.id for m, _ in ranked], session)

    candidates: list[dict[str, Any]] = []
    for match, candidate in ranked:
        # The queue shows everyone; the client greys out those already decided.
        score = int(match.overall_score or 0)
        candidates.append(
            {
                "id": candidate.id,
                "name": candidate.display_name or "Candidate",
                "anchor": candidate.display_name or "Candidate",
                "anchor_short": candidate.display_name or "Candidate",
                "score": score,
                "band": match.band or "",
                "delta": _delta_str(score - population_mean),
                "hero_quote": pick_hero_quote(
                    match,
                    rollouts=prefetch.rollouts(match.id),
                    scores=prefetch.scores_for(match.id),
                ),
                "signals": _build_signals(position, _dim_mean_map(match.report or {})),
            }
        )

    return {
        "position": _build_position_context(position),
        "candidates": candidates,
        "decided": triage,
    }
