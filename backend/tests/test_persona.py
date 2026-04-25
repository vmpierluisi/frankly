"""Persona synthesis regression tests.

These pin the Python port against hand-computed values derived from the JSX
reference (`hiring-sim-demo.jsx`, `synthesizePersona`). If these ever drift,
the Python logic has diverged from the JSX — investigate before proceeding.
"""
from __future__ import annotations

import math

import pytest

from app.services.persona import synthesize_persona


def _approx(a: float, b: float, tol: float = 1e-9) -> bool:
    return math.isclose(a, b, rel_tol=tol, abs_tol=tol)


# ---------------------------------------------------------------------------
# Fixture: a "Meridian-aligned" candidate — picks the highest-rigor / highest-
# honesty / highest-dissent option on every SJT, self-reports as thorough
# (high C), reserved (low E), somewhat disagreeable (low A), calm (low N),
# open (high O). Expected persona scores computed from the same formulas.
# ---------------------------------------------------------------------------
ALIGNED_BFI = {
    # Reversed items phrased negatively; answering 1 maps to high trait.
    "e1": 5, "a1": 4, "c1": 1, "n1": 5, "o1": 1,
    # Non-reversed items.
    "e2": 2, "a2": 4, "c2": 5, "n2": 2, "o2": 5,
}
# After reverse-scoring:
#   e1 reverse: 6-5=1;  e2 direct: 2  → E avg = (1+2)/2 = 1.5
#   a1 direct: 4;       a2 reverse: 6-4=2 → A avg = (4+2)/2 = 3.0
#   c1 reverse: 6-1=5;  c2 direct: 5  → C avg = (5+5)/2 = 5.0
#   n1 reverse: 6-5=1;  n2 direct: 2  → N avg = (1+2)/2 = 1.5
#   o1 reverse: 6-1=5;  o2 direct: 5  → O avg = (5+5)/2 = 5.0

ALIGNED_SJT = {"sjt1": "a", "sjt2": "a", "sjt3": "d"}
# Sum signals over three SJT picks, then divide by 3:
#   sjt1-a: {intellectualHonesty:5, writtenDissent:5, analyticalRigor:4}
#   sjt2-a: {writtenDissent:5, analyticalRigor:5, lowEgoCollab:3}
#   sjt3-d: {intellectualHonesty:4, ambiguityTolerance:5, analyticalRigor:5, lowEgoCollab:4}
# Totals:
#   analyticalRigor:     4+5+5 = 14 / 3 ≈ 4.6667
#   intellectualHonesty: 5+0+4 = 9  / 3  = 3.0
#   writtenDissent:      5+5+0 = 10 / 3 ≈ 3.3333
#   ambiguityTolerance:  0+0+5 = 5  / 3 ≈ 1.6667
#   lowEgoCollab:        0+3+4 = 7  / 3 ≈ 2.3333


def test_aligned_candidate_big_five():
    p = synthesize_persona(ALIGNED_BFI, ALIGNED_SJT)
    bf = p["bigFive"]
    assert _approx(bf["extraversion"], 1.5)
    assert _approx(bf["agreeableness"], 3.0)
    assert _approx(bf["conscientiousness"], 5.0)
    assert _approx(bf["neuroticism"], 1.5)
    assert _approx(bf["openness"], 5.0)


def test_aligned_candidate_sjt_signals():
    p = synthesize_persona(ALIGNED_BFI, ALIGNED_SJT)
    s = p["sjtSignals"]
    assert _approx(s["analyticalRigor"], 14 / 3)
    assert _approx(s["intellectualHonesty"], 3.0)
    assert _approx(s["writtenDissent"], 10 / 3)
    assert _approx(s["ambiguityTolerance"], 5 / 3)
    assert _approx(s["lowEgoCollab"], 7 / 3)


def test_aligned_candidate_narrative_includes_expected_bits():
    p = synthesize_persona(ALIGNED_BFI, ALIGNED_SJT)
    narrative = p["narrative"]
    # C=5 ≥ 4 → detail-oriented
    assert "detail-oriented and thorough" in narrative
    # O=5 ≥ 4 → intellectually curious
    assert "intellectually curious" in narrative
    # E=1.5 ≤ 2.5 → works deeply in solitude
    assert "works deeply in solitude" in narrative
    # A=3.0, skips "comfortable with conflict" (threshold ≤ 2.5)
    assert "comfortable with conflict" not in narrative


def test_aligned_candidate_no_inconsistency_flags_when_a_mid():
    # A = 3.0, so agreeable-dissenter threshold (A ≥ 4) isn't tripped.
    p = synthesize_persona(ALIGNED_BFI, ALIGNED_SJT)
    flag_types = {f["type"] for f in p["inconsistencies"]}
    assert "agreeable-dissenter" not in flag_types


def test_agreeable_dissenter_flag_fires():
    """High A (≥4) + high writtenDissent (≥4) → agreeable-dissenter flag."""
    bfi = dict(ALIGNED_BFI)
    # Push A up: a1 direct 5, a2 reversed from 5 → 1 gives avg 3; we need ≥ 4.
    # Set a1=5, a2=1  →  direct 5, reverse(1)=5 → A=5.
    bfi["a1"] = 5
    bfi["a2"] = 1
    # Keep writtenDissent high — ALIGNED_SJT already gives ≈ 3.33; bump with
    # sjt1 "a" (WD=5) and sjt2 "a" (WD=5) and sjt3 "b" (WD=3) → 13/3 ≈ 4.33.
    sjt = {"sjt1": "a", "sjt2": "a", "sjt3": "b"}
    p = synthesize_persona(bfi, sjt)
    assert p["bigFive"]["agreeableness"] >= 4
    assert p["sjtSignals"]["writtenDissent"] >= 4
    flag_types = {f["type"] for f in p["inconsistencies"]}
    assert "agreeable-dissenter" in flag_types


def test_empty_inputs_return_zeros_and_incomplete_narrative():
    p = synthesize_persona({}, {})
    # Missing BFI responses default to 3; reverse-scored items become 3 too.
    # So every trait averages 3.0 — no threshold tripped.
    for v in p["bigFive"].values():
        assert _approx(v, 3.0)
    # Missing SJTs → zero count → all signals 0.
    for v in p["sjtSignals"].values():
        assert v == 0.0
    assert p["inconsistencies"] == []
    # Narrative: no thresholds tripped → "Profile synthesis incomplete."
    assert p["narrative"] == "Profile synthesis incomplete."
