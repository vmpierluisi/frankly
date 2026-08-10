import React from "react";
import { COLORS, FONT_MONO, candidateColor } from "../../design.js";

// Manager Shortlist V7 — comparison chips.
//   * "In comparison" — active set. Removable via × (min 1 stays).
//   * "Also considered · click to add" — the ranked remainder; click to add.
// Triage-passed candidates carry a small × glyph in their label (history) but
// remain toggleable (triage isn't binding).
export default function ChipBar({ activeCandidates, availableCandidates, onAdd, onRemove }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10, margin: "18px 0" }}>
      <ChipGroup label="In comparison">
        {activeCandidates.map((c) => (
          <Chip
            key={c.id}
            candidate={c}
            solid
            onClick={activeCandidates.length > 1 ? () => onRemove(c.id) : undefined}
            trailing={activeCandidates.length > 1 ? "×" : null}
            ariaLabel={`Remove ${c.anchor_short || c.name} from comparison`}
          />
        ))}
      </ChipGroup>

      {availableCandidates.length > 0 && (
        <ChipGroup label="Also considered · click to add">
          {availableCandidates.map((c) => (
            <Chip
              key={c.id}
              candidate={c}
              dashed
              onClick={() => onAdd(c.id)}
              passed={c.triage_decision === "pass"}
              ariaLabel={`Add ${c.anchor_short || c.name} to comparison`}
            />
          ))}
        </ChipGroup>
      )}
    </div>
  );
}

function ChipGroup({ label, children }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
      <span
        className="label-mono"
        style={{ fontFamily: FONT_MONO, fontSize: 10, letterSpacing: "0.16em", flexShrink: 0 }}
      >
        {label}
      </span>
      {children}
    </div>
  );
}

function Chip({ candidate, solid, dashed, passed, onClick, trailing, ariaLabel }) {
  const color = candidateColor(candidate.palette_color_var);
  const interactive = Boolean(onClick);
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={ariaLabel}
      disabled={!interactive}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        border: dashed ? `1px dashed ${COLORS.muted}` : `1px solid ${color}`,
        background: solid ? color : "transparent",
        color: solid ? "#fff" : COLORS.ink,
        fontFamily: FONT_MONO,
        fontSize: 11,
        letterSpacing: "0.06em",
        padding: "5px 10px",
        cursor: interactive ? "pointer" : "default",
        opacity: dashed && !passed ? 0.85 : 1,
      }}
    >
      {!solid && (
        <span
          aria-hidden
          style={{ width: 8, height: 8, borderRadius: "50%", background: color, display: "inline-block" }}
        />
      )}
      <span>{candidate.anchor_short || candidate.name}</span>
      {passed && <span aria-hidden title="Passed in triage" style={{ opacity: 0.7 }}>✕</span>}
      {trailing && <span aria-hidden style={{ marginLeft: 2, fontWeight: 600 }}>{trailing}</span>}
    </button>
  );
}
