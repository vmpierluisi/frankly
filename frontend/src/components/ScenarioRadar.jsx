import React, { useMemo, useState } from "react";
import { COLORS, FONT_DISPLAY, FONT_MONO } from "../design.js";

/**
 * Multi-scenario stress-test radar — PR #3.5.
 *
 * Renders one spoke per scenario, distance from centre proportional to the
 * candidate's per-scenario aggregate score (0..100). Solid polygon shows
 * the candidate's "shape" across contexts — a tight central blob = even
 * performance, a spiked star = strong in some scenarios and weak in others.
 *
 * Hovering / focusing a spoke surfaces the scenario title + score in a
 * small annotation. iPhone-easy: no toolbar, no legend, just the chart.
 *
 * Hidden when fewer than 3 scenarios — a radar with 1-2 points isn't
 * useful (degenerates to a line / dot).
 */
export default function ScenarioRadar({ scenarios = [], size = 380 }) {
  const data = (scenarios || []).filter(
    (s) => typeof s.score === "number" && s.score !== null,
  );
  const [hover, setHover] = useState(null);

  const geometry = useMemo(() => {
    if (data.length < 3) return null;
    const cx = size / 2;
    const cy = size / 2;
    // Generous margin so spoke labels (some titles run ~22 chars) don't
    // clip the viewBox on the left / right.
    const radius = (size / 2) - 95;
    const n = data.length;
    const ringValues = [25, 50, 75, 100]; // gridlines
    const angle = (i) => (-Math.PI / 2) + (i / n) * Math.PI * 2;
    const point = (i, value) => {
      const r = radius * (Math.max(0, Math.min(100, value)) / 100);
      const a = angle(i);
      return [cx + Math.cos(a) * r, cy + Math.sin(a) * r];
    };
    const labelPoint = (i) => {
      const a = angle(i);
      const r = radius + 18;
      return [cx + Math.cos(a) * r, cy + Math.sin(a) * r, a];
    };
    return { cx, cy, radius, n, ringValues, angle, point, labelPoint };
  }, [data, size]);

  if (!geometry) return null;
  const { cx, cy, radius, n, ringValues, point, labelPoint } = geometry;

  const polygonPoints = data
    .map((s, i) => point(i, s.score).join(","))
    .join(" ");

  return (
    <div>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "baseline",
          marginBottom: 8,
        }}
      >
        <div className="label-mono">Scenario stress test</div>
        <div
          style={{ color: COLORS.muted, fontSize: 12, fontStyle: "italic" }}
        >
          {data.length} scenarios · score per scenario
        </div>
      </div>
      <svg
        width={size}
        height={size}
        viewBox={`0 0 ${size} ${size}`}
        role="img"
        aria-label="Multi-scenario performance radar"
        // overflow:visible lets spoke labels render outside the viewBox
        // (they extend leftward / rightward from the rim).
        style={{ display: "block", margin: "0 auto", overflow: "visible" }}
      >
        {/* concentric grid rings */}
        {ringValues.map((v, idx) => (
          <circle
            key={v}
            cx={cx}
            cy={cy}
            r={radius * (v / 100)}
            fill="none"
            stroke={COLORS.rule}
            strokeDasharray={idx === ringValues.length - 1 ? "0" : "2 4"}
            strokeWidth={1}
          />
        ))}
        {/* spokes */}
        {data.map((s, i) => {
          const [x, y] = point(i, 100);
          return (
            <line
              key={s.scenarioId}
              x1={cx}
              y1={cy}
              x2={x}
              y2={y}
              stroke={COLORS.rule}
              strokeWidth={1}
            />
          );
        })}
        {/* candidate polygon */}
        <polygon
          points={polygonPoints}
          fill={COLORS.accent}
          fillOpacity={0.18}
          stroke={COLORS.accent}
          strokeWidth={2}
          strokeLinejoin="round"
        />
        {/* score dots */}
        {data.map((s, i) => {
          const [x, y] = point(i, s.score);
          const active = hover === i;
          return (
            <g key={s.scenarioId}>
              <circle
                cx={x}
                cy={y}
                r={active ? 6 : 4}
                fill={active ? COLORS.ink : COLORS.accent}
                stroke="#fff"
                strokeWidth={1.5}
                style={{ cursor: "pointer", transition: "r 0.15s" }}
                onMouseEnter={() => setHover(i)}
                onMouseLeave={() => setHover(null)}
              />
            </g>
          );
        })}
        {/* spoke labels */}
        {data.map((s, i) => {
          const [lx, ly, a] = labelPoint(i);
          // anchor based on angle so labels don't overlap the polygon
          const anchor =
            Math.abs(Math.cos(a)) < 0.2
              ? "middle"
              : Math.cos(a) > 0
              ? "start"
              : "end";
          const label = (s.title || s.scenarioId || "").trim();
          const truncated =
            label.length > 18 ? label.slice(0, 16) + "…" : label;
          return (
            <text
              key={s.scenarioId}
              x={lx}
              y={ly}
              textAnchor={anchor}
              dominantBaseline="middle"
              style={{
                fontFamily: FONT_MONO,
                fontSize: 10,
                letterSpacing: "0.05em",
                fill: hover === i ? COLORS.ink : COLORS.muted,
                cursor: "pointer",
              }}
              onMouseEnter={() => setHover(i)}
              onMouseLeave={() => setHover(null)}
            >
              {truncated}
            </text>
          );
        })}
      </svg>

      {/* Hover details box */}
      <div
        style={{
          minHeight: 44,
          marginTop: 12,
          padding: "8px 12px",
          border: `1px solid ${COLORS.rule}`,
          background: COLORS.cardBg,
        }}
      >
        {hover != null ? (
          <>
            <div
              style={{
                fontFamily: FONT_DISPLAY,
                fontSize: 15,
                fontWeight: 500,
                color: COLORS.ink,
              }}
            >
              {data[hover].title || data[hover].scenarioId}
            </div>
            <div
              style={{
                fontFamily: FONT_MONO,
                fontSize: 11,
                color: COLORS.muted,
                letterSpacing: "0.04em",
                marginTop: 2,
              }}
            >
              score {data[hover].score} · {data[hover].nRollouts}{" "}
              rollout{data[hover].nRollouts !== 1 ? "s" : ""}
            </div>
          </>
        ) : (
          <div
            style={{
              fontFamily: FONT_MONO,
              fontSize: 11,
              color: COLORS.muted,
              fontStyle: "italic",
            }}
          >
            Hover a spoke for scenario detail.
          </div>
        )}
      </div>
    </div>
  );
}
