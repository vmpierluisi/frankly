# Hiring Simulation Platform — v0

A hiring **screening** tool — not a hiring decision tool. Candidates take a
short psychometric quiz, the system synthesizes a behavioral persona, and that
persona is run inside a simulation of a specific company's environment. Only
the matcher's output is shown to the hiring manager. Candidates never see
which companies they're being matched against (blind matching), and an
interview only happens if both parties opt in.

This repository is the Week 1–3 design-partner-ready build. It is meant to
survive a live demo where a stranger uploads their own company artifacts and
sees candidates scored against them.

> **Architectural boundary (do not blur).** The matcher service is the only
> piece that gets replaced when we move from this build to the production
> stack. Same input shape, same output shape. Persona synthesis stays the
> same until MiroFish lands (Week 8–16). Audit-trail wrapping is
> ReasoningLayer's job (Week 16–24).

---

## Two-command quickstart

```bash
cp .env.example .env       # fill in OPENROUTER_API_KEY, change MANAGER_PASSWORD
docker compose up --build  # backend on :8000, frontend on :5173
```

That's it. Open <http://localhost:5173>.

The backend seeds two contrasting fictional Financial-Analyst companies on
first boot:

- **Meridian Capital Partners** — mid-market private credit. Patience, written
  dissent, intellectual honesty. Ported verbatim from the v0 visual prototype.
- **Kestrel Growth Partners** — late-stage growth equity. Speed of conviction,
  pattern recognition, verbal agility. Authored as a deliberate counterweight
  so the matcher visibly discriminates between environments for the same
  candidate during a demo.

You don't need to log in to take the candidate intake. To use the manager
dashboard, sign in with `MANAGER_USERNAME` / `MANAGER_PASSWORD` from your
`.env` (defaults are `manager` / `changeme` — change them).

---

## How a demo runs

1. **Candidate side.** Visit <http://localhost:5173>. The browser doesn't have
   a stored UUID yet, so you land on `/intake`.
   - Read the intro. Take the BFI-10 (10 Likert items). Take the three SJTs.
     Submit.
   - The server synthesizes a persona, persists it under a UUID, returns it,
     and the frontend stores the UUID in `localStorage`. From then on,
     visiting the root takes you to `/profile`.
2. **Manager side.** Visit <http://localhost:5173/manager>. Sign in.
   - You'll see two seed companies and your candidate.
   - Pick the candidate. Pick a company. Click **Run match**.
   - The matcher (one OpenRouter call, strict JSON schema, response-healing
     enabled) returns a fit report grounded in artifact text, broken down by
     criterion, with cross-validation flags surfaced for interview probing.
3. **Stress test the demo.** Pick the same candidate, run them against the
   *other* seed company. The criteria are different and the LLM should produce
   different scores — the contrast is the point.
4. **Live template setup.** Go to **+ New** under Templates. Paste (or upload
   PDF / DOCX of) a values doc, role spec, team-structure note, and a sample
   IC memo or partner email. Run criteria extraction. Edit weights / labels.
   Save. Run a match against the new company.

---

## Repo layout

```
.
├── backend/                FastAPI, Python 3.11+
│   ├── app/
│   │   ├── main.py         CORS + routers + lifespan-seed
│   │   ├── config.py       env-driven Settings
│   │   ├── db.py           SQLAlchemy session, init_db
│   │   ├── models.py       Candidate, Company, Criterion, Match
│   │   ├── schemas.py      Pydantic request/response shapes
│   │   ├── auth.py         shared-password Basic auth dependency
│   │   ├── seed_data.py    BFI10, SJTs, Meridian + Kestrel
│   │   ├── routes/
│   │   │   ├── candidates.py    public intake + UUID-keyed profile
│   │   │   ├── companies.py     manager-gated CRUD
│   │   │   ├── templates.py     parse-artifact + extract-criteria
│   │   │   └── matches.py       trigger / list / get fit reports
│   │   └── services/
│   │       ├── openrouter.py    httpx wrapper: response_format + healing
│   │       ├── persona.py       Python port of synthesizePersona
│   │       ├── criteria_extractor.py   real LLM call #1
│   │       ├── matcher.py              real LLM call #2
│   │       └── artifact_parser.py      pypdf + python-docx → text
│   ├── tests/test_persona.py   pins port to JSX reference
│   ├── pyproject.toml
│   └── Dockerfile
├── frontend/               Vite + React
│   ├── src/
│   │   ├── App.jsx
│   │   ├── main.jsx
│   │   ├── api.js          fetch wrapper, manager creds, candidate UUID
│   │   ├── design.js       editorial tokens (FT-meets-research-lab)
│   │   ├── components/
│   │   │   ├── Widgets.jsx     MiniBar, ScoreBar, Pillar, GeneratingScreen
│   │   │   └── FitReport.jsx   the editorial fit-report panel
│   │   └── pages/
│   │       ├── CandidateIntake.jsx     ported from hiring-sim-demo.jsx
│   │       ├── CandidateProfile.jsx    persistent profile view
│   │       ├── ManagerDashboard.jsx    candidate × company → match → report
│   │       └── TemplateSetup.jsx       paste/upload → extract → review → save
│   ├── package.json
│   ├── vite.config.js
│   ├── index.html
│   └── Dockerfile
├── docker-compose.yml      backend + frontend + persistent SQLite volume
├── .env.example            OpenRouter key, manager password, ports
├── .gitignore
└── README.md
```

---

## Configuration (.env)

| Var                      | Default                          | Notes                                              |
|--------------------------|----------------------------------|----------------------------------------------------|
| `OPENROUTER_API_KEY`     | _(required)_                     | <https://openrouter.ai/keys>                       |
| `OPENROUTER_MODEL`       | `anthropic/claude-sonnet-4.6`    | Any OpenAI-compatible OpenRouter model. Swappable. |
| `MANAGER_USERNAME`       | `manager`                        |                                                    |
| `MANAGER_PASSWORD`       | `changeme`                       | **Change this.**                                   |
| `BACKEND_PORT`           | `8000`                           |                                                    |
| `FRONTEND_PORT`          | `5173`                           |                                                    |
| `VITE_API_BASE_URL`      | `http://localhost:8000`          | Baked into frontend at build time.                 |
| `CORS_ALLOW_ORIGINS`     | `http://localhost:5173,…`        | Comma-separated.                                   |
| `DATABASE_URL`           | `sqlite:////data/hiring_sim.db`  | Path inside the container; the volume mounts here. |

---

## How matching works

Every match is two layers:

1. **Persona synthesis** runs locally in Python (`services/persona.py`). BFI-10
   responses are reverse-scored and averaged per trait; SJT responses are
   aggregated across the three scenarios; three cross-validation rules (
   `agreeable-dissenter`, `low-c-high-rigor`, `neurotic-but-tolerant`) flag
   tensions between self-report and situational response. The Python port is
   regression-tested against the JSX reference (`backend/tests/test_persona.py`).
2. **Matcher** sends the persona + company artifacts + criteria to OpenRouter
   in a single chat completion with:
   - `response_format: {type: "json_schema", strict: true}` — schema enforced
     server-side; criterion keys come from the company row, not the model.
   - `plugins: [{id: "response-healing"}]` — repairs malformed JSON.
   The model produces a 0–100 score per criterion plus a one-sentence
   justification that quotes artifact text. We compute the weighted overall
   ourselves so the arithmetic is deterministic. The band thresholds (Strong /
   Plausible / Edge / Low) match the JSX reference.

The matcher prompt explicitly forbids referring to protected characteristics
and requires every justification to cite artifact text. Bias auditing is the
Week 4+ workstream.

---

## Scope boundaries (intentionally out for v0)

- No MiroFish (Week 8–16)
- No ReasoningLayer (Week 16–24)
- No HrFlow / resume parsing (would dilute the matching story; revisit at v1)
- No cognitive ability testing (adverse-impact risk; deferred)
- No Slack / email ingestion (GDPR / CCPA exposure; Year 2+)
- No real auth — shared-password only. Magic-link or SSO is post-design-partner.
- No Postgres. SQLite is fine at this scale and the SQLAlchemy models port
  directly to Postgres later.
- No hosted deployment. `docker compose up` locally is the entire surface.

---

## Notes on the ported source

`hiring-sim-demo.jsx` was the visual prototype that established the editorial
aesthetic, BFI-10 scoring logic, SJT content, and the v0 deterministic matching
sketch. Everything from that file has been ported and verified:

- `BFI10`, `SJTS`, and the Meridian seed entry → `backend/app/seed_data.py`.
- `synthesizePersona` and `generateNarrative` → `backend/app/services/persona.py`,
  pinned with regression tests against hand-computed reference values.
- `MATCHING_PROMPT` and the band thresholds → `backend/app/services/matcher.py`.
- The `IntroScreen` / `BfiScreen` / `SjtScreen` / `GeneratingScreen` /
  `ReportScreen` / `MiniBar` / `Pillar` UI primitives → `frontend/src/pages/CandidateIntake.jsx`,
  `frontend/src/components/Widgets.jsx`, `frontend/src/components/FitReport.jsx`.
- The COLORS / FONT_DISPLAY / FONT_BODY / FONT_MONO design tokens →
  `frontend/src/design.js`.

The original file can be deleted once you've sanity-checked the port:

```bash
rm hiring-sim-demo.jsx
```

---

## Validation checklist

- [x] Persona Python port passes regression tests against JSX reference.
- [x] Backend boots and serves `/health`, `/candidates/instruments`,
      `/candidates`, `/companies`, `/matches`.
- [x] SQLite volume persists across `docker compose down && up` cycles.
- [x] CandidateIntake → POST `/candidates` round-trips a UUID and a
      narrative-summary persona.
- [x] Manager dashboard lists Meridian + Kestrel and the new candidate.
- [ ] _Live LLM call when OPENROUTER_API_KEY is real — exercise during demo prep._
