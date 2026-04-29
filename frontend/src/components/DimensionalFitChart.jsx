import React from "react";
import { COLORS, FONT_DISPLAY, FONT_MONO } from "../design.js";
import VarianceBar from "./VarianceBar.jsx";
import { formatCriterion } from "./Widgets.jsx";

export default function DimensionalFitChart({ criterionScores = {}, dimensionalFit = null, criteriaIndex = {} }) {
  const keys = Object.keys(criteriaIndex).length > 0
    ? Object.keys(criteriaIndex)
    : Object.keys(criterionScores);

  return (
    <div>
      {keys.map((key) => {
        const val = criterionScores[key] || {};
        const dim = dimensionalFit?.[key];
        const meta = criteriaIndex[key];

        const mean = dim?.mean ?? val.score ?? 0;
        const std = dim?.std ?? 0;
        const score = val.score ?? mean;
        const agreement = dim?.judgeAgreement;

        return (
          <div key={key} style={{ padding: "20px 0", borderBottom: `1px solid ${COLORS.rule}` }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 6 }}>
              <div style={{ display: "flex", alignItems: "baseline", gap: 12 }}>
                <div style={{ fontFamily: FONT_DISPLAY, fontSize: 20, fontWeight: 500 }}>
                  {meta?.label || formatCriterion(key)}
                </div>
                {meta && (
                  <span className="label-mono">weight {Math.round((meta.weight ?? 0) * 100)}%</span>
                )}
                {agreement != null && (
                  <span className="label-mono">agreement {agreement.toFixed(2)}</span>
                )}
              </div>
              <span style={{ fontFamily: FONT_MONO, fontSize: 20, fontWeight: 500, minWidth: 48, textAlign: "right" }}>
                {Math.round(score)}
              </span>
            </div>
            <div style={{ marginBottom: 12 }}>
              <VarianceBar mean={mean} std={std} height={8} showBand={dimensionalFit != null} />
            </div>
            {val.justification && (
              <div style={{ fontSize: 15, color: COLORS.muted, lineHeight: 1.55 }}>
                {val.justification}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
