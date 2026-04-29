import React, { useMemo, useState } from "react";
import { COLORS, FONT_DISPLAY, FONT_MONO } from "../design.js";
import { ScoreBar } from "./Widgets.jsx";
import FitReport from "./FitReport.jsx";
import FitProfileV2 from "./FitProfileV2.jsx";

function FitReportShell({ report, criteriaIndex, onOpenRollout }) {
  if (report?.version === "v2") {
    return <FitProfileV2 report={report} criteriaIndex={criteriaIndex} onOpenRollout={onOpenRollout} />;
  }
  return <FitReport report={report} criteriaIndex={criteriaIndex} />;
}

// Ranked candidates for a single position. Each row shows absolute fit (raw
// 0-100) and relative fit (rank in pool + percentile). Click expands the
// existing FitReport panel inline.

export default function SearchReport({ search, criteriaIndex }) {
  const [expandedId, setExpandedId] = useState(null);
  const results = search.results || [];

  const summary = useMemo(() => {
    const strong = results.filter((r) => r.overall_score >= 75).length;
    const top = results[0]?.overall_score ?? 0;
    return { strong, top };
  }, [results]);

  if (results.length === 0) {
    return (
      <div className="card">
        <p style={{ color: COLORS.muted, fontStyle: "italic", margin: 0 }}>
          No candidates in the pool yet — have someone go through /intake first.
        </p>
      </div>
    );
  }

  return (
    <div>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "baseline",
          marginBottom: 16,
          gap: 16,
          flexWrap: "wrap",
        }}
      >
        <div>
          <div className="label-mono" style={{ marginBottom: 4 }}>
            {search.company_name} · {search.role}
          </div>
          <div style={{ fontFamily: FONT_DISPLAY, fontSize: 22, fontWeight: 500 }}>
            {results.length} candidates scanned · {summary.strong} strong fit
            {summary.strong === 1 ? "" : "s"} · top score {summary.top}
          </div>
        </div>
      </div>

      <div style={{ borderTop: `2px solid ${COLORS.ink}` }}>
        {results.map((r, i) => {
          const expanded = expandedId === r.candidate_id;
          const percentile = results.length > 1
            ? Math.round(((results.length - i - 1) / (results.length - 1)) * 100)
            : 100;
          return (
            <div
              key={r.candidate_id}
              style={{ borderBottom: `1px solid ${COLORS.rule}` }}
            >
              <div
                onClick={() => setExpandedId(expanded ? null : r.candidate_id)}
                style={{
                  display: "grid",
                  gridTemplateColumns: "48px 120px 1fr 160px 160px 96px",
                  alignItems: "center",
                  gap: 16,
                  padding: "16px 8px",
                  cursor: "pointer",
                }}
              >
                <div
                  style={{
                    fontFamily: FONT_DISPLAY,
                    fontSize: 24,
                    fontWeight: 500,
                    color: COLORS.muted,
                  }}
                >
                  {i + 1}
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                  <div style={{ fontFamily: FONT_MONO, fontSize: 12, color: COLORS.muted }}>
                    {r.display_name
                      ? r.display_name.split(" ")[0]
                      : r.candidate_id.slice(0, 8)}
                  </div>
                  {r.is_seed && (
                    <div
                      style={{
                        fontFamily: FONT_MONO,
                        fontSize: 9,
                        letterSpacing: "0.1em",
                        textTransform: "uppercase",
                        color: COLORS.muted,
                        border: `1px solid ${COLORS.rule}`,
                        padding: "1px 5px",
                        width: "fit-content",
                      }}
                    >
                      seed
                    </div>
                  )}
                </div>
                <div
                  style={{
                    fontFamily: FONT_DISPLAY,
                    fontSize: 16,
                    fontStyle: "italic",
                    color: COLORS.ink,
                    lineHeight: 1.4,
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    display: "-webkit-box",
                    WebkitLineClamp: 2,
                    WebkitBoxOrient: "vertical",
                  }}
                >
                  {r.narrative || "(persona not synthesized)"}
                </div>
                <div>
                  <div className="label-mono" style={{ marginBottom: 4 }}>Absolute fit</div>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span
                      style={{
                        fontFamily: FONT_MONO,
                        fontSize: 16,
                        fontWeight: 500,
                        minWidth: 32,
                      }}
                    >
                      {r.overall_score}
                    </span>
                    <div style={{ flex: 1 }}>
                      <ScoreBar score={r.overall_score} />
                    </div>
                  </div>
                </div>
                <div>
                  <div className="label-mono" style={{ marginBottom: 4 }}>Relative fit</div>
                  <div style={{ fontFamily: FONT_MONO, fontSize: 13 }}>
                    {i + 1} / {results.length}
                    <span style={{ color: COLORS.muted, marginLeft: 6 }}>
                      ({percentile}th pct)
                    </span>
                  </div>
                </div>
                <div style={{ textAlign: "right" }}>
                  <span
                    style={{
                      fontFamily: FONT_MONO,
                      fontSize: 11,
                      letterSpacing: "0.12em",
                      textTransform: "uppercase",
                      padding: "4px 8px",
                      border: `1px solid ${
                        r.overall_score >= 75
                          ? COLORS.ink
                          : r.overall_score >= 60
                          ? COLORS.accent
                          : COLORS.muted
                      }`,
                      color:
                        r.overall_score >= 75
                          ? COLORS.ink
                          : r.overall_score >= 60
                          ? COLORS.accent
                          : COLORS.muted,
                    }}
                  >
                    {r.band}
                  </span>
                </div>
              </div>
              {expanded && (
                <div
                  style={{
                    background: "#fff",
                    padding: "32px 28px",
                    borderTop: `1px solid ${COLORS.rule}`,
                  }}
                >
                  <FitReportShell report={r.report} criteriaIndex={criteriaIndex} />
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
