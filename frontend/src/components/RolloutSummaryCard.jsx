import React from "react";
import { COLORS, FONT_DISPLAY, FONT_MONO } from "../design.js";

function scoreTick(score) {
  if (score == null) return COLORS.muted;
  if (score >= 70) return "#4a7c59";
  if (score >= 50) return COLORS.accent;
  return COLORS.muted;
}

export default function RolloutSummaryCard({ summary, onClick }) {
  const { rolloutId, scenarioTitle, kIndex, headline, scores = {} } = summary;
  const scoreEntries = Object.entries(scores);

  return (
    <div
      className="card"
      onClick={() => onClick(rolloutId)}
      style={{ cursor: "pointer", minWidth: 220, maxWidth: 280, flex: "0 0 auto", transition: "box-shadow 0.15s" }}
      onMouseEnter={(e) => e.currentTarget.style.boxShadow = "0 4px 16px rgba(0,0,0,0.10)"}
      onMouseLeave={(e) => e.currentTarget.style.boxShadow = "none"}
    >
      <div className="label-mono" style={{ marginBottom: 8 }}>
        Rollout #{kIndex} · {scenarioTitle}
      </div>
      {headline ? (
        <div style={{ fontFamily: FONT_DISPLAY, fontSize: 16, fontStyle: "italic", lineHeight: 1.45, marginBottom: 12, minHeight: 48 }}>
          {headline.length > 120 ? headline.slice(0, 117) + "…" : headline}
        </div>
      ) : (
        <div style={{ minHeight: 48, marginBottom: 12 }} />
      )}
      {scoreEntries.length > 0 && (
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          {scoreEntries.map(([key, score]) => (
            <div key={key} style={{ display: "flex", alignItems: "center", gap: 4 }}>
              <div style={{ width: 8, height: 8, borderRadius: "50%", background: scoreTick(score) }} />
              <span style={{ fontFamily: FONT_MONO, fontSize: 10, color: COLORS.muted }}>
                {Math.round(score)}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
