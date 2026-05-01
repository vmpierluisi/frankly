"""Proof layer interface — ReasoningLayer integration seam.

MiroFish lineage: this module is the integration point where MiroFish's
ProofLayer would plug in. v0 ships NullProofLayer (passthrough); the real
ReasoningLayer adapter drops in here with a one-config-flag swap.

Wire points in simulation_matcher.run_match:
  1. After persona aggregation: attest_persona(persona)
  2. After each judge call:     attest_score(score, evidence)
  3. After fit aggregation:     build_proof_chain(fit_profile, rollouts)
"""
from __future__ import annotations
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ProofLayer(Protocol):
    async def attest_persona(self, persona: dict[str, Any]) -> dict[str, Any]: ...
    async def attest_score(self, score: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]: ...
    async def build_proof_chain(self, fit_profile: dict[str, Any], rollouts: list[Any]) -> dict[str, Any]: ...


class NullProofLayer:
    """v0 passthrough. Replace with ReasoningLayerProofLayer when the time comes."""
    async def attest_persona(self, persona: dict[str, Any]) -> dict[str, Any]:
        return persona

    async def attest_score(self, score: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
        return score

    async def build_proof_chain(self, fit_profile: dict[str, Any], rollouts: list[Any]) -> dict[str, Any]:
        return {"status": "deferred"}


_proof_layer: NullProofLayer = NullProofLayer()


def get_proof_layer() -> NullProofLayer:
    return _proof_layer
