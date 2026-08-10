import React from "react";
import { COLORS, FONT_DISPLAY, FONT_MONO, candidateColor } from "../../design.js";

// Manager Shortlist V7 — dense comparison table.
// Row groups: I · Behavioral (criteria), Tell row, II · Hard skills.
// Every value cell is clickable → onCellAction(type, candidateId, rowId, rect).
export default function OverviewTable({ report, onCellAction }) {
  const { position, candidates } = report;
  const n = candidates.length;
  const gridTemplate = `220px repeat(${n}, minmax(180px, 1fr))`;

  return (
    <div style={{ overflowX: "auto", border: `1px solid ${COLORS.rule}`, background: "#fff" }}>
      <div style={{ minWidth: 220 + n * 180 }}>
        {/* Header — candidate names */}
        <Row template={gridTemplate}>
          <HeadCell />
          {candidates.map((c) => (
            <div
              key={c.id}
              style={{
                padding: "14px 16px",
                borderLeft: `1px solid ${COLORS.rule}`,
                borderBottom: `2px solid ${COLORS.ink}`,
              }}
            >
              <div
                style={{
                  fontFamily: FONT_DISPLAY,
                  fontSize: 18,
                  fontWeight: 500,
                  color: candidateColor(c.palette_color_var),
                }}
              >
                {c.anchor_short || c.name}
              </div>
              <div style={{ fontFamily: FONT_MONO, fontSize: 11, color: COLORS.muted }}>
                {c.score}/100 · {c.band}
              </div>
            </div>
          ))}
        </Row>

        <SectionBar template={gridTemplate} label="I · Behavioral" n={n} />
        {position.criteria.map((crit) => (
          <Row key={crit.id} template={gridTemplate}>
            <RowLabel label={crit.label} sub={crit.why} />
            {candidates.map((c) => (
              <ValueCell
                key={c.id}
                cell={c.overview[crit.id]}
                onClick={(rect) => onCellAction("behavior", c.id, crit.id, rect)}
              />
            ))}
          </Row>
        ))}

        {/* Tell row */}
        <Row template={gridTemplate} tinted>
          <RowLabel label="The tell" mono />
          {candidates.map((c) => (
            <div
              key={c.id}
              onClick={(e) =>
                onCellAction("tell", c.id, null, e.currentTarget.getBoundingClientRect())
              }
              style={{
                padding: "12px 16px",
                borderLeft: `1px solid ${COLORS.rule}`,
                fontStyle: "italic",
                fontSize: 14,
                color: COLORS.ink,
                cursor: "pointer",
              }}
            >
              {c.tell || "—"}
            </div>
          ))}
        </Row>

        {position.skills.length > 0 && (
          <>
            <SectionBar template={gridTemplate} label="II · Hard skills" n={n} />
            {position.skills.map((skill) => (
              <Row key={skill.id} template={gridTemplate}>
                <RowLabel label={skill.label} sub={skill.reason} />
                {candidates.map((c) => (
                  <SkillValueCell
                    key={c.id}
                    cell={c.skills[skill.id]}
                    onClick={(rect) => onCellAction("skill", c.id, skill.id, rect)}
                  />
                ))}
              </Row>
            ))}
          </>
        )}
      </div>
    </div>
  );
}

function Row({ template, children, tinted }) {
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: template,
        borderBottom: `1px solid ${COLORS.rule}`,
        background: tinted ? COLORS.accentSoft : "transparent",
      }}
    >
      {children}
    </div>
  );
}

function SectionBar({ template, label, n }) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: template }}>
      <div
        style={{
          gridColumn: `1 / span ${n + 1}`,
          background: COLORS.ink,
          color: COLORS.paper,
          fontFamily: FONT_MONO,
          fontSize: 11,
          letterSpacing: "0.18em",
          textTransform: "uppercase",
          padding: "8px 16px",
        }}
      >
        {label}
      </div>
    </div>
  );
}

function HeadCell() {
  return <div style={{ borderBottom: `2px solid ${COLORS.ink}` }} />;
}

function RowLabel({ label, sub, mono }) {
  return (
    <div style={{ padding: "12px 16px" }}>
      <div
        style={{
          fontFamily: mono ? FONT_MONO : FONT_DISPLAY,
          fontSize: mono ? 11 : 16,
          fontWeight: 500,
          letterSpacing: mono ? "0.16em" : "normal",
          textTransform: mono ? "uppercase" : "none",
        }}
      >
        {label}
      </div>
      {sub && <div style={{ fontSize: 12, color: COLORS.muted, marginTop: 2 }}>{sub}</div>}
    </div>
  );
}

function markerStyle(cell) {
  if (cell?.top) return { borderLeft: `3px solid ${COLORS.accent}` };
  if (cell?.weak) return { borderLeft: `3px solid ${COLORS.muted}`, opacity: 0.8 };
  return { borderLeft: `1px solid ${COLORS.rule}` };
}

function ValueCell({ cell, onClick }) {
  return (
    <div
      onClick={(e) => onClick(e.currentTarget.getBoundingClientRect())}
      style={{ padding: "12px 16px", cursor: "pointer", ...markerStyle(cell) }}
    >
      <div style={{ fontSize: 15, fontWeight: cell?.top ? 600 : 400 }}>
        {cell?.v || "—"}
        {cell?.top && <span title="Top of set" style={{ color: COLORS.accent }}> ▲</span>}
      </div>
      {cell?.d && (
        <div style={{ fontSize: 12, color: COLORS.muted, fontStyle: "italic", marginTop: 2 }}>
          {cell.d}
        </div>
      )}
    </div>
  );
}

function SkillValueCell({ cell, onClick }) {
  return (
    <div
      onClick={(e) => onClick(e.currentTarget.getBoundingClientRect())}
      style={{ padding: "12px 16px", cursor: "pointer", ...markerStyle(cell) }}
    >
      <div style={{ fontFamily: FONT_MONO, fontSize: 12, fontWeight: cell?.top ? 600 : 400 }}>
        {cell?.lev || "—"}
        {cell?.top && <span style={{ color: COLORS.accent }}> ▲</span>}
      </div>
      {cell?.src && (
        <div style={{ fontSize: 11, color: COLORS.muted, marginTop: 2 }}>{cell.src}</div>
      )}
    </div>
  );
}
