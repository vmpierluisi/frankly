import React from "react";
import { Link } from "react-router-dom";
import { COLORS, FONT_DISPLAY, FONT_MONO } from "../design.js";

/**
 * Roadmap 2 / PR #6 follow-up — shared audit chart primitives.
 *
 * Originally lived inside ReliabilityAuditPanel.jsx. Lifted into their own
 * module so the new Audit tab (single-position + all/open/closed scopes)
 * and the legacy per-position page can both render off the same set of
 * primitives without divergence.
 *
 * No charting deps — inline SVG and CSS-based bars only.
 */

// ===========================================================================
// Reliability section
// ===========================================================================
export function ReliabilitySection({ data }) {
  const r = data.scatter.pearson;
  let bandNote = "healthy";
  let bandTone = "good";
  if (r < 0.4) {
    bandNote = "below band · low signal";
    bandTone = "warn";
  } else if (r > 0.7) {
    bandNote = "above band · sim mirrors baseline";
    bandTone = "muted";
  }
  return (
    <section style={{ display: "flex", flexDirection: "column", gap: 22 }}>
      <Kpi
        items={[
          { label: "Matches", value: data.n_matches },
          { label: "Rollouts", value: data.n_rollouts },
          {
            label: "Baseline ⇄ sim r",
            value: r,
            note: bandNote,
            tone: bandTone,
          },
          {
            label: "Mean fidelity",
            value: data.fidelity.mean ?? "—",
            note: data.fidelity.low_count
              ? `${data.fidelity.low_count} low`
              : "all clear",
          },
        ]}
      />

      <Card title="Baseline ↔ simulation scatter">
        <Scatter scatter={data.scatter} />
      </Card>

      <Card title="|Δ| histogram (|sim − baseline|)">
        <Histogram bins={data.delta_histogram} />
      </Card>

      <Card title="Per-criterion judge agreement">
        <Table
          rows={data.criteria}
          columns={[
            { key: "key", label: "Criterion" },
            { key: "n", label: "N" },
            { key: "mean_agreement", label: "Mean agreement" },
            {
              key: "flag_low",
              label: "",
              render: (v) =>
                v ? (
                  <Pill tone="warn">rubric ambiguity</Pill>
                ) : (
                  <Pill tone="muted">ok</Pill>
                ),
            },
          ]}
          empty="No criterion scores yet."
        />
      </Card>

      <Card title="σ across rollouts (per scenario)">
        <Table
          rows={data.scenarios}
          columns={[
            {
              key: "scenario_name",
              label: "Scenario",
              render: (_, row) => <ScenarioLink row={row} />,
            },
            { key: "n", label: "N" },
            { key: "sigma", label: "σ" },
            {
              key: "flag_high",
              label: "",
              render: (v) =>
                v ? (
                  <Pill tone="warn">prompt looseness</Pill>
                ) : (
                  <Pill tone="muted">stable</Pill>
                ),
            },
          ]}
          empty="No scenario-scoped scores yet."
        />
      </Card>

      <Card title="Persona fidelity distribution">
        <Histogram bins={data.fidelity.histogram} maxLabel="fidelity" />
        <div style={{ marginTop: 10, fontSize: 13, color: COLORS.muted }}>
          Retry rate: {data.fidelity.retry_rate ?? "—"}
        </div>
      </Card>

      <Card title="By prompt version">
        <Table
          rows={data.by_prompt_version}
          columns={[
            { key: "prompt_version", label: "Prompt" },
            { key: "rollouts", label: "Rollouts" },
            { key: "fidelity_mean", label: "Fidelity μ" },
            { key: "delta_mean", label: "|Δ| μ" },
          ]}
          empty="Only one prompt version seen so far."
        />
      </Card>
    </section>
  );
}


// ===========================================================================
// Fairness section
// ===========================================================================
export function FairnessSection({ data }) {
  return (
    <section style={{ marginTop: 24, display: "flex", flexDirection: "column", gap: 22 }}>
      <h2
        style={{
          fontFamily: FONT_DISPLAY,
          fontSize: 26,
          fontWeight: 500,
          margin: 0,
          letterSpacing: "-0.01em",
        }}
      >
        Fairness
      </h2>
      <p style={{ color: COLORS.muted, fontSize: 14, margin: 0 }}>
        Distributions across <em>self-reported, opt-in</em> demographics.
        Never inferred. Disparate-impact flagged when {"<"} 0.8 (four-fifths rule).
      </p>

      {(data.dimensions || []).map((dim) => (
        <Card key={dim.dimension} title={`Score distribution · ${dim.dimension}`}>
          <Bars groups={dim.groups} />
          <div style={{ marginTop: 10, display: "flex", gap: 14, fontSize: 13 }}>
            <span>
              <strong>Parity gap:</strong>{" "}
              {dim.parity_gap !== null ? dim.parity_gap : "—"}
            </span>
            <span>
              <strong>Disparate impact:</strong>{" "}
              {dim.disparate_impact !== null ? dim.disparate_impact : "—"}{" "}
              {dim.flag_disparate_impact && <Pill tone="warn">flag</Pill>}
            </span>
          </div>
        </Card>
      ))}
    </section>
  );
}


// ===========================================================================
// Primitives
// ===========================================================================
export function Card({ title, children }) {
  return (
    <section className="card">
      <div className="label-mono" style={{ marginBottom: 10 }}>
        {title}
      </div>
      {children}
    </section>
  );
}

export function Kpi({ items }) {
  return (
    <section
      className="card"
      style={{ display: "flex", gap: 24, flexWrap: "wrap" }}
    >
      {items.map((it, i) => (
        <div key={i} style={{ minWidth: 140 }}>
          <div
            className="label-mono"
            style={{ fontSize: 10, color: COLORS.muted, marginBottom: 4 }}
          >
            {it.label}
          </div>
          <div style={{ fontFamily: FONT_DISPLAY, fontSize: 26, fontWeight: 500 }}>
            {it.value}
          </div>
          {it.note && (
            <div
              style={{
                fontSize: 11,
                color: it.tone === "warn" ? COLORS.accent : COLORS.muted,
                marginTop: 2,
              }}
            >
              {it.note}
            </div>
          )}
        </div>
      ))}
    </section>
  );
}

export function Table({ rows, columns, empty }) {
  if (!rows || rows.length === 0) {
    return <Empty>{empty || "No data."}</Empty>;
  }
  return (
    <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
      <thead>
        <tr>
          {columns.map((c) => (
            <th
              key={c.key}
              style={{
                textAlign: "left",
                padding: "6px 8px",
                borderBottom: `1px solid ${COLORS.rule}`,
                fontFamily: FONT_MONO,
                fontSize: 10,
                letterSpacing: "0.12em",
                textTransform: "uppercase",
                color: COLORS.muted,
                fontWeight: 500,
              }}
            >
              {c.label}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={i}>
            {columns.map((c) => (
              <td
                key={c.key}
                style={{
                  padding: "8px 8px",
                  borderBottom: `1px solid ${COLORS.rule}`,
                }}
              >
                {c.render ? c.render(r[c.key], r) : r[c.key] ?? "—"}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function Pill({ children, tone }) {
  const colors =
    tone === "warn"
      ? { bg: COLORS.accent, fg: "#fff" }
      : tone === "good"
      ? { bg: COLORS.ink, fg: "#fff" }
      : { bg: "transparent", fg: COLORS.muted };
  return (
    <span
      style={{
        display: "inline-block",
        padding: "2px 8px",
        background: colors.bg,
        color: colors.fg,
        border: `1px solid ${tone === "muted" ? COLORS.rule : "transparent"}`,
        fontFamily: FONT_MONO,
        fontSize: 10,
        letterSpacing: "0.1em",
        textTransform: "uppercase",
      }}
    >
      {children}
    </span>
  );
}

export function Empty({ children }) {
  return (
    <div
      style={{
        padding: 14,
        background: COLORS.paper,
        border: `1px solid ${COLORS.rule}`,
        color: COLORS.muted,
        fontSize: 13,
      }}
    >
      {children}
    </div>
  );
}


function ScenarioLink({ row }) {
  const name = row.scenario_name || row.scenario_id || "—";
  const positionId = row.position_id;
  const scenarioId = row.scenario_id;
  if (!positionId) {
    return <span>{name}</span>;
  }
  return (
    <Link
      to={`/manager/positions/${positionId}/scenarios${scenarioId ? `#${scenarioId}` : ""}`}
      style={{ color: COLORS.ink, textDecoration: "underline" }}
    >
      {name}
    </Link>
  );
}


// ===========================================================================
// Inline SVG charts
// ===========================================================================
export function Scatter({ scatter }) {
  const W = 480;
  const H = 280;
  const PAD = 28;
  const points = scatter?.points || [];
  if (points.length === 0) {
    return <Empty>No baseline-vs-sim pairs yet.</Empty>;
  }
  const xMin = 0,
    xMax = 100,
    yMin = 0,
    yMax = 100;
  const sx = (v) => PAD + ((v - xMin) / (xMax - xMin)) * (W - 2 * PAD);
  const sy = (v) => H - PAD - ((v - yMin) / (yMax - yMin)) * (H - 2 * PAD);
  const a = scatter.regression?.slope ?? 0;
  const b = scatter.regression?.intercept ?? 0;
  return (
    <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`}>
      <line x1={PAD} y1={H - PAD} x2={W - PAD} y2={H - PAD} stroke={COLORS.rule} />
      <line x1={PAD} y1={PAD} x2={PAD} y2={H - PAD} stroke={COLORS.rule} />
      <line
        x1={sx(0)}
        y1={sy(0)}
        x2={sx(100)}
        y2={sy(100)}
        stroke={COLORS.rule}
        strokeDasharray="4 4"
      />
      <line
        x1={sx(0)}
        y1={sy(b)}
        x2={sx(100)}
        y2={sy(a * 100 + b)}
        stroke={COLORS.ink}
        strokeWidth={1.5}
      />
      {points.map((p, i) => (
        <circle
          key={i}
          cx={sx(p.baseline)}
          cy={sy(p.sim)}
          r={4}
          fill={COLORS.ink}
          fillOpacity={0.7}
        />
      ))}
      <text
        x={W - PAD}
        y={H - 8}
        textAnchor="end"
        style={{ fontFamily: FONT_MONO, fontSize: 10, fill: COLORS.muted }}
      >
        baseline →
      </text>
      <text
        x={6}
        y={PAD}
        style={{ fontFamily: FONT_MONO, fontSize: 10, fill: COLORS.muted }}
      >
        sim ↑
      </text>
    </svg>
  );
}

export function Histogram({ bins, maxLabel = "Δ" }) {
  if (!bins || bins.length === 0) return <Empty>No data yet.</Empty>;
  const max = Math.max(1, ...bins.map((b) => b.count));
  const W = 480;
  const H = 180;
  const PAD = 26;
  const bw = (W - 2 * PAD) / bins.length;
  return (
    <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`}>
      <line x1={PAD} y1={H - PAD} x2={W - PAD} y2={H - PAD} stroke={COLORS.rule} />
      {bins.map((b, i) => {
        const h = ((b.count / max) * (H - 2 * PAD)) | 0;
        const x = PAD + i * bw + 4;
        const y = H - PAD - h;
        return (
          <g key={i}>
            <rect x={x} y={y} width={bw - 8} height={h} fill={COLORS.ink} fillOpacity={0.78} />
            <text
              x={x + (bw - 8) / 2}
              y={H - PAD + 12}
              textAnchor="middle"
              style={{ fontFamily: FONT_MONO, fontSize: 9, fill: COLORS.muted }}
            >
              {b.lo}-{b.hi}
            </text>
            <text
              x={x + (bw - 8) / 2}
              y={y - 4}
              textAnchor="middle"
              style={{ fontFamily: FONT_MONO, fontSize: 10, fill: COLORS.ink }}
            >
              {b.count || ""}
            </text>
          </g>
        );
      })}
      <text
        x={W - PAD}
        y={H - 6}
        textAnchor="end"
        style={{ fontFamily: FONT_MONO, fontSize: 10, fill: COLORS.muted }}
      >
        {maxLabel}
      </text>
    </svg>
  );
}

export function Bars({ groups }) {
  if (!groups || groups.length === 0) return <Empty>No data yet.</Empty>;
  const max = Math.max(1, ...groups.map((g) => g.mean_score ?? 0));
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      {groups.map((g, i) => {
        const pct = g.mean_score ? Math.round((g.mean_score / max) * 100) : 0;
        return (
          <div
            key={i}
            style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13 }}
          >
            <div style={{ minWidth: 130, color: COLORS.muted }}>{g.label}</div>
            <div
              style={{
                flex: 1,
                background: COLORS.paper,
                border: `1px solid ${COLORS.rule}`,
                height: 22,
                position: "relative",
              }}
            >
              <div
                style={{
                  background: COLORS.ink,
                  width: `${pct}%`,
                  height: "100%",
                  opacity: 0.78,
                }}
              />
            </div>
            <div
              style={{
                minWidth: 90,
                textAlign: "right",
                fontFamily: FONT_MONO,
                fontSize: 12,
              }}
            >
              {g.mean_score ?? "—"} · n={g.n}
            </div>
          </div>
        );
      })}
    </div>
  );
}
