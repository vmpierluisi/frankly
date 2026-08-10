import React from "react";
import { COLORS, FONT_MONO } from "../../design.js";

// Manager Shortlist V7 — pure SVG radar primitive.
// Props:
//   axes:    [{ id, label }]                 — one spoke per axis
//   series:  [{ id, name, color, values }]   — values keyed by axis id (0..100)
//   size:    px (square). focusedId dims the other series.
//   onAxisHover(axis | null), onSeriesHover(seriesId | null)
export default function RadarSVG({
  axes,
  series,
  size = 460,
  focusedId = null,
  onAxisHover,
  onSeriesHover,
}) {
  const cx = size / 2;
  const cy = size / 2;
  const radius = size / 2 - 64; // leave room for labels
  const n = axes.length;

  if (n < 3) {
    return (
      <div style={{ color: COLORS.muted, fontStyle: "italic", padding: 24 }}>
        Need at least three axes to draw a radar.
      </div>
    );
  }

  // Angle for axis i (start at top, clockwise).
  const angle = (i) => (Math.PI * 2 * i) / n - Math.PI / 2;
  const point = (i, r) => [cx + Math.cos(angle(i)) * r, cy + Math.sin(angle(i)) * r];

  const rings = [0.25, 0.5, 0.75, 1];

  return (
    <svg
      viewBox={`0 0 ${size} ${size}`}
      width="100%"
      style={{ maxWidth: size, display: "block" }}
      role="img"
      aria-label="Fit radar chart"
    >
      {/* Grid rings */}
      {rings.map((f) => (
        <polygon
          key={f}
          points={axes.map((_, i) => point(i, radius * f).join(",")).join(" ")}
          fill="none"
          stroke={COLORS.rule}
          strokeWidth={1}
        />
      ))}

      {/* Spokes + axis labels */}
      {axes.map((ax, i) => {
        const [x, y] = point(i, radius);
        const [lx, ly] = point(i, radius + 22);
        const anchor = Math.abs(lx - cx) < 8 ? "middle" : lx > cx ? "start" : "end";
        return (
          <g key={ax.id}>
            <line x1={cx} y1={cy} x2={x} y2={y} stroke={COLORS.rule} strokeWidth={1} />
            <text
              x={lx}
              y={ly}
              textAnchor={anchor}
              dominantBaseline="middle"
              fontFamily={FONT_MONO}
              fontSize={10}
              fill={COLORS.muted}
              style={{ cursor: onAxisHover ? "pointer" : "default" }}
              onMouseEnter={() => onAxisHover?.(ax)}
              onMouseLeave={() => onAxisHover?.(null)}
            >
              {truncate(ax.label, 16)}
            </text>
          </g>
        );
      })}

      {/* Series polygons */}
      {series.map((s) => {
        const dimmed = focusedId && focusedId !== s.id;
        const pts = axes
          .map((ax, i) => point(i, (radius * clamp(s.values[ax.id])) / 100).join(","))
          .join(" ");
        return (
          <g
            key={s.id}
            style={{ transition: "opacity 0.22s ease" }}
            opacity={dimmed ? 0.14 : 1}
            onMouseEnter={() => onSeriesHover?.(s.id)}
            onMouseLeave={() => onSeriesHover?.(null)}
          >
            <polygon points={pts} fill={s.color} fillOpacity={0.12} stroke={s.color} strokeWidth={2} />
            {axes.map((ax, i) => {
              const [px, py] = point(i, (radius * clamp(s.values[ax.id])) / 100);
              return <circle key={ax.id} cx={px} cy={py} r={3} fill={s.color} />;
            })}
          </g>
        );
      })}
    </svg>
  );
}

function clamp(v) {
  const n = Number(v);
  if (Number.isNaN(n)) return 0;
  return Math.max(0, Math.min(100, n));
}

function truncate(s, max) {
  return s && s.length > max ? s.slice(0, max - 1) + "…" : s;
}
