import React from "react";
import { COLORS, FONT_DISPLAY, FONT_MONO } from "../design.js";
import { ScoreBar, formatCriterion } from "./Widgets.jsx";

// The editorial fit-report panel. Same visual language as the JSX reference
// `ReportScreen`. Used inside the manager dashboard. The shape mirrors what
// /matches/trigger returns.

export default function FitReport({ report, criteriaIndex }) {
  const { criterionScores = {}, inconsistencyFlags = [], auditTrail = {} } = report;

  return (
    <div>
      <div className="label-mono" style={{ marginBottom: 12 }}>Fit Report · Confidential · Screening Signal</div>
      <h2
        style={{
          fontFamily: FONT_DISPLAY,
          fontSize: 44,
          fontWeight: 500,
          letterSpacing: "-0.015em",
          margin: "0 0 8px",
          lineHeight: 1.1,
        }}
      >
        {report.band}.
      </h2>
      <p style={{ fontSize: 18, color: COLORS.muted, marginBottom: 8, fontStyle: "italic" }}>
        {report.bandNote || report.band_note}
      </p>
      <hr className="rule-thick" style={{ margin: "32px 0 24px" }} />

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 40, marginBottom: 40 }}>
        <div>
          <div className="label-mono" style={{ marginBottom: 8 }}>Matched environment</div>
          <div style={{ fontFamily: FONT_DISPLAY, fontSize: 26, fontWeight: 500 }}>
            {report.companyName || report.company_name}
          </div>
          <div style={{ color: COLORS.muted, fontSize: 16 }}>{report.role}</div>
        </div>
        <div style={{ textAlign: "right" }}>
          <div className="label-mono" style={{ marginBottom: 8 }}>Weighted fit</div>
          <div
            style={{
              fontFamily: FONT_DISPLAY,
              fontSize: 72,
              fontWeight: 500,
              lineHeight: 1,
              color: COLORS.accent,
              letterSpacing: "-0.03em",
            }}
          >
            {report.overallScore ?? report.overall_score}
          </div>
          <div className="label-mono">of 100</div>
        </div>
      </div>

      <div className="label-mono" style={{ marginBottom: 16 }}>Scoring decomposition</div>
      {Object.entries(criterionScores).map(([key, val]) => {
        const meta = criteriaIndex?.[key];
        return (
          <div key={key} style={{ padding: "20px 0", borderBottom: `1px solid ${COLORS.rule}` }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 8 }}>
              <div style={{ fontFamily: FONT_DISPLAY, fontSize: 20, fontWeight: 500 }}>
                {meta?.label || formatCriterion(key)}
              </div>
              <div style={{ display: "flex", alignItems: "baseline", gap: 12 }}>
                {meta && (
                  <span className="label-mono">weight {Math.round(meta.weight * 100)}%</span>
                )}
                <span
                  style={{
                    fontFamily: FONT_MONO,
                    fontSize: 20,
                    fontWeight: 500,
                    minWidth: 48,
                    textAlign: "right",
                  }}
                >
                  {Math.round(val.score)}
                </span>
              </div>
            </div>
            <div style={{ marginBottom: 12 }}>
              <ScoreBar score={val.score} />
            </div>
            <div style={{ fontSize: 15, color: COLORS.muted, lineHeight: 1.55 }}>
              {val.justification}
            </div>
          </div>
        );
      })}

      {inconsistencyFlags?.length > 0 && (
        <div
          style={{
            marginTop: 40,
            background: COLORS.accentSoft,
            padding: "24px 28px",
            borderLeft: `3px solid ${COLORS.accent}`,
          }}
        >
          <div className="label-mono" style={{ marginBottom: 10, color: COLORS.accent }}>
            Cross-validation flags
          </div>
          <div style={{ fontSize: 14, color: COLORS.muted, marginBottom: 16 }}>
            Signals that don't cleanly align between self-report and situational response.
            Useful questions for a human interviewer.
          </div>
          {inconsistencyFlags.map((flag, i) => (
            <div key={i} style={{ marginBottom: 12 }}>
              <div
                style={{
                  fontFamily: FONT_MONO,
                  fontSize: 12,
                  color: COLORS.accent,
                  textTransform: "uppercase",
                  letterSpacing: "0.1em",
                  marginBottom: 4,
                }}
              >
                {flag.type}
              </div>
              <div style={{ fontSize: 15, lineHeight: 1.55 }}>{flag.note}</div>
            </div>
          ))}
        </div>
      )}

      <div
        style={{
          marginTop: 40,
          paddingTop: 24,
          borderTop: `1px solid ${COLORS.rule}`,
          fontSize: 13,
          color: COLORS.muted,
          fontFamily: FONT_MONO,
        }}
      >
        <div>
          audit · model={auditTrail.model} · ts={auditTrail.timestamp}
        </div>
        {auditTrail.note && (
          <div style={{ marginTop: 6, fontStyle: "italic" }}>{auditTrail.note}</div>
        )}
      </div>
    </div>
  );
}
