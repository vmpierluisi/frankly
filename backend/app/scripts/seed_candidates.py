"""Seed the candidate pool with LLM-generated fake profiles.

Usage:
    python -m app.scripts.seed_candidates --count 100
    python -m app.scripts.seed_candidates --count 100 --force   # replace existing seeds
    python -m app.scripts.seed_candidates --clear               # delete all seeds

Cost: ~100 calls to claude-haiku-4-5 at ~$0.01–0.02 total.
Time: ~3–5 minutes with semaphore(8) concurrency.
"""
from __future__ import annotations

import argparse
import asyncio
import re
import sys
import os

# Allow running as `python -m app.scripts.seed_candidates` from backend/.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

# Load .env from backend/ or project root before importing settings.
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

from app.db import SessionLocal
from app import models
from app.services.persona import synthesize_persona
from app.services.persona_generator import ARCHETYPES, generate_synthetic_responses


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


async def _generate_one(
    sem: asyncio.Semaphore,
    archetype: str,
    idx: int,
) -> models.Candidate:
    async with sem:
        print(f"  [{idx:>3}] generating — {archetype[:50]}…")
        try:
            data = await generate_synthetic_responses(archetype)
        except Exception as e:
            print(f"  [{idx:>3}] ERROR: {e} — using fallback random responses")
            # Fallback: random but valid responses so the seed still completes.
            import random
            bfi_ids = ["e1", "a1", "c1", "n1", "o1", "e2", "a2", "c2", "n2", "o2"]
            data = {
                "display_name": f"Candidate {idx}",
                "bfi_responses": {k: random.randint(1, 5) for k in bfi_ids},
                "sjt_responses": {
                    f"sjt{i}": random.choice(["a", "b", "c", "d"]) for i in range(1, 4)
                },
            }

    persona = synthesize_persona(data["bfi_responses"], data["sjt_responses"])
    slug = _slug(data["display_name"])

    return models.Candidate(
        display_name=data["display_name"],
        bfi_responses=data["bfi_responses"],
        sjt_responses=data["sjt_responses"],
        cached_big_five=persona["bigFive"],
        cached_sjt_signals=persona["sjtSignals"],
        cached_inconsistencies=persona["inconsistencies"],
        cached_narrative=persona["narrative"],
        assessment_status="completed",
        is_seed=True,
        linkedin_url=f"https://linkedin.com/in/{slug}",
        github_url=f"https://github.com/{slug}",
    )


async def seed(count: int, force: bool) -> None:
    with SessionLocal() as db:
        existing = db.query(models.Candidate).filter(models.Candidate.is_seed == True).count()

    if existing >= count and not force:
        print(f"Pool already has {existing} seeds (≥ {count}). Use --force to replace.")
        return

    if force and existing > 0:
        print(f"--force: deleting {existing} existing seed rows…")
        with SessionLocal() as db:
            db.query(models.Candidate).filter(models.Candidate.is_seed == True).delete()
            db.commit()

    print(f"Generating {count} synthetic candidates (semaphore=8)…")

    sem = asyncio.Semaphore(8)
    archetypes = [ARCHETYPES[i % len(ARCHETYPES)] for i in range(count)]
    tasks = [_generate_one(sem, arch, i + 1) for i, arch in enumerate(archetypes)]
    candidates = await asyncio.gather(*tasks)

    print("Inserting into database…")
    with SessionLocal() as db:
        for c in candidates:
            db.add(c)
        db.commit()

    print(f"Done. {count} seed candidates inserted.")


def clear() -> None:
    with SessionLocal() as db:
        n = db.query(models.Candidate).filter(models.Candidate.is_seed == True).delete()
        db.commit()
    print(f"Deleted {n} seed candidates (and their cached matches via CASCADE).")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the candidate pool with LLM-generated profiles.")
    parser.add_argument("--count", type=int, default=0, help="Number of seeds to generate")
    parser.add_argument("--force", action="store_true", help="Replace existing seeds")
    parser.add_argument("--clear", action="store_true", help="Delete all seed candidates and exit")
    args = parser.parse_args()

    if args.clear:
        clear()
        return

    if args.count <= 0:
        parser.error("--count N is required (e.g. --count 100)")

    asyncio.run(seed(args.count, args.force))


if __name__ == "__main__":
    main()
