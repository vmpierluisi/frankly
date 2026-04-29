import React from "react";
import { useNavigate } from "react-router-dom";
import { COLORS, FONT_DISPLAY, FONT_MONO } from "../design.js";
import DimensionalFitChart from "./DimensionalFitChart.jsx";
import BaselineCompareStrip from "./BaselineCompareStrip.jsx";
import RolloutSummaryCard from "./RolloutSummaryCard.jsx";

export default function FitProfileV2({ report, criteriaIndex = {}, onOpenRollout }) {
  const navigate = useNavigate();
  const {
    matchId,
    overallScore,
    band,
    bandNote,
    companyName,
    company_name,
    role,
    criterionScores = {},
    dimensionalFit = null,
    rolloutSummaries = [],
    baselineComparison = null,
    inconsistencyFlags = [],
    confidenceSignals = null,
    auditTrailV2 = {},
  } = report;

  const displayName = companyName || company_name;

  return (
    <div>
      <div className="label-mono" style={{ marginBottom: 12 }}>Fit Report v2 · Confidential · Screening Signal</div>

      {/* Headline strip */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: 24, marginBottom: 8 }}>
        <div>
          <h2 style={{ fontFamily: FONT_DISPLAY, fontSize: 44, fontWeight: 500, letterSpacing: "-0.015em", margin: "0 0 8px", lineHeight: 1.1 }}>
            {band}.
          </h2>
          <p style={{ fontSize: 18, color: COLORS.muted, margin: 0, fontStyle: "italic" }}>
            {bandNote || band}
          </p>
        </div>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 12 }}>
          <div style={{ textAlign: "right" }}>
            <div className="label-mono" style={{ marginBottom: 4 }}>Weighted fit</div>
            <div style={{ fontFamily: FONT_DISPLAY, fontSize: 72, fontWeight: 500, lineHeight: 1, color: COLORS.accent, letterSpacing: "-0.03em" }}>
              {overallScore}
            </div>
            <div className="label-mono">of 100</div>
          </div>
          <BaselineCompareStrip
            baselineComparison={baselineComparison}
            simulationOverallScore={overallScore}
            criteriaIndex={criteriaIndex}
          />
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 40, margin: "24px 0" }}>
        <div>
          <div className="label-mono" style={{ marginBottom: 8 }}>Matched environment</div>
          <div style={{ fontFamily: FONT_DISPLAY, fontSize: 26, fontWeight: 500 }}>{displayName}</div>
          <div style={{ color: COLORS.muted, fontSize: 16 }}>{role}</div>
        </div>
        {confidenceSignals && (
          <div style={{ textAlign: "right" }}>
            <div className="label-mono" style={{ marginBottom: 8 }}>Confidence signals</div>
            <div style={{ fontFamily: FONT_MONO, fontSize: 13, color: COLORS.muted, lineHeight: 1.8 }}>
              <div>σ overall: {(confidenceSignals.overallStd ?? 0).toFixed(1)}</div>
              <div>judge agreement: {(confidenceSignals.judgeAgreementMean ?? 0).toFixed(2)}</div>
              <div>min rollouts: {confidenceSignals.minNRollouts ?? 0}</div>
            </div>
          </div>
        )}
      </div>

      <hr className="rule-thick" style={{ margin: "24px 0" }} />

      {/* Dimensional fit chart */}
      <div className="label-mono" style={{ marginBottom: 16 }}>Scoring decomposition</div>
      <DimensionalFitChart
        criterionScores={criterionScores}
        dimensionalFit={dimensionalFit}
        criteriaIndex={criteriaIndex}
      />

      {/* Rollout summaries */}
      {rolloutSummaries.length > 0 ? (
        <div style={{ marginTop: 40 }}>
          <div className="label-mono" style={{ marginBottom: 16 }}>Simulation rollouts</div>
          <div style={{ display: "flex", gap: 16, overflowX: "auto", paddingBottom: 8 }}>
            {rolloutSummaries.map((s) => (
              <RolloutSummaryCard
                key={s.rolloutId}
                summary={s}
                onClick={(rolloutId) => {
                  if (onOpenRollout) return onOpenRollout(rolloutId);
                  if (matchId) navigate(`/manager/matches/${matchId}/rollouts/${rolloutId}`);
                }}
              />
            ))}
          </div>
        </div>
      ) : (
        <div style={{ marginTop: 40 }}>
          <span className="label-mono">no rollouts persisted for this match</span>
        </div>
      )}

      {/* Inconsistency flags */}
      {inconsistencyFlags.length > 0 && (
        <div style={{ marginTop: 40, background: COLORS.accentSoft, padding: "24px 28px", borderLeft: `3px solid ${COLORS.accent}` }}>
          <div className="label-mono" style={{ marginBottom: 10, color: COLORS.accent }}>Cross-validation flags</div>
          <div style={{ fontSize: 14, color: COLORS.muted, marginBottom: 16 }}>
            Signals that don't cleanly align between self-report and situational response.
          </div>
          {inconsistencyFlags.map((flag, i) => (
            <div key={i} style={{ marginBottom: 12 }}>
              <div style={{ fontFamily: FONT_MONO, fontSize: 12, color: COLORS.accent, textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 4 }}>
                {flag.type}
              </div>
              <div style={{ fontSize: 15, lineHeight: 1.55 }}>{flag.note}</div>
            </div>
          ))}
        </div>
      )}

      {/* Methodology footer */}
      <div style={{ marginTop: 40, paddingTop: 24, borderTop: `1px solid ${COLORS.rule}`, fontSize: 12, color: COLORS.muted, fontFamily: FONT_MONO, lineHeight: 1.8 }}>
        <div>
          {[
            auditTrailV2.kPerScenario != null && `K=${auditTrailV2.kPerScenario}`,
            auditTrailV2.scenariosRun != null && `${auditTrailV2.scenariosRun} scenario${auditTrailV2.scenariosRun !== 1 ? "s" : ""}`,
            auditTrailV2.judgeModel && `judge=${auditTrailV2.judgeModel}`,
            auditTrailV2.judgeCount != null && `${auditTrailV2.judgeCount} judges/rollout`,
            auditTrailV2.proofLayer && `proof=${auditTrailV2.proofLayer}`,
          ].filter(Boolean).join(" · ")}
        </div>
        {auditTrailV2.timestamp && (
          <div>ts={auditTrailV2.timestamp}</div>
        )}
        {confidenceSignals && (
          <div>
            per-criterion σ: {Object.entries(confidenceSignals.perCriterionStd || {}).map(([k, v]) => `${k}=${v.toFixed(1)}`).join(", ")}
          </div>
        )}
      </div>
    </div>
  );
}
