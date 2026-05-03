# frankly — Roadmap 2

Long-term plan for the next major iteration of the platform. PRs shipped sequentially. After each stage: test, pause, review, commit.

> **Note**: PR #2 grew into a four-part series during execution (#2a–d) as design refined. Original numbering preserved; new sub-PRs documented under "PR #2d — Three-tier hierarchy (Org → Team → Position)".

## Guiding principles

- **Persona faithfulness over polish.** The product's moat is that the agent reflects the real candidate's skills and communication. Every decision serves this.
- **iPhone-easy UX.** No dense reports. Progressive disclosure. Tap-to-explain. One number where one number is enough.
- **Balance signal.** Skills + education + experience weighted *with* behavior, not subordinate to it.
- **Calibration, always.** Persona accuracy is a measurable, growing number — not a static guess.

---

## PR #1 — Persona enrichment + faithfulness

Internal scaffolding only. No UI changes. The goal is for the candidate agent to behave like the real person within the limits of what we know about them.

### Scope

1. **Wire VerifiedProfile ledgers into the agent prompt.**
   - `agent_runtime.py` system prompt currently injects narrative + trait_sheet + private_goals only.
   - Extend to include the **full** `capability_ledger`, `communication_ledger`, and `voice_samples` from the candidate's VerifiedProfile.
   - Voice samples appear as verbatim few-shot examples ("Here is how this person actually writes: …").

2. **Behavioral contract block.**
   - New section in the system prompt with explicit *forbidden* and *required* behaviors derived from the capability ledger.
   - **Deterministic** rules for skill confidence < 0.3 ("You will admit you don't know X." / "You will not produce idiomatic code in Y.").
   - **Probabilistic** rules for skill confidence 0.3–0.6 ("You may fumble … with ~50% likelihood").
   - Skills with confidence ≥ 0.6 are unconstrained.

3. **Pre-flight scenario → skill gap mapping.**
   - Before each rollout, a one-shot LLM call: "Scenario X requires these skills. Candidate has these skill levels. Which gaps should manifest?"
   - The resulting concrete gap list is injected into the system prompt for that rollout.
   - Cached per (scenario_id, candidate_id) to avoid re-computing.

4. **`persona_fidelity` judge dimension.**
   - New scored dimension (0–100) on every rollout: "Did the agent's response use skills/vocabulary/communication consistent with the persona ledger?"
   - **Not rolled into `overall_fit`.** Quality gate, not candidate signal.
   - Below threshold (default 60) → **automatic re-run** (one retry max). Surfaced in audit_trail.

5. **Lower agent temperature for skill-gap turns.**
   - When a turn touches a skill with confidence < 0.4, drop temperature from 0.6 → 0.4.

6. **Backfill `aggregated_persona`** for existing candidates so they get the new prompt structure.

### Acceptance

- A candidate with `python: 0.1` runs a Python-heavy scenario → the agent visibly admits unfamiliarity / produces non-idiomatic code in the transcript.
- Two candidates with very different communication ledgers produce visibly different transcripts on the same scenario.
- `persona_fidelity` dimension appears on every RolloutScore row.
- Re-runs are logged in audit_trail when fidelity < 60.

### Test plan

- Unit tests on prompt-builder (golden snapshot).
- Integration test: run two synthetic candidates through the same scenario, assert transcript differences on style/skill markers.
- Eyeball: manager-side audit_trail shows fidelity scores.

---

## PR #2 — Tabbed dashboards + Fit Profile v3

Major UX restructure. iPhone-style. Where most of the demo value lives.

### Candidate dashboard tabs

- **Overview**
  - Profile completeness ring (CV / GitHub / Portfolio / LinkedIn / Bio).
  - **Profile accuracy** ring — single 0–100% number, grows with calibration data. Tap → timeline view.
  - Extracted persona at-a-glance: skills (with confidence bars), education timeline, experience cards, communication-style summary (descriptors only — *no* voice samples or ledger internals visible to candidate; gaming risk).
  - "We extracted from: ✓ CV, ✓ 12 GitHub READMEs, ✓ portfolio" — show *that*, never *what*.
  - Inline edit on skills/education/experience — corrections feed back into the persona.
- **Matches**
  - Interview invites with status (pending / accepted / declined / proposed alt time).
  - Vacancy details visible **only** on this tab (and only after invite — gating preserved).
- **Settings**
  - Account, email prefs, source URLs (CV upload, GitHub, portfolio, LinkedIn).
  - Calibration opt-out toggle.

### Recruiter dashboard tabs

- **Overview** — open positions, pipeline funnel, recent simulation activity, alerts (low fidelity flags, calibration drift).
- **Positions** — vacancy list → leaderboard → FitProfile v3.
- **Settings** — company profile, criteria, **required skills taxonomy editor**, team, judge weights.

### Fit Profile v3

- **Profile-link buttons** at the top: CV / LinkedIn / GitHub / Portfolio. Each opens in a new tab. **Hidden when URL absent** (no disabled buttons).
- **Skills + education + experience resume section** — visually weighted equally with behavior.
- **Configurable skill-match weight** in company settings (default 40% skills/edu/exp / 60% behavior).
- **Tappable score explanations (#9).** Every score number is interactive: tap → slide-up sheet with 2-3 transcript turns + one plain-English sentence + link to full transcript. No new sections on main view.
- **Skills radar chart** (candidate vs role-required).
- **Communication-style summary chart** (formality, verbosity, technicality, etc).
- **Profile-accuracy chip** (small "73% confident" pill near overall score).

### Required-skills UI for vacancies

- Recruiter-side, in vacancy/company settings.
- Skill chips with required level (e.g., `python: senior`, `system_design: mid`).
- Mirrors the same skill taxonomy used in `capability_ledger` so matching is apples-to-apples.

### Acceptance

- Both dashboards refactored into tabbed layout — no flat scroll-walls.
- All 4 profile links open in new tab; missing URLs → no button.
- Required skills configurable per company; skill-match score visible on FitProfile.
- Tapping any score number on FitProfile opens explanation sheet.
- Profile accuracy ring visible on candidate Overview (initially default value; populated by PR #5).

---

## PR #2d — Three-tier hierarchy (Org → Team → Position)

Architectural refinement after #2a–c shipped. Splits company-level config into three tiers so culture lives at the org, the simulation team lives at the team, and role-specific config lives at the position.

### Sub-PRs

- **#2d.1 — Backend schema split** *(done)*: new `organizations` + `teams` tables, FK columns on `companies` (= positions), data migrated, services + routes updated. Back-compat layer (legacy-kwargs `__init__` + pass-through `@property` accessors) keeps existing call sites + tests working during the transition.
- **#2d.2 — Frontend**: Org Settings tab in recruiter dashboard, Team management page, TemplateSetup becomes "New position under {team}". Endpoints `/organizations`, `/teams`. Existing `/companies/*` routes preserved until UI fully migrates.
- **#2d.3 — Dual-score scoring**: `skills_fit` and `behaviour_fit` always shown separately; `overall_fit = (skills_fit + behaviour_fit) / 2`. No thresholds, no flags. `skill_match_weight` removed.
- **#2d.4 — Naming + cleanup pass** *(after #2d.3 + real-usage validation)*:
  - Rename `Company` → `Position` (class + table) and `Match.company_id` → `position_id`. Single migration + codebase-wide rename of ~50 references across services, routes, tests, frontend.
  - Remove the deprecated back-compat `Company.__init__` legacy-kwargs absorber.
  - Remove the deprecated `@property` pass-throughs (`company.tagline`, `company.artifact_values`, `company.knowledge_graph`, `company.teammates`, `company.scenarios`). Update all call sites to reference `position.team.X` / `position.organization.X` explicitly.
  - Drop the temporary `_StubCompany.team_id` test scaffolding once tests use real model fixtures.

### Why #2d.4 is staged separately

The renames are mechanical but invasive. Doing them while #2d.3 is still settling risks merging two failure modes (design drift + rename collisions). Once dual-score has been used in real demos and the schema design is validated, do the rename in one cohesive PR with no behavior changes.

---

## PR #3 — Highlight reels + percentile + multi-scenario

Demo magic layer. Builds on top of v3 surfaces.

### Highlight reel auto-generation (#6)

- Replaces the current rollout-summary list section in the recruiter UI.
- One card per rollout with:
  - 30-second LLM-generated "best moments" summary
  - 2-3 key turn snippets w/ score band
  - Tap → existing TranscriptViewer page, **reorganized with one tab per scenario**

### Comparative percentile (#7)

- "Top 12% of senior PMs we've simulated" chip on FitProfile and candidate Overview.
- Aggregate stats computed from existing rollouts; no new infra needed beyond a percentile query.
- Cohort defined by (role_family, seniority).

### Multi-scenario stress test (#5)

- For each candidate: 5 distinct scenario archetypes (cooperative team, toxic teammate, ambiguous priorities, time pressure, ethics dilemma).
- Radar chart on FitProfile showing performance across all 5.
- Adds depth signal — not a one-shot evaluation.

### Acceptance

- Recruiter clicks rollout list → sees highlight cards → tap into per-scenario tabbed transcript view.
- Percentile chip rendered on FitProfile + candidate Overview.
- Stress-test radar visible on FitProfile.

---

## PR #4 — Notifications + interview scheduling + email + vacancy reveal

End-to-end flow from "I want to interview this candidate" to "the candidate is on a call."

### Schema additions

- `notifications` table: id, candidate_id, type, payload, status (unread / read / dismissed), created_at.
- `interviews` table: id, match_id, recruiter_id, candidate_id, proposed_slots (JSON), selected_slot, status (proposed / accepted / declined / rescheduled / completed), created_at.

### Recruiter side

- "Schedule interview" button on FitProfile.
- Slot picker: recruiter proposes 3 time slots.
- On submit: creates interview row, fires notification + email to candidate.

### Candidate side

- Bell icon on dashboard (notification center).
- New interview shows up on **Matches** tab as a card.
- Candidate sees the **vacancy details** for the first time on this card (vacancy reveal on invite).
- Actions: Accept (pick one slot) / Decline / Propose new time.
- Each action fires return notification + email to recruiter.

### Email transport

- **Resend.** Cheap, great DX, React Email templates, async send from FastAPI.
- Templates: interview-invite, interview-confirmed, interview-declined, interview-counter-proposed, calibration-nudge (used in PR #5).

### Acceptance

- Recruiter schedules an interview → candidate receives email + dashboard notification within seconds.
- Candidate accepts/declines/counter-proposes → recruiter sees the response in their notification center.
- Vacancy details remain hidden from candidates outside of the Matches tab interview card.

---

## PR #5 — Calibration loop

Closes the persona-accuracy feedback loop and powers the profile-accuracy ring from PR #2.

### Schema

- `calibration_responses` table: id, candidate_id, scenario_id, rollout_id, agent_response_text, mcq_options (JSON), candidate_selection_index (nullable), candidate_free_text (nullable), divergence_score, created_at.

### Sampling

- After each round: sample **15%** of candidates whose rollouts completed.
- **Bias toward low-confidence rollouts** (judge confidence < 0.6 OR persona_fidelity flag).
- **Frequency cap:** max 1 calibration per candidate per week.

### Candidate UX

- **Low rollout confidence** → free-text-only ("How would you have handled this?").
- **Otherwise** → 4 shuffled MCQ options + free-text box always available alongside.
- The 4 options generated by a single LLM call: 1 = the agent's actual response (paraphrased), 3 = plausible alternatives at different style/skill levels.
- Order randomized per candidate. Agent's option **never labeled**.
- Surfaced via dashboard card + email nudge.

### Persona update

- Append-only: each calibration response stored as evidence on the persona.
- Persona re-derived from the **full evidence set** on demand (no lossy delta logic).
- Updates `aggregated_persona`, `capability_ledger`, `communication_ledger` as appropriate.
- Increments **profile accuracy** number.

### Profile evolution timeline (#10, reframed)

- Replaces "AI twin" framing.
- Headline metric: **"How well we know you: 73%"** (single number, iPhone-simple).
- Tap → timeline view: how the number sharpened over weeks, which calibrations contributed.
- Visible on candidate Overview tab.

### Acceptance

- Sampled candidates receive calibration prompt within 24h of round completion.
- MCQ ordering verified random.
- Candidate response → persona delta visible in audit_trail.
- Profile accuracy ring increments after submission.

---

## PR #6 — Bias / fairness audit panel (#4 on demo list)

Recruiter-only, behind a settings toggle initially.

### Scope

- Score distributions across self-reported demographics.
- Statistical parity gap highlights.
- Disparate-impact ratio per dimension.
- Audit log export (for EU AI Act compliance).

### Acceptance

- Recruiter can toggle audit panel on per-company.
- Distributions render across at least: gender, age band, education tier.
- Export produces a defensible CSV/PDF report.

---

## Process rules

1. Build PR-by-PR, in order.
2. After each PR: **run tests + verify in browser preview** + pause for user review and commit.
3. **Do not start the next PR until the previous is committed.**
4. Reference this roadmap before each PR; update if scope shifts.
5. Memory updates: any non-obvious decisions made during implementation get logged via auto-memory.

---

## Out of scope (deferred / dropped)

- LinkedIn scraping (ToS risk; URL field stays for the open-in-tab button only).
- Voice agents / ElevenLabs TTS (deferred — strong demo lever, but post-funding).
- Shareable candidate links / white-label (deferred to v3 roadmap).
- "AI twin" framing (dropped per user feedback).
- Voice samples visible in candidate Overview (dropped — gaming risk).
