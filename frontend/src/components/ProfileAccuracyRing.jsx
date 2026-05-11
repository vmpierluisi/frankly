import React from "react";
import { COLORS, FONT_DISPLAY, FONT_MONO } from "../design.js";

/**
 * "How well we know you" ring. Single 0..100 number rendered as a circular
 * progress arc. Companion copy makes it honest: low number = early days,
 * grows as the calibration loop (PR #5) adds evidence.
 */
export default function ProfileAccuracyRing({ value = 0, size = 140, onClick }) {
  const v = Math.max(0, Math.min(100, Math.round(value)));
  const stroke = 10;
  const r = (size - stroke) / 2;
  const cx = size / 2;
  const cy = size / 2;
  const circumference = 2 * Math.PI * r;
  const dashoffset = circumference * (1 - v / 100);

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 20,
        cursor: onClick ? "pointer" : "default",
      }}
      onClick={onClick}
      role={onClick ? "button" : undefined}
      title={onClick ? "Tap to see how this number sharpened over time" : undefined}
    >
      <svg
        width={size}
        height={size}
        viewBox={`0 0 ${size} ${size}`}
        style={{ flexShrink: 0 }}
      >
        <circle
          cx={cx}
          cy={cy}
          r={r}
          fill="none"
          stroke={COLORS.rule}
          strokeWidth={stroke}
        />
        <circle
          cx={cx}
          cy={cy}
          r={r}
          fill="none"
          stroke={COLORS.ink}
          strokeWidth={stroke}
          strokeDasharray={circumference}
          strokeDashoffset={dashoffset}
          strokeLinecap="round"
          transform={`rotate(-90 ${cx} ${cy})`}
          style={{ transition: "stroke-dashoffset 0.6s ease-out" }}
        />
        <text
          x={cx}
          y={cy + 8}
          textAnchor="middle"
          style={{
            fontFamily: FONT_DISPLAY,
            fontSize: 32,
            fontWeight: 500,
            fill: COLORS.ink,
          }}
        >
          {v}%
        </text>
      </svg>
      <div>
        <div
          className="label-mono"
          style={{ marginBottom: 6 }}
        >
          How well we know you
        </div>
        <div
          style={{
            color: COLORS.muted,
            fontSize: 14,
            lineHeight: 1.5,
            maxWidth: 320,
          }}
        >
          {v < 25
            ? "Just getting started. Add a CV and link your GitHub to sharpen your simulation profile."
            : v < 60
            ? "Building up. Each calibration round refines how the simulation represents you."
            : "Well-calibrated. The simulation should faithfully reflect your real responses."}
        </div>
      </div>
    </div>
  );
}

/**
 * Tiny inline percent pill — used elsewhere on FitProfile etc.
 */
export function ProfileAccuracyChip({ value = 0 }) {
  const v = Math.max(0, Math.min(100, Math.round(value)));
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        padding: "3px 10px",
        border: `1px solid ${COLORS.rule}`,
        background: COLORS.cardBg,
        color: COLORS.muted,
        fontFamily: FONT_MONO,
        fontSize: 10,
        letterSpacing: "0.12em",
        textTransform: "uppercase",
      }}
      title="Profile accuracy: how well our simulation reflects this candidate"
    >
      Profile accuracy · {v}%
    </span>
  );
}
