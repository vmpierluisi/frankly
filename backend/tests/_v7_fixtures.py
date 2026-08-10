"""Shared fixtures for Manager Shortlist V7 backend tests.

Builds a small but realistic world: one position with two criteria + two
required skills, a synthetic team of two, two scenarios, and N candidates each
with a succeeded Match, rollouts, and rollout scores.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app import models


def make_session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    Session_ = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return Session_()


def _turn(turn: int, speaker_id: str, content: str, intent: str = "") -> dict:
    return {
        "turn": turn,
        "speaker_id": speaker_id,
        "speaker_role": "Candidate" if speaker_id == "candidate" else "Teammate",
        "content": content,
        "intent": intent,
        "internal_state": "",
    }


def build_world(db: Session, *, candidate_specs: list[dict]) -> dict:
    """Create a full position world.

    ``candidate_specs`` items: {name, overall, per_dim: {crit_key: score},
    scenario_scores: {scenario_key: score}, linkedin?, cv?}.
    """
    org = models.Organization(name="Meridian Capital Partners")
    team = models.Team(organization=org, name="Financial Analyst core team")
    db.add_all([org, team])
    db.flush()

    tm_a = models.SyntheticTeammate(
        team_id=team.id, name="Maya Kestrel", role_on_team="MD",
        seniority="senior", trait_sheet={}, narrative="Blunt. Demands rigor. Hates vague memos.",
        ordering=0,
    )
    tm_b = models.SyntheticTeammate(
        team_id=team.id, name="Devon Park", role_on_team="VP",
        seniority="mid", trait_sheet={}, narrative="Collaborative connector.",
        ordering=1,
    )
    db.add_all([tm_a, tm_b])

    position = models.Position(
        id="meridian-fa",
        organization_id=org.id,
        team_id=team.id,
        name="Meridian Capital Partners",
        role="Financial Analyst",
        role_family="financial_analyst",
        target_seniority="mid",
        is_open=True,
        required_skills=[
            {"skill": "Financial Modeling", "level": "senior"},
            {"skill": "Python", "level": "mid"},
        ],
    )
    db.add(position)
    db.flush()

    crit_honesty = models.Criterion(
        position_id=position.id, key="honesty", label="Intellectual honesty",
        description="Accuracy over advocacy.", weight=0.6, ordering=0,
    )
    crit_rigor = models.Criterion(
        position_id=position.id, key="rigor", label="Analytical rigor",
        description="Shows the work.", weight=0.4, ordering=1,
    )
    db.add_all([crit_honesty, crit_rigor])

    sc_a = models.MomentOfTruth(
        team_id=team.id, title="The asterisk", scenario_type="dyad",
        prompt="Maya asks you to soften a footnote.", candidate_role="Analyst",
        expected_arc="", scoring_dims=["honesty"], participating_roles=["Maya Kestrel, MD"],
        ordering=0,
    )
    sc_b = models.MomentOfTruth(
        team_id=team.id, title="The model gap", scenario_type="dyad",
        prompt="Devon flags a hole in your model.", candidate_role="Analyst",
        expected_arc="", scoring_dims=["rigor"], participating_roles=["Devon Park, VP"],
        ordering=1,
    )
    db.add_all([sc_a, sc_b])
    db.flush()

    scenario_by_key = {"asterisk": sc_a, "model_gap": sc_b}
    teammate_by_scenario = {"asterisk": tm_a.id, "model_gap": tm_b.id}

    now = datetime.now(timezone.utc)
    created: list[models.Candidate] = []
    for spec in candidate_specs:
        cand = models.Candidate(
            display_name=spec["name"],
            target_role_family="financial_analyst",
            target_seniority="mid",
            assessment_status="completed",
            bfi_responses={}, sjt_responses={},
            linkedin_url=spec.get("linkedin"),
            cv_path=spec.get("cv"),
        )
        db.add(cand)
        db.flush()

        per_dim = spec.get("per_dim", {"honesty": spec["overall"], "rigor": spec["overall"]})
        dimensional_fit = {
            k: {"mean": float(v), "std": 0.0, "n": 1, "judgeAgreement": 0.9}
            for k, v in per_dim.items()
        }
        scenario_aggs = [
            {"scenarioId": scenario_by_key[k].id, "title": scenario_by_key[k].title,
             "score": v, "nRollouts": 1, "perDim": {}}
            for k, v in spec.get("scenario_scores", {}).items()
        ]
        report = {
            "overallScore": spec["overall"],
            "behaviourFit": spec["overall"],
            "skillsFit": spec.get("skills_fit", 70),
            "dimensionalFit": dimensional_fit,
            "criterionScores": {
                k: {"score": int(v), "justification": f"{spec['name']} on {k}."}
                for k, v in per_dim.items()
            },
            "scenarioAggregates": scenario_aggs,
            "skillsFitDetails": {
                "score": spec.get("skills_fit", 70),
                "n_required": 2,
                "per_skill": [
                    {"skill": "Financial Modeling", "level": "senior",
                     "score": spec.get("fm_score", 75), "coverage": "covered"},
                    {"skill": "Python", "level": "mid",
                     "score": spec.get("py_score", 40), "coverage": "limited"},
                ],
            },
        }
        match = models.Match(
            candidate_id=cand.id, position_id=position.id, status="succeeded",
            overall_score=spec["overall"], band=spec.get("band", "Good fit"),
            report=report, finished_at=now,
        )
        db.add(match)
        db.flush()

        # Rollouts — one per scenario, with candidate + teammate turns.
        for k, scenario in scenario_by_key.items():
            sc_score = spec.get("scenario_scores", {}).get(k, spec["overall"])
            rollout = models.Rollout(
                match_id=match.id, scenario_id=scenario.id, rollout_index=0,
                transcript=[
                    _turn(0, teammate_by_scenario[k], "What's your read?"),
                    _turn(1, "candidate",
                          f"{spec['name']}'s considered answer on {scenario.title}.",
                          intent=spec.get("intent", "productive_disagreement")),
                ],
                final_state={"scenario_title": scenario.title},
                duration_turns=2, status="completed",
            )
            db.add(rollout)
            db.flush()
            dim_key = scenario.scoring_dims[0]
            db.add(models.RolloutScore(
                rollout_id=rollout.id, dimension_key=dim_key, score=sc_score,
                justification=f"{spec['name']} scored {sc_score} on {dim_key}.",
                evidence_turns=[1], judge_model="judge-v1", confidence=0.9,
            ))
        created.append(cand)

    db.commit()
    return {
        "position": position, "team": team, "candidates": created,
        "teammates": {"maya": tm_a, "devon": tm_b},
        "scenarios": {"asterisk": sc_a, "model_gap": sc_b},
        "criteria": {"honesty": crit_honesty, "rigor": crit_rigor},
    }
