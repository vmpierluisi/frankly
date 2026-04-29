import React from "react";
import { COLORS, FONT_DISPLAY, FONT_MONO } from "../design.js";

export default function TranscriptTurn({ turn, isHighlighted, showIntents }) {
  const isCandidate = turn.speakerRole === "candidate" || turn.speaker_id === "candidate";

  return (
    <div
      style={{
        padding: "18px 20px",
        background: isHighlighted ? COLORS.accentSoft : "transparent",
        borderLeft: isHighlighted ? `3px solid ${COLORS.accent}` : "3px solid transparent",
        transition: "background 0.15s, border-color 0.15s",
        marginBottom: 2,
      }}
    >
      <div style={{ display: "flex", alignItems: "baseline", gap: 10, marginBottom: 6 }}>
        <span
          style={{
            fontFamily: FONT_MONO,
            fontSize: 10,
            letterSpacing: "0.15em",
            textTransform: "uppercase",
            color: isCandidate ? COLORS.accent : COLORS.ink,
            border: `1px solid ${isCandidate ? COLORS.accent : COLORS.rule}`,
            padding: "2px 6px",
            flexShrink: 0,
          }}
        >
          {turn.speaker_name || turn.speaker}
        </span>
        <span className="label-mono" style={{ color: COLORS.muted }}>#{turn.turn ?? turn.index}</span>
        {isHighlighted && (
          <span className="label-mono" style={{ color: COLORS.accent }}>evidence</span>
        )}
      </div>

      <div style={{ fontSize: 16, lineHeight: 1.6, fontFamily: FONT_DISPLAY }}>
        {turn.content || turn.utterance}
      </div>

      {(showIntents || isHighlighted) && (turn.intent || turn.internal_state || turn.internalState) && (
        <div style={{ marginTop: 8, display: "flex", gap: 16, flexWrap: "wrap" }}>
          {(turn.intent) && (
            <span style={{ fontFamily: FONT_MONO, fontSize: 11, color: COLORS.muted }}>
              intent: {turn.intent}
            </span>
          )}
          {(turn.internal_state || turn.internalState) && (
            <span style={{ fontFamily: FONT_MONO, fontSize: 11, color: COLORS.muted }}>
              state: {turn.internal_state || turn.internalState}
            </span>
          )}
        </div>
      )}
    </div>
  );
}
