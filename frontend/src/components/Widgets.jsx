import React from "react";
import { COLORS, FONT_DISPLAY, FONT_MONO } from "../design.js";

// Reusable presentational primitives shared across pages. Editorial,
// minimal, no third-party UI lib.

export function MiniBar({ label, value, max = 5 }) {
  const safeVal = Number.isFinite(value) ? value : 0;
  const pct = Math.max(0, Math.min(100, (safeVal / max) * 100));
  return (
    <div style={{ marginBottom: 10 }}>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 14, marginBottom: 4 }}>
        <span style={{ textTransform: "capitalize" }}>{label}</span>
        <span style={{ fontFamily: FONT_MONO, fontSize: 12, color: COLORS.muted }}>
          {safeVal.toFixed(1)}
        </span>
      </div>
      <div style={{ height: 2, background: COLORS.rule }}>
        <div style={{ height: "100%", width: `${pct}%`, background: COLORS.ink }} />
      </div>
    </div>
  );
}

export function ScoreBar({ score }) {
  const safe = Math.max(0, Math.min(100, score ?? 0));
  return (
    <div style={{ height: 3, background: COLORS.rule, position: "relative" }}>
      <div
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          height: "100%",
          width: `${safe}%`,
          background: safe >= 70 ? COLORS.ink : safe >= 50 ? COLORS.accent : COLORS.muted,
        }}
      />
    </div>
  );
}

export function formatCriterion(k) {
  if (!k) return "";
  return k
    .replace(/([A-Z])/g, " $1")
    .replace(/^./, (s) => s.toUpperCase())
    .trim();
}

export function Pillar({ n, title, body }) {
  return (
    <div>
      <div style={{ fontFamily: FONT_DISPLAY, fontSize: 32, color: COLORS.accent, fontStyle: "italic" }}>
        {n}
      </div>
      <div style={{ fontFamily: FONT_DISPLAY, fontSize: 20, fontWeight: 500, margin: "4px 0 8px" }}>
        {title}
      </div>
      <div style={{ fontSize: 15, color: COLORS.muted, lineHeight: 1.5 }}>{body}</div>
    </div>
  );
}

export function GeneratingScreen({ note }) {
  return (
    <div style={{ padding: "120px 0", textAlign: "center" }}>
      <div className="label-mono" style={{ marginBottom: 24 }}>
        <span className="pulse-dot"></span>&nbsp;
        <span className="pulse-dot"></span>&nbsp;
        <span className="pulse-dot"></span>
      </div>
      <div style={{ fontFamily: FONT_DISPLAY, fontSize: 28, fontStyle: "italic", color: COLORS.muted }}>
        {note || "Synthesizing persona…"}
      </div>
    </div>
  );
}
