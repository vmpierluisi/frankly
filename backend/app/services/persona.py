"""Persona synthesis — Python port of hiring-sim-demo.jsx `synthesizePersona`.

Contract: given raw BFI-10 responses (1–5 per item) and SJT responses (option
id per scenario), return a persona dict with the same keys the JSX returned:

    {
      "bigFive": {"openness": float, "conscientiousness": float,
                   "extraversion": float, "agreeableness": float,
                   "neuroticism": float},
      "sjtSignals": {"analyticalRigor": float, "intellectualHonesty": float,
                      "writtenDissent": float, "ambiguityTolerance": float,
                      "lowEgoCollab": float},
      "inconsistencies": [{"type": str, "note": str}, ...],
      "narrative": str,
    }

This MUST produce byte-identical output (to within float tolerance) as the
JSX reference on the same inputs. test_persona.py enforces this.
"""
from __future__ import annotations

from typing import Any

from ..seed_data import BFI10, SJTS


def synthesize_persona(
    bfi_responses: dict[str, int],
    sjt_responses: dict[str, str],
) -> dict[str, Any]:
    # BFI-10 scoring: average the two items per trait, reversed where flagged.
    traits: dict[str, list[float]] = {"O": [], "C": [], "E": [], "A": [], "N": []}
    for item in BFI10:
        raw = bfi_responses.get(item["id"], 3)
        scored = 6 - raw if item["reverse"] else raw
        traits[item["trait"]].append(scored)

    big_five = {
        "openness":          _avg(traits["O"]),
        "conscientiousness": _avg(traits["C"]),
        "extraversion":      _avg(traits["E"]),
        "agreeableness":     _avg(traits["A"]),
        "neuroticism":       _avg(traits["N"]),
    }

    # SJT signal aggregation.
    sjt_signals = {
        "analyticalRigor": 0.0,
        "intellectualHonesty": 0.0,
        "writtenDissent": 0.0,
        "ambiguityTolerance": 0.0,
        "lowEgoCollab": 0.0,
    }
    sjt_count = 0
    for sjt in SJTS:
        chosen_id = sjt_responses.get(sjt["id"])
        if not chosen_id:
            continue
        chosen = next((o for o in sjt["options"] if o["id"] == chosen_id), None)
        if not chosen:
            continue
        for k, v in chosen["signal"].items():
            if k in sjt_signals:
                sjt_signals[k] += v
        sjt_count += 1

    if sjt_count > 0:
        for k in list(sjt_signals.keys()):
            sjt_signals[k] = sjt_signals[k] / sjt_count
    # else: all zeros, which matches the JSX behavior (ternary defaults to 0).

    # Cross-validation flags — three rules ported from the JSX.
    inconsistencies: list[dict[str, str]] = []
    if big_five["agreeableness"] >= 4 and sjt_signals["writtenDissent"] >= 4:
        inconsistencies.append({
            "type": "agreeable-dissenter",
            "note": (
                "Self-reports high agreeableness but SJT responses indicate "
                "strong willingness to dissent in writing. Could be genuine "
                "(principled dissent within a cooperative disposition) or "
                "social-desirability bias in BFI. Worth probing in interview."
            ),
        })
    if big_five["conscientiousness"] <= 2.5 and sjt_signals["analyticalRigor"] >= 4:
        inconsistencies.append({
            "type": "low-c-high-rigor",
            "note": (
                "Self-reports lower conscientiousness but SJT responses favor "
                "thorough analysis. May indicate domain-specific rigor vs "
                "general tidiness."
            ),
        })
    if big_five["neuroticism"] >= 4 and sjt_signals["ambiguityTolerance"] >= 4:
        inconsistencies.append({
            "type": "neurotic-but-tolerant",
            "note": (
                "High neuroticism paired with high demonstrated ambiguity "
                "tolerance. Could indicate coping through structure rather "
                "than genuine comfort — worth probing."
            ),
        })

    return {
        "bigFive": big_five,
        "sjtSignals": sjt_signals,
        "inconsistencies": inconsistencies,
        "narrative": _generate_narrative(big_five, sjt_signals),
    }


def _avg(arr: list[float]) -> float:
    return sum(arr) / len(arr) if arr else 0.0


def _generate_narrative(bf: dict[str, float], sjt: dict[str, float]) -> str:
    """Ported from the JSX generateNarrative. Same thresholds, same strings,
    same Oxford-comma join."""
    bits: list[str] = []
    if bf["conscientiousness"] >= 4:
        bits.append("detail-oriented and thorough")
    elif bf["conscientiousness"] <= 2.5:
        bits.append("favors velocity over exhaustiveness")
    if bf["openness"] >= 4:
        bits.append("intellectually curious")
    if bf["extraversion"] <= 2.5:
        bits.append("works deeply in solitude")
    elif bf["extraversion"] >= 4:
        bits.append("processes ideas socially")
    if bf["agreeableness"] <= 2.5:
        bits.append("comfortable with conflict")
    if sjt["writtenDissent"] >= 4:
        bits.append("disagrees constructively in writing")
    if sjt["intellectualHonesty"] >= 4:
        bits.append("acknowledges uncertainty openly")
    if sjt["ambiguityTolerance"] >= 4:
        bits.append("operates well without playbooks")

    if not bits:
        return "Profile synthesis incomplete."

    if len(bits) == 1:
        return f"A candidate who is {bits[0]}."

    head = ", ".join(bits[:-1])
    return f"A candidate who is {head}, and {bits[-1]}."


