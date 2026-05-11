"""Pre-seed simulation matches for the demo leaderboards.

For each seed position, picks N candidates deterministically (mix of seniorities)
and runs the full V2 simulation synchronously, persisting results.

Idempotent — skips any (candidate, position) pair that already has a
`status='succeeded'` match.

Usage:
    docker compose exec backend python -m app.scripts.preseed_matches --per-company 10
    docker compose exec backend python -m app.scripts.preseed_matches --per-company 10 --fast

Options:
    --per-company N    How many candidates to seed per company (default: 10)
    --fast             Force SIM_FAST_MODE=1 regardless of env setting
    --company ID       Only seed for this company id (repeat for multiple)

Cost estimate (fast mode, K=1, 2 scenarios, 1 judge):
    ~$0.10–0.20 per candidate, ~$1–2 for 10 candidates × 2 positions.
Time:  ~30s/candidate × 10 = ~5 minutes total.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

try:
    from dotenv import load_dotenv
    _here = os.path.dirname(os.path.abspath(__file__))
    for _p in [
        os.path.join(_here, "../../.env"),
        os.path.join(_here, "../../../.env"),
    ]:
        if os.path.exists(_p):
            load_dotenv(_p)
            break
except ImportError:
    pass

from sqlalchemy import select

from app.db import SessionLocal
from app import models
from app.services.matching_engine import find_open_companies_for_candidate
from app.services.simulation import simulation_matcher
from app.config import settings


def _pick_candidates(db, position: models.Position, n: int) -> list[models.Candidate]:
    """Pick N seed candidates compatible with this company's role family + seniority.

    Selection is deterministic: sort by id (stable across runs), then take the
    first N. Excludes candidates that already have a succeeded match for this position.
    """
    from app.lib.role_families import compatible_seniorities

    compat = compatible_seniorities(position.target_seniority or "mid")

    # Already-succeeded candidate ids for this position.
    succeeded_ids: set[str] = set(
        row[0]
        for row in db.execute(
            select(models.Match.candidate_id).where(
                models.Match.position_id == position.id,
                models.Match.status == "succeeded",
            )
        ).all()
    )

    candidates = db.execute(
        select(models.Candidate).where(
            models.Candidate.is_seed == True,  # noqa: E712
            models.Candidate.target_role_family == position.role_family,
            models.Candidate.target_seniority.in_(compat),
            models.Candidate.assessment_status == "completed",
        ).order_by(models.Candidate.id)
    ).scalars().all()

    # Exclude already-seeded, then pick first N.
    eligible = [c for c in candidates if c.id not in succeeded_ids]
    return eligible[:n]


async def _seed_one(
    company: models.Position,
    candidate: models.Candidate,
    dry_run: bool = False,
) -> str:
    """Run simulation for one (candidate, position) pair. Returns status string."""
    with SessionLocal() as db:
        # Refresh objects in this session.
        position_db = db.get(models.Position, position.id)
        candidate_db = db.get(models.Candidate, candidate.id)

        if position_db is None or candidate_db is None:
            return "skip:not_found"

        # Create or reuse a pending Match row.
        existing = db.execute(
            select(models.Match).where(
                models.Match.candidate_id == candidate_db.id,
                models.Match.position_id == position_db.id,
            )
        ).scalar_one_or_none()

        if existing is not None and existing.status == "succeeded":
            return "skip:already_succeeded"

        if existing is not None:
            match = existing
            match.status = "running"
            match.error_message = None
        else:
            match = models.Match(
                candidate_id=candidate_db.id,
                position_id=position_db.id,
                status="running",
                overall_score=0,
                band="",
                band_note="",
                report={},
            )
            db.add(match)

        db.flush()
        match_id = match.id

        if dry_run:
            db.rollback()
            return "dry_run"

        try:
            k = 1 if settings.sim_fast_mode else None
            kwargs: dict = dict(
                match_id=match_id,
                candidate=candidate_db,
                company=position_db,
                db=db,
            )
            if k is not None:
                kwargs["k_per_scenario"] = k

            report = await asyncio.wait_for(
                simulation_matcher.run_match(**kwargs),
                timeout=settings.sim_match_wall_timeout_s,
            )
            match.overall_score = int(report.get("overallScore", 0))
            match.band = report.get("band", "")
            match.band_note = report.get("bandNote", "")
            match.report = report
            match.status = "succeeded"
            db.commit()
            return f"ok:{match.overall_score}"
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            # Mark failed in a fresh transaction.
            with SessionLocal() as err_db:
                err_match = err_db.get(models.Match, match_id)
                if err_match:
                    err_match.status = "failed"
                    err_match.error_message = str(exc)[:500]
                    err_db.commit()
            return f"fail:{exc}"


async def preseed(
    per_company: int,
    position_ids: list[str] | None,
    dry_run: bool,
) -> None:
    with SessionLocal() as db:
        q = select(models.Position).where(models.Position.is_open == True)  # noqa: E712
        if position_ids:
            q = q.where(models.Position.id.in_(position_ids))
        positions = db.execute(q).scalars().all()

    if not positions:
        print("No open positions found. Check that seed data is loaded and migrations are run.")
        return

    for position in positions:
        print(f"\n{'='*60}")
        print(f"Position: {position.name} ({position.id})")
        print(f"  role_family={position.role_family}, target_seniority={position.target_seniority}")

        with SessionLocal() as db:
            position_fresh = db.get(models.Position, position.id)
            candidates = _pick_candidates(db, position_fresh, per_company)

        if not candidates:
            print("  No eligible seed candidates found.")
            print("  → Run seed_candidates.py first: python -m app.scripts.seed_candidates --count 100")
            continue

        print(f"  Picked {len(candidates)} candidate(s) to simulate.")

        sem = asyncio.Semaphore(2)  # max 2 concurrent matches per company

        async def _bounded(c):
            async with sem:
                result = await _seed_one(position, c, dry_run=dry_run)
                label = c.display_name or c.id[:8]
                print(f"    [{label:<30}] {result}")
                return result

        results = await asyncio.gather(*[_bounded(c) for c in candidates])

        ok = sum(1 for r in results if r.startswith("ok:"))
        skipped = sum(1 for r in results if r.startswith("skip:"))
        failed = sum(1 for r in results if r.startswith("fail:"))
        print(f"\n  → {ok} succeeded, {skipped} skipped, {failed} failed")

    print(f"\n{'='*60}")
    print("Preseed complete. Refresh the manager dashboard to see the leaderboards.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Pre-seed demo leaderboards with V2 simulation results.")
    parser.add_argument("--per-position", type=int, default=10, metavar="N",
                        help="Candidates to simulate per company (default: 10)")
    parser.add_argument("--position", action="append", dest="position_ids", metavar="ID",
                        help="Only seed this company (repeat for multiple). Default: all open.")
    parser.add_argument("--fast", action="store_true",
                        help="Force SIM_FAST_MODE=1 (K=1, 2 scenarios, 1 judge)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would run without calling the LLM")
    args = parser.parse_args()

    if args.fast:
        os.environ["SIM_FAST_MODE"] = "1"
        # Re-read settings after env override.
        settings.__class__.model_rebuild()  # type: ignore[attr-defined]

    fast_label = " [FAST MODE]" if (args.fast or settings.sim_fast_mode) else ""
    print(f"preseed_matches{fast_label}")
    print(f"  per_company={args.per_company}, positions={args.position_ids or 'all open'}")
    print(f"  dry_run={args.dry_run}")

    asyncio.run(preseed(
        per_company=args.per_company,
        position_ids=args.position_ids,
        dry_run=args.dry_run,
    ))


if __name__ == "__main__":
    main()
