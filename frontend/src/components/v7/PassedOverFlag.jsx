import React from "react";
import { COLORS, FONT_MONO, candidateColor } from "../../design.js";

// Manager Shortlist V7 — "you would have missed this" callout.
// Rendered beneath a scenario's response row when a candidate NOT in the
// current comparison beat every active candidate on that scenario (strict).
export default function PassedOverFlag({ candidate, scenarioTitle, score, beatBy, onAdd }) {
  const color = candidateColor(candidate.palette_color_var);
  return (
    <div
      role="note"
      style={{
        border: `1px dashed ${COLORS.accent}`,
        background: COLORS.accentSoft,
        padding: "14px 18px",
        margin: "12px 0 4px",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: 16,
        flexWrap: "wrap",
      }}
    >
      <div>
        <div
          className="label-mono"
          style={{ fontFamily: FONT_MONO, fontSize: 10, color: COLORS.accent, marginBottom: 4 }}
        >
          You would have missed this
        </div>
        <div style={{ fontSize: 15 }}>
          <strong style={{ color }}>{candidate.anchor_short || candidate.name}</strong>{" "}
          isn't in your comparison, but scored{" "}
          <strong>{score}/100</strong> on {scenarioTitle}
          {beatBy != null && (
            <> — {beatBy} above your strongest shortlisted response.</>
          )}
        </div>
      </div>
      <button
        type="button"
        className="ghost"
        style={{ padding: "8px 14px", fontSize: 11, whiteSpace: "nowrap" }}
        onClick={() => onAdd(candidate.id)}
      >
        + Add to comparison
      </button>
    </div>
  );
}
