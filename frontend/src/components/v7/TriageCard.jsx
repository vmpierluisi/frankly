import React from "react";
import { COLORS, FONT_DISPLAY, FONT_MONO } from "../../design.js";

// Manager Shortlist V7 — a single triage card. Pure presentation:
// hero quote + score + four signal tiles. Consumed by TriageStack.
export default function TriageCard({ candidate }) {
  const { hero_quote: hero, signals = [] } = candidate;
  return (
    <div
      style={{
        background: "#fff",
        border: `1px solid ${COLORS.ink}`,
        padding: "28px 32px",
        display: "flex",
        flexDirection: "column",
        gap: 20,
        height: "100%",
        boxShadow: "0 8px 32px rgba(0,0,0,0.10)",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
        <div>
          <div className="label-mono" style={{ fontFamily: FONT_MONO, fontSize: 10 }}>
            Candidate
          </div>
          <div style={{ fontFamily: FONT_DISPLAY, fontSize: 30, fontWeight: 500 }}>
            {candidate.anchor_short || candidate.name}
          </div>
        </div>
        <div style={{ textAlign: "right" }}>
          <div style={{ fontFamily: FONT_DISPLAY, fontSize: 34, fontWeight: 500 }}>
            {candidate.score}
          </div>
          <div style={{ fontFamily: FONT_MONO, fontSize: 11, color: COLORS.muted }}>
            {candidate.band}
            {candidate.delta ? ` · ${candidate.delta}` : ""}
          </div>
        </div>
      </div>

      {hero?.text && (
        <blockquote
          style={{
            margin: 0,
            fontFamily: FONT_DISPLAY,
            fontStyle: "italic",
            fontSize: 21,
            lineHeight: 1.4,
            borderLeft: `3px solid ${COLORS.accent}`,
            paddingLeft: 18,
            display: "-webkit-box",
            WebkitLineClamp: 6,
            WebkitBoxOrient: "vertical",
            overflow: "hidden",
          }}
        >
          “{hero.text}”
        </blockquote>
      )}

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(2, 1fr)",
          gap: 12,
          marginTop: "auto",
        }}
      >
        {signals.map((s, i) => (
          <div
            key={i}
            style={{
              border: `1px solid ${s.tell ? COLORS.accent : COLORS.rule}`,
              background: s.tell ? COLORS.accentSoft : "transparent",
              padding: "12px 14px",
            }}
          >
            <div className="label-mono" style={{ fontFamily: FONT_MONO, fontSize: 9, marginBottom: 4 }}>
              {s.lab}
            </div>
            <div style={{ fontFamily: FONT_DISPLAY, fontSize: 18, fontWeight: 500 }}>{s.v}</div>
            {s.e && <div style={{ fontSize: 12, color: COLORS.muted }}>{s.e}</div>}
          </div>
        ))}
      </div>
    </div>
  );
}
