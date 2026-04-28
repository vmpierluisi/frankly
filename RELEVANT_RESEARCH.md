# Relevant Research & Future Directions

**Purpose.** A living index of academic and industrial work that informs — or could inform — future versions of this platform. Nothing here is in the v0 build (see `SIMULATION_BRIEF.md` for what's actually being built). This document is for: (a) intellectual provenance, so the team knows where ideas came from; (b) a roadmap of upgrade paths the v0 architecture is designed to accommodate; (c) a reading list for new contributors.

**How to read this.** Each entry has the same shape: *what it is*, *why it matters to us*, and *where in our roadmap it could land*. Sections are organized by where the research slots into our pipeline (candidate persona, synthetic team, simulation, scoring, validation, long-term).

**Maintenance.** Add new entries as the literature evolves. Mark entries as "incorporated into v_" when their ideas land in the codebase, but keep the entry — the citation matters even after the idea is shipped.

---

## 0. v0 implementation status — what's in `SIMULATION_BRIEF.md` vs deferred

Snapshot of which research from this index is being incorporated *now* (in the v0 simulation pipeline build) versus pushed to later versions. Read this first if you want to know what's actually shipping.

| Source | v0 status | What it contributes to v0 (or doesn't) |
|---|---|---|
| **Park et al. — Generative Agent Simulations of 1,000 People** | Architectural influence only | Validates the *choice* of hybrid narrative-plus-traits persona representation. The 2-hour-interview ingestion methodology and multi-expert-lens technique are deferred to v1. |
| **MiroFish (in-house)** | Primitives reimplemented | `services/simulation/team_synthesizer.py`, `agent_runtime.py`, `knowledge_graph.py` reimplement the relevant MiroFish primitives inline. The library itself is not imported. |
| **Sotopia** | Pattern lifted, library not used | The structured-scenario-with-private-goals pattern is in `scenario_engine.py` and `agent_runtime.py`. The multi-objective rubric (relationship maintenance, info disclosure, etc.) is *not* yet in our judge — v1 candidate. |
| **Validation challenges in generative social simulation (Springer, 2025)** | Methodological framing | The retrospective study + baseline comparison + bias audit infrastructure exists *because* of this paper's critique. Not "implemented" in code, but shapes our entire validation philosophy. |
| **Schmidt & Hunter meta-analyses** | Bar-clearing reference | Frames the retrospective study: "does our simulation predict 12-month performance better than the design partner's existing screening process?" Not in code; in the methodology. |
| **PersonaFuse** | Deferred to v1 | Our agent runtime uses simple "trait sheet in system prompt" — adequate for v0 but not as rigorous as PersonaFuse-style activation. Quality-gate candidate for v1. |
| **PersonaGym** | Deferred to v1 | We have no teammate-drift detection in v0. PersonaGym-style consistency scoring is the v1 quality gate. |
| **Population-Aligned Persona Generation** | Deferred to v1.5 | v0 team synthesizer uses centroid + Gaussian sampling, not optimal-transport calibration to reference cohorts. |
| **PersonaX (multimodal trait inference)** | Deferred | Our v0 source-reliability priors are hand-coded in the aggregator prompt, not empirically derived. |
| **LLM Agents Grounded in Self-Reports** | Background influence | Validates our use of BFI/SJT as grounding. No specific v0 implementation. |
| **Generative Agents (Smallville)** | Partial influence | Our `agent_runtime.py` is a stripped-down version. No memory-stream or reflection passes in v0 — those are v2 candidates. |
| **SOTOPIA-π** | Deferred to v2.5+ | Per-design-partner fine-tuning of teammate models. Requires substantial rollout data we don't have yet. |
| **DreamerV3 / Genie / Sora-style world models** | Deferred to v3+ | Requires ~10K+ (rollout, outcome) tuples we won't have until 12+ months of design-partner deployment. |
| **Persona-induced bias literature** | Awareness only | Informs what biases we should test for. Bias audit code is v0 (stub) → v1 (real). |
| **IPIP norms** | Deferred to v1.5 | Will be the reference distribution for Population-Aligned-style calibration. |

**Reading the table.** Three tiers, roughly: (a) *Pattern lifted / primitives implemented* — the idea is in the code in some form. (b) *Architectural / methodological influence* — the idea shaped our design but isn't directly coded. (c) *Deferred* — explicit v1+/v2+/v3+ candidates with a place reserved in the architecture (seam, table, or stub).

If a reader of this document only has 60 seconds, the takeaway is: v0 is intentionally a thin slice — Sotopia-pattern simulation, MiroFish-primitive teammates, hand-coded source-reliability priors, baseline matcher kept alive for validation. Almost everything in the rest of this index is a future-version candidate.

---

## 1. Candidate persona aggregation

This is the part of the pipeline where we synthesize a rich behavioral profile from heterogeneous evidence (BFI-10, SJTs, CV, LinkedIn, GitHub). v0 does this with a single careful LLM prompt. The literature below points to where that prompt evolves.

### Generative Agent Simulations of 1,000 People (Park et al., Stanford + DeepMind, 2024)

**arXiv:** [2411.10109](https://arxiv.org/abs/2411.10109) · **Code:** [StanfordHCI/genagents](https://github.com/StanfordHCI/genagents)

A team led by Joon Sung Park built generative agents that reproduce real human survey responses at 85% of human test-retest reliability — meaning the agents are nearly as consistent with the source human as the human is with themselves two weeks later. The mechanism: a 2-hour qualitative interview transcript loaded into agent memory, plus an LLM that reviews the transcript from multiple expert lenses (social psychologist, economist, sociologist) to extract structured commentary that becomes the persona's "scaffolding."

**Why it matters.** This is the most rigorously validated result for "rich text persona → behavioral fidelity" in the literature, and it's the empirical backbone for our entire architectural choice to use a hybrid narrative-plus-traits persona representation rather than a pure trait-vector model.

**Where it could land for us.**
- *v1 candidate intake:* a "structured interview" intake mode (LLM conducts the interview; candidate types responses; transcript becomes part of the persona). This is a much richer evidence source than BFI-10 + SJTs and would plug directly into the existing aggregator.
- *v1 persona aggregator:* the multi-expert-lens technique (have the aggregator emit commentary from multiple expert perspectives, not just one synthesized narrative). Already partially aligned with our `provenance_map` structure.
- *Validation reference:* their 85%-of-test-retest benchmark is a number we can aim at. If our retrospective study can show our personas predict behavior at 60%+ of test-retest reliability, we have a legitimate result.

### LLM Agents Grounded in Self-Reports Enable General-Purpose Simulation of Individuals (Park et al., 2024)

**arXiv:** [2411.10109](https://arxiv.org/abs/2411.10109) (same paper as above; the title used in earlier drafts).

**Why it matters separately.** The "grounded in self-reports" framing is directly applicable to us: BFI-10 and SJT responses *are* self-reports. The paper shows self-reports can serve as reliable grounding even without the 2-hour interview, provided they're augmented with behavioral evidence.

**Where it could land.** Our v0 aggregator already uses self-reports + behavioral residue (CV/GitHub). Track this paper for follow-ups on optimal weighting between self-report and observed behavior — we hard-coded reliability priors in v0; the literature could give us better defaults.

### PersonaX: Multimodal Datasets with LLM-Inferred Behavior Traits (2025)

**arXiv:** [2509.11362](https://arxiv.org/html/2509.11362)

Multi-modal persona datasets (text descriptions + photos + organizational affiliations) with LLM-inferred behavioral traits. The paper finds systematic differences in how information transfers across persona types — celebrity representations are shaped more by appearance, athlete representations more by organizational affiliation.

**Why it matters.** We're combining heterogeneous evidence sources (CV, LinkedIn, GitHub) and the per-source reliability problem is real. PersonaX is one of the few papers to study this directly.

**Where it could land for us.** When we move beyond hand-coded reliability priors in the aggregator, PersonaX-style empirical reliability mapping is a candidate methodology.

### Population-Aligned Persona Generation for LLM-Based Social Simulation (2025)

**arXiv:** [2509.10127](https://arxiv.org/html/2509.10127v2)

Synthetic persona populations are systematically off-distribution relative to real psychometric cohorts (e.g. over-representing high-conscientiousness profiles because behavioral residue biases that way). The paper uses optimal transport to align generated populations to reference distributions and reports up to 50% reduction in distributional error.

**Why it matters.** This is directly relevant to *both* sides of our pipeline — candidate persona aggregation could drift over time, and synthetic teammate generation needs explicit calibration against a reference team distribution.

**Where it could land.**
- *v1.5 calibration audit:* periodically score the distribution of personas we've aggregated against IPIP population norms; flag drift.
- *v2 team synthesizer:* once we have enough sanctioned company data, use optimal-transport calibration to ensure synthetic teammates match the actual diversity of healthy teams (not just centroid + Gaussian noise as in v0).

### PersonaLLM Workshop, NeurIPS 2025

**Site:** [personallmworkshop.github.io](https://personallmworkshop.github.io/)

A growing research community focused on LLM persona modeling. Workshop papers cover persona consistency, persona-induced bias, persona evaluation methodology, and applications to marketing, social science, and HCI.

**Why it matters.** This is the field we're building in. Tracking the workshop is the cheapest way to stay current.

**Where it could land.** Action item: assign someone (Daria?) to skim each year's accepted papers and flag candidates for inclusion in this document.

---

## 2. Synthetic teammate / company-side population generation

The v0 team synthesizer is centroid-plus-Gaussian sampling around an LLM-extracted "team centroid." That works for a 5-person team. The literature below matters when we want richer team dynamics.

### MiroFish (in-house)

The repurposed open-source swarm intelligence engine — originally for opinion dynamics, now mined for primitives we reimplement inside `services/simulation/`. The relevant primitives are: synthetic-agent generation from source documents, agent-state container with memory, message-passing loop, knowledge graph from source data.

**Why it matters.** It's ours. The v0 build reimplements its primitives; v2+ may extract them back into MiroFish as a workplace-simulation submodule.

**Where it could land.** Once `services/simulation/` stabilizes, identify the genuinely generic modules (probably `agent_runtime.py` and `knowledge_graph.py`) and contribute them upstream as a MiroFish module.

### PersonaFuse: Personality Activation-Driven Framework (2025)

**arXiv:** [2509.07370](https://arxiv.org/html/2509.07370v2)

A framework for activating specific Big Five trait profiles in LLMs at runtime, with reliability across contexts. The paper shows trait profiles are relatively insensitive to scenario changes — a stability property we depend on.

**Why it matters.** Our synthetic teammates need to *act in character* across many scenarios. PersonaFuse-style activation gives us empirically-validated techniques for that.

**Where it could land.**
- *v1 agent runtime:* current implementation is "trait sheet in system prompt and hope." PersonaFuse-style activation prompting is a more rigorous approach.
- *Quality gate:* run a teammate persona through PersonaFuse-style consistency checks across rollouts; flag if a teammate's behavior drifts.

### Generative Agents: Interactive Simulacra of Human Behavior (Park et al., Stanford, 2023)

**arXiv:** [2304.03442](https://arxiv.org/abs/2304.03442) · **Code:** [joonspk-research/generative_agents](https://github.com/joonspk-research/generative_agents)

The original "Smallville" paper. Agents with memory, reflection, and planning loops produce emergent social behavior over time. Less directly relevant than the 2024 follow-up, but the *architecture* (memory stream → reflection → plan → act) is influential and worth understanding before designing the agent runtime.

**Why it matters.** Our `agent_runtime.py` is a stripped-down version of this. If we want richer emergent dynamics in v2+ (teammates remembering interactions across rollouts, reflecting on the candidate, updating beliefs), we'd add the memory + reflection layers from this paper.

**Where it could land.** v2 agent runtime: add reflection passes between rollouts so teammates accumulate "impressions" of the candidate over a simulated week.

---

## 3. Simulation environment & multi-agent interaction

This is where Sotopia fits. We're not importing Sotopia as a library, but the *pattern* is what we're using.

### SOTOPIA: Interactive Evaluation for Social Intelligence in Language Agents (Zhou et al., CMU, 2023)

**arXiv:** [2310.11667](https://arxiv.org/abs/2310.11667) · **Site:** [sotopia.world](https://sotopia.world/projects/sotopia)

A benchmark of 90 social scenarios (negotiation, collaboration, competition) where LLM agents are given private goals and interact in multi-turn dialogue. Performance is scored on a multi-objective rubric: relationship maintenance, goal achievement, financial outcomes, info disclosure, keeping secrets, social rule adherence.

**Why it matters.** This is the architecture we're using for the simulation step, lifted as pattern. The richness of their multi-objective rubric is more sophisticated than our v0 "score per criterion" approach.

**Where it could land.**
- *v0 (already):* the structured-scenario-with-private-goals pattern is in our `scenario_engine.py` and `agent_runtime.py`.
- *v1 judge:* lift Sotopia's multi-objective rubric structure. Currently each criterion gets one score; Sotopia would have us score each rollout on (goal achievement, relationship maintenance, info disclosure, social rules) as a separate axis, with criterion mapping derived from those primitives.
- *v2 scenario library:* their published scenarios are a starting point for our scenario library, particularly for cross-functional roles.

### SOTOPIA-π: Interactive Learning of Socially Intelligent Agents (Wang et al., 2024)

**ACL 2024:** [aclanthology.org/2024.acl-long.698](https://aclanthology.org/2024.acl-long.698.pdf)

A follow-up that fine-tunes LLM agents via interactive social learning, improving their social intelligence on Sotopia benchmarks while maintaining other capabilities.

**Why it matters.** This is the path for fine-tuning *synthetic teammate behavior* in v2+ once we have enough rollout data. The methodology generalizes: fine-tune teammate agents to better embody their company's specific norms, validated against rollouts.

**Where it could land.** v2.5: fine-tune a small model per design partner to act as that company's synthetic teammates more authentically than a generic model with a system prompt can.

### SOTOPIA-S4 (CMU, 2025)

**PDF:** [cs.cmu.edu/~sherryw/assets/pubs/2025-sotopia-s4.pdf](https://www.cs.cmu.edu/~sherryw/assets/pubs/2025-sotopia-s4.pdf)

A user-friendly system for flexible, customizable, parallel social simulation with user-defined metrics and APIs. Worth scanning when our `agent_runtime.py` matures — they've solved engineering problems we'll hit.

---

## 4. Scoring, judging & evaluation

### PersonaGym (Suresh et al., 2024)

**Site:** [personagym.com](https://personagym.com/)

Evaluation framework for measuring whether persona agents are actually behaving in-character. Defines metrics for persona consistency, faithfulness to source descriptors, and resistance to drift.

**Why it matters.** Our judge layer scores candidate fit. PersonaGym would give us a separate evaluation for *teammate quality* — are our synthetic teammates actually staying in character across rollouts? Without this we have no way to detect when teammate drift is corrupting our scoring.

**Where it could land.** v1 quality gate in `services/simulation/`: after each match, run PersonaGym-style consistency checks on teammate behavior across the K rollouts; surface drift in `/admin/logs/`.

### Evaluating LLMs for Synthetic Personas Generation (Italian SIGCHI Chapter, 2025)

**ACM:** [dl.acm.org/doi/10.1145/3750069.3750142](https://dl.acm.org/doi/10.1145/3750069.3750142)

Comparative analysis of LLM-generated personas across personality representation and censorship effects. Relevant to choosing which model to use for persona aggregation and teammate generation.

**Where it could land.** Inform model selection for `persona_aggregator.py` and `team_synthesizer.py`. Currently both run on the default OpenRouter model (Claude Sonnet 4.6); we may want different models for different components.

---

## 5. Validation, calibration & critical literature

### Validation is the Central Challenge for Generative Social Simulation (Springer, April 2025)

**Springer:** [link.springer.com/article/10.1007/s10462-025-11412-6](https://link.springer.com/article/10.1007/s10462-025-11412-6)

A critical review of LLMs in agent-based modeling. The paper's central argument: most generative social simulation work produces sophisticated-looking outputs that haven't been validated against ground truth, and the field's biggest risk is over-claiming.

**Why it matters.** This is the keep-us-honest paper. Our entire validation infrastructure (retrospective study + baseline comparison + bias audits) exists because of the concerns this review raises.

**Where it could land.** Read it before each design partner conversation. Use it as the methodological framing for our published validation studies.

### Schmidt & Hunter meta-analyses (foundational)

**Reference:** Schmidt, F. L., & Hunter, J. E. (1998). The validity and utility of selection methods in personnel psychology. *Psychological Bulletin*, 124(2), 262.

Decades of evidence on which hiring methods actually predict job performance. Structured interviews + work samples + cognitive ability are the meaningfully predictive methods; unstructured interviews and personality tests alone have low predictive validity.

**Why it matters.** This is the bar our retrospective study has to clear. If our simulation can't outperform a structured interview's predictive validity, we don't have a product. The good news: structured interviews + work samples are operationally expensive, and our pitch is "comparable validity at much lower operational cost."

**Where it could land.** Methodology framing for the design-partner pitch. Cite explicitly in our retrospective study writeup.

### IPIP Big Five population norms

**Site:** [ipip.ori.org](https://ipip.ori.org/)

The International Personality Item Pool — open-source Big Five item bank with documented population distributions across age, gender, and culture.

**Why it matters.** Population-Aligned Persona Generation (above) needs a reference distribution; IPIP is the obvious one.

**Where it could land.** v1.5 calibration audit will compare our aggregated persona distributions against IPIP norms.

---

## 6. Long-term: learned world models

This section is for v3+ — the learned-model successor to LLM-as-implicit-world-model.

### DreamerV3 (Hafner et al., DeepMind, 2023)

**arXiv:** [2301.04104](https://arxiv.org/abs/2301.04104)

A general-purpose world model that learns to predict environment dynamics from rollout data, then trains a policy in imagination. Used for control tasks but the architecture generalizes.

**Why it matters.** This is the long-term moat. Once we have enough (persona, scenario, rollout, outcome) tuples, we can train a learned model that predicts simulation outcomes without LLM rollouts, dramatically faster and cheaper. *We don't have the data yet* — this is a v3+ direction.

**Where it could land.** When `RolloutLog` accumulates ~10K+ (rollout → 12-month outcome) tuples from real design-partner deployments, evaluate whether a learned model can match LLM-rollout fidelity at 100× the throughput.

### Genie (DeepMind, 2024) and Sora (OpenAI, 2024)

Generative world models trained on video. Different domain from ours but the *paradigm* — learning to simulate environment dynamics from observation — is the same north star.

**Why it matters.** Mostly inspirational. Our equivalent would be a model that learns "team dynamics dynamics" from observed rollouts.

---

## 7. Adjacent / keep an eye on

### From Single to Societal: Persona-Induced Bias in Multi-Agent Interactions (2025)

**arXiv:** [2511.11789](https://arxiv.org/html/2511.11789v1)

Studies how persona prompting in multi-agent systems can amplify bias. Directly relevant to our bias audit infrastructure — we should know what biases the literature has documented in similar setups so we can audit for them specifically.

### Big Five Personality Profiles in LLMs

**EmergentMind summary:** [emergentmind.com/topics/big-five-personality-profiles-in-llms](https://www.emergentmind.com/topics/big-five-personality-profiles-in-llms)

Active line of research on whether LLMs themselves exhibit consistent Big Five trait profiles. Relevant for understanding what biases the underlying model brings to persona simulation.

### Anthropic alignment work on Persona Selection Models

**Anthropic alignment blog:** [alignment.anthropic.com/2026/psm/](https://alignment.anthropic.com/2026/psm/)

Frames LLMs as actors capable of simulating many characters; the "Assistant" persona is one such character elicited by post-training. Relevant context for understanding what's happening *inside* the model when we ask it to play a synthetic teammate or aggregate a candidate persona.

### Awesome Social Agents (curated list)

**GitHub:** [sotopia-lab/awesome-social-agents](https://github.com/sotopia-lab/awesome-social-agents)

Maintained collection of social-agent research across text, embodied, and robotics contexts. Use this as a periodic check for new work.

---

## 8. Gaps in our current research base

Things we *should* be reading and aren't yet:

- **Person-Environment Fit theory (Kristof-Brown and others)** — the actual psychological literature on what we're trying to predict. We've leaned heavily on the AI side and haven't done the I/O psychology homework. Worth a focused reading sprint.
- **Adverse Impact and the Uniform Guidelines on Employee Selection Procedures (US EEOC)** — the legal framework our bias audits must satisfy in the US market. Currently we have a hand-wave plan; we need a concrete compliance methodology.
- **Empirical evaluations of incumbent tools (Pymetrics, HireVue, Plum)** — academic critiques of what's already in market. Knowing what they've been credibly criticized for sharpens our positioning.
- **Construct validity of SJTs** — our SJTs are competent but unvalidated. There's literature on what makes SJTs psychometrically sound; we should know it before scaling SJT design.
- **Recent EU AI Act guidance on hiring systems** — specific regulatory text and any case law since the Act took effect.

Action item: each of these gaps becomes a reading task the next time we have a research-focused week.

---

## 9. How research becomes product

A standing rule: ideas from this document don't enter the codebase opportunistically. They enter via:

1. *A specific user-facing problem* — "the persona aggregator over-weights GitHub commit cadence." Then: search this document for the relevant calibration paper.
2. *A specific competitive gap* — "design partners ask whether our personas are bias-tested against population norms." Then: PersonaX + Population-Aligned Persona Generation become candidate solutions.
3. *A planned phase boundary* — at the start of each major version (v1, v2, v3), do a focused re-read of this document to identify candidates for integration.

Random ad-hoc adoption of a paper's methodology is how research-driven products become unmaintainable.

---

*End of research index. Last updated by Victor & Daria, April 2026.*
