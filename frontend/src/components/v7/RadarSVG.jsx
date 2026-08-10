import React from "react";
import { COLORS, FONT_MONO } from "../../design.js";

// Manager Shortlist V7 — pure SVG radar primitive.
// Props:
//   axes:    [{ id, label }]                 — one spoke per axis
//   series:  [{ id, name, color, values }]   — values keyed by axis id (0..100)
//   size:    px (square plot area). focusedId dims the other series.
//   onAxisHover(axis | null), onSeriesHover(seriesId | null)
//
// The viewBox is padded well beyond the plot square so axis labels anchored to
// the left/right (start/end) have room and never clip at the edge.
const PAD_X = 104; // horizontal room for side labels
const PAD_Y = 52; // vertical room for top/bottom labels

export default function RadarSVG({
  axes,
  series,
  size = 480,
  focusedId = null,
  onAxisHover,
  onSeriesHover,
}) {
  const cx = size / 2;
  const cy = size / 2;
  const radius = size / 2 - 8; // labels live in the padding, so use nearly all of it
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
  const vbW = size + PAD_X * 2;
  const vbH = size + PAD_Y * 2;

  return (
    <svg
      viewBox={`${-PAD_X} ${-PAD_Y} ${vbW} ${vbH}`}
      width="100%"
      style={{ maxWidth: vbW, display: "block", margin: "0 auto" }}
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
        const [lx, ly] = point(i, radius + 20);
        const nearCenterX = Math.abs(lx - cx) < 8;
        const anchor = nearCenterX ? "middle" : lx > cx ? "start" : "end";
        const lines = wrapLabel(ax.label, 16);
        // Nudge multi-line labels up so they stay vertically centered on the spoke.
        const y0 = ly - ((lines.length - 1) * 11) / 2;
        return (
          <g key={ax.id}>
            <line x1={cx} y1={cy} x2={x} y2={y} stroke={COLORS.rule} strokeWidth={1} />
            <text
              x={lx}
              y={y0}
              textAnchor={anchor}
              dominantBaseline="middle"
              fontFamily={FONT_MONO}
              fontSize={11}
              fill={COLORS.muted}
              style={{ cursor: onAxisHover ? "pointer" : "default" }}
              onMouseEnter={() => onAxisHover?.(ax)}
              onMouseLeave={() => onAxisHover?.(null)}
            >
              {lines.map((ln, li) => (
                <tspan key={li} x={lx} dy={li === 0 ? 0 : 12}>
                  {ln}
                </tspan>
              ))}
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

// Wrap a label into at most two lines near `max` chars, breaking on a space.
// Falls back to a hard split when a single word is too long.
function wrapLabel(s, max) {
  const label = s || "";
  if (label.length <= max) return [label];
  const words = label.split(" ");
  if (words.length > 1) {
    const lines = ["", ""];
    let idx = 0;
    for (const w of words) {
      const candidate = lines[idx] ? `${lines[idx]} ${w}` : w;
      if (candidate.length > max && idx === 0) {
        idx = 1;
        lines[1] = w;
      } else {
        lines[idx] = candidate;
      }
    }
    return lines.filter(Boolean);
  }
  return [label.slice(0, max), label.slice(max)];
}
