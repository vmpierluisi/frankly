import React, { useMemo, useState } from "react";
import { COLORS, FONT_DISPLAY, FONT_MONO, candidateColor } from "../../design.js";
import RadarSVG from "./RadarSVG.jsx";
import FitLegend from "./FitLegend.jsx";

// Manager Shortlist V7 — Fit chart tab. Three sub-views (Role / Team / Overall)
// crossfading the radar. Role reveals fit against the role's criteria + skills;
// Team reveals who the candidate would clash with; Overall shows six composites.
const VIEWS = [
  { id: "role", label: "Role fit", headline: "Fit against the role.", lede: "Behavioral criteria and hard skills as axes." },
  { id: "team", label: "Team fit", headline: "Fit with the team.", lede: "Each synthetic teammate is an axis — see who they'd click with." },
  { id: "overall", label: "Overall", headline: "The whole picture.", lede: "Six composite axes across role, team, and tenure." },
];

export default function FitChart({ report, view = "role", onChangeView }) {
  const { candidates, position } = report;
  const [focusedId, setFocusedId] = useState(null);
  const [tip, setTip] = useState(null); // { label, body }

  const active = VIEWS.find((v) => v.id === view) || VIEWS[0];

  const { axes, seriesKey, tipFor } = useMemo(() => {
    if (view === "team") {
      return {
        axes: position.team.map((t) => ({ id: t.id, label: t.short })),
        seriesKey: "team_fit",
        tipFor: (axisId) => {
          const t = position.team.find((x) => x.id === axisId);
          return t ? { label: t.short, body: t.voice || t.role } : null;
        },
      };
    }
    if (view === "overall") {
      return {
        axes: position.overall_axes.map((a) => ({ id: a.id, label: a.label })),
        seriesKey: "overall_fit",
        tipFor: (axisId) => {
          const a = position.overall_axes.find((x) => x.id === axisId);
          return a ? { label: a.label, body: a.tip } : null;
        },
      };
    }
    // role
    const roleAxes = [
      ...position.criteria.map((c) => ({ id: c.id, label: c.label, why: c.why })),
      ...position.skills.map((s) => ({ id: s.id, label: s.label, why: s.reason })),
    ];
    return {
      axes: roleAxes,
      seriesKey: "role_fit",
      tipFor: (axisId) => {
        const a = roleAxes.find((x) => x.id === axisId);
        return a ? { label: a.label, body: a.why } : null;
      },
    };
  }, [view, position]);

  const series = candidates.map((c) => ({
    id: c.id,
    name: c.anchor_short || c.name,
    color: candidateColor(c.palette_color_var),
    values: c[seriesKey] || {},
  }));

  return (
    <div>
      {/* Sub-toggle */}
      <div style={{ display: "inline-flex", border: `1px solid ${COLORS.ink}`, marginBottom: 18 }}>
        {VIEWS.map((v, i) => {
          const on = v.id === view;
          return (
            <button
              key={v.id}
              type="button"
              aria-pressed={on}
              onClick={() => onChangeView(v.id)}
              style={{
                border: "none",
                borderRight: i < VIEWS.length - 1 ? `1px solid ${COLORS.ink}` : "none",
                background: on ? COLORS.ink : "transparent",
                color: on ? COLORS.paper : COLORS.ink,
                fontFamily: FONT_MONO,
                fontSize: 12,
                letterSpacing: "0.12em",
                textTransform: "uppercase",
                padding: "8px 16px",
                cursor: "pointer",
              }}
            >
              {v.label}
            </button>
          );
        })}
      </div>

      <h3 style={{ fontFamily: FONT_DISPLAY, fontSize: 26, fontWeight: 500, margin: "0 0 4px" }}>
        {active.headline}
      </h3>
      <p style={{ color: COLORS.muted, fontStyle: "italic", margin: "0 0 20px" }}>{active.lede}</p>

      <div style={{ display: "flex", gap: 32, alignItems: "flex-start", flexWrap: "wrap" }}>
        <div style={{ position: "relative", flex: "1 1 460px", minWidth: 320, transition: "opacity 0.22s" }}>
          <RadarSVG
            axes={axes}
            series={series}
            focusedId={focusedId}
            onSeriesHover={setFocusedId}
            onAxisHover={(ax) => setTip(ax ? tipFor(ax.id) : null)}
          />
          {tip && tip.body && (
            <div
              style={{
                position: "absolute",
                top: 8,
                left: 8,
                maxWidth: 240,
                background: COLORS.ink,
                color: COLORS.paper,
                padding: "8px 12px",
                fontSize: 12,
                lineHeight: 1.4,
              }}
            >
              <strong style={{ display: "block", fontFamily: FONT_MONO, fontSize: 10, letterSpacing: "0.1em", textTransform: "uppercase", marginBottom: 3 }}>
                {tip.label}
              </strong>
              {tip.body}
            </div>
          )}
        </div>

        <FitLegend
          candidates={candidates}
          focusedId={focusedId}
          onFocus={setFocusedId}
          team={view === "team" ? position.team : null}
        />
      </div>
    </div>
  );
}
