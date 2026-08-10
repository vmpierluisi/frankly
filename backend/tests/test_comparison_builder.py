"""Unit tests for services/comparison_builder.py (V7)."""
from __future__ import annotations

import pytest

from app.services.comparison_builder import build_shortlist_report
from tests._v7_fixtures import build_world, make_session


@pytest.fixture()
def world_db():
    db = make_session()
    world = build_world(
        db,
        candidate_specs=[
            {"name": "Alex", "overall": 90, "linkedin": "https://li/alex", "cv": "alex.pdf",
             "scenario_scores": {"asterisk": 92, "model_gap": 88}},
            {"name": "Priya", "overall": 82,
             "scenario_scores": {"asterisk": 80, "model_gap": 84}},
            {"name": "Sam", "overall": 74,
             "scenario_scores": {"asterisk": 70, "model_gap": 78}},
            {"name": "Devon", "overall": 66,
             "scenario_scores": {"asterisk": 95, "model_gap": 40}},  # scenario spike
            {"name": "Jordan", "overall": 58},
        ],
    )
    yield world, db
    db.close()


def test_auto_top_n_default_returns_top_three(world_db):
    _, db = world_db
    report = build_shortlist_report("meridian-fa", top_n=3, session=db)

    assert report["selection_mode"] == "auto_top_n"
    assert report["top_n_applied"] == 3
    names = [c["name"] for c in report["candidates"]]
    assert names == ["Alex", "Priya", "Sam"]
    # Remainder become available_candidates, still ranked.
    avail = [c["name"] for c in report["available_candidates"]]
    assert avail == ["Devon", "Jordan"]


def test_widening_n_keeps_top_three_prefix(world_db):
    _, db = world_db
    top3 = build_shortlist_report("meridian-fa", top_n=3, session=db)
    top5 = build_shortlist_report("meridian-fa", top_n=5, session=db)

    n3 = [c["name"] for c in top3["candidates"]]
    n5 = [c["name"] for c in top5["candidates"]]
    assert n5[:3] == n3  # same top-3, same order
    assert n5 == ["Alex", "Priya", "Sam", "Devon", "Jordan"]


def test_explicit_mode_selects_exact_set(world_db):
    _, db = world_db
    report = build_shortlist_report(
        "meridian-fa", candidate_ids=None, top_n=3, session=db
    )
    ids = [c["id"] for c in report["candidates"]]

    explicit = build_shortlist_report(
        "meridian-fa", candidate_ids=[ids[0], ids[2]], session=db
    )
    assert explicit["selection_mode"] == "explicit"
    assert explicit["top_n_applied"] is None
    assert [c["id"] for c in explicit["candidates"]] == [ids[0], ids[2]]
    # The un-selected candidate appears in available.
    assert ids[1] in [c["id"] for c in explicit["available_candidates"]]


def test_palette_assigned_in_rank_order(world_db):
    _, db = world_db
    report = build_shortlist_report("meridian-fa", top_n=3, session=db)
    vars_ = [c["palette_color_var"] for c in report["candidates"]]
    assert vars_ == ["--c-slot1", "--c-slot2", "--c-slot3"]


def test_top_and_weak_markers_across_active_set(world_db):
    _, db = world_db
    report = build_shortlist_report("meridian-fa", top_n=3, session=db)
    # Alex has the highest honesty; Sam the lowest → top/weak set.
    alex = report["candidates"][0]
    sam = report["candidates"][2]
    assert alex["overview"]["honesty"]["top"] is True
    assert sam["overview"]["honesty"]["weak"] is True


def test_candidate_payload_shape(world_db):
    _, db = world_db
    report = build_shortlist_report("meridian-fa", top_n=1, session=db)
    alex = report["candidates"][0]

    assert alex["linkedin_url"] == "https://li/alex"
    assert alex["cv_available"] is True
    assert alex["hero_quote"]["text"]
    assert set(alex["overall_fit"].keys()) >= {"role_fit", "team_chem"}
    assert alex["team_fit"]  # per-teammate
    assert alex["responses"]  # per-scenario
    assert alex["delta"].startswith("+")  # top scorer above the mean


def test_position_context_includes_axes_criteria_skills_team(world_db):
    _, db = world_db
    report = build_shortlist_report("meridian-fa", top_n=3, session=db)
    pos = report["position"]
    assert pos["company_name"] == "Meridian Capital Partners"
    assert {c["id"] for c in pos["criteria"]} == {"honesty", "rigor"}
    assert len(pos["skills"]) == 2
    assert len(pos["team"]) == 2
    assert len(pos["overall_axes"]) == 6
    assert len(report["scenarios"]) == 2


def test_criteria_map_to_primary_scenario(world_db):
    world, db = world_db
    report = build_shortlist_report("meridian-fa", top_n=3, session=db)
    crit_by_id = {c["id"]: c for c in report["position"]["criteria"]}
    # honesty is scored in the asterisk scenario; rigor in the model_gap.
    assert crit_by_id["honesty"]["scenario_id"] == world["scenarios"]["asterisk"].id
    assert crit_by_id["rigor"]["scenario_id"] == world["scenarios"]["model_gap"].id


def test_unknown_position_raises(world_db):
    _, db = world_db
    with pytest.raises(LookupError):
        build_shortlist_report("does-not-exist", session=db)


def _count_queries(db, fn):
    """Count SQL statements emitted while calling fn()."""
    from sqlalchemy import event

    count = {"n": 0}

    def before(conn, cursor, statement, params, context, executemany):
        count["n"] += 1

    engine = db.get_bind()
    event.listen(engine, "before_cursor_execute", before)
    try:
        fn()
    finally:
        event.remove(engine, "before_cursor_execute", before)
    return count["n"]


def test_query_count_is_flat_regardless_of_candidate_count():
    """The prefetch collapses the old N+1 storm: building a 3-candidate report
    and a 5-candidate report must issue the same (small, constant) number of
    queries — proof there is no per-candidate rollout/score fan-out."""
    db = make_session()
    build_world(
        db,
        candidate_specs=[{"name": f"C{i}", "overall": 90 - i} for i in range(8)],
    )

    q3 = _count_queries(db, lambda: build_shortlist_report("meridian-fa", top_n=3, session=db))
    q5 = _count_queries(db, lambda: build_shortlist_report("meridian-fa", top_n=5, session=db))

    # Same query count for 3 vs 5 active (available set covers the rest either
    # way) — the prefetch means candidate count doesn't drive query count.
    assert q3 == q5
    # A small constant (position + relationship loads + 2 prefetch queries).
    # Well under the old per-candidate N+1 (which was ~8 queries × N candidates).
    assert q3 <= 12
    db.close()
