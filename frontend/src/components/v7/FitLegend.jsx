import React from "react";
import { COLORS, FONT_DISPLAY, FONT_MONO, candidateColor } from "../../design.js";

// Manager Shortlist V7 — radar legend + optional team glossary.
// Clicking a swatch focuses that candidate (others dim). Keyboard accessible.
export default function FitLegend({ candidates, focusedId, onFocus, team }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18, minWidth: 200 }}>
      <div>
        <div className="label-mono" style={{ fontFamily: FONT_MONO, fontSize: 10, marginBottom: 10 }}>
          Candidates
        </div>
        <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", flexDirection: "column", gap: 6 }}>
          {candidates.map((c) => {
            const color = candidateColor(c.palette_color_var);
            const active = focusedId === c.id;
            return (
              <li key={c.id}>
                <button
                  type="button"
                  aria-pressed={active}
                  onClick={() => onFocus(active ? null : c.id)}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 8,
                    width: "100%",
                    background: active ? COLORS.accentSoft : "transparent",
                    border: "none",
                    cursor: "pointer",
                    padding: "4px 6px",
                    textAlign: "left",
                    opacity: focusedId && !active ? 0.5 : 1,
                  }}
                >
                  <span style={{ width: 12, height: 12, background: color, flexShrink: 0 }} />
                  <span style={{ fontFamily: FONT_DISPLAY, fontSize: 15 }}>
                    {c.anchor_short || c.name}
                  </span>
                  <span style={{ marginLeft: "auto", fontFamily: FONT_MONO, fontSize: 11, color: COLORS.muted }}>
                    {c.score}
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      </div>

      {team && team.length > 0 && (
        <div>
          <div className="label-mono" style={{ fontFamily: FONT_MONO, fontSize: 10, marginBottom: 10 }}>
            The team
          </div>
          <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", flexDirection: "column", gap: 8 }}>
            {team.map((t) => (
              <li key={t.id}>
                <div style={{ fontFamily: FONT_DISPLAY, fontSize: 14, fontWeight: 500 }}>{t.short}</div>
                {t.voice && (
                  <div style={{ fontSize: 12, color: COLORS.muted, fontStyle: "italic" }}>{t.voice}</div>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
