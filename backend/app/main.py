"""FastAPI app entry point."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .db import SessionLocal, init_db
from .routes import candidates, companies, matches, templates
from .schemas import HealthOut
from .seed_data import seed_companies


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    # Seed the two fictional companies on first boot. Idempotent — existing
    # rows are left alone so manager edits survive restarts.
    with SessionLocal() as db:
        seed_companies(db)
    yield


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


app.include_router(candidates.router)
app.include_router(companies.router)
app.include_router(templates.router)
app.include_router(matches.router)
