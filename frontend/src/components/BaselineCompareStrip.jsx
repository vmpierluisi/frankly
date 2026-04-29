import React, { useState } from "react";
import { COLORS, FONT_DISPLAY, FONT_MONO } from "../design.js";
import { formatCriterion } from "./Widgets.jsx";

export default function BaselineCompareStrip({ baselineComparison, simulationOverallScore, criteriaIndex = {}, onExpand }) {
  const [modalOpen, setModalOpen] = useState(false);

  if (!baselineComparison) return null;

  const { overallScore, deltaVsSim = {}, robustnessSummary = "" } = baselineComparison;
  const delta = simulationOverallScore - overallScore;
  const deltaLabel = delta > 0 ? `+${delta}` : `${delta}`;
  const deltaColor = delta > 0 ? COLORS.accent : delta < 0 ? COLORS.muted : COLORS.ink;

  return (
    <>
      <div
        onClick={() => setModalOpen(true)}
        style={{
          border: `1px solid ${COLORS.accent}`,
          padding: "14px 18px",
          cursor: "pointer",
          minWidth: 280,
          maxWidth: 360,
        }}
      >
        <div className="label-mono" style={{ marginBottom: 6 }}>Robustness check</div>
        <div style={{ fontFamily: FONT_MONO, fontSize: 14, marginBottom: 4 }}>
          Sim{" "}
          <span style={{ color: COLORS.accent, fontWeight: 600 }}>{simulationOverallScore}</span>
          {" · "}Baseline{" "}
          <span>{overallScore}</span>
          {" "}
          <span style={{ color: deltaColor, fontWeight: 600 }}>{deltaLabel}</span>
        </div>
        {robustnessSummary && (
          <div
            style={{
              fontSize: 13,
              color: COLORS.muted,
              lineHeight: 1.4,
              overflow: "hidden",
              display: "-webkit-box",
              WebkitLineClamp: 2,
              WebkitBoxOrient: "vertical",
            }}
          >
            {robustnessSummary}
          </div>
        )}
        <div className="label-mono" style={{ marginTop: 8, color: COLORS.accent }}>View detail →</div>
      </div>

      {modalOpen && (
        <div
          onClick={() => setModalOpen(false)}
          style={{
            position: "fixed", inset: 0,
            background: "rgba(0,0,0,0.45)",
            display: "flex", alignItems: "center", justifyContent: "center",
            zIndex: 1000,
          }}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              background: COLORS.paper,
              border: `1px solid ${COLORS.rule}`,
              padding: "40px 44px",
              maxWidth: 560,
              width: "100%",
              maxHeight: "80vh",
              overflowY: "auto",
            }}
          >
            <div className="label-mono" style={{ marginBottom: 16 }}>Baseline comparison — per criterion</div>
            {Object.entries(deltaVsSim).map(([key, d]) => {
              const label = criteriaIndex[key]?.label || formatCriterion(key);
              const dNum = Number(d);
              return (
                <div key={key} style={{ display: "flex", justifyContent: "space-between", padding: "10px 0", borderBottom: `1px solid ${COLORS.rule}` }}>
                  <span style={{ fontFamily: FONT_MONO, fontSize: 13 }}>{label}</span>
                  <span style={{ fontFamily: FONT_MONO, fontSize: 13, color: dNum > 0 ? COLORS.accent : dNum < 0 ? COLORS.muted : COLORS.ink, fontWeight: 600 }}>
                    {dNum > 0 ? `+${dNum}` : dNum}
                  </span>
                </div>
              );
            })}
            {robustnessSummary && (
              <p style={{ marginTop: 20, fontSize: 14, color: COLORS.muted, lineHeight: 1.55 }}>{robustnessSummary}</p>
            )}
            <button className="ghost" style={{ marginTop: 24 }} onClick={() => setModalOpen(false)}>Close</button>
          </div>
        </div>
      )}
    </>
  );
}
