"""FastAPI app entry point."""
from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .db import SessionLocal, init_db
from .routes import (
    admin,
    calibration,
    candidates,
    interviews,
    matches,
    notifications,
    organizations,
    positions,
    scenarios,
    team,
    teams,
    templates,
)
from .schemas import HealthOut
from .seed_data import seed_companies, backfill_company_role_families
from .services.simulation import background_runner


def _run_migrations() -> None:
    """Run Alembic migrations programmatically on startup (Postgres only)."""
    from alembic.config import Config
    from alembic import command

    # alembic.ini lives one directory above app/
    ini_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "alembic.ini")
    cfg = Config(ini_path)
    cfg.set_main_option("sqlalchemy.url", settings.database_url)
    command.upgrade(cfg, "head")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.use_alembic:
        _run_migrations()
    else:
        init_db()

    with SessionLocal() as db:
        seed_companies(db)
        backfill_company_role_families(db)

    await background_runner.sweep_pending()
    yield

    await background_runner.shutdown()


app = FastAPI(
    title="hiring-sim",
    version="0.1.0",
    description=(
        "v0 hiring-screening platform. Screening signal only — not a hiring "
        "decision tool. Candidates never know which companies they are being "
        "matched against; both parties must opt in before an interview."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthOut, tags=["meta"])
def health() -> HealthOut:
    return HealthOut(ok=True)


app.include_router(admin.router)
app.include_router(candidates.router)
app.include_router(positions.router)
app.include_router(templates.router)
app.include_router(matches.router)
app.include_router(team.router)
app.include_router(scenarios.router)
app.include_router(organizations.router)
app.include_router(teams.router)
app.include_router(interviews.router)
app.include_router(notifications.router)
app.include_router(calibration.router)
