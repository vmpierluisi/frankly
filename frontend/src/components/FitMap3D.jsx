import React, { useMemo, useRef, useState } from "react";
import { COLORS, FONT_DISPLAY, FONT_MONO } from "../design.js";
import { ScoreBar, formatCriterion } from "./Widgets.jsx";

// Placeholder 3D fit map — graph-neural-network style. Each candidate is a
// node positioned by abstract (role, culture, growth) fit axes; the vacancy
// sits at the (100,100,100) target. Drag to rotate. Click a node to see the
// decomposition and the "why" of the gap.
//
// The real 3D mapping will come from the mirofish adaptation; swap the
// coordinate source by changing `getNodePosition` below.

const VACANCY_POINT = { role: 100, culture: 100, growth: 100 };

// Axis labels are exported so the legend stays in sync with the projection.
const AXES = [
  { key: "role", label: "Role fit", color: COLORS.ink },
  { key: "culture", label: "Culture fit", color: COLORS.accent },
  { key: "growth", label: "Growth fit", color: COLORS.muted },
];

function getNodePosition(result) {
  // Single source of truth for candidate coordinates. Replace with mirofish
  // embedding output when it lands.
  return result.fit_axes;
}

function project(point, rotX, rotY, scale) {
  // Center on (50,50,50), normalize to [-1, 1], then rotate around Y then X,
  // and orthographically project to 2D. Returns {x, y, z} in screen space —
  // z is kept for painter's-algorithm sorting and depth shading.
  const nx = (point.role - 50) / 50;
  const ny = (point.culture - 50) / 50;
  const nz = (point.growth - 50) / 50;

  // rotate around Y axis
  const cosY = Math.cos(rotY);
  const sinY = Math.sin(rotY);
  const x1 = nx * cosY + nz * sinY;
  const y1 = ny;
  const z1 = -nx * sinY + nz * cosY;

  // rotate around X axis
  const cosX = Math.cos(rotX);
  const sinX = Math.sin(rotX);
  const x2 = x1;
  const y2 = y1 * cosX - z1 * sinX;
  const z2 = y1 * sinX + z1 * cosX;

  return { x: x2 * scale, y: -y2 * scale, z: z2 };
}

function diagnoseGap(result, criteriaIndex) {
  // Identify the worst axis, then the worst criterion within that axis's
  // bucket. The bucket logic mirrors the backend's project_fit_axes keywords.
  const axes = result.fit_axes;
  const worstAxis = AXES.reduce((acc, a) => (axes[a.key] < axes[acc.key] ? a : acc), AXES[0]);
  const scores = result.report?.criterionScores || {};
  const entries = Object.entries(scores).map(([key, val]) => {
    const meta = criteriaIndex?.[key];
    const haystack = `${key} ${meta?.label || ""}`.toLowerCase();
    let bucket = "role";
    if (/(culture|value|comm|collaborat|team|trust|feedback|dissent)/.test(haystack)) bucket = "culture";
    else if (/(growth|learn|ambition|curios|adapt|develop|potential|openness)/.test(haystack)) bucket = "growth";
    return { key, score: Number(val.score), justification: val.justification, bucket, label: meta?.label || formatCriterion(key) };
  });
  const inBucket = entries.filter((e) => e.bucket === worstAxis.key);
  const worstCriterion = (inBucket.length ? inBucket : entries).sort((a, b) => a.score - b.score)[0];
  if (!worstCriterion) return { worstAxis, line: "" };
  return {
    worstAxis,
    worstCriterion,
    line: `Persona doesn't match the ${worstAxis.label.toLowerCase()} — ${worstCriterion.label} score ${Math.round(worstCriterion.score)}: "${worstCriterion.justification}"`,
  };
}

export default function FitMap3D({ search, criteriaIndex }) {
  const [rotX, setRotX] = useState(-0.4);
  const [rotY, setRotY] = useState(0.6);
  const [selectedId, setSelectedId] = useState(null);
  const dragRef = useRef(null);

  const results = search.results || [];
  const W = 520;
  const H = 480;
  const scale = 140;
  const cx = W / 2;
  const cy = H / 2;

  const vacancy = useMemo(() => project(VACANCY_POINT, rotX, rotY, scale), [rotX, rotY]);
  const origin = useMemo(() => project({ role: 0, culture: 0, growth: 0 }, rotX, rotY, scale), [rotX, rotY]);

  const axisEnds = useMemo(
    () => ({
      role: project({ role: 110, culture: 0, growth: 0 }, rotX, rotY, scale),
      culture: project({ role: 0, culture: 110, growth: 0 }, rotX, rotY, scale),
      growth: project({ role: 0, culture: 0, growth: 110 }, rotX, rotY, scale),
    }),
    [rotX, rotY],
  );

  const nodes = useMemo(() => {
    return results
      .map((r) => ({ result: r, pos: project(getNodePosition(r), rotX, rotY, scale) }))
      .sort((a, b) => a.pos.z - b.pos.z); // back to front
  }, [results, rotX, rotY]);

  const selected = results.find((r) => r.candidate_id === selectedId) || null;
  const diag = selected ? diagnoseGap(selected, criteriaIndex) : null;

  function onPointerDown(e) {
    dragRef.current = { x: e.clientX, y: e.clientY, rotX, rotY };
    e.currentTarget.setPointerCapture(e.pointerId);
  }
  function onPointerMove(e) {
    const d = dragRef.current;
    if (!d) return;
    const dx = e.clientX - d.x;
    const dy = e.clientY - d.y;
    setRotY(d.rotY + dx * 0.008);
    setRotX(Math.max(-Math.PI / 2, Math.min(Math.PI / 2, d.rotX - dy * 0.008)));
  }
  function onPointerUp(e) {
    dragRef.current = null;
    e.currentTarget.releasePointerCapture?.(e.pointerId);
  }

  function nodeRadius(score) {
    return 5 + (score / 100) * 8;
  }
  function nodeColor(score) {
    if (score >= 75) return COLORS.ink;
    if (score >= 60) return COLORS.accent;
    if (score >= 45) return COLORS.muted;
    return COLORS.rule;
  }

  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 24, alignItems: "start" }}>
      {/* 3D canvas */}
      <div className="card" style={{ padding: 16 }}>
        <div className="label-mono" style={{ marginBottom: 8 }}>
          Fit space · drag to rotate · placeholder for mirofish output
        </div>
        <svg
          width={W}
          height={H}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerCancel={onPointerUp}
          style={{ touchAction: "none", cursor: "grab", userSelect: "none", display: "block" }}
        >
          {/* Axes */}
          {AXES.map((a) => (
            <g key={a.key}>
              <line
                x1={cx + origin.x}
                y1={cy + origin.y}
                x2={cx + axisEnds[a.key].x}
                y2={cy + axisEnds[a.key].y}
                stroke={COLORS.rule}
                strokeWidth={1}
              />
              <text
                x={cx + axisEnds[a.key].x}
                y={cy + axisEnds[a.key].y}
                fill={a.color}
                fontFamily={FONT_MONO}
                fontSize={10}
                style={{ letterSpacing: "0.12em", textTransform: "uppercase" }}
                dx={4}
                dy={-4}
              >
                {a.label}
              </text>
            </g>
          ))}

          {/* Edges from each candidate to the vacancy. Opacity = fit. */}
          {nodes.map(({ result, pos }) => {
            const op = Math.max(0.05, result.overall_score / 100);
            return (
              <line
                key={`edge-${result.candidate_id}`}
                x1={cx + pos.x}
                y1={cy + pos.y}
                x2={cx + vacancy.x}
                y2={cy + vacancy.y}
                stroke={COLORS.ink}
                strokeWidth={0.6}
                opacity={op * 0.4}
              />
            );
          })}

          {/* Candidate nodes */}
          {nodes.map(({ result, pos }) => {
            const r = nodeRadius(result.overall_score);
            const isSel = result.candidate_id === selectedId;
            const depthShade = 0.55 + 0.45 * ((pos.z + 1.7) / 3.4); // z range ~ [-1.7,1.7]
            return (
              <g
                key={result.candidate_id}
                onClick={(e) => {
                  e.stopPropagation();
                  setSelectedId(result.candidate_id);
                }}
                style={{ cursor: "pointer" }}
              >
                <circle
                  cx={cx + pos.x}
                  cy={cy + pos.y}
                  r={r}
                  fill={nodeColor(result.overall_score)}
                  opacity={Math.max(0.35, Math.min(1, depthShade))}
                  stroke={isSel ? COLORS.accent : "#fff"}
                  strokeWidth={isSel ? 3 : 1.5}
                />
                {isSel && (
                  <text
                    x={cx + pos.x + r + 4}
                    y={cy + pos.y + 4}
                    fontFamily={FONT_MONO}
                    fontSize={10}
                    fill={COLORS.ink}
                  >
                    {result.candidate_id.slice(0, 8)} · {result.overall_score}
                  </text>
                )}
              </g>
            );
          })}

          {/* Vacancy node — outlined square */}
          <g>
            <rect
              x={cx + vacancy.x - 9}
              y={cy + vacancy.y - 9}
              width={18}
              height={18}
              fill="#fff"
              stroke={COLORS.ink}
              strokeWidth={2}
            />
            <text
              x={cx + vacancy.x + 14}
              y={cy + vacancy.y + 4}
              fontFamily={FONT_MONO}
              fontSize={10}
              fill={COLORS.ink}
              style={{ letterSpacing: "0.12em", textTransform: "uppercase" }}
            >
              vacancy
            </text>
          </g>
        </svg>
        <div style={{ marginTop: 10, display: "flex", gap: 16, flexWrap: "wrap" }}>
          {AXES.map((a) => (
            <div key={a.key} style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <span
                style={{
                  display: "inline-block",
                  width: 10,
                  height: 2,
                  background: a.color,
                }}
              />
              <span className="label-mono">{a.label}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Decomposition panel */}
      <div className="card" style={{ minHeight: 480 }}>
        {!selected && (
          <div style={{ color: COLORS.muted, fontStyle: "italic" }}>
            Click a node to see the decomposition — which axis is the gap, which
            criterion drives it, and the matcher's own justification.
          </div>
        )}
        {selected && (
          <div>
            <div className="label-mono" style={{ marginBottom: 6 }}>
              Candidate · {selected.candidate_id.slice(0, 8)}
            </div>
            <div
              style={{
                fontFamily: FONT_DISPLAY,
                fontSize: 18,
                fontStyle: "italic",
                lineHeight: 1.45,
                marginBottom: 18,
              }}
            >
              {selected.narrative || "(persona not synthesized)"}
            </div>

            <div className="label-mono" style={{ marginBottom: 8 }}>Axis fit · target 100</div>
            {AXES.map((a) => (
              <div key={a.key} style={{ marginBottom: 10 }}>
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    fontSize: 13,
                    marginBottom: 4,
                  }}
                >
                  <span>{a.label}</span>
                  <span style={{ fontFamily: FONT_MONO }}>
                    {Math.round(selected.fit_axes[a.key])} / 100
                  </span>
                </div>
                <ScoreBar score={selected.fit_axes[a.key]} />
              </div>
            ))}

            {diag?.line && (
              <div
                style={{
                  marginTop: 18,
                  background: COLORS.accentSoft,
                  borderLeft: `3px solid ${COLORS.accent}`,
                  padding: "14px 18px",
                  fontStyle: "italic",
                  fontSize: 14,
                  lineHeight: 1.5,
                }}
              >
                {diag.line}
              </div>
            )}

            <div className="label-mono" style={{ margin: "20px 0 8px" }}>
              Per-criterion decomposition
            </div>
            {Object.entries(selected.report?.criterionScores || {}).map(([key, val]) => (
              <div key={key} style={{ padding: "10px 0", borderBottom: `1px solid ${COLORS.rule}` }}>
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    fontSize: 14,
                    marginBottom: 4,
                  }}
                >
                  <span>{criteriaIndex?.[key]?.label || formatCriterion(key)}</span>
                  <span style={{ fontFamily: FONT_MONO }}>{Math.round(val.score)}</span>
                </div>
                <ScoreBar score={val.score} />
                <div style={{ fontSize: 13, color: COLORS.muted, marginTop: 6, lineHeight: 1.5 }}>
                  {val.justification}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
