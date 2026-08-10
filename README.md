# frankly

A hiring **screening** tool — not a hiring-decision tool. A candidate completes
a short intake (a BFI-10 personality inventory, situational-judgment items, and
an optional verified profile built from their CV / LinkedIn / GitHub). The
platform synthesizes a behavioral **persona**, then runs that persona through a
multi-agent **simulation** of a specific role's team across a library of
"moments of truth." A judging layer scores each simulated rollout against the
role's criteria, and the manager sees a comparative **fit report**.

Two product invariants shape the whole design:

- **Blind matching.** Candidate-facing API responses never reveal which role or
  company a candidate is being evaluated for. This is enforced at the API layer.
- **Mutual opt-in before contact.** A manager's triage/shortlist decisions never
  notify the candidate. Only an actual interview schedule reaches out.

> **Status: research prototype.** This is a demo-grade build meant to survive a
> live walkthrough, not a hardened production service. Read the
> [Security & auth](#security--auth) section before deploying it anywhere
> reachable from the internet.

---

## Quickstart

```bash
cp .env.example .env    # then fill in the values below
docker compose up --build
```

- Frontend: <http://localhost:5173>
- Backend API + docs: <http://localhost:8000> · <http://localhost:8000/docs>

At minimum you need an `OPENROUTER_API_KEY` (for the LLM calls) and, unless you
run in `DEV_MODE`, a Supabase project for auth. See
[Configuration](#configuration).

The backend seeds two contrasting fictional Financial-Analyst positions on first
boot so the simulation has something to compare against:

- **Meridian Capital Partners** — mid-market private credit. Rewards patience,
  written dissent, intellectual honesty.
- **Kestrel Growth Partners** — late-stage growth equity. Rewards speed of
  conviction, pattern recognition, verbal agility.

The same candidate should score differently against each — that contrast is the
point.

---

## Architecture

```
Candidate intake ─┐
                  ├─▶ persona synthesis ─▶ simulation pipeline ─▶ fit report
Verified profile ─┘        (Python)         (multi-agent + judges)     (manager)
```

**Backend** — FastAPI (Python 3.11+), SQLAlchemy, Alembic. Auth is Supabase
JWT (verified via JWKS); role (`manager` vs `candidate`) is derived from an
email allowlist. SQLite locally; Postgres (e.g. Supabase) in production — a
`postgresql://` `DATABASE_URL` makes the app run Alembic migrations on startup.

**Simulation pipeline** (`backend/app/services/simulation/`) — synthesizes a
team, drafts scenarios, runs multi-agent rollouts, scores them with an ensemble
of judges, and aggregates into a `FitProfile` per match. LLM access goes through
OpenRouter (`services/openrouter.py`), so the model is swappable via
`OPENROUTER_MODEL`.

**Frontend** — Vite + React + React Router, Supabase JS for auth. Editorial
design tokens live in `frontend/src/design.js`. In dev, Vite proxies API paths
to the backend, so the browser talks to a single origin (no CORS).

### Manager Shortlist (V7)

The manager's primary surface is the **shortlist compare** page at
`/manager/positions/:id/shortlist`. Opening a position lands here on an
auto-ranked top-N comparison, with three tabs:

- **Overview** — a dense, cell-clickable comparison table; every score drills to
  its evidence.
- **Scenarios** — per-scenario response cards, including a "you would have missed
  this" flag when a below-threshold candidate out-responds the shortlist.
- **Fit chart** — an SVG radar with role / team / overall sub-views.

A floating decide bar (invite / decline) persists across tabs. An optional
**Triage** page (`/triage`) lets a manager swipe candidates manually instead of
trusting the auto-ranking. See `V7_IMPLEMENTATION_PLAN.md` for the full spec.

---

## Configuration

Copy `.env.example` to `.env` and fill it in. `.env` is gitignored — never commit
real values.

| Var | Required | Notes |
|-----|----------|-------|
| `OPENROUTER_API_KEY` | yes | <https://openrouter.ai/keys> |
| `OPENROUTER_MODEL` | no | Any OpenAI-compatible OpenRouter model. |
| `DATABASE_URL` | no | SQLite by default; a `postgresql://` URL enables Alembic on boot. |
| `SUPABASE_URL` / `SUPABASE_PUBLISHABLE_KEY` / `SUPABASE_SECRET_KEY` | for auth | Required unless `DEV_MODE=true`. |
| `MANAGER_EMAILS` | for auth | Comma-separated emails that get the manager role. |
| `ADMIN_PASSWORD` | **prod** | Bearer token for `/admin/*`. **Change the default.** |
| `DEV_MODE` | no | `true` **bypasses all auth** — local dev only. |
| `CORS_ALLOW_ORIGINS` | no | Comma-separated origins. Don't use `*` with credentials. |
| `VITE_SUPABASE_URL` / `VITE_SUPABASE_PUBLISHABLE_KEY` / `VITE_MANAGER_EMAILS` | for auth | Browser-side mirrors of the above. |

---

## Security & auth

This repo is safe to publish — no secrets, keys, or databases are tracked, and
none appear in git history. But because the source is now public, a few
deployment defaults matter:

- **`DEV_MODE=true` disables authentication entirely** and treats every request
  as a manager. It exists for local development and has a safe default
  (`false`). **Never set it true on any deployed or public host.**
- **`ADMIN_PASSWORD` guards the `/admin/*` routes** (validation, match logs,
  training export). Its default (`changeme-admin`) is visible in this repo, so
  you **must** override it with a strong secret in any real deployment.
- **Auth model.** Backend routes verify a Supabase JWT via JWKS; the
  `manager` role is granted only to emails in `MANAGER_EMAILS`. Blind matching
  and mutual opt-in are enforced server-side, not merely hidden in the UI.
- **CORS.** Set `CORS_ALLOW_ORIGINS` to your real frontend origin(s). The app
  sends credentials, so a `*` origin is unsafe and unsupported.
- **LLM data flow.** Candidate intake, personas, and simulation transcripts are
  sent to OpenRouter (and thus the upstream model provider) to run matches. Use
  fictional or consented data; don't feed real candidate PII into a demo.

If you deploy this, also put it behind HTTPS and rotate the Supabase and
OpenRouter keys you use for it.

---

## Repo layout

```
.
├── backend/                       FastAPI + SQLAlchemy + Alembic
│   ├── app/
│   │   ├── main.py                app factory, routers, lifespan seed
│   │   ├── config.py              env-driven Settings
│   │   ├── auth.py                Supabase JWT (JWKS) dependencies
│   │   ├── models.py              ORM models (Candidate, Position, Match, …)
│   │   ├── schemas.py             Pydantic request/response shapes
│   │   ├── routes/                candidates, positions, matches, triage, …
│   │   └── services/
│   │       ├── comparison_builder.py   V7 shortlist report composer
│   │       ├── composite_fit.py        team_fit + overall_fit axes
│   │       ├── hero_quote.py           defining-turn picker
│   │       └── simulation/             persona → team → scenarios → rollouts → judges
│   ├── alembic/versions/          migrations 0001 … 0017
│   └── tests/                     pytest suite
├── frontend/                      Vite + React
│   └── src/
│       ├── pages/                 ManagerDashboard, ShortlistComparePage, intake, …
│       ├── components/v7/         shortlist / triage / radar components
│       ├── api.js                 fetch client
│       └── design.js              design tokens
├── docker-compose.yml
├── .env.example
└── V7_IMPLEMENTATION_PLAN.md
```

---

## Development

Run the backend test suite:

```bash
cd backend
python -m pytest -q
```

Migrations run automatically on startup against Postgres. The frontend has no
separate test runner; verify UI changes against the running dev server.

---

## License

No license is set yet. Until a `LICENSE` file is added, this code is
**"all rights reserved"** by default — add one (e.g. MIT or Apache-2.0) if you
intend to let others use or contribute.
