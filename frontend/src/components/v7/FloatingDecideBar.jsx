import React from "react";
import { COLORS, FONT_DISPLAY, FONT_MONO, candidateColor } from "../../design.js";

// Manager Shortlist V7 — sticky bottom decide bar.
// Left: heading + a compact pill per active candidate (× decline / ↗ invite).
// Right: primary "Invite shortlist →". Recovered-from-passed pills get an
// accent border. Hidden on the standalone Triage page (caller controls mount).
export default function FloatingDecideBar({
  activeCandidates,
  onDecline,
  onInvite,
  onInviteAll,
  busyId,
}) {
  if (!activeCandidates || activeCandidates.length === 0) return null;
  return (
    <div
      style={{
        position: "fixed",
        left: 0,
        right: 0,
        bottom: 0,
        zIndex: 900,
        background: "rgba(247,243,236,0.86)",
        backdropFilter: "blur(8px)",
        WebkitBackdropFilter: "blur(8px)",
        borderTop: `2px solid ${COLORS.ink}`,
        padding: "14px 32px",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: 24,
        flexWrap: "wrap",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap" }}>
        <span
          className="label-mono"
          style={{ fontFamily: FONT_MONO, fontSize: 11, letterSpacing: "0.16em" }}
        >
          Decide
        </span>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          {activeCandidates.map((c) => (
            <div
              key={c.id}
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 8,
                border:
                  c.triage_decision === "pass"
                    ? `1px solid ${COLORS.accent}`
                    : `1px solid ${COLORS.rule}`,
                background: "#fff",
                padding: "4px 6px 4px 10px",
              }}
            >
              <span
                aria-hidden
                style={{
                  width: 8,
                  height: 8,
                  borderRadius: "50%",
                  background: candidateColor(c.palette_color_var),
                }}
              />
              <span style={{ fontFamily: FONT_DISPLAY, fontSize: 15 }}>
                {c.anchor_short || c.name}
              </span>
              <button
                type="button"
                aria-label={`Decline ${c.anchor_short || c.name}`}
                onClick={() => onDecline(c)}
                disabled={busyId === c.id}
                style={pillBtn}
              >
                ×
              </button>
              <button
                type="button"
                aria-label={`Invite ${c.anchor_short || c.name}`}
                onClick={() => onInvite(c)}
                disabled={busyId === c.id}
                style={{ ...pillBtn, color: COLORS.accent }}
              >
                ↗
              </button>
            </div>
          ))}
        </div>
      </div>

      <button
        className="primary"
        onClick={onInviteAll}
        style={{ whiteSpace: "nowrap" }}
      >
        Invite shortlist →
      </button>
    </div>
  );
}

const pillBtn = {
  border: "none",
  background: "transparent",
  cursor: "pointer",
  fontSize: 15,
  lineHeight: 1,
  padding: "2px 4px",
  color: COLORS.ink,
};
