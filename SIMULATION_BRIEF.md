# Simulation Pipeline — Build Brief

**Status:** Handoff to Claude Code. Greenlit by Victor & Daria.
**Scope:** Replace the single-call matcher with a multi-agent simulation pipeline. Add a candidate-side persona aggregator. Add company-side synthetic teammates. Keep the existing matcher alive as a baseline. Bake in logging, ReasoningLayer seams, and validation infrastructure from day one.
**Non-scope:** Real ReasoningLayer integration (Week 16+). Hosted deployment. Slack/email ingestion. These remain on the existing roadmap.

**Already in place — leverage, don't redo:** Supabase JWT auth with JWKS-based verification and manager/candidate role splitting (`backend/app/auth.py`); Postgres support via `DATABASE_URL` switch with Alembic migrations on the Postgres path (`backend/app/config.py::use_alembic`, `backend/alembic/`); SQLite still the local-dev default. All new tables in this brief require corresponding Alembic migrations on the Postgres path; `Base.metadata.create_all` continues to handle the SQLite path. New routes use the existing `require_manager` / `require_candidate` / `require_user` dependencies — do not introduce a parallel auth scheme.

---

## 1. Architectural intent

The repo already declared the right architectural boundary: `services/matcher.py` is the piece that gets replaced when MiroFish lands. This brief executes that planned swap.

The new pipeline:

```
                     ┌───────────────────────────────────────┐
                     │   COMPANY (one-time per role)         │
                     │                                       │
                     │  4 sanctioned artifacts ──┐           │
                     │  + criteria               │           │
                     │                           ▼           │
                     │  team_synthesizer ──> SyntheticTeam   │
                     │  (3-5 colleague personas, editable)   │
                     │                                       │
                     │  scenario_drafter ──> ScenarioLibrary │
                     │  (5-10 moments-of-truth, editable)    │
                     │                                       │
                     │  knowledge_graph ──> CompanyKG        │
                     └───────────────────────────────────────┘

                     ┌───────────────────────────────────────┐
                     │   CANDIDATE (per intake)              │
                     │                                       │
                     │  BFI-10 ──┐                           │
                     │  SJTs    ─┤                           │
                     │  CV       ├─> persona_aggregator      │
                     │  LinkedIn │   (LLM, source-weighted)  │
                     │  GitHub  ─┘                           │
                     │           │                           │
                     │           ▼                           │
                     │   AggregatedPersona                   │
                     │   {structured_traits, narrative,      │
                     │    provenance_map}                    │
                     └───────────────────────────────────────┘

                     ┌───────────────────────────────────────┐
                     │   MATCH (per pairing)                 │
                     │                                       │
                     │  for scenario in ScenarioLibrary:     │
                     │    for k in 1..K:                     │
                     │      rollout(candidate, team, scn) ─┐ │
                     │                                     │ │
                     │  judge(transcripts) ─> per_dim_scores│ │
                     │                                     │ │
                     │  aggregate ─> FitProfile            │ │
                     │                                     ▼ │
                     │  (parallel) baseline_matcher ─> baseline_score
                     │                                       │
                     │  log all of the above ───> rollout_logs
                     └───────────────────────────────────────┘
```

The hiring manager sees the FitProfile with confidence bands and a compact baseline-comparison strip. We see the full rollout logs and validation outputs.

---

## 2. Decisions log (recorded so future maintainers don't re-litigate)

| Decision | Resolution |
|---|---|
| MiroFish integration shape | Reimplement relevant primitives inside this repo as `services/simulation/`. Document MiroFish lineage in code comments. |
| Candidate evidence sources for v0 | BFI-10 + SJTs + CV + LinkedIn URL + GitHub URL. No cover letter, no free-text behavioral fields. Already wired in `Candidate` model. |
| Synthetic teammate count | Default 3–5 per company, editable by manager. |
| Scenario authoring | LLM proposes draft library from artifacts; manager reviews and edits before save. |
| Rollouts per scenario (K) | Default K=5 in v0. Tunable per company in config. Designed so K can scale to 20+ when budget allows. |
| Frontend priority | Clarity, transparency, interpretability. Visuals where they help, plain prose where they don't. |
| Validation visibility | Heavy lifting (retrospective study, correlation, bias audits) is developer-only behind `/admin/`. Customer-facing surface gets per-criterion confidence bands and a robustness-check baseline strip. |
| Logging | Structured per-rollout logs to a dedicated table, designed for offline analysis and future fine-tuning. |
| ReasoningLayer seams | Structured claim emission from scoring; provenance tracking on persona; machine-readable transcripts; `proof_layer` stub interface. |

---

## 3. Data model changes

All in `backend/app/models.py`.

### 3.1 New entities

**`SyntheticTeammate`** — generated from company artifacts; editable by manager.

```
id              str (uuid)
company_id      FK -> companies
name            str
role_on_team    str               # "Senior Analyst", "Pod VP", etc.
seniority       str               # "junior" | "mid" | "senior" | "lead"
trait_sheet     JSON              # Big Five facets + role-relevant skill vector
narrative       Text              # ~500 word personality + work-style prose
private_goals   JSON              # default goals injected into rollouts
generated_from  JSON              # provenance: which artifact lines inspired which traits
is_edited       bool              # true once manager has touched
ordering        int
created_at, updated_at
```

**`MomentOfTruth`** — scenario library per company.

```
id              str (uuid)
company_id      FK -> companies
title           str
prompt          Text              # the scenario setup
candidate_role  Text              # what the candidate needs to do
scoring_dims    JSON              # which criteria this scenario probes
expected_arc    Text              # short note on what good looks like (used by judge)
is_llm_drafted  bool              # true if generated, false if hand-authored
ordering        int
created_at, updated_at
```

**`Rollout`** — single execution of one scenario.

```
id              str (uuid)
match_id        FK -> matches
scenario_id     FK -> moments_of_truth
rollout_index   int               # k in 1..K
transcript      JSON              # list of {turn, speaker_id, speaker_role, content, intent, internal_state}
final_state     JSON              # snapshot of agent states at end
duration_turns  int
seed            str               # for reproducibility
created_at
```

**`RolloutScore`** — judge output per rollout per dimension.

```
id              int
rollout_id      FK -> rollouts
dimension_key   str               # matches Criterion.key
score           int               # 0-100
justification   Text              # cites specific transcript turn ids
evidence_turns  JSON              # list of turn indices the score draws from
judge_model     str               # for audit
confidence      float             # judge self-reported
created_at
```

**`BaselineComparison`** — output of the existing matcher on the same match, run in parallel.

```
match_id        FK -> matches (one-to-one)
overall_score   int
per_criterion   JSON              # {key: {score, justification}}
band            str
band_note       Text
delta_vs_sim    JSON              # absolute and signed deltas per criterion
created_at
```

**`RolloutLog`** — structured event log for offline analysis. Append-only.

```
id              int
match_id        FK -> matches
rollout_id      FK -> rollouts (nullable for non-rollout events)
event_type      str               # "rollout_start", "agent_turn", "judge_score", "baseline_run", "fit_aggregated"
payload         JSON              # event-specific structured payload
created_at      datetime          # indexed
```

### 3.2 Modifications to existing entities

**`Candidate`** — add aggregated persona cache.

```
+ aggregated_persona  JSON | None
+ aggregation_audit   JSON | None    # which sources contributed which claims
+ aggregated_at       datetime | None
```

(The existing `cached_*` fields stay — they back the basic profile view. The new `aggregated_persona` is the rich hybrid object the simulation consumes.)

**`Match.report`** — already JSON, expand its shape (no schema change needed) to carry:
- `overall_score`, `band`, `band_note` (as today)
- `dimensional_fit` (per-criterion mean ± std across rollouts)
- `rollout_summaries` (one per rollout: scenario, score, headline excerpt)
- `baseline_comparison` (embedded snapshot from `BaselineComparison`)
- `confidence_signals` (per-criterion variance, judge agreement)
- `inconsistency_flags` (passed through from persona)
- `audit_trail` (model versions, K used, run timestamps)

---

## 4. New module: `services/simulation/`

Create `backend/app/services/simulation/` as a package. Each file has a tight responsibility.

### 4.1 `persona_aggregator.py`

**Responsibility:** Take all candidate evidence sources and produce an `AggregatedPersona` hybrid object.

**Inputs:**
- `bfi_responses`, `sjt_responses` (existing)
- `cv_text` (parsed via `artifact_parser.py`)
- `linkedin_url`, `github_url` (fetched/sketched at v0; full extraction is a follow-up)

**Output shape:**
```python
{
  "structured_traits": {
    "big_five": {...},          # from BFI, with confidence
    "sjt_signals": {...},        # from SJTs
    "skill_inferences": {...},   # from CV/GitHub: e.g. {"systems_thinking": 0.7, ...}
    "work_style": {...},         # e.g. {"async_pref": 0.6, ...}
  },
  "narrative": str,              # ~1000-2000 word prose synthesis
  "provenance_map": [
    {"claim": "demonstrates written rigor",
     "sources": [{"source": "cv", "evidence": "..."},
                 {"source": "sjt2", "evidence": "Option A choice"}],
     "confidence": 0.78,
     "reliability_weight": "high"},
    ...
  ],
  "inconsistencies": [...],      # carried forward from persona.py's logic, expanded
  "aggregator_version": "v0.1",
}
```

**Implementation:** single LLM call via `openrouter.chat_json` with strict JSON schema. The prompt embeds explicit reliability priors per source ("BFI is high-reliability for self-perception, moderate for behavior; LinkedIn is low-reliability for personality, moderate for skill inference; GitHub commit residue is low-reliability for personality, moderate for conscientiousness"). The narrative is generated in the same call, anchored to the structured claims.

**Important:** this aggregator is the v1 fine-tuning target. Design it as a single prompt template, isolated, easy to swap. No business logic should depend on its internals — only on the output shape.

**ReasoningLayer seam:** the `provenance_map` is the structured artifact ReasoningLayer will consume to produce proof trees. Keep its shape stable.

### 4.2 `team_synthesizer.py`

**Responsibility:** Given a company's 4 artifacts + criteria, generate N (default 5) `SyntheticTeammate` rows with calibrated heterogeneity.

**Algorithm:**
1. LLM call: extract a "team centroid" trait sheet from values + team_structure artifacts (what's the typical personality of someone on this team?).
2. Sample N teammates around the centroid. For each trait, draw from a Gaussian with mean = centroid value and σ tuned to "plausible team variance" (start σ = 0.6 on 0–5 scales). Clip to range.
3. For each sampled trait sheet, second LLM call generates: name, role_on_team, seniority, narrative, default private_goals.
4. Provenance: log which artifact passages drove each trait inference.

**Editability:** every field on `SyntheticTeammate` is editable via the manager UI. `is_edited` flips to true on first edit so we can distinguish generated-untouched from manager-curated.

**MiroFish lineage:** this replaces what MiroFish-the-library would have done as `generate_population_from_documents`. Document this in module docstring.

### 4.3 `knowledge_graph.py`

**Responsibility:** Build a lightweight knowledge graph over company artifacts. Nodes: values, behaviors, roles, decisions. Edges: typed relations (e.g. `value -> demands -> behavior`).

**Implementation:** LLM extraction with strict JSON schema; persisted as JSON on `Company` (new column `knowledge_graph: JSON`).

**Used by:** scenario drafter (to ensure scenarios touch graph-significant nodes); team synthesizer (to ground centroid in graph nodes); judge (to anchor scoring justifications).

**v0 scope:** simple node/edge JSON, no Neo4j. Postgres + JSON works fine.

### 4.4 `agent_runtime.py`

**Responsibility:** State container and turn-execution loop for multi-agent dialogue.

**Core abstractions:**
```python
@dataclass
class AgentState:
    agent_id: str
    persona: dict              # SyntheticTeammate.trait_sheet + narrative + private_goals
    memory: list[dict]         # turn history visible to this agent
    scratchpad: dict           # per-agent internal state (mood, beliefs about candidate, etc.)

@dataclass
class WorldState:
    scenario: dict
    agents: dict[str, AgentState]
    turn_history: list[dict]
    current_turn: int
    seed: str
```

**Turn loop:** at each turn, the runtime picks the next speaker (round-robin v0; later: speaker selector LLM), constructs that agent's prompt from persona + memory + scenario context, calls the LLM, parses output as `{utterance, intent, internal_state_update}`, updates world state, broadcasts to other agents' memory.

**v0 simplification:** synchronous turn-taking, no parallel events, no long-running background state. K turns per rollout, K_per_scenario configurable per company.

**Logging:** every turn emits a `RolloutLog` event with full state snapshot.

### 4.5 `scenario_engine.py`

**Responsibility:** Scenario library management + scenario-to-rollout setup.

Two main functions:
- `draft_scenarios(company) -> list[MomentOfTruth]`: LLM call that proposes 5–10 scenarios grounded in the role spec, team structure, and knowledge graph. Each scenario specifies which dimensions it probes.
- `prepare_rollout(scenario, candidate_persona, teammates) -> WorldState`: select which teammates participate (based on scenario's required roles), construct private goals for each agent, initialize world state.

### 4.6 `rollout.py`

**Responsibility:** Execute one rollout end-to-end.

```python
async def execute_rollout(
    *, match_id: str, scenario: dict, candidate_persona: dict,
    teammates: list[dict], k_index: int, seed: str | None = None,
) -> Rollout:
    world = scenario_engine.prepare_rollout(scenario, candidate_persona, teammates)
    while world.current_turn < world.scenario["max_turns"]:
        await agent_runtime.advance_turn(world)
        await rollout_logger.log_turn(match_id, world)
    return persist_rollout(world)
```

**Concurrency:** rollouts within a match run in parallel via `asyncio.gather`. Default concurrency = 5 (= K) with semaphore.

### 4.7 `judge.py`

**Responsibility:** Score a transcript against a scenario's target dimensions.

**Multi-judge design:** each rollout gets scored by 2 LLM calls (different temperature seeds). Per-dimension score = mean. Per-dimension confidence = inverse variance.

**Output per call:** for each `dimension_key` in `scenario.scoring_dims`, return `{score, justification, evidence_turns, confidence}`. Justification cites specific transcript turn indices, not artifact text directly — the candidate's *behavior in the simulation* is the evidence. Artifact text remains the criterion definition, not the score evidence.

**ReasoningLayer seam:** judge output is the most important structured-claim source. Make sure each justification includes `evidence_turns` as a list of integer indices into the transcript, so downstream tooling can build proof chains.

### 4.8 `aggregator.py`

**Responsibility:** Combine K rollouts × multiple scenarios into a `FitProfile`.

```python
def aggregate_fit_profile(
    rollouts: list[Rollout], scores: list[RolloutScore],
    company_criteria: list[dict],
) -> FitProfile:
    # per criterion: weighted mean across all rollouts that scored it,
    # weighted by judge confidence; track variance.
    # overall = weighted mean per company criterion weights.
    # confidence_signals = {criterion_key: {mean, std, n_rollouts, judge_agreement}}
    # rollout_summaries = headline excerpt per rollout
```

The output is what populates `Match.report`.

### 4.9 `proof_layer.py` — ReasoningLayer stub

**Responsibility:** Interface that ReasoningLayer will plug into. v0 returns a passthrough.

```python
class ProofLayer(Protocol):
    async def attest_persona(self, persona: dict) -> dict: ...
    async def attest_score(self, score: dict, evidence: dict) -> dict: ...
    async def build_proof_chain(self, fit_profile: dict, rollouts: list) -> dict: ...

class NullProofLayer:
    """v0 implementation. Passes through; no proofs generated."""
    async def attest_persona(self, persona): return persona
    async def attest_score(self, score, evidence): return score
    async def build_proof_chain(self, fit_profile, rollouts): return {"status": "deferred"}
```

Wire `NullProofLayer` into the pipeline at the right call sites now. When ReasoningLayer lands, swap the implementation.

### 4.10 `rollout_logger.py`

**Responsibility:** Structured event logging to `RolloutLog`.

Single async function `log_event(match_id, rollout_id, event_type, payload)`. All other simulation modules call this at meaningful checkpoints. The payload schema is documented in module docstring.

---

## 5. Baseline coexistence

**Rename** `services/matcher.py` to `services/baseline_matcher.py`. Its behavior is unchanged — it remains the single-LLM-call matcher.

**Add** `services/simulation_matcher.py` as the new top-level orchestrator that:
1. Loads candidate `aggregated_persona` (or aggregates on the fly if not cached).
2. Loads company `synthetic_teammates` and `scenario_library`.
3. Spawns rollouts (K per scenario) via `rollout.execute_rollout`.
4. Runs `judge.score_rollout` on each.
5. Aggregates via `aggregator.aggregate_fit_profile`.
6. **In parallel**, calls `baseline_matcher.run_match` and persists output to `BaselineComparison`.
7. Computes per-criterion deltas between simulation and baseline.
8. Persists `Match.report` with the full FitProfile + embedded baseline.
9. Logs everything via `rollout_logger`.

**Wiring:** `routes/matches.py` swaps from importing `matcher` to importing `simulation_matcher`. Same input shape, same output shape contract — but the report payload is richer.

---

## 6. API surface

Add these routes. All under existing auth pattern (manager-gated where appropriate).

### Manager-facing

```
POST   /companies/{id}/team/synthesize           -> regenerate synthetic teammates
GET    /companies/{id}/team                      -> list teammates
PATCH  /companies/{id}/team/{teammate_id}        -> edit teammate
DELETE /companies/{id}/team/{teammate_id}

POST   /companies/{id}/scenarios/draft           -> LLM-draft scenario library
GET    /companies/{id}/scenarios                 -> list scenarios
POST   /companies/{id}/scenarios                 -> create hand-authored scenario
PATCH  /companies/{id}/scenarios/{scenario_id}   -> edit
DELETE /companies/{id}/scenarios/{scenario_id}

GET    /matches/{match_id}/rollouts              -> list rollout summaries
GET    /matches/{match_id}/rollouts/{rid}        -> full transcript
GET    /matches/{match_id}/baseline              -> baseline comparison detail
```

### Candidate-facing

```
POST   /candidates/me/persona/aggregate          -> trigger aggregation (auth: candidate)
GET    /candidates/me/persona                    -> aggregated persona (auth: candidate)
```

These follow the existing `/candidates/me/*` self-service convention in `routes/candidates.py` (auth-gated to the signed-in candidate via `require_candidate`). The aggregator can also be invoked manager-side for re-aggregation; defer that endpoint to a follow-up unless explicitly needed by the build.

### Developer-only (`/admin/` prefix, separate auth)

```
POST   /admin/validation/retrospective/upload    -> CSV of historical hires
POST   /admin/validation/retrospective/run       -> score historical hires through current pipeline
GET    /admin/validation/retrospective/{run_id}  -> correlation report
GET    /admin/validation/bias-audit/{run_id}     -> stratified scoring report
GET    /admin/logs/match/{match_id}              -> raw RolloutLog dump
GET    /admin/logs/training-export               -> jsonlines export for fine-tuning
```

---

## 7. Frontend

Same Vite + React + design.js conventions as today. Keep the editorial aesthetic — it's a real asset.

### 7.1 New pages

**`/manager/companies/{id}/team`** — synthetic team viewer/editor.
Manager sees the 5 generated teammates as cards. Each card: name, role, seniority, narrative excerpt, expandable trait sheet. Edit-in-place. "Regenerate team" button. Provenance footnotes on hover (which artifact line drove which trait).

**`/manager/companies/{id}/scenarios`** — scenario library.
List of scenarios with title, prompt preview, scoring dims tagged. "Draft from artifacts" button. Edit modal per scenario. Add hand-authored.

**`/manager/matches/{match_id}/rollout/{rid}`** — single transcript viewer.
Shows the full multi-turn transcript with: speaker badges (candidate vs teammate names), per-turn intent annotations (collapsed by default), highlighted turns that judges cited as evidence, scoring strip at bottom (this rollout's per-dim scores).

### 7.2 Replace `FitReport.jsx`

The current `FitReport` shows per-criterion bars and a band note. The new version (`FitProfileV2.jsx`) shows:

1. **Headline strip:** overall score with band, plus a small "robustness check" pill comparing to baseline (e.g. "Sim 78 / Baseline 72 — sim higher on Written Dissent, lower on Pattern Recognition").
2. **Dimensional fit chart:** per-criterion bars with confidence bands (mean ± std across K rollouts). Wide bars = uncertain. This is the visual that screams "we ran this multiple times, here's what's stable."
3. **Rollout summaries strip:** K mini-cards, one per rollout, each with scenario title, headline excerpt from transcript, this-rollout's overall score. Click expands to full transcript viewer.
4. **Inconsistency flags panel:** unchanged from today's behavior.
5. **Methodology footer:** "Based on K=5 simulated interactions across N scenarios. Models: ..., judge model: ..., baseline matcher: ..." (audit trail visible to manager, not buried.)

### 7.3 New components

- `TranscriptTurn.jsx` — speaker, content, optional intent annotation, optional evidence highlight.
- `VarianceBar.jsx` — bar with mean and ±σ band overlay. Use everywhere a per-criterion score is shown.
- `DimensionalFitChart.jsx` — collection of `VarianceBar`s with shared scale.
- `BaselineCompareStrip.jsx` — compact diff visualization for the headline strip.
- `TeammateCard.jsx` — for the synthetic team page.
- `ScenarioCard.jsx` — for the scenario library page.

### 7.4 UX intent

The user explicitly asked for **clarity, transparency, interpretability**. This means:
- Never show a single number where a range is honest (variance bars over point estimates).
- Always cite. Every justification quotes its evidence (transcript turn for sim, artifact line for baseline).
- Methodology is visible, not buried in tooltips.
- The robustness check exists *because* it makes the system trustworthy, not because we're hiding behind it.

---

## 8. Logging and telemetry

`RolloutLog` is the canonical event store. Schema:

```
event_type           when emitted                      payload (illustrative)
-----------------    -----------------------------     ------------------------
match_started        before any rollout                {match_id, candidate_id, company_id, k, scenarios}
persona_aggregated   after persona_aggregator          {persona, audit, sources_present}
team_loaded          before rollouts                   {teammate_ids, edited_count}
rollout_started      per rollout                       {rollout_id, scenario_id, k_index, seed}
agent_turn           every turn in every rollout       {rollout_id, turn, speaker_id, utterance, intent, internal_state}
rollout_finished     per rollout                       {rollout_id, duration_turns, final_state_summary}
judge_scored         per (rollout, judge)              {rollout_id, judge_model, dim_scores}
baseline_run         once per match                    {baseline_overall, per_criterion, deltas}
fit_aggregated       once per match                    {overall, per_dim_mean_std, confidence_signals}
match_finished       end                               {match_id, total_llm_calls, total_tokens, wall_time_ms}
```

Indexed by `match_id` and `created_at`. Append-only. No deletes.

A nightly cron (out of v0 scope, but design for) exports these to a `training_export.jsonl` artifact suitable for fine-tuning the persona aggregator and (eventually) training a learned scoring model.

---

## 9. Validation infrastructure

All under `/admin/`, behind separate auth (developer-only).

### 9.1 Retrospective study

Endpoint: `POST /admin/validation/retrospective/upload` accepts a CSV with anonymized historical hires:

```
candidate_id_external, cv_text, linkedin_url, github_url, bfi_responses_json,
sjt_responses_json, hired (bool), performance_rating_12mo (1-5),
retention_12mo (bool), promotion_12mo (bool), notes
```

Endpoint: `POST /admin/validation/retrospective/run` runs each row through:
- The simulation pipeline
- The baseline matcher

For each row, persist both scores plus the actual outcome.

Endpoint: `GET /admin/validation/retrospective/{run_id}` returns:
- Pearson + Spearman correlations between (sim_score, performance), (baseline_score, performance), and a paired delta showing whether sim outperforms baseline
- Confusion matrix at the threshold the company uses for advance/reject
- Per-dimension correlations
- Sample size, confidence intervals
- A pre-registerable result block

### 9.2 Bias audit

Endpoint: `GET /admin/validation/bias-audit/{run_id}` runs differential analysis on a configured stratification (initially: only what the design partner provides anonymized; later, derived demographics where consented). Outputs adverse-impact ratios and per-dimension differential scoring.

### 9.3 Customer-facing byproducts

The two validation byproducts that surface in the manager UI:
- **Per-criterion variance bands** (already in `DimensionalFitChart`): managers see uncertainty.
- **Baseline comparison strip** (already in `FitProfileV2` headline): managers see whether the simulation is moving the score and where.

These are not "validation" in the methodological sense — they're confidence signals derived from validation infrastructure. Explicit narrative for design partners: "you can see the model's uncertainty per dimension, and you can see how it differs from a vanilla LLM screening on this candidate."

---

## 10. ReasoningLayer integration plan

The seams are explicit in the code so swap-in is mechanical:

1. **Persona provenance** (`persona_aggregator` → `provenance_map`): structured (claim, sources, confidence, reliability_weight) tuples ready for proof construction.
2. **Judge evidence** (`judge` → `evidence_turns`): each score points to specific transcript turns, not vibes.
3. **Transcript machine-readability** (`Rollout.transcript`): JSON, not freeform text. Each turn has `intent` and `internal_state` fields for downstream reasoning.
4. **`proof_layer` interface**: called at three points (persona attestation, score attestation, fit-profile proof chain). v0 has `NullProofLayer` wired in. ReasoningLayer adapter goes here later.

When ReasoningLayer lands, the only changes are: implement `ReasoningLayerProofLayer` against the same Protocol; flip a config flag; persist proof artifacts alongside reports.

---

## 11. Build sequence (micro-phased)

Each phase below is scoped to one focused Claude Code session — small, independently shippable, with an explicit validation gate. Phases assume strict ordering: a phase may only start once its predecessors are merged. Each cell in the table is the *contract* for that phase — anything not listed is out of scope and should be deferred.

The original 7-phase plan has been decomposed into 14 phases. This is deliberate: smaller phases mean less scope drift per commit, easier code review, and faster recovery from missteps.

| # | Phase | Depends on | Scope | Validation gate |
|---|---|---|---|---|
| **0** | **Plumbing scaffolding** | — | Add `Settings` additions (Appendix D.7). Add `OPENROUTER_GLOBAL_CONCURRENCY` env. Add `services/simulation/cost_tracker.py` (Appendix D.3). Add `chat_json_with_retry` and `RetryableError`/`FatalError` to `openrouter.py` (Appendix D.1). Wrap `chat_json` in the global semaphore. **No new tables, no new routes, no behavior change for existing flows.** | All existing tests still pass. `from app.services.simulation.cost_tracker import CostBudget, CostCeilingExceeded, tracked_chat_json` imports cleanly. Manual smoke: existing `/matches/trigger` still works against a real OpenRouter key, and one transient 429 retries cleanly. |
| **1A** | **Persona aggregator (module only)** | 0 | Create `services/simulation/__init__.py`, `services/simulation/types.py` (TypedDicts for AggregatedPersona, RolloutTurn, etc.), `services/simulation/persona_aggregator.py` with the Appendix A.1 prompt and Appendix B.1 schema. Implement `async def aggregate(candidate, *, budget) -> dict` returning the AggregatedPersona shape. **No DB writes, no routes — pure module callable from tests.** | Unit tests in `backend/tests/simulation/test_persona_aggregator.py` (Appendix F.1) all pass. `synthesize_persona` legacy port (`persona.py`) still passes its existing regression tests. |
| **1B** | **Persona aggregator persistence + endpoint** | 1A | Migration `0003_persona_aggregator.py` (3 columns on `candidates` only — `aggregated_persona`, `aggregation_audit`, `aggregated_at`). Update `models.Candidate`. Add `POST /candidates/me/persona/aggregate` (auth: candidate) and `GET /candidates/me/persona` (auth: candidate). Frontend `api.js`: `candidates.aggregatePersona`, `candidates.getPersona`. **Existing manager match flow unchanged — no UI for this yet.** | After candidate intake, calling `/candidates/me/persona/aggregate` populates the new columns. `GET` returns the aggregated persona. SQLite create_all and Alembic upgrade both work. |
| **2A** | **Knowledge graph + team centroid** | 1B | Migration `0004_company_knowledge_graph.py` (one column on `companies`: `knowledge_graph`). Implement `services/simulation/knowledge_graph.py::extract(company, *, budget)` using Appendix A.4 / B.4. Implement `services/simulation/team_synthesizer.py::extract_centroid(company, *, budget)` using Appendix A.2 / B.2. **No teammate generation yet, no routes.** | Unit tests pass. Manual: run extractors against Meridian and Kestrel and inspect the JSON outputs — they should look distinct. |
| **2B** | **Teammate generator + persistence + routes** | 2A | Migration `0005_simulation_pipeline.py` (the rest of Appendix C.1 — synthetic_teammates, moments_of_truth, rollouts, rollout_scores, baseline_comparisons, rollout_logs — grouped to avoid migration sprawl). Add `models.SyntheticTeammate` (and stubs for `MomentOfTruth`, `Rollout`, `RolloutScore`, `BaselineComparison`, `RolloutLog` — only the team-related is wired this phase). Implement `team_synthesizer.synthesize(company, *, budget) -> list[SyntheticTeammate]` end-to-end (centroid → sample → generate via Appendix A.3 / B.3). Routes: `GET /companies/:id/team`, `POST /companies/:id/team/synthesize`, `PATCH /companies/:id/team/:tid`, `DELETE /companies/:id/team/:tid` (all `require_manager`). Add `seed_teams_for_seed_companies` helper called optionally on first boot. | Manager can call `POST /team/synthesize` against Meridian and get 5 teammates back; can edit a teammate; can delete one. Unit tests pass. Logs row inserted via the new `RolloutLog` table for each synthesis (event_type=`team_synthesized`). |
| **2C** | **Synthetic team frontend** | 2B | New page `frontend/src/pages/SyntheticTeamPage.jsx`. New component `TeammateCard.jsx`. Wire route `/manager/companies/:id/team`. Add `team` namespace to `api.js`. Smoke test (Appendix F.4). | Manager visits the page for Meridian, sees 5 cards, edits a name + saves, deletes one, regenerates the team. No console errors. Existing FitReport flow unchanged. |
| **3A** | **Scenario engine backend** | 2B (data model) | Implement `services/simulation/scenario_engine.py::draft_scenarios(company, *, budget)` using Appendix A.5 / B.5. Implement `prepare_rollout(scenario, candidate_persona, teammates) -> WorldState` (the data prep, no execution yet). Routes: `POST /companies/:id/scenarios/draft`, `GET /companies/:id/scenarios`, `POST /companies/:id/scenarios`, `PATCH /companies/:id/scenarios/:sid`, `DELETE /companies/:id/scenarios/:sid`. Validation: `scoring_dims` keys must exist in company's criteria. Add `seed_scenarios_for_seed_companies` helper. | LLM drafts a 5-8 scenario library for Meridian and Kestrel that visibly differ; manager can edit and save. Validation rejects scoring_dims keys not in the company's criteria. |
| **3B** | **Scenario library frontend** | 3A | `ScenarioLibraryPage.jsx`, `ScenarioCard.jsx`, route, `scenarios` namespace in `api.js`. Smoke test. | Manager visits `/manager/companies/:id/scenarios`, drafts the library, edits one scenario in a modal, saves. |
| **4A** | **Agent runtime + rollout (mocked scoring)** | 2B (data model) | `services/simulation/agent_runtime.py` with `AgentState`, `WorldState` dataclasses, `advance_turn(world, *, budget)` round-robin per Appendix A.6 / B.6. `services/simulation/rollout.py::execute_rollout(...)` end-to-end producing a `Rollout` row with full transcript. **Judge is mocked at this phase — `rollout.py` is independently testable without a real judge.** Implement `rollout_logger.py` (append-only RolloutLog writes). | Unit tests pass. Manual: invoke `execute_rollout` from a Python REPL with a real candidate persona + Meridian team + one drafted scenario, inspect the resulting `Rollout` row. Transcript looks coherent. |
| **4B** | **Judge + scoring persistence** | 4A | `services/simulation/judge.py::score_rollout(rollout, scenario, *, budget)` doing 2 judge calls per rollout (Appendix A.7 / B.7). Persists `RolloutScore` rows. Falls back to single-judge gracefully on judge failure (Appendix D.2). | Unit tests pass. Manual: run a rollout from 4A through the judge; inspect RolloutScore rows; check `evidence_turns` are non-empty when scores are non-null. |
| **4C** | **Simulation matcher orchestrator + baseline coexistence** | 4B, 1B | Rename `services/matcher.py` → `services/baseline_matcher.py` (no behavior change). Implement `services/simulation/aggregator.py::aggregate_fit_profile(...)` producing the Appendix B.8 shape. Implement `services/simulation/simulation_matcher.py::run_match(...)` orchestrating: persona aggregation → team load → scenario load → K rollouts in parallel per scenario → judge → aggregate → baseline parallel → persist `Match.report` (v2) + `BaselineComparison` row + RolloutLog events. Switch `routes/matches.py` to use `simulation_matcher.run_match`. Cost ceiling and timeouts wired (Appendix D.3, D.5). | Integration test from Appendix F.2 passes. Manual: trigger a match for Meridian + a real candidate; inspect the `Match.report` for v2 fields; inspect the `BaselineComparison` row; inspect RolloutLog events for the canonical sequence. |
| **5A** | **FitProfileV2 + variance components** | 4C | New components `VarianceBar.jsx`, `DimensionalFitChart.jsx`, `BaselineCompareStrip.jsx`, `RolloutSummaryCard.jsx`, `FitProfileV2.jsx`. Wrap pattern in `ManagerDashboard.jsx` so legacy v1 reports still render via `FitReport.jsx`. Add `matches.listRollouts`, `matches.getRollout`, `matches.getBaseline` API client methods. Smoke test (Appendix F.4). | Manager runs a match against Meridian and sees the v2 report with: dimensional fit bars including variance bands, rollout cards, baseline strip, methodology footer. A legacy report still renders via the old component. |
| **5B** | **Transcript viewer page** | 5A | `TranscriptViewer.jsx`, `TranscriptTurn.jsx`, route `/manager/matches/:matchId/rollouts/:rolloutId`. Click-through from `RolloutSummaryCard` opens the viewer. Dimension-chip highlight + intent-toggle behavior implemented. Smoke test. | From the FitProfileV2, manager clicks a rollout card → arrives at the transcript viewer → can toggle intents and click a dimension chip to highlight the cited turns. |
| **6** | **Validation infrastructure (admin-only, no frontend)** | 4C | `/admin` router with separate auth gate (env `ADMIN_PASSWORD` or scoped to a specific manager email — keep simple in v0). Routes: `POST /admin/validation/retrospective/upload` (CSV upload), `POST /admin/validation/retrospective/run/:run_id`, `GET /admin/validation/retrospective/:run_id` (correlation report JSON), `GET /admin/validation/bias-audit/:run_id` (stub returning `{"status": "deferred"}`), `GET /admin/logs/match/:match_id`, `GET /admin/logs/training-export` (jsonlines stream). | Synthetic CSV with 10 fake historical hires is uploadable, runnable, and produces a coherent correlation report JSON. `/admin/logs/match/:id` returns RolloutLog rows for a real match. |
| **7** | **ReasoningLayer seams + logging audit** | 4C (anywhere after; can run alongside 5A/B/6) | `services/simulation/proof_layer.py` with `ProofLayer` Protocol, `NullProofLayer` impl (passthrough). Wire `NullProofLayer` into `simulation_matcher.run_match` at three call sites: after persona aggregation (`attest_persona`), after each judge call (`attest_score`), after fit aggregation (`build_proof_chain`). Audit `rollout_logger` coverage — every event type in section 8 of the brief actually fires. Document MiroFish lineage in `services/simulation/__init__.py` docstring listing which primitives map to which MiroFish concepts. | Code review checklist passes: a future ReasoningLayer adapter can replace `NullProofLayer` with a one-line config flip. RolloutLog event types are complete. Module docstrings document MiroFish lineage. |

**Total: 14 phases.** Phases 1A through 4C constitute the backend pipeline; 5A and 5B make it visible; 6 makes it validatable; 7 makes it auditable for the future.

**Ordering flexibility.** Phase 7 (ReasoningLayer seams) can run in parallel with 5A/5B/6 — its only dependency is 4C. Similarly, 6 (validation infra) only depends on 4C and is independent of frontend work. The critical path is 0 → 1A → 1B → 2A → 2B → 3A → 4A → 4B → 4C, then 5A → 5B for visibility.

**Pause points.** After **Phase 1B**, the persona aggregator is shippable in isolation — you could pause the simulation buildout entirely and the existing matcher still works with the richer persona as input (with a small change to `routes/matches.py` to prefer `aggregated_persona` over `cached_persona` when present). After **Phase 4C**, the simulation pipeline works end-to-end via API; the manager has no UI for it yet but can be demoed via curl and the `/admin/logs/match/:id` endpoint. After **Phase 5B**, the demo is fully walkable. These are natural review-and-decide moments.

---

## 12. Open questions to resolve during build

These are intentionally not pre-decided. Flag back if any of them turn into blockers.

- **Scenario-to-teammate mapping:** does the manager pick which teammates appear in each scenario, or does the LLM select based on scenario context? Default: LLM selects, manager can override.
- **Speaker selection inside a rollout:** round-robin v0, or speaker-selector LLM call per turn? Default: round-robin v0; revisit if dialogues feel mechanical.
- **Judge calibration:** start with two judges per rollout. If their agreement is consistently > 0.85, drop to one to save tokens. If consistently < 0.6, add a third.
- **Persona aggregator failure modes:** what happens when a candidate has no LinkedIn URL? CV is malformed? Aggregator should degrade gracefully — emit reduced-confidence claims rather than refuse.
- **Cost ceiling per match:** estimate tokens per match end-to-end. If a match costs > $X, surface that in `/admin` and consider reducing K or judges per rollout.
- **MiroFish primitive boundaries:** as `services/simulation/` matures, identify which modules are generic enough to extract back into a MiroFish workplace-simulation submodule. Don't extract prematurely.

---

## 13. Done definition for the brief

This brief is "executed" when:
- A clean clone of the repo, after `docker compose up`, can take a candidate through intake, run a match against Meridian, and produce a `FitProfileV2` in the UI containing: dimensional fit chart with variance bands, K=5 rollout summaries clickable into transcripts, baseline comparison strip, audit trail.
- `/admin/logs/match/{match_id}` returns a structured event log for that match.
- `/admin/validation/retrospective/upload` + `run` work end-to-end against a synthetic CSV.
- The MiroFish lineage is documented in `services/simulation/__init__.py` and individual module docstrings.
- `proof_layer.py` is wired in at the three call sites with `NullProofLayer` as the default implementation.
- Existing tests pass; new tests cover the persona aggregator, team synthesizer, judge, and aggregator at unit level (Appendix F.1).
- Baseline matcher coexists at `services/baseline_matcher.py` and runs in parallel on every match; `BaselineComparison` rows are persisted; the FitProfileV2 headline strip surfaces the comparison.
- Cost ceiling and concurrency caps from Appendix D are wired and surface in `/health` and the audit trail.

The 14-phase plan in Section 11 is the road to this end-state. Phases are independently shippable; pause points after **Phase 1B**, **Phase 4C**, and **Phase 5B** are natural review-and-decide moments.

---

# APPENDICES

The appendices below take the brief from "design spec" to "execution spec." Each is referenced from the relevant section above. If you find yourself uncertain about an implementation detail, the appendix should resolve it; if it doesn't, that's a brief gap and worth flagging.

---

## Appendix A — Prompt templates

The prompts below are the v0 starting point. Treat them as version 0.1 — committed to the repo as constants in their respective service modules, evolved via prompt-snapshot tests (Appendix F.3), and considered the v1 fine-tuning target. Do not paraphrase them at integration time; copy verbatim.

**General constraints applying to every prompt below:**
- Output is strict JSON conforming to the matching schema in Appendix B.
- The Anthropic schema validator rejects `minimum`, `maximum`, `minItems`, `maxItems`, `pattern` — numeric ranges and length constraints are enforced in the prompt text and in post-hoc Python validation, never in the schema. Mirror the pattern already established in `services/criteria_extractor.py`.
- Every prompt forbids reference to protected characteristics or proxies for them. This is non-negotiable — keep the language identical across prompts so future bias audits can grep for it.
- Tone is clinical-but-humane, matching the editorial aesthetic of the existing matcher prompt.

### A.1 — Persona aggregator (`services/simulation/persona_aggregator.py`)

**System prompt** (constant `PERSONA_AGGREGATOR_SYSTEM`):

```
You are the candidate persona aggregator inside a hiring-screening platform.
Your job is to synthesize a behavioral profile of a candidate from
heterogeneous evidence sources, with explicit reliability weighting per source.

YOU PRODUCE A SCREENING-LEVEL ARTIFACT, NOT A HIRING JUDGMENT.

SOURCE RELIABILITY PRIORS (apply rigorously):
  * BFI-10 self-report: HIGH reliability for self-perception, MODERATE for
    behavior. Use as trait anchors. Documented self-presentation bias.
  * Situational Judgment Tests: HIGH reliability for situational reasoning
    (well-validated psychometric instrument). Use as behavior anchors.
  * CV / resume text: MODERATE reliability for skill claims (presentation
    bias), LOW for personality. Treat skill claims as candidate-asserted.
  * LinkedIn URL or extracted summary (where available): LOW reliability for
    personality (heavy presentation bias), MODERATE for trajectory and role
    inference.
  * GitHub URL or extracted summary (where available): LOW reliability as
    personality signal, MODERATE for conscientiousness and skill proxies
    (commit cadence, code review behavior, documentation habits, languages).

HARD RULES:
  1. Every claim in structured_traits or narrative MUST appear in
     provenance_map with at least one cited source plus a reliability_weight
     tag of "high", "moderate", or "low".
  2. When sources conflict, surface the conflict in inconsistencies — do not
     silently average. Each inconsistency gets a type slug and a one-paragraph
     note framed for a human interviewer.
  3. Never reference protected characteristics (race, gender, age, national
     origin, religion, disability, sexual orientation, pregnancy, marital
     status) or proxies for them.
  4. Frame every claim as "self-reports", "behavioral evidence suggests",
     "trajectory indicates" — never as fixed personality verdicts.
  5. Output STRICT JSON matching the provided schema exactly. Do not invent
     fields. Do not omit required fields.
  6. If an evidence source is missing or empty, produce reduced-confidence
     claims rather than refusing — note the absence in
     evidence_completeness.

SCALES:
  * Big Five traits: 0.0 to 5.0 (BFI-10 native scale, two-decimal precision).
  * SJT signals: 0.0 to 5.0 (matches existing seed_data.SJTS signal weights).
  * Skill inferences: 0.0 to 1.0 (likelihood-to-demonstrate scale).
  * Work-style inferences: 0.0 to 1.0 (preference intensity scale).
  * provenance_map confidence: 0.0 to 1.0.

NARRATIVE REQUIREMENTS:
  * 800 to 1500 words. Plain prose. No headers, no bullets, no numbered
    lists.
  * Cite the structured anchors organically; do not number or label them.
  * Tone: clinical-but-humane, like a research note. Past-tense observations,
    present-tense inferences, conditional language for predictions.
  * Never address the candidate directly. Third-person throughout.
  * Surface uncertainty. A short narrative honestly acknowledging missing
    evidence is better than a long one filling gaps with confabulation.
```

**User prompt template** (constant `PERSONA_AGGREGATOR_USER_TEMPLATE`):

```
Synthesize the candidate's behavioral profile from the evidence below.

CANDIDATE METADATA
------------------
Display name: {display_name_or_anon}
Email present: {email_present}

BFI-10 RAW RESPONSES (1-5 Likert, item id : score)
--------------------------------------------------
{bfi_block}

BFI-10 ITEMS (for your reference)
{bfi_items_block}

SJT RESPONSES (situation : chosen option, with that option's signal weights)
----------------------------------------------------------------------------
{sjt_block}

CV / RESUME TEXT (parsed; may be empty)
"""
{cv_text}
"""

LINKEDIN
--------
URL provided: {linkedin_present}
Extracted summary (may be empty in v0; treat as URL-only when absent):
"""
{linkedin_summary}
"""

GITHUB
------
URL provided: {github_present}
Extracted summary (may be empty in v0; treat as URL-only when absent):
"""
{github_summary}
"""

TASK
----
Return a JSON object matching the AggregatedPersona schema. Specifically:

1. Compute big_five from the BFI-10 responses (items, reverse-scoring rules,
   averaging — see persona.py for the canonical algorithm; reproduce it
   inside your reasoning, do not call out to it).
2. Compute sjt_signals from the SJT responses (sum signal weights across
   selected options, divide by number of SJTs answered).
3. Infer skill_inferences and work_style from CV / LinkedIn / GitHub
   evidence. If a category has no supporting evidence, omit the key
   entirely rather than fabricating a midpoint score.
4. Build provenance_map: every non-trivial claim is one entry. Cite the
   specific source and quote a short evidence excerpt where possible.
5. Detect inconsistencies. The three rules from persona.py
   (agreeable-dissenter, low-c-high-rigor, neurotic-but-tolerant) are the
   floor — surface additional cross-source tensions you observe.
6. Write the narrative last, anchored in the structured claims and the
   provenance_map.
7. Set evidence_completeness to flag missing sources and any confidence
   degradation.
8. Set aggregator_version to "v0.1".
```

**Where the User template is filled in `services/simulation/persona_aggregator.py`:** `bfi_block` is `"\n".join(f"  {k}: {v}" for k, v in bfi_responses.items())`; `bfi_items_block` is the BFI10 list rendered as `"  {id}: {text} (trait={trait}, reverse={reverse})"`; `sjt_block` lists chosen options with their signal weights expanded from `SJTS`. Empty CV / LinkedIn / GitHub render as `"(none provided)"` — never as the empty string, so the model can clearly distinguish empty-but-present from absent.

**Call-site parameters:** `temperature=0.2`, `max_tokens=4500` (narrative is the long part), `schema_name="aggregated_persona"`.

---

### A.2 — Team centroid extractor (`services/simulation/team_synthesizer.py`)

This is the first of two LLM calls inside team synthesis. It extracts the implicit "what does a typical good teammate on this team look like" centroid from the company's artifacts, before sampling N teammates around it.

**System prompt** (constant `TEAM_CENTROID_SYSTEM`):

```
You extract the implicit centroid trait sheet of a high-functioning teammate
inside a specific company, from that company's sanctioned artifacts.

You do NOT design an aspirational ideal. You describe what the artifacts
collectively imply about who actually thrives on this team today.

HARD RULES:
  1. Ground every trait inference in cited artifact text. The provenance
     field on each trait is non-optional.
  2. Surface tensions inside the company's stated values and observed
     behaviors (sample comms). Tensions go in centroid_tensions and
     should NOT be averaged away.
  3. Big Five and skill scales match the persona aggregator (Appendix A.1).
  4. Never reference protected characteristics or proxies.
  5. Strict JSON only.

This is the centroid only. Variance around it is sampled later — do not
inject artificial diversity here.
```

**User prompt template** (constant `TEAM_CENTROID_USER_TEMPLATE`):

```
Extract the centroid trait sheet for this company's team.

COMPANY: {company_name}
ROLE: {role}
TAGLINE: {tagline}

VALUES DOCUMENT
"""
{artifact_values}
"""

ROLE SPECIFICATION
"""
{artifact_role_spec}
"""

TEAM STRUCTURE
"""
{artifact_team_structure}
"""

SAMPLE COMMUNICATIONS
"""
{artifact_sample_comms}
"""

CRITERIA (what the company formally evaluates against)
{criteria_block}

KNOWLEDGE GRAPH NODES (extracted previously; may be empty)
{knowledge_graph_summary}

TASK
----
Return a JSON object matching the TeamCentroid schema. Specifically:

1. Compute big_five_centroid: the mean trait profile of a person who would
   thrive on this team. Cite artifact evidence.
2. Compute skill_centroid: the mean role-relevant skill profile.
3. Compute work_style_centroid: collaboration, communication, decision-style
   defaults.
4. List centroid_tensions: places where the company's stated values and
   observed behavior pull in different directions. Each tension has an
   id, a description, and the artifact lines it draws from. These tensions
   later inform variance — teammates may sit at different points along
   them.
5. Set sigma_recommendations: per-trait recommended Gaussian σ for sampling
   teammates around the centroid. Default σ = 0.6 unless centroid_tensions
   suggest a wider spread (then up to 1.0).
```

**Call-site parameters:** `temperature=0.2`, `max_tokens=2500`, `schema_name="team_centroid"`.

---

### A.3 — Teammate generator (`services/simulation/team_synthesizer.py`)

Second LLM call. Takes the centroid + a sampled trait sheet + company artifacts, produces one fully-realized teammate.

**System prompt** (constant `TEAMMATE_GENERATOR_SYSTEM`):

```
You generate a single fully-realized teammate persona for a hiring
simulation. The teammate's traits have been pre-sampled — your job is to
write the rest of the persona consistent with those traits and grounded in
the company's environment.

HARD RULES:
  1. The structured trait_sheet you receive is FIXED. Do not alter values.
     Generate the narrative, name, role_on_team, seniority, and
     private_goals consistent with those values.
  2. Names: anglophone-neutral, varied across calls. Avoid culturally-
     coded names that could carry stereotype freight. Surnames common.
     Do not generate names of real public figures.
  3. private_goals are the teammate's typical goals when interacting with
     a candidate during a simulated workday. They are private to the
     teammate (the candidate does not see them) and drive how the
     teammate behaves in rollouts. Each goal is one sentence; produce
     2-4 goals.
  4. Seniority must be one of: junior, mid, senior, lead.
  5. role_on_team is a short specific job title (e.g. "Senior Credit
     Analyst", "Pod VP — Healthcare", "Founding Operator").
  6. Narrative is 300-600 words, third-person, plain prose, no headers,
     no bullets. Same clinical tone as persona aggregator.
  7. provenance_notes field cites which artifact lines you drew from
     when grounding behavior — the structured trait values came from
     centroid+noise, but the narrative behaviors should be cited.
  8. Strict JSON only. Never reference protected characteristics or proxies.
```

**User prompt template** (constant `TEAMMATE_GENERATOR_USER_TEMPLATE`):

```
Generate one teammate persona consistent with the trait sheet and grounded
in the company environment.

COMPANY: {company_name}
ROLE: {role}
TAGLINE: {tagline}

CENTROID TENSIONS (this teammate may sit at any point along these)
{centroid_tensions_block}

PRE-SAMPLED TRAIT SHEET (FIXED — do not alter)
{sampled_trait_sheet_json}

ARTIFACT EXCERPTS (for grounding the narrative and goals)
"""
{artifact_excerpts}
"""

INSTRUCTIONS
------------
Return a JSON object matching the SyntheticTeammate schema (single object,
not a list). Fill all fields. Make the teammate feel specific and
internally consistent — a reader should believe this person works at this
company at this seniority.
```

**Call-site parameters:** `temperature=0.7` (higher than other calls — we want diversity across teammates), `max_tokens=2000`, `schema_name="synthetic_teammate"`. Called N times in sequence (or with light parallelism, semaphore=2) per `team/synthesize`.

---

### A.4 — Knowledge graph extractor (`services/simulation/knowledge_graph.py`)

**System prompt** (constant `KNOWLEDGE_GRAPH_SYSTEM`):

```
You build a lightweight knowledge graph over a company's sanctioned
artifacts. The graph is consumed downstream by team synthesis, scenario
drafting, and judge scoring — keep nodes specific and edges meaningful.

NODE TYPES (use these exactly, no others):
  * value          — an explicit company value or principle
  * behavior       — an observable behavior the company expects or rewards
  * anti_behavior  — a behavior the company explicitly does not reward
  * role           — a position, seniority level, or pod/team unit
  * decision       — a recurring decision the team makes
  * artifact_quote — a directly-quoted artifact passage that anchors other
                      nodes (max 240 chars)

EDGE TYPES (use these exactly):
  * demands        — value -> behavior, role -> behavior
  * forbids        — value -> anti_behavior
  * cites          — any node -> artifact_quote (provenance)
  * informs        — decision -> behavior
  * conflicts_with — value -> value, behavior -> behavior (surface tensions)

HARD RULES:
  1. Every value, behavior, anti_behavior, role, and decision node MUST
     have at least one cites edge to an artifact_quote.
  2. Surface conflicts via conflicts_with edges. Do not paper over
     contradictions inside the artifacts.
  3. Keep node count modest: 8-25 non-quote nodes plus their backing
     artifact_quote nodes.
  4. Strict JSON only. Never reference protected characteristics.
```

**User prompt template** (constant `KNOWLEDGE_GRAPH_USER_TEMPLATE`):

```
Build the knowledge graph for this company.

COMPANY: {company_name}
ROLE: {role}

ARTIFACTS
=========
VALUES:
"""
{artifact_values}
"""

ROLE SPEC:
"""
{artifact_role_spec}
"""

TEAM STRUCTURE:
"""
{artifact_team_structure}
"""

SAMPLE COMMS:
"""
{artifact_sample_comms}
"""

Return a JSON object matching the KnowledgeGraph schema.
```

**Call-site parameters:** `temperature=0.2`, `max_tokens=3000`, `schema_name="knowledge_graph"`.

---

### A.5 — Scenario drafter (`services/simulation/scenario_engine.py`)

**System prompt** (constant `SCENARIO_DRAFTER_SYSTEM`):

```
You draft a library of "moments of truth" — concrete situations the role
actually encounters that probe whether a candidate would thrive in this
specific environment.

A good scenario:
  * Is grounded in the role spec, sample comms, or a knowledge_graph
    decision node — not a generic case.
  * Probes 1-3 specific company criteria (named in scoring_dims).
  * Has a clear candidate_role: what does the candidate need to do here?
  * Has a clear expected_arc: what does "good" look like for this team?
    (Used by the judge later. Do not write a single right answer — write
    the kinds of behaviors that would land well.)
  * Is one of three types:
      - dyad: candidate and one teammate (e.g. 1:1 escalation)
      - small_group: candidate and 2-3 teammates (e.g. deal review)
      - written: candidate produces written artifact, teammates respond async

HARD RULES:
  1. Produce 5-8 scenarios per call. Avoid repetition — each scenario
     should probe a distinct combination of criteria or a distinct social
     mode (dyad / small_group / written).
  2. Each scenario.scoring_dims uses the exact keys from the company's
     criteria — do not invent new dimension keys.
  3. Cite the artifact passages that motivated each scenario in
     scenario.grounding.
  4. Difficulty calibration: roughly half the scenarios should be hard
     (genuine value tensions, real stakes); roughly half should be normal
     workdays. Avoid trick questions.
  5. Strict JSON only.
```

**User prompt template** (constant `SCENARIO_DRAFTER_USER_TEMPLATE`):

```
Draft the scenario library for this company.

COMPANY: {company_name}
ROLE: {role}

CRITERIA (use exact keys for scoring_dims)
{criteria_block}

VALUES:
"""
{artifact_values}
"""
ROLE SPEC:
"""
{artifact_role_spec}
"""
TEAM STRUCTURE:
"""
{artifact_team_structure}
"""
SAMPLE COMMS:
"""
{artifact_sample_comms}
"""

KNOWLEDGE GRAPH (decision nodes are particularly useful seeds)
{knowledge_graph_summary}

Return a JSON object with `scenarios: [...]` matching the ScenarioLibrary
schema.
```

**Call-site parameters:** `temperature=0.6` (we want variety), `max_tokens=4500`, `schema_name="scenario_library"`.

---

### A.6 — Agent turn (`services/simulation/agent_runtime.py`)

This is the per-turn prompt for any agent in a rollout (candidate or teammate). Keep one template for all roles — the agent's persona and goals are injected as data, not as a different prompt.

**System prompt** (constant `AGENT_TURN_SYSTEM`):

```
You are participating in a workplace simulation as a specific person with
a specific role and specific private goals. Your task is to produce one
turn of dialogue or action that this person would plausibly take given
the situation, the conversation so far, and your private goals.

HARD RULES:
  1. STAY IN CHARACTER. Your persona's traits, goals, and seniority are
     fixed — do not drift.
  2. Produce ONE turn. Not the whole scene. Other agents will respond.
  3. Your private_goals are private. Do not narrate them. Other agents
     do not see them. Your behavior should pursue them, but your
     utterance should not announce them.
  4. Express intent in the structured intent field — this is metadata
     visible only to the simulation system. The intent should describe
     what you are trying to accomplish with this turn (e.g. "probe the
     candidate's reasoning", "concede the analytical point but push back
     on tone", "redirect to a tactical decision").
  5. internal_state is a brief note for your own continuity across turns
     (e.g. "growing concerned about the candidate's deadline framing",
     "satisfied with the analytical depth"). Other agents do not see it.
  6. Never reference protected characteristics or proxies.
  7. Output strict JSON matching the AgentTurn schema.
  8. Set ends_turn=true ONLY when the conversation has reached a natural
     stopping point that this character would recognize (a partner has
     decided; the IC has voted; you have explicitly excused yourself; the
     written deliverable is complete). Do not set it as a way to shorten
     a difficult conversation. The runtime may end the rollout early on
     this signal — use it sparingly.

LENGTH GUIDANCE:
  * utterance: 1 short paragraph for verbal turns (60-200 words);
    1-3 sentences for terse roles (e.g. a partner who decides quickly).
  * intent: one short sentence.
  * internal_state: one short sentence.
```

**User prompt template** (constant `AGENT_TURN_USER_TEMPLATE`):

```
You are: {agent_name}, {role_on_team} ({seniority}) at {company_name}.

YOUR PERSONA
{persona_narrative}

YOUR STRUCTURED TRAITS (for reference)
{trait_sheet_json}

YOUR PRIVATE GOALS IN THIS SCENARIO
{private_goals_block}

YOUR INTERNAL STATE FROM PRIOR TURNS (may be empty on turn 1)
{internal_state_history}

SCENARIO (visible to all participants)
{scenario_prompt}

PARTICIPANTS
{participants_block}

CONVERSATION SO FAR (turn-by-turn)
{conversation_so_far}

It is now your turn ({agent_name}'s turn, turn #{turn_number}). Produce
your turn as JSON matching the AgentTurn schema.
```

**Where the User template is filled:** `private_goals_block` renders the agent's `private_goals` array as `"  * {goal}"` lines. `internal_state_history` renders this agent's previous `internal_state` notes from earlier turns in the same rollout. `participants_block` lists `"  * {name} — {role_on_team} ({seniority})"` for each participant. `conversation_so_far` renders prior turns as `"[turn N · {speaker}] {utterance}"` (intents and internal states from other agents are NOT included — those are private).

**Call-site parameters:** `temperature=0.7` (we want variation across rollouts), `max_tokens=600`, `schema_name="agent_turn"`. Called once per turn per rollout.

---

### A.7 — Judge (`services/simulation/judge.py`)

**System prompt** (constant `JUDGE_SYSTEM`):

```
You are a workplace-simulation judge. You score a transcript on specific
behavioral dimensions, citing the exact turns that justify each score.

YOU PRODUCE A SCREENING-LEVEL SIGNAL, NOT A HIRING JUDGMENT.

HARD RULES:
  1. Score ONLY the candidate's behavior. Teammate behavior is context.
  2. Every score MUST cite specific turn indices in evidence_turns. A
     score with no cited turns is invalid — return null and explain in
     justification why no evidence was available.
  3. Score on the 0-100 scale: 0 = strong misfit, 50 = ambiguous /
     insufficient evidence, 100 = strong fit.
  4. Self-report your confidence (0.0-1.0) per dimension. Lower
     confidence when: candidate had few turns, evidence is thin, the
     scenario didn't strongly probe this dimension.
  5. Justifications quote transcript text in quotation marks where
     possible. One to two sentences per justification.
  6. Never reference protected characteristics or proxies.
  7. Strict JSON only.

DIMENSION ANCHORING:
  Use the dimension's description (provided per dimension) as the rubric
  anchor. If a dimension is "Written Dissent: disagrees in writing,
  early, constructively", a score of 90 means the candidate did so
  visibly in this transcript; a score of 50 means insufficient signal;
  a score of 20 means the candidate avoided dissent or did so
  destructively.
```

**User prompt template** (constant `JUDGE_USER_TEMPLATE`):

```
Score the candidate's behavior in this transcript on the dimensions
listed below.

COMPANY: {company_name}
ROLE: {role}

SCENARIO
{scenario_block}

EXPECTED ARC (for the judge's reference; what does "good" look like on
this team)
{expected_arc}

DIMENSIONS TO SCORE (use these exact keys)
{dimensions_block}

CANDIDATE: {candidate_label}

TRANSCRIPT (turns are indexed; you cite indices in evidence_turns)
{indexed_transcript}

Return a JSON object matching the JudgeOutput schema. dimension_scores
keys match the dimension keys above exactly.
```

**Where the User template is filled:** `dimensions_block` renders each scoring dimension as `"  * {key} ({label}): {description}"`. `indexed_transcript` renders each turn as `"[#{i} · {speaker}] {utterance}"` (no intents, no internal states — judge sees only what would be observable).

**Call-site parameters:** `temperature=0.15` (consistency), `max_tokens=2500`, `schema_name="judge_output"`. Called twice per rollout (different temperature seeds: 0.15 and 0.25 to introduce judge variance, used for confidence estimation per Appendix D.4).

---

## Appendix B — JSON schemas (Python dicts, ready to paste)

All schemas below conform to the OpenRouter / Anthropic strict-mode constraints: `type`, `properties`, `required`, `additionalProperties: False`, descriptions; **no** `minimum`, `maximum`, `minItems`, `maxItems`, `pattern`. Numeric ranges and length constraints are enforced in prompts (Appendix A) and post-hoc Python validation. Each schema is named for its target call site.

### B.1 — `aggregated_persona`

```python
AGGREGATED_PERSONA_SCHEMA = {
    "type": "object",
    "properties": {
        "structured_traits": {
            "type": "object",
            "properties": {
                "big_five": {
                    "type": "object",
                    "properties": {
                        "openness":          {"type": "number"},
                        "conscientiousness": {"type": "number"},
                        "extraversion":      {"type": "number"},
                        "agreeableness":     {"type": "number"},
                        "neuroticism":       {"type": "number"},
                    },
                    "required": [
                        "openness", "conscientiousness", "extraversion",
                        "agreeableness", "neuroticism",
                    ],
                    "additionalProperties": False,
                },
                "sjt_signals": {
                    "type": "object",
                    "properties": {
                        "analyticalRigor":     {"type": "number"},
                        "intellectualHonesty": {"type": "number"},
                        "writtenDissent":      {"type": "number"},
                        "ambiguityTolerance":  {"type": "number"},
                        "lowEgoCollab":        {"type": "number"},
                    },
                    "required": [
                        "analyticalRigor", "intellectualHonesty",
                        "writtenDissent", "ambiguityTolerance", "lowEgoCollab",
                    ],
                    "additionalProperties": False,
                },
                "skill_inferences": {
                    "type": "object",
                    "additionalProperties": {"type": "number"},
                    "properties": {},
                    "required": [],
                    "description": (
                        "Free-form key/value map of skill -> 0.0-1.0. "
                        "Omit a skill entirely rather than inventing a midpoint. "
                        "Example keys: systems_thinking, written_communication, "
                        "domain_finance, code_review_discipline."
                    ),
                },
                "work_style": {
                    "type": "object",
                    "additionalProperties": {"type": "number"},
                    "properties": {},
                    "required": [],
                    "description": (
                        "Free-form key/value map of work-style preference -> 0.0-1.0. "
                        "Example keys: async_pref, written_first, conflict_comfort, "
                        "structure_seeking."
                    ),
                },
            },
            "required": ["big_five", "sjt_signals", "skill_inferences", "work_style"],
            "additionalProperties": False,
        },
        "narrative": {
            "type": "string",
            "description": (
                "800-1500 word prose synthesis. Plain prose, no headers, "
                "third-person, clinical-but-humane."
            ),
        },
        "provenance_map": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "claim": {"type": "string"},
                    "sources": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "source": {
                                    "type": "string",
                                    "description": (
                                        "One of: 'bfi', 'sjt:<sjt_id>', 'cv', "
                                        "'linkedin', 'github'."
                                    ),
                                },
                                "evidence": {
                                    "type": "string",
                                    "description": "Short quoted excerpt or item id.",
                                },
                            },
                            "required": ["source", "evidence"],
                            "additionalProperties": False,
                        },
                    },
                    "confidence": {"type": "number"},
                    "reliability_weight": {
                        "type": "string",
                        "description": "One of 'high', 'moderate', 'low'.",
                    },
                },
                "required": ["claim", "sources", "confidence", "reliability_weight"],
                "additionalProperties": False,
            },
        },
        "inconsistencies": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string"},
                    "note": {"type": "string"},
                },
                "required": ["type", "note"],
                "additionalProperties": False,
            },
        },
        "evidence_completeness": {
            "type": "object",
            "properties": {
                "bfi_present":      {"type": "boolean"},
                "sjt_present":      {"type": "boolean"},
                "cv_present":       {"type": "boolean"},
                "linkedin_present": {"type": "boolean"},
                "github_present":   {"type": "boolean"},
                "notes":            {"type": "string"},
            },
            "required": [
                "bfi_present", "sjt_present", "cv_present",
                "linkedin_present", "github_present", "notes",
            ],
            "additionalProperties": False,
        },
        "aggregator_version": {"type": "string"},
    },
    "required": [
        "structured_traits", "narrative", "provenance_map",
        "inconsistencies", "evidence_completeness", "aggregator_version",
    ],
    "additionalProperties": False,
}
```

### B.2 — `team_centroid`

```python
TEAM_CENTROID_SCHEMA = {
    "type": "object",
    "properties": {
        "big_five_centroid": {
            "type": "object",
            "properties": {
                "openness":          {"type": "object", "properties": {"value": {"type": "number"}, "provenance": {"type": "string"}}, "required": ["value", "provenance"], "additionalProperties": False},
                "conscientiousness": {"type": "object", "properties": {"value": {"type": "number"}, "provenance": {"type": "string"}}, "required": ["value", "provenance"], "additionalProperties": False},
                "extraversion":      {"type": "object", "properties": {"value": {"type": "number"}, "provenance": {"type": "string"}}, "required": ["value", "provenance"], "additionalProperties": False},
                "agreeableness":     {"type": "object", "properties": {"value": {"type": "number"}, "provenance": {"type": "string"}}, "required": ["value", "provenance"], "additionalProperties": False},
                "neuroticism":       {"type": "object", "properties": {"value": {"type": "number"}, "provenance": {"type": "string"}}, "required": ["value", "provenance"], "additionalProperties": False},
            },
            "required": ["openness", "conscientiousness", "extraversion", "agreeableness", "neuroticism"],
            "additionalProperties": False,
        },
        "skill_centroid": {
            "type": "object",
            "additionalProperties": {
                "type": "object",
                "properties": {"value": {"type": "number"}, "provenance": {"type": "string"}},
                "required": ["value", "provenance"],
                "additionalProperties": False,
            },
            "properties": {},
            "required": [],
        },
        "work_style_centroid": {
            "type": "object",
            "additionalProperties": {
                "type": "object",
                "properties": {"value": {"type": "number"}, "provenance": {"type": "string"}},
                "required": ["value", "provenance"],
                "additionalProperties": False,
            },
            "properties": {},
            "required": [],
        },
        "centroid_tensions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id":          {"type": "string"},
                    "description": {"type": "string"},
                    "evidence":    {"type": "string", "description": "Cited artifact lines that surface the tension."},
                },
                "required": ["id", "description", "evidence"],
                "additionalProperties": False,
            },
        },
        "sigma_recommendations": {
            "type": "object",
            "properties": {
                "big_five":   {"type": "number"},
                "skill":      {"type": "number"},
                "work_style": {"type": "number"},
            },
            "required": ["big_five", "skill", "work_style"],
            "additionalProperties": False,
        },
    },
    "required": [
        "big_five_centroid", "skill_centroid", "work_style_centroid",
        "centroid_tensions", "sigma_recommendations",
    ],
    "additionalProperties": False,
}
```

### B.3 — `synthetic_teammate`

```python
SYNTHETIC_TEAMMATE_SCHEMA = {
    "type": "object",
    "properties": {
        "name":            {"type": "string"},
        "role_on_team":    {"type": "string"},
        "seniority": {
            "type": "string",
            "description": "One of: junior, mid, senior, lead.",
        },
        "trait_sheet": {
            "type": "object",
            "properties": {
                "big_five": {
                    "type": "object",
                    "properties": {
                        "openness":          {"type": "number"},
                        "conscientiousness": {"type": "number"},
                        "extraversion":      {"type": "number"},
                        "agreeableness":     {"type": "number"},
                        "neuroticism":       {"type": "number"},
                    },
                    "required": ["openness", "conscientiousness", "extraversion", "agreeableness", "neuroticism"],
                    "additionalProperties": False,
                },
                "skill_profile":      {"type": "object", "additionalProperties": {"type": "number"}, "properties": {}, "required": []},
                "work_style":         {"type": "object", "additionalProperties": {"type": "number"}, "properties": {}, "required": []},
            },
            "required": ["big_five", "skill_profile", "work_style"],
            "additionalProperties": False,
        },
        "narrative":     {"type": "string", "description": "300-600 words, third-person, plain prose."},
        "private_goals": {
            "type": "array",
            "items": {"type": "string", "description": "One sentence per goal."},
        },
        "provenance_notes": {
            "type": "string",
            "description": "Cites which artifact passages grounded the narrative behaviors.",
        },
    },
    "required": [
        "name", "role_on_team", "seniority", "trait_sheet",
        "narrative", "private_goals", "provenance_notes",
    ],
    "additionalProperties": False,
}
```

### B.4 — `knowledge_graph`

```python
KNOWLEDGE_GRAPH_SCHEMA = {
    "type": "object",
    "properties": {
        "nodes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id":   {"type": "string", "description": "Stable slug, e.g. 'value:patience'."},
                    "type": {"type": "string", "description": "One of: value, behavior, anti_behavior, role, decision, artifact_quote."},
                    "label":{"type": "string"},
                    "body": {"type": "string", "description": "1-3 sentences. For artifact_quote: the quoted text (max 240 chars)."},
                },
                "required": ["id", "type", "label", "body"],
                "additionalProperties": False,
            },
        },
        "edges": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "source":{"type": "string"},
                    "target":{"type": "string"},
                    "type":  {"type": "string", "description": "One of: demands, forbids, cites, informs, conflicts_with."},
                    "note":  {"type": "string"},
                },
                "required": ["source", "target", "type", "note"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["nodes", "edges"],
    "additionalProperties": False,
}
```

### B.5 — `scenario_library`

```python
SCENARIO_LIBRARY_SCHEMA = {
    "type": "object",
    "properties": {
        "scenarios": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title":         {"type": "string"},
                    "type":          {"type": "string", "description": "One of: dyad, small_group, written."},
                    "prompt":        {"type": "string", "description": "The scenario setup, visible to all agents."},
                    "candidate_role":{"type": "string", "description": "What the candidate needs to do."},
                    "expected_arc":  {"type": "string", "description": "What 'good' looks like on this team. NOT a single right answer — describe the kinds of behaviors that would land well."},
                    "scoring_dims": {
                        "type": "array",
                        "items": {"type": "string", "description": "Exact criterion key from the company. E.g. 'analyticalRigor'."},
                    },
                    "participating_roles": {
                        "type": "array",
                        "items": {"type": "string", "description": "Role descriptions of teammates needed (e.g. 'senior analyst', 'pod VP'). Used by scenario_engine.prepare_rollout to select teammates."},
                    },
                    "max_turns": {"type": "integer", "description": "Suggested max turns for the rollout. Typical: 6 for dyad, 10 for small_group, 4 for written."},
                    "grounding": {
                        "type": "string",
                        "description": "Artifact lines that motivated this scenario.",
                    },
                },
                "required": [
                    "title", "type", "prompt", "candidate_role", "expected_arc",
                    "scoring_dims", "participating_roles", "max_turns", "grounding",
                ],
                "additionalProperties": False,
            },
        },
    },
    "required": ["scenarios"],
    "additionalProperties": False,
}
```

### B.6 — `agent_turn`

```python
AGENT_TURN_SCHEMA = {
    "type": "object",
    "properties": {
        "utterance": {
            "type": "string",
            "description": "The agent's spoken / written contribution this turn. 1-200 words.",
        },
        "intent": {
            "type": "string",
            "description": "One short sentence describing what the agent is trying to accomplish. NOT visible to other agents.",
        },
        "internal_state": {
            "type": "string",
            "description": "One short sentence note for this agent's continuity across turns. NOT visible to other agents.",
        },
        "ends_turn": {
            "type": "boolean",
            "description": "True if the agent considers the conversation naturally complete after this turn (e.g. partner has decided). The runtime may end the rollout early on this signal.",
        },
    },
    "required": ["utterance", "intent", "internal_state", "ends_turn"],
    "additionalProperties": False,
}
```

### B.7 — `judge_output`

```python
def judge_output_schema(dimension_keys: list[str]) -> dict:
    """Per-call schema bound to the specific dimension keys for this scenario.
    Pattern matches matcher._schema_for_criteria — keys come from the row,
    not from the model.
    """
    dim_score_schema = {
        "type": "object",
        "properties": {
            "score": {"type": "integer", "description": "0-100; null only when no evidence is available."},
            "justification": {"type": "string", "description": "1-2 sentences quoting transcript text."},
            "evidence_turns": {
                "type": "array",
                "items": {"type": "integer", "description": "Index into the indexed_transcript. Required to be non-empty unless score is null."},
            },
            "confidence": {"type": "number", "description": "0.0-1.0 self-reported confidence."},
        },
        "required": ["score", "justification", "evidence_turns", "confidence"],
        "additionalProperties": False,
    }
    dimension_scores = {
        "type": "object",
        "properties": {k: dim_score_schema for k in dimension_keys},
        "required": dimension_keys,
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {
            "dimension_scores": dimension_scores,
            "transcript_summary": {
                "type": "string",
                "description": "1-2 sentence headline summary of what the candidate did. Surfaced in rollout summaries.",
            },
            "judge_notes": {
                "type": "string",
                "description": "Optional notes from the judge for the audit trail.",
            },
        },
        "required": ["dimension_scores", "transcript_summary", "judge_notes"],
        "additionalProperties": False,
    }
```

### B.8 — `FitProfile` (the top-level Match.report shape)

This isn't a JSON schema for an LLM call — it's the final shape persisted to `Match.report`. It is *additive* relative to the existing report shape so the existing `FitReport.jsx` keeps reading correctly during the migration window.

```python
# Persisted to Match.report. Backward-compatible: existing fields preserved
# for the legacy FitReport.jsx, new fields layered on top for FitProfileV2.jsx.
FIT_PROFILE_SHAPE = {
    # ===== Legacy fields (preserved verbatim) =====
    "companyId": "...",
    "companyName": "...",
    "role": "...",
    "overallScore": 78,                    # weighted from criterionScores
    "band": "Strong fit" | "Plausible fit" | "Edge case" | "Low fit",
    "bandNote": "...",
    "criterionScores": {
        "<key>": {"score": 78, "justification": "..."},
    },
    "inconsistencyFlags": [{"type": "...", "note": "..."}],
    "auditTrail": {"model": "...", "timestamp": "...", "note": "..."},

    # ===== New fields (FitProfileV2) =====
    "version": "v2",                       # legacy reports omit this; v2 sets it
    "dimensionalFit": {
        "<key>": {
            "mean":  78.4,
            "std":   6.1,
            "n":     5,                    # number of rollouts contributing
            "judgeAgreement": 0.92,        # 1 - (inter-judge std / max possible std)
        },
    },
    "rolloutSummaries": [
        {
            "rolloutId":     "...",
            "scenarioId":    "...",
            "scenarioTitle": "...",
            "kIndex":        1,
            "headline":      "...",        # transcript_summary from judge
            "scores":        {"<key>": 78}, # this rollout's per-dim scores (mean of judges)
        },
    ],
    "baselineComparison": {
        "overallScore":       72,
        "perCriterion":       {"<key>": {"score": 70, "justification": "..."}},
        "deltaVsSim":         {"<key>": +8},
        "robustnessSummary":  "Sim higher on Written Dissent (+12), lower on Pattern Recognition (-6).",
    },
    "confidenceSignals": {
        "overallStd":      4.7,
        "perCriterionStd": {"<key>": 6.1},
        "minNRollouts":    5,
        "judgeAgreementMean": 0.91,
    },
    "auditTrailV2": {
        "personaAggregatorVersion": "v0.1",
        "judgeModel":               "anthropic/claude-sonnet-4.6",
        "judgeCount":               2,
        "kPerScenario":             5,
        "scenariosRun":             8,
        "totalLLMCalls":            127,
        "totalTokens":              { "prompt": 92141, "completion": 18733 },
        "wallTimeMs":               48211,
        "proofLayer":               "null",  # NullProofLayer; "reasoning_layer" later
    },
}
```

---

## Appendix C — Migrations + data compatibility

### C.1 — Alembic migrations (split across phases)

Per Section 11, the schema changes ship in **three** Alembic migrations, each scoped to its phase. This avoids creating tables that are not yet read or written, and keeps every commit independently revertable. The SQLite local-dev path continues to use `Base.metadata.create_all` and picks up new tables automatically once `models.py` is updated — these Alembic files are the canonical Postgres path.

#### C.1.1 — `0003_persona_aggregator.py` (Phase 1B)

Adds the three columns the persona aggregator needs to cache its output. No new tables.

```python
"""Persona aggregator cache columns on candidates.

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-26
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("candidates", sa.Column("aggregated_persona", sa.JSON, nullable=True))
    op.add_column("candidates", sa.Column("aggregation_audit", sa.JSON, nullable=True))
    op.add_column("candidates", sa.Column("aggregated_at", sa.DateTime, nullable=True))


def downgrade() -> None:
    op.drop_column("candidates", "aggregated_at")
    op.drop_column("candidates", "aggregation_audit")
    op.drop_column("candidates", "aggregated_persona")
```

#### C.1.2 — `0004_company_knowledge_graph.py` (Phase 2A)

Adds the single column for the company's extracted knowledge graph.

```python
"""Knowledge graph column on companies.

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-26
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("companies", sa.Column("knowledge_graph", sa.JSON, nullable=True))


def downgrade() -> None:
    op.drop_column("companies", "knowledge_graph")
```

#### C.1.3 — `0005_simulation_pipeline.py` (Phase 2B)

Adds the simulation tables in one migration. Grouped together because they reference each other and rolling them out individually would require more juggling than it's worth — `synthetic_teammates`, `moments_of_truth`, `rollouts`, `rollout_scores`, `baseline_comparisons`, and `rollout_logs` all land here. Phase 2B writes only `synthetic_teammates`; Phase 3A writes `moments_of_truth`; Phases 4A–4C write the rest. Empty tables don't cost anything.

```python
"""Simulation pipeline tables: teammates, scenarios, rollouts, scoring, logs.

Revision ID: 0005
Revises: 0004
Create Date: 2026-04-26
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---- synthetic_teammates ----
    op.create_table(
        "synthetic_teammates",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("company_id", sa.String(64), sa.ForeignKey("companies.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("role_on_team", sa.String(200), nullable=False),
        sa.Column("seniority", sa.String(20), nullable=False),
        sa.Column("trait_sheet", sa.JSON, nullable=False),
        sa.Column("narrative", sa.Text, nullable=False, server_default=""),
        sa.Column("private_goals", sa.JSON, nullable=False),
        sa.Column("generated_from", sa.JSON, nullable=True),
        sa.Column("is_edited", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("ordering", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )

    # ---- moments_of_truth ----
    op.create_table(
        "moments_of_truth",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("company_id", sa.String(64), sa.ForeignKey("companies.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("scenario_type", sa.String(20), nullable=False),  # dyad | small_group | written
        sa.Column("prompt", sa.Text, nullable=False),
        sa.Column("candidate_role", sa.Text, nullable=False),
        sa.Column("expected_arc", sa.Text, nullable=False),
        sa.Column("scoring_dims", sa.JSON, nullable=False),
        sa.Column("participating_roles", sa.JSON, nullable=False),
        sa.Column("max_turns", sa.Integer, nullable=False, server_default="6"),
        sa.Column("grounding", sa.Text, nullable=False, server_default=""),
        sa.Column("is_llm_drafted", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("ordering", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )

    # ---- rollouts ----
    op.create_table(
        "rollouts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("match_id", sa.String(36), sa.ForeignKey("matches.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("scenario_id", sa.String(36), sa.ForeignKey("moments_of_truth.id", ondelete="SET NULL"), index=True, nullable=True),
        sa.Column("rollout_index", sa.Integer, nullable=False),
        sa.Column("transcript", sa.JSON, nullable=False),
        sa.Column("final_state", sa.JSON, nullable=False),
        sa.Column("duration_turns", sa.Integer, nullable=False, server_default="0"),
        sa.Column("seed", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="completed"),  # completed | failed | aborted
        sa.Column("failure_reason", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )

    # ---- rollout_scores ----
    op.create_table(
        "rollout_scores",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("rollout_id", sa.String(36), sa.ForeignKey("rollouts.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("dimension_key", sa.String(80), nullable=False),
        sa.Column("score", sa.Integer, nullable=True),  # null when judge had no evidence
        sa.Column("justification", sa.Text, nullable=False, server_default=""),
        sa.Column("evidence_turns", sa.JSON, nullable=False),
        sa.Column("judge_model", sa.String(120), nullable=False),
        sa.Column("judge_seed_index", sa.Integer, nullable=False, server_default="0"),
        sa.Column("confidence", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_rollout_scores_dim", "rollout_scores", ["rollout_id", "dimension_key"])

    # ---- baseline_comparisons ----
    op.create_table(
        "baseline_comparisons",
        sa.Column("match_id", sa.String(36), sa.ForeignKey("matches.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("overall_score", sa.Integer, nullable=False),
        sa.Column("per_criterion", sa.JSON, nullable=False),
        sa.Column("band", sa.String(40), nullable=False, server_default=""),
        sa.Column("band_note", sa.Text, nullable=False, server_default=""),
        sa.Column("delta_vs_sim", sa.JSON, nullable=False),
        sa.Column("robustness_summary", sa.Text, nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )

    # ---- rollout_logs (append-only event store) ----
    op.create_table(
        "rollout_logs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("match_id", sa.String(36), sa.ForeignKey("matches.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("rollout_id", sa.String(36), sa.ForeignKey("rollouts.id", ondelete="CASCADE"), index=True, nullable=True),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("payload", sa.JSON, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now(), index=True),
    )


def downgrade() -> None:
    op.drop_table("rollout_logs")
    op.drop_table("baseline_comparisons")
    op.drop_index("ix_rollout_scores_dim", table_name="rollout_scores")
    op.drop_table("rollout_scores")
    op.drop_table("rollouts")
    op.drop_table("moments_of_truth")
    op.drop_table("synthetic_teammates")
```

### C.2 — `models.py` additions

Add SQLAlchemy classes mirroring the migration. Pattern: same as existing entities — `mapped_column` typing, `JSON` for the structured fields, `relationship` back-refs. A few concrete decisions to bake in:

- `SyntheticTeammate.private_goals` is `Mapped[list[str]]` with `JSON` column, default `list`. Validate at write time that it's a list of strings.
- `MomentOfTruth.scoring_dims` is `Mapped[list[str]]` of criterion keys; validate at write time that every key matches an existing `Criterion.key` for the company.
- `Rollout.transcript` is the canonical JSON shape `[{turn, speaker_id, speaker_role, content, intent, internal_state}, ...]` — define as a TypedDict in `services/simulation/types.py` for typed access.
- `RolloutLog` rows are append-only. Add a SQLAlchemy event listener that raises on any update or delete attempt to enforce this in code.

### C.3 — Backward compatibility for existing `Match.report`

Existing `Match.report` rows persisted by the legacy matcher have the shape documented at the top of `FIT_PROFILE_SHAPE` (legacy fields only, no `version` key). The migration to FitProfileV2 must not break them.

Strategy:

1. **Schema is already permissive.** `Match.report` is already a `JSON` column with no enforced shape. New rows simply add new fields. No migration of existing rows is needed.
2. **Frontend handles both shapes.** `FitProfileV2.jsx` checks for `report.version === "v2"`; if absent, it falls back to rendering the legacy `FitReport.jsx`. Both stay in the codebase indefinitely (the legacy one is small).
3. **Simulation matcher tags new outputs.** Every report produced by `simulation_matcher.run_match` sets `report["version"] = "v2"` and includes the new fields.
4. **Baseline comparison is also a fresh row.** When the simulation matcher runs, it populates a new `BaselineComparison` row with the same `match_id`. Legacy matches have no corresponding `BaselineComparison` row — the frontend treats absence as "no baseline available" (the strip is hidden, not errored).

### C.4 — Seed data updates

`seed_data.py` does not change shape — Meridian and Kestrel keep their existing structure. After Phase 2B (team synthesizer) ships, add an optional one-time helper `seed_teams_for_seed_companies()` that calls the team synthesizer for the two seed companies on first boot if they have no teammates yet. This makes the demo immediately walkable without manager-side action.

```python
# backend/app/seed_data.py — append after seed_companies()
async def seed_teams_for_seed_companies(db: Session) -> None:
    """One-time bootstrap: synthesize teammates for seed companies if absent.
    Idempotent. Safe on every boot."""
    from .services.simulation import team_synthesizer
    for company_id in ("meridian-capital", "kestrel-growth"):
        company = db.get(models.Company, company_id)
        if company is None:
            continue
        existing = db.query(models.SyntheticTeammate).filter_by(
            company_id=company.id
        ).count()
        if existing > 0:
            continue
        teammates = await team_synthesizer.synthesize(company)
        for t in teammates:
            db.add(t)
    db.commit()
```

The same pattern applies to scenario libraries once the scenario drafter ships — add `seed_scenarios_for_seed_companies()` in Phase 3A.

### C.5 — Migration ordering recap

Three migrations, one per logical schema landing:

1. **`0003_persona_aggregator.py`** ships in **Phase 1B** — three `candidates` columns. No new tables. Reverting drops only the persona cache.
2. **`0004_company_knowledge_graph.py`** ships in **Phase 2A** — one `companies` column. Reverting drops only the graph storage.
3. **`0005_simulation_pipeline.py`** ships in **Phase 2B** — all six simulation tables (`synthetic_teammates`, `moments_of_truth`, `rollouts`, `rollout_scores`, `baseline_comparisons`, `rollout_logs`). Phases 3A through 4C populate them progressively; the migration itself does not move between phases.

Generate each migration only at the start of its owning phase — do not pre-create empty files. `Base.metadata.create_all` on the SQLite local-dev path picks up new `models.py` declarations regardless of Alembic state, so SQLite contributors are unaffected by Postgres migration ordering.

---

## Appendix D — Errors, retries, concurrency, cost

### D.1 — OpenRouter retry policy

The current `services/openrouter.py::chat_json` has no retries. Wrap it (in the wrapper, not the call sites) with exponential backoff. Add a thin retry layer in the same module:

```python
# services/openrouter.py — additions

class RetryableError(OpenRouterError):
    """Raised on conditions worth retrying (429, 5xx, transient JSON failures)."""

class FatalError(OpenRouterError):
    """Raised on conditions where retry will not help (4xx other than 429,
    schema-mismatch after healing exhausted)."""

_RETRY_DELAYS = (1.0, 2.0, 4.0)  # 3 retries; 7s total worst-case wait

async def chat_json_with_retry(*args, max_attempts: int = 4, **kwargs) -> dict[str, Any]:
    last_exc: Exception | None = None
    for attempt in range(max_attempts):
        try:
            return await chat_json(*args, **kwargs)
        except RetryableError as e:
            last_exc = e
            if attempt + 1 >= max_attempts:
                break
            await asyncio.sleep(_RETRY_DELAYS[min(attempt, len(_RETRY_DELAYS) - 1)])
        except FatalError:
            raise
    raise last_exc  # surface the last retryable failure
```

In `chat_json`, classify failures:
- HTTP 429, 502, 503, 504 → `RetryableError`
- HTTP 400, 401, 403, 404, 422 (other 4xx) → `FatalError`
- `httpx.HTTPError` (network) → `RetryableError`
- `JSONDecodeError` after healing → `FatalError` (the healing plugin already retried)

All new simulation modules use `chat_json_with_retry`. Legacy `criteria_extractor` and `matcher` can stay on `chat_json` for v0 to keep blast radius contained, then migrate in a follow-up.

### D.2 — Mid-rollout failure semantics

A rollout is K (default 5) per scenario; a match runs N (typical 5-8) scenarios. Failures cascade thoughtfully:

| Failure point | Behavior | Logging |
|---|---|---|
| Single agent turn fails (after retries) | Mark this rollout as `status="failed"` with `failure_reason`. **Do not retry the rollout** — the partial transcript is preserved for debugging. | `rollout_failed` event |
| Single rollout fails | Continue other rollouts in parallel. The aggregator reduces effective N for affected dimensions. If `failed_count > K // 2 + 1`, abort the *match* — partial signal is misleading. | per-rollout + `match_partial_failure` if abort |
| Single judge call fails | Fall back to single-judge for that rollout. Halve confidence in `RolloutScore.confidence`. | `judge_fallback` event |
| Both judges fail for a rollout | Mark `RolloutScore` for that rollout's dimensions as `score=null`. Aggregator treats null scores as "no signal" and reduces effective N. | `rollout_unscored` |
| Persona aggregator fails | Abort the match before any rollout starts. The matcher returns a `502` to the trigger endpoint with `detail` explaining. | `persona_aggregation_failed` |
| Team or scenario library missing | Abort with `409` and `detail="Company has no synthetic team — synthesize the team first."` (or analogous for scenarios). The route surfaces an actionable manager message. | `match_blocked_by_missing_setup` |
| Baseline matcher fails | The simulation continues and persists. Match.report's `baselineComparison` field is omitted. Frontend hides the comparison strip. | `baseline_failed` (warn-level) |

### D.3 — Per-match cost ceiling and circuit breaker

Add `cost_tracker.py` to `services/simulation/`:

```python
@dataclass
class CostBudget:
    ceiling_usd: float                  # from settings
    spent_usd: float = 0.0
    calls_made: int = 0
    tokens_in: int = 0
    tokens_out: int = 0

class CostCeilingExceeded(RuntimeError):
    pass

# Per-model price table (USD per 1K tokens). Update on model changes.
_MODEL_PRICES = {
    "anthropic/claude-sonnet-4.6":  {"in": 0.003, "out": 0.015},
    "anthropic/claude-haiku-4.5":   {"in": 0.0008, "out": 0.004},
    # add others as needed; default to sonnet pricing
}

def estimate_call_cost(model: str, usage: dict) -> float:
    p = _MODEL_PRICES.get(model, _MODEL_PRICES["anthropic/claude-sonnet-4.6"])
    return (usage.get("prompt_tokens", 0) / 1000) * p["in"] \
         + (usage.get("completion_tokens", 0) / 1000) * p["out"]

async def tracked_chat_json(budget: CostBudget, **kwargs):
    if budget.spent_usd >= budget.ceiling_usd:
        raise CostCeilingExceeded(
            f"Match exceeded ${budget.ceiling_usd:.2f} ceiling "
            f"after {budget.calls_made} calls."
        )
    out = await openrouter.chat_json_with_retry(**kwargs)
    # OpenRouter returns usage in the body — extract it in chat_json and pass through.
    usage = out.pop("_usage", {})  # internal field set by chat_json
    cost = estimate_call_cost(kwargs.get("model") or settings.openrouter_model, usage)
    budget.spent_usd += cost
    budget.calls_made += 1
    budget.tokens_in += usage.get("prompt_tokens", 0)
    budget.tokens_out += usage.get("completion_tokens", 0)
    return out
```

`simulation_matcher.run_match` constructs a `CostBudget` per match (ceiling from `settings.match_cost_ceiling_usd`, default `5.00`), passes it through every LLM call, and on `CostCeilingExceeded`:
- Aborts further rollouts.
- Aggregates whatever scoring is complete.
- Sets `auditTrailV2.aborted = "cost_ceiling"` in the report.
- Logs `match_aborted_cost_ceiling` event.

Add `MATCH_COST_CEILING_USD=5.00` to `.env.example` and `Settings` in `config.py`.

### D.4 — Concurrency caps

Three semaphore layers, configured per match:

```python
# services/simulation/simulation_matcher.py — concurrency setup
match_concurrency = SimulationConcurrency(
    rollouts_in_flight = settings.sim_rollouts_concurrency,    # default K=5
    judges_per_rollout = settings.sim_judges_per_rollout,      # default 2
    teammate_synthesis = 2,                                    # team synthesizer parallelism
)
```

Existing `routes/matches.py::search_candidates` uses a `Semaphore(4)` for outer-loop concurrency across candidates. The simulation pipeline's per-match semaphores are independent. Total OpenRouter concurrency under `/matches/search` could spike — add a global semaphore in `openrouter.py` (default 16) as a backstop:

```python
# services/openrouter.py — top of file
_GLOBAL_OPENROUTER_SEM = asyncio.Semaphore(int(os.environ.get("OPENROUTER_GLOBAL_CONCURRENCY", "16")))
```

Wrap `chat_json`'s `httpx.AsyncClient.post` call in `async with _GLOBAL_OPENROUTER_SEM:`.

### D.5 — Timeout defaults

| Layer | Default timeout | Failure handling |
|---|---|---|
| Single OpenRouter call | 90s (existing in `chat_json`) | RetryableError → backoff |
| Single agent turn | 90s (one LLM call) | Same as above |
| Single rollout (wall) | 5 min | Abort rollout → mark `failed` |
| Per-judge call | 90s | Same as above |
| Single match (wall) | 15 min | Abort match → partial report with `auditTrailV2.aborted = "wall_timeout"` |

Implement match-level timeout via `asyncio.wait_for` in `simulation_matcher.run_match`. Implement rollout-level timeout via `asyncio.wait_for` inside `rollout.execute_rollout`. Both honor cooperative cancellation — finally blocks must persist whatever rollouts/scores already completed before re-raising.

### D.6 — Health check additions

Extend the `/health` endpoint to also surface simulation-pipeline readiness:

```python
@router.get("/health")
def health(db: Session = Depends(get_session)) -> dict:
    return {
        "status": "ok",
        "db": _check_db(db),
        "openrouter_key_set": bool(settings.openrouter_api_key),
        "supabase_configured": bool(settings.supabase_url),
        "simulation_pipeline": {
            "default_k": settings.sim_rollouts_concurrency,
            "judges_per_rollout": settings.sim_judges_per_rollout,
            "match_cost_ceiling_usd": settings.match_cost_ceiling_usd,
        },
    }
```

This makes ops issues visible at a single GET.

### D.7 — Required `Settings` additions

Add to `backend/app/config.py::Settings`:

```python
# --- Simulation ---
sim_rollouts_concurrency: int = 5    # K — also the default rollouts-per-scenario
sim_judges_per_rollout: int = 2
sim_max_turns_dyad: int = 6
sim_max_turns_small_group: int = 10
sim_max_turns_written: int = 4
sim_default_team_size: int = 5
sim_match_wall_timeout_s: int = 900   # 15 min
sim_rollout_wall_timeout_s: int = 300  # 5 min
match_cost_ceiling_usd: float = 5.0
openrouter_global_concurrency: int = 16
```

And to `.env.example`:

```bash
SIM_ROLLOUTS_CONCURRENCY=5
SIM_JUDGES_PER_ROLLOUT=2
SIM_DEFAULT_TEAM_SIZE=5
MATCH_COST_CEILING_USD=5.00
OPENROUTER_GLOBAL_CONCURRENCY=16
```

---

## Appendix E — Frontend component contracts

All new components live under `frontend/src/components/` unless noted. They use the existing `design.js` tokens (`COLORS`, `FONT_DISPLAY`, `FONT_BODY`, `FONT_MONO`) and the existing CSS utility classes (`label-mono`, `rule`, `rule-thick`, `card`, `pulse-dot`). Do not introduce a new design system — the editorial aesthetic is a real asset and consistency matters more than novelty.

Each component below specifies: **purpose**, **props** (with types), **state** (if any), **layout intent** (what the user sees), and **failure modes** (what to render when data is missing).

### E.1 — `FitProfileV2.jsx` (replaces `FitReport.jsx` for v2 reports)

**Purpose.** Top-level fit-report panel. Replaces `FitReport.jsx` for reports with `report.version === "v2"`. Falls back to legacy `FitReport.jsx` when the report has no `version` field.

**Wrapper pattern** (in `ManagerDashboard.jsx` or wherever `FitReport` is currently rendered):

```jsx
import FitReport from "../components/FitReport.jsx";
import FitProfileV2 from "../components/FitProfileV2.jsx";

function FitReportShell({ report, criteriaIndex, onOpenRollout }) {
  if (report?.version === "v2") {
    return <FitProfileV2 report={report} criteriaIndex={criteriaIndex} onOpenRollout={onOpenRollout} />;
  }
  return <FitReport report={report} criteriaIndex={criteriaIndex} />;
}
```

**Props.**

```ts
{
  report: {
    version: "v2",
    companyId: string,
    companyName: string,
    role: string,
    overallScore: number,
    band: string,
    bandNote: string,
    criterionScores: Record<string, {score: number, justification: string}>,
    inconsistencyFlags: Array<{type: string, note: string}>,
    dimensionalFit: Record<string, {mean: number, std: number, n: number, judgeAgreement: number}>,
    rolloutSummaries: Array<{rolloutId: string, scenarioId: string, scenarioTitle: string, kIndex: number, headline: string, scores: Record<string, number>}>,
    baselineComparison: {
      overallScore: number,
      perCriterion: Record<string, {score: number, justification: string}>,
      deltaVsSim: Record<string, number>,
      robustnessSummary: string,
    } | null,
    confidenceSignals: {overallStd: number, perCriterionStd: Record<string, number>, minNRollouts: number, judgeAgreementMean: number},
    auditTrailV2: object,
  },
  criteriaIndex: Record<string, {key: string, label: string, description: string, weight: number}>,
  onOpenRollout: (rolloutId: string) => void,
}
```

**State.** None internal; this is a presentational component.

**Layout intent.** Top-to-bottom:
1. Headline strip: same `band` + `bandNote` as legacy, with `BaselineCompareStrip` rendered to the right of the weighted-fit number when `baselineComparison` is present.
2. Dimensional fit chart: `DimensionalFitChart` renders `criterionScores` enriched with `dimensionalFit` variance.
3. Rollout summaries strip: row of `RolloutSummaryCard`s, click → `onOpenRollout(rolloutId)`.
4. Inconsistency flags panel: identical to legacy.
5. Methodology footer: rendered from `auditTrailV2`. Visible to manager — `JetBrains Mono`, muted color, with explicit `K=5 across 8 scenarios · judge=Claude Sonnet 4.6 · 2 judges per rollout · proof layer=null`.

**Failure modes.**
- `dimensionalFit` missing → render `DimensionalFitChart` without variance bands (degrade, don't crash).
- `rolloutSummaries` empty → omit the strip entirely with a `label-mono` note "no rollouts persisted for this match" (should never happen for v2 but defensive).
- `baselineComparison` null → `BaselineCompareStrip` not rendered.
- `confidenceSignals` missing → methodology footer hides confidence numbers.

### E.2 — `DimensionalFitChart.jsx`

**Purpose.** Replaces the per-criterion `ScoreBar` rows in legacy `FitReport`. Same vertical-list layout but each row gets a `VarianceBar` instead of a flat bar, plus the per-criterion judge-agreement number in the row header.

**Props.**

```ts
{
  criterionScores: Record<string, {score: number, justification: string}>,
  dimensionalFit: Record<string, {mean: number, std: number, n: number, judgeAgreement: number}> | null,
  criteriaIndex: Record<string, {label: string, description: string, weight: number}>,
}
```

**Layout intent.**
- One row per criterion in `criteriaIndex` order (preserve existing ordering — `Criterion.ordering` from the company).
- Row header: criterion label (FONT_DISPLAY 20px), weight as `label-mono` "weight 25%", judge-agreement as `label-mono` "agreement 0.92" (right-justified). Score number in FONT_MONO 20px, right edge.
- Row bar: `VarianceBar` with `mean = dimensionalFit[key].mean`, `std = dimensionalFit[key].std`, `displayedScore = criterionScores[key].score`. When `dimensionalFit` missing for a key, use `score` as mean and `std=0`.
- Row footer: justification text in muted color, line-height 1.55 (matches legacy).

**Failure modes.**
- `dimensionalFit === null` → render exactly like legacy `FitReport`'s decomposition section. Backwards-compat fallback.

### E.3 — `VarianceBar.jsx`

**Purpose.** Visual primitive: a horizontal bar showing a mean score with a ±σ shaded band overlay. Replaces flat `ScoreBar` everywhere in v2.

**Props.**

```ts
{
  mean: number,         // 0-100
  std: number,          // 0-50 typical
  height?: number,      // px, default 8
  showBand?: boolean,   // default true; false renders flat ScoreBar look
  accentColor?: string, // default COLORS.accent
}
```

**Layout intent.**
- Outer track: full-width, `height` px, background `COLORS.rule`.
- Filled portion: from 0 to `mean`%, color `accentColor`.
- Variance band overlay: from `(mean - std)` to `(mean + std)`% (clamped to [0, 100]), shown as a slightly translucent overlay using `COLORS.accentSoft` at 0.6 opacity, behind the filled portion's leading edge.
- A 2px vertical tick at `mean` to make the central estimate readable.

**Visual rule:** narrow band = high confidence; wide band = uncertain. The variance band must be visible to the eye — if `std === 0`, render a flat bar identical to legacy `ScoreBar`.

**Failure modes.** None — degrades to a flat bar when std is 0.

### E.4 — `BaselineCompareStrip.jsx`

**Purpose.** Compact "robustness check" badge rendered in the headline area showing simulation-vs-baseline divergence. The sales-narrative byproduct of validation infrastructure.

**Props.**

```ts
{
  baselineComparison: {
    overallScore: number,
    perCriterion: Record<string, {score: number, justification: string}>,
    deltaVsSim: Record<string, number>,  // positive = sim is higher
    robustnessSummary: string,
  },
  simulationOverallScore: number,
  criteriaIndex: Record<string, {label: string}>,
  onExpand?: () => void,  // optional click target to open detailed comparison view
}
```

**Layout intent.**
- A pill-shaped strip, accent-bordered, ~280-360px wide.
- Top line: `label-mono` "Robustness check".
- Body: "Sim {sim}/100 · Baseline {baseline}/100" with the delta in the accent color (e.g. "+6").
- Sub-body: `robustnessSummary` text, two lines max, ellipsis after.
- If `onExpand` provided, a small "View detail" affordance using `label-mono`; clicking expands a modal with full per-criterion deltas.

**Failure modes.** Hidden entirely when prop is null.

### E.5 — `RolloutSummaryCard.jsx`

**Purpose.** Single rollout in the rollout-summaries strip. Click → opens transcript viewer.

**Props.**

```ts
{
  summary: {
    rolloutId: string,
    scenarioId: string,
    scenarioTitle: string,
    kIndex: number,
    headline: string,
    scores: Record<string, number>,
  },
  onClick: (rolloutId: string) => void,
}
```

**Layout intent.**
- Card class (existing `.card` style).
- Top: `label-mono` "Rollout #{kIndex} · {scenarioTitle}".
- Headline: 1-2 lines, FONT_DISPLAY 18px, `font-style: italic`, drop-cap optional.
- Score bar at bottom showing the rollout's per-dim scores as 5 thin colored ticks (one per criterion), color-coded green/amber/red by tertile.
- Hover: subtle elevation + cursor pointer.

**Failure modes.** None — card is self-contained.

### E.6 — `TranscriptViewer.jsx`

**Purpose.** Modal or full-page view showing one rollout's transcript with per-turn annotations.

**Lives at:** `frontend/src/pages/TranscriptViewer.jsx` (it's a full route, not just a component).

**Route.** `/manager/matches/:matchId/rollouts/:rolloutId`.

**Props.** Pulls from API; takes route params. Internal data fetch via `api.matches.getRollout(matchId, rolloutId)`.

**State.**
```ts
{
  rollout: {id, scenarioTitle, transcript: TurnArray, scores: ScoreArray, status} | null,
  loading: boolean,
  error: string | null,
  showIntents: boolean,           // toggle to reveal intent + internal_state per turn
  highlightedTurnIndices: Set,    // turns the judge cited as evidence
  selectedDimension: string | null, // when a dimension is selected, only its evidence turns highlight
}
```

**Layout intent.**
- Header: scenario title (FONT_DISPLAY 32px), scenario prompt as a blockquote in muted text.
- Toolbar: dimension chips (one per scoring dim), click toggles `selectedDimension` and updates highlights. "Show intents" checkbox toggles `showIntents`.
- Transcript: vertical list of `TranscriptTurn` (sub-component) — each turn renders speaker badge, content, and (when `showIntents` is true OR turn is highlighted) the per-turn intent in muted small text.
- Sidebar (or footer on narrow screens): per-dimension scores from this rollout, with each dimension's `justification` shown when expanded. Clicking a dimension scrolls highlighted turns into view.

**Failure modes.**
- Rollout `status === "failed"` → render the partial transcript prefixed with a `label-mono` "rollout failed: {reason}" banner. Do not hide the partial data — debugging value.
- Empty transcript → render scenario header only with a "no turns recorded" note.

**Sub-component `TranscriptTurn.jsx` props.**

```ts
{
  turn: {
    index: number,
    speaker: string,        // display name
    speakerRole: string,    // role_on_team OR "candidate"
    content: string,        // utterance
    intent?: string,        // optional, hidden unless toggled
    internalState?: string, // optional, hidden unless toggled
  },
  isHighlighted: boolean,
  showIntents: boolean,
}
```

### E.7 — `TeammateCard.jsx`

**Purpose.** Single synthetic teammate on the team-viewer page. Edit-in-place.

**Lives at:** `frontend/src/components/TeammateCard.jsx`. Used inside `frontend/src/pages/SyntheticTeamPage.jsx`.

**Props.**

```ts
{
  teammate: SyntheticTeammate,    // full row
  onSave: (id: string, patch: Partial<SyntheticTeammate>) => Promise<void>,
  onDelete: (id: string) => Promise<void>,
  onRegenerate: (id: string) => Promise<void>,  // regenerate a single teammate
}
```

**State.**
```ts
{
  isEditing: boolean,
  draft: Partial<SyntheticTeammate>,  // changes pending save
  saving: boolean,
  error: string | null,
}
```

**Layout intent.**
- Card layout, two columns on wide screens.
- Left: name (FONT_DISPLAY 22px, editable inline), role_on_team + seniority below (FONT_MONO label-mono).
- Right: collapsible trait sheet visualization — Big Five as 5 small `VarianceBar`s with std=0, skill_profile and work_style as text rows.
- Below: narrative as a paragraph (editable as textarea when `isEditing`).
- Below: private_goals as bulleted list (editable).
- Footer: `is_edited` indicator (small accent dot + "edited" if true), provenance_notes accessible via hover/tooltip.
- Action row: Edit / Save / Cancel / Regenerate / Delete buttons (using existing `button.primary` / `button.ghost` styles).

**Failure modes.** Save failure → preserve draft, show error inline, do not clobber server state.

### E.8 — `ScenarioCard.jsx`

**Purpose.** Single scenario on the scenario-library page. Edit-in-place modal.

**Props.**

```ts
{
  scenario: MomentOfTruth,
  criteriaIndex: Record<string, {label: string}>,  // for rendering scoring_dims
  onSave: (id: string, patch: Partial<MomentOfTruth>) => Promise<void>,
  onDelete: (id: string) => Promise<void>,
}
```

**Layout intent.**
- Card layout.
- Top: title (FONT_DISPLAY 22px) + scenario_type pill (FONT_MONO label).
- Body: prompt (1-2 line excerpt with "..." truncation), candidate_role below in muted text.
- Footer: scoring_dims as small chips using criterion labels, `is_llm_drafted` indicator if true.
- Click → modal with full prompt, candidate_role, expected_arc, participating_roles, max_turns, grounding — all editable.

**Failure modes.** Same as TeammateCard.

### E.9 — `frontend/src/api.js` extensions

Add the following exports alongside existing `candidates`, `companies`, `templates`, `matches`:

```js
// ---------- Synthetic team ----------
export const team = {
  list: (companyId) =>
    request(`/companies/${companyId}/team`, { auth: true }),
  synthesize: (companyId, { teamSize } = {}) =>
    request(`/companies/${companyId}/team/synthesize`, {
      method: "POST",
      body: { team_size: teamSize },
      auth: true,
    }),
  update: (companyId, teammateId, patch) =>
    request(`/companies/${companyId}/team/${teammateId}`, {
      method: "PATCH",
      body: patch,
      auth: true,
    }),
  remove: (companyId, teammateId) =>
    request(`/companies/${companyId}/team/${teammateId}`, {
      method: "DELETE",
      auth: true,
      raw: true,
    }),
};

// ---------- Scenarios ----------
export const scenarios = {
  list: (companyId) =>
    request(`/companies/${companyId}/scenarios`, { auth: true }),
  draft: (companyId) =>
    request(`/companies/${companyId}/scenarios/draft`, { method: "POST", auth: true }),
  create: (companyId, payload) =>
    request(`/companies/${companyId}/scenarios`, { method: "POST", body: payload, auth: true }),
  update: (companyId, scenarioId, patch) =>
    request(`/companies/${companyId}/scenarios/${scenarioId}`, {
      method: "PATCH",
      body: patch,
      auth: true,
    }),
  remove: (companyId, scenarioId) =>
    request(`/companies/${companyId}/scenarios/${scenarioId}`, {
      method: "DELETE",
      auth: true,
      raw: true,
    }),
};

// ---------- Rollouts (extend matches namespace) ----------
matches.listRollouts = (matchId) =>
  request(`/matches/${matchId}/rollouts`, { auth: true });
matches.getRollout = (matchId, rolloutId) =>
  request(`/matches/${matchId}/rollouts/${rolloutId}`, { auth: true });
matches.getBaseline = (matchId) =>
  request(`/matches/${matchId}/baseline`, { auth: true });

// ---------- Candidate persona aggregator (self-service) ----------
candidates.aggregatePersona = () =>
  request("/candidates/me/persona/aggregate", { method: "POST", auth: true });
candidates.getPersona = () =>
  request("/candidates/me/persona", { auth: true });
```

### E.10 — Routing additions

In `App.jsx` (or wherever React Router config lives), register:

```js
// Manager-only
<Route path="/manager/companies/:id/team" element={<SyntheticTeamPage />} />
<Route path="/manager/companies/:id/scenarios" element={<ScenarioLibraryPage />} />
<Route path="/manager/matches/:matchId/rollouts/:rolloutId" element={<TranscriptViewer />} />

// (Existing routes unchanged.)
```

### E.11 — UX intent reminder

The user explicitly asked for **clarity, transparency, interpretability**. When implementing the components above:

- Never show a single number where a range is honest. Variance bars over point estimates everywhere.
- Always cite. Each justification quotes its evidence (transcript turn for sim, artifact line for baseline).
- Methodology is visible, not buried in tooltips. The audit footer in FitProfileV2 should be readable at a glance.
- Loading states use the existing `pulse-dot` pattern (3 staggered dots) — no spinners, no skeleton screens, consistent with the editorial aesthetic.
- Errors render inline with the relevant component, accent-bordered, in plain prose. No toast notifications.
- Empty states use `label-mono` text in muted color explaining what's missing and what action would populate it (e.g. "no scenarios yet — draft from artifacts above").

---

## Appendix F — Test plan

The contract is: every Phase in Section 11 has an explicit validation gate (now refined in the micro-phase plan in Section 11). The tests below are what those gates measure against. Where existing tests exist, they must continue to pass — additive only.

### F.1 — Unit tests per new module

Each new file in `services/simulation/` gets a sibling test file in `backend/tests/simulation/`. Tests mock OpenRouter via a fixture that returns canned JSON matching the schema.

| Module | Test file | What to test |
|---|---|---|
| `persona_aggregator.py` | `test_persona_aggregator.py` | (1) Output validates against `AGGREGATED_PERSONA_SCHEMA` (use the `jsonschema` library, or a Pydantic mirror in `schemas.py` — implementer's call). (2) `provenance_map` covers every claim in `structured_traits`. (3) Missing CV → `evidence_completeness.cv_present === False` and confidence drops on CV-derived claims. (4) Three legacy persona.py inconsistency rules (`agreeable-dissenter`, `low-c-high-rigor`, `neurotic-but-tolerant`) still surface. (5) BFI computation matches `persona.py::synthesize_persona` numeric output to within float tolerance — same regression invariant. |
| `team_synthesizer.py` | `test_team_synthesizer.py` | (1) `synthesize(company)` returns N teammates where N = `settings.sim_default_team_size`. (2) Big Five centroid is computed and teammates' traits scatter within `sigma_recommendations.big_five` ± 2σ. (3) Each teammate's `private_goals` is non-empty. (4) `is_edited` is False on freshly generated teammates. (5) `provenance_notes` is non-empty. |
| `knowledge_graph.py` | `test_knowledge_graph.py` | (1) Every `value`, `behavior`, `anti_behavior`, `role`, `decision` node has at least one `cites` edge to an `artifact_quote` node. (2) `conflicts_with` edges have valid endpoints. (3) Node count between 8 and 30 (in code; not enforceable in schema). |
| `scenario_engine.py` | `test_scenario_engine.py` | (1) `draft_scenarios(company)` returns 5–8 scenarios. (2) Every `scoring_dims` key matches an existing `Criterion.key` for the company. (3) `scenario_type` is one of `dyad`/`small_group`/`written`. (4) `prepare_rollout(...)` selects appropriate teammates based on `participating_roles`. |
| `agent_runtime.py` | `test_agent_runtime.py` | (1) `advance_turn(world)` mutates only the next-speaker's state and the global `turn_history`. (2) Other agents' `internal_state` and `intent` are NOT included in the next agent's prompt. (3) `ends_turn=True` from any agent halts the rollout. (4) Round-robin speaker selection covers all participants once before repeating. |
| `rollout.py` | `test_rollout.py` | (1) `execute_rollout(...)` returns a Rollout with `transcript` length equal to actual turns taken. (2) On simulated agent-turn failure, returns `status="failed"` with `failure_reason` set and partial transcript preserved. (3) Wall timeout respected via `asyncio.wait_for`. (4) Seed parameter produces deterministic output when LLM is mocked. |
| `judge.py` | `test_judge.py` | (1) Output schema validates. (2) `evidence_turns` is non-empty when `score` is non-null. (3) Score is null only when `evidence_turns` is empty AND `justification` explains why. (4) Multi-judge variant (2 calls) returns 2 scores per dimension; mean and inter-judge std computed correctly. |
| `aggregator.py` | `test_aggregator.py` | (1) `aggregate_fit_profile(rollouts, scores, criteria)` produces a `FitProfile` matching `FIT_PROFILE_SHAPE` (Appendix B.8). (2) `dimensionalFit[key].mean` == weighted mean of judge scores for that dim across rollouts. (3) `dimensionalFit[key].std` reflects judge-cross-rollout variance, not within-judge variance. (4) `overallScore` matches the legacy weighted-overall formula. (5) When `n=1` for a dim, `std=0` and `judgeAgreement=null` (both must be tolerated downstream). |
| `simulation_matcher.py` | `test_simulation_matcher.py` | (1) End-to-end happy-path: persona + company + team + scenarios → FitProfile with all required keys. (2) Baseline matcher runs in parallel and `BaselineComparison` row is persisted. (3) Cost ceiling exceeded → match aborts with partial report and `auditTrailV2.aborted="cost_ceiling"`. (4) All rollouts failing → match returns 502 with explanatory detail. (5) `RolloutLog` rows exist for `match_started`, `persona_aggregated`, `rollout_started`, `agent_turn`, `judge_scored`, `baseline_run`, `fit_aggregated`, `match_finished`. |
| `proof_layer.py` | `test_proof_layer.py` | (1) `NullProofLayer` passes through inputs unchanged. (2) Interface methods `attest_persona`, `attest_score`, `build_proof_chain` exist and have stable signatures. |
| `cost_tracker.py` | `test_cost_tracker.py` | (1) `tracked_chat_json` raises `CostCeilingExceeded` when budget exhausted. (2) Cost estimation matches `_MODEL_PRICES` table for known models. (3) Unknown model defaults to Sonnet pricing without crashing. |

### F.2 — Integration test

`backend/tests/simulation/test_integration_match_flow.py`:

```python
"""Full match-flow integration test. LLM calls are mocked at the
openrouter.chat_json layer with canned responses derived from real fixtures.
"""

@pytest.mark.asyncio
async def test_full_match_flow_meridian(db, mock_openrouter):
    # 1. Seed: Meridian + a candidate (BFI + SJT pre-filled, CV text fixture)
    seed_companies(db)
    candidate = make_test_candidate(db, profile="thorough_dissenter")

    # 2. Synthesize team for Meridian (mocked OpenRouter)
    teammates = await team_synthesizer.synthesize(db.get(Company, "meridian-capital"))
    db.add_all(teammates); db.commit()

    # 3. Draft scenarios for Meridian
    scenarios = await scenario_engine.draft_scenarios(db.get(Company, "meridian-capital"))
    db.add_all(scenarios); db.commit()

    # 4. Aggregate persona
    persona = await persona_aggregator.aggregate(candidate)

    # 5. Run match
    report = await simulation_matcher.run_match(
        candidate=candidate,
        company=db.get(Company, "meridian-capital"),
    )

    # 6. Assert
    assert report["version"] == "v2"
    assert "dimensionalFit" in report
    assert len(report["rolloutSummaries"]) > 0
    assert report["baselineComparison"] is not None
    assert report["auditTrailV2"]["proofLayer"] == "null"

    # 7. Logs persisted
    log_events = {row.event_type for row in db.query(RolloutLog).filter_by(match_id=...)}
    assert "match_started" in log_events
    assert "fit_aggregated" in log_events
    assert "match_finished" in log_events
```

The `mock_openrouter` fixture lives in `backend/tests/conftest.py` and routes calls by `schema_name` to a fixture file under `backend/tests/fixtures/` (e.g. `aggregated_persona__thorough_dissenter.json`).

### F.3 — Prompt snapshot tests

For each prompt in Appendix A, create a snapshot test:

```python
# backend/tests/simulation/test_prompt_snapshots.py
def test_persona_aggregator_user_prompt_snapshot(snapshot):
    user_prompt = persona_aggregator._render_user_prompt(
        candidate=fixture_candidate("thorough_dissenter"),
    )
    snapshot.assert_match(user_prompt, "persona_aggregator__thorough_dissenter.txt")
```

Snapshots live under `backend/tests/snapshots/`. Use `pytest-snapshot` or roll a tiny helper. The intent: any change to a prompt template surfaces as a snapshot diff during code review, so prompt evolution is deliberate.

### F.4 — Frontend smoke tests

In v0 keep these light. One Playwright (or Vitest + React Testing Library) test per new page:

| Test | Asserts |
|---|---|
| FitProfileV2 renders v2 report | All sections present, baseline strip visible when data, hidden when not |
| FitProfileV2 falls back to FitReport on legacy report | Legacy report shape (no `version` key) renders the legacy component |
| TranscriptViewer renders rollout | Turns visible, dimension chips toggle highlights |
| SyntheticTeamPage renders teammate cards | N cards, each editable |
| ScenarioLibraryPage renders scenarios | Edit modal opens and saves |

These do not need live LLM calls — mock the API client.

### F.5 — Existing test compatibility

These existing tests must continue to pass without modification:

- `backend/tests/test_persona.py` — pins the legacy `persona.py` Python port to the JSX reference values. The persona aggregator is additive; legacy persona.py stays in the repo and is still callable.
- Any existing matcher or company-route tests.

If any of them break during the build, that's a regression — surface it before continuing the phase.

### F.6 — What is intentionally NOT tested in v0

- Model-output quality is not unit-tested. We have no automated way to assert "the persona aggregator produces a good narrative" — that's the retrospective study's job (Phase 6 in the refined sequence).
- Bias auditing is stubbed but not enforced in CI in v0. Real bias audits are a v1 follow-up (the Phase 6 endpoint stubs the response shape).
- Production rate-limit behavior is not tested. Cost ceiling and concurrency are unit-tested with mocks; real-world OpenRouter behavior is observed during demo prep.

---

*End of brief. The 14 phases in Section 11 are the execution plan; the appendices are the implementation reference. If a build-time question is not resolved by either, that is a brief gap — flag it back for revision rather than guessing.*
