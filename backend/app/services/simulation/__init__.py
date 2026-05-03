"""Simulation pipeline — multi-agent hiring simulation.

MiroFish lineage
----------------
This package reimplements the relevant MiroFish primitives inside the repo
rather than taking a library dependency. The mapping is:

  MiroFish primitive           → This repo module
  ──────────────────────────────────────────────────────────────────────────
  PersonaAggregator            → simulation/persona_aggregator.py
  TeamSynthesizer / Population → simulation/team_synthesizer.py
  CompanyKnowledgeGraph        → simulation/knowledge_graph.py
  AgentRuntime / TurnEngine    → simulation/agent_runtime.py
  ScenarioLibrary / Drafter    → simulation/scenario_engine.py
  RolloutExecutor              → simulation/rollout.py
  ScoreJudge                   → simulation/judge.py
  FitAggregator                → simulation/aggregator.py
  ProofLayer (interface)       → simulation/proof_layer.py
  MatchOrchestrator            → simulation/simulation_matcher.py

When MiroFish ships a stable workplace-simulation submodule, this package is
the target for extraction. Until then, keep the primitives here and document
any divergence from MiroFish semantics in individual module docstrings.
"""

# Prompt-scaffolding version — tag every Rollout + RolloutScore write so
# analytics can group by the prompt configuration that produced them. Bump
# whenever the agent system prompt, behavioral contract, gap-briefing
# template, or fidelity rubric changes materially. Used by rollout.py and
# downstream queries (admin/sim-health). See ROADMAP_2.md for context.
PROMPT_VERSION = "pr1.0"

