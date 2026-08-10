# frankly

**A behavioral hiring-screening platform built around a multi-agent simulation.**

Instead of scoring a résumé, frankly synthesizes a candidate's behavioral
*persona* from a short intake, then drops that persona into a simulated version
of a specific team and watches how it handles the role's hardest moments — a
partner pushing back on a memo, a teammate flagging a hole in a model, a
disagreement that has to stay productive. An ensemble of LLM judges scores each
simulated rollout against the role's criteria, and the hiring manager gets a
comparative, evidence-linked fit report.

Two principles are enforced in the backend, not just the UI:

- **Blind matching** — candidate-facing API responses never reveal which role or
  company a candidate is being evaluated for.
- **Mutual opt-in** — a manager's shortlist decisions never contact the
  candidate; only an explicit interview invite does.

> Built as a full-stack portfolio project: a FastAPI + React application with a
> real simulation/judging pipeline, Supabase auth, Alembic-migrated Postgres, and
> a tested backend. It's a research-grade prototype, not a production service —
> see [Security & auth](#security--auth).

---

## What's interesting here (engineering)

- **Multi-agent simulation pipeline** (`backend/app/services/simulation/`) —
  synthesizes a synthetic team, drafts role-specific scenarios, runs multi-agent
  rollouts (candidate persona vs. teammates), and scores each with an ensemble of
  judges before aggregating into a per-match `FitProfile`. Prompt scaffolding is
  versioned so results stay comparable across changes.
- **Derived comparison layer, no double-storage** — the manager "shortlist"
  report (team-fit per teammate, six composite fit axes, a rule-based "hero
  quote," per-scenario responses) is computed at request time from existing
  rollout/judge data rather than persisted, keeping the simulation output the
  single source of truth.
- **A real performance fix under load.** The shortlist endpoint originally issued
  an N+1 storm — roughly 8 queries per candidate across ~23 candidates (~180
  sequential round-trips), invisible on local SQLite but painful against a remote
  Postgres. It now batch-loads all rollouts and scores in **two** queries up
  front and threads them through the builders, collapsing query count to a small
  constant regardless of candidate count. A regression test asserts the count
  stays flat as candidates grow.
- **Enforced product invariants.** Blind matching and mutual opt-in live at the
  API boundary; the matcher/aggregator service contract is kept stable so the
  scoring core can be swapped without touching the presentation layer.
- **Tested and migrated.** ~260 backend tests (pytest) covering services and
  routes; schema evolution is managed through 17 Alembic migrations.

**Stack:** Python 3.11 · FastAPI · SQLAlchemy · Alembic · Pydantic · pytest ·
React · Vite · React Router · Supabase (auth + Postgres) · OpenRouter (LLM
access, model-agnostic) · Docker Compose.

---

## The manager surface

Opening a position lands on the **shortlist compare** page
(`/manager/positions/:id/shortlist`) — an auto-ranked top-N comparison with three
tabs:

- **Overview** — a dense, cell-clickable comparison table; every score drills to
  its supporting evidence.
- **Scenarios** — per-scenario response cards, with a "you would have missed
  this" flag when a below-threshold candidate out-responds the shortlist on a
  given scenario.
- **Fit chart** — an SVG radar with role / team / overall sub-views, so "who
  fits *this team*" is visible rather than merely inferable.

A floating decide bar (invite / decline) persists across tabs, and an optional
**Triage** page lets a manager swipe candidates manually instead of trusting the
auto-ranking.

---

## Run it locally

```bash
cp .env.example .env    # fill in the values below
docker compose up --build
```

- Frontend: <http://localhost:5173>
- API + interactive docs: <http://localhost:8000/docs>

The fastest way to explore without wiring up Supabase is to set `DEV_MODE=true`
in `.env`, which bypasses auth and treats you as a manager (local only — see the
security note). You still need an `OPENROUTER_API_KEY` to run live matches.

The backend seeds two deliberately contrasting Financial-Analyst positions on
first boot — **Meridian Capital Partners** (rewards patience, written dissent,
intellectual honesty) and **Kestrel Growth Partners** (rewards speed of
conviction, pattern recognition, verbal agility) — so the same candidate scores
differently against each. That contrast is the point.

### Backend tests

```bash
cd backend
python -m pytest -q
```

---

## Configuration

Copy `.env.example` to `.env`. `.env` is gitignored — never commit real values.

| Var | Required | Notes |
|-----|----------|-------|
| `OPENROUTER_API_KEY` | yes | LLM access — <https://openrouter.ai/keys> |
| `OPENROUTER_MODEL` | no | Any OpenAI-compatible OpenRouter model; swappable. |
| `DATABASE_URL` | no | SQLite by default; a `postgresql://` URL enables Alembic on boot. |
| `SUPABASE_URL` / `SUPABASE_PUBLISHABLE_KEY` / `SUPABASE_SECRET_KEY` | for auth | Required unless `DEV_MODE=true`. |
| `MANAGER_EMAILS` | for auth | Comma-separated emails granted the manager role. |
| `ADMIN_PASSWORD` | **prod** | Bearer token for `/admin/*`. **Change the default.** |
| `DEV_MODE` | no | `true` **bypasses all auth** — local dev only. |
| `CORS_ALLOW_ORIGINS` | no | Comma-separated origins. Don't use `*` with credentials. |

---

## Architecture

```
Candidate intake ─┐
                  ├─▶ persona synthesis ─▶ simulation ─▶ judging ─▶ fit report
Verified profile ─┘        (Python)      (multi-agent)  (ensemble)   (manager)
```

- **Backend** — FastAPI + SQLAlchemy + Alembic. Auth verifies Supabase JWTs via
  JWKS; the `manager` role is granted by email allowlist. SQLite locally,
  Postgres in production (a `postgresql://` URL triggers migrations on startup).
- **Simulation** — `services/simulation/` runs the team synthesis → scenario
  drafting → rollout → judging → aggregation pipeline. LLM calls route through
  `services/openrouter.py`, so the model is a config value.
- **Frontend** — Vite + React + React Router with Supabase JS for auth. In dev,
  Vite proxies API paths to the backend so the browser talks to one origin.

```
backend/
  app/
    routes/        candidates, positions, matches, triage, audit, …
    services/
      comparison_builder.py   shortlist report composer (request-time derived)
      composite_fit.py        per-teammate + composite fit axes
      hero_quote.py           defining-turn picker
      simulation/             persona → team → scenarios → rollouts → judges
    models.py schemas.py auth.py config.py
  alembic/versions/           migrations 0001 … 0017
  tests/                      pytest suite
frontend/
  src/
    pages/         ManagerDashboard, ShortlistComparePage, intake, …
    components/v7/ shortlist / triage / radar components
    api.js design.js
```

---

## Security & auth

This is a prototype; a few defaults matter before exposing it anywhere public:

- **`DEV_MODE=true` disables authentication entirely** and treats every request
  as a manager. Safe default is `false`. Never set it true on a deployed host.
- **`ADMIN_PASSWORD` guards `/admin/*`** (validation, match logs, training
  export). Its default is visible in this repo — override it in any real deploy.
- **Auth is enforced server-side.** Routes verify a Supabase JWT; blind matching
  and mutual opt-in are backend invariants, not UI conventions.
- **LLM data flow.** Intake, personas, and simulation transcripts are sent to
  OpenRouter (and the upstream model) to run matches — use fictional or consented
  data, never real candidate PII in a demo.

No secrets, keys, or databases are tracked in this repository or its history.

---

## License

Licensed under the [Apache License 2.0](LICENSE).
