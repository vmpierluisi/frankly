"""Simulation pipeline — multi-agent hiring simulation.

MiroFish lineage
----------------
This package reimplements the relevant MiroFish primitives inside the repo
rather than taking a library dependency. The mapping is:

  MiroFish concept                  → This module
  ──────────────────────────────    ─────────────────────────────────────────
  generate_population_from_docs()   → team_synthesizer.synthesize()
  PersonaDocument / trait_sheet     → types.TraitSheet, SyntheticTeammate.trait_sheet
  ScenarioLibrary / draft_moments   → scenario_engine.draft_scenarios()
  RolloutExecutor / run_rollout     → rollout.execute_rollout()
  ScoringJudge / score_transcript   → judge.score_rollout()
  ProofLayer / attest()             → proof_layer.NullProofLayer (v0 stub)

When MiroFish ships a stable workplace-simulation submodule, this package is
the target for extraction. Until then, keep the primitives here and document
any divergence from MiroFish semantics in individual module docstrings.
"""
