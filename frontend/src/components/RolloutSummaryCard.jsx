import React from "react";
import { COLORS, FONT_DISPLAY, FONT_MONO } from "../design.js";

function scoreTick(score) {
  if (score == null) return COLORS.muted;
  if (score >= 70) return "#4a7c59";
  if (score >= 50) return COLORS.accent;
  return COLORS.muted;
}

/**
 * Roadmap 2 / PR #3 — Rollout card with optional highlight reel.
 *
 * When the backend attaches a ``highlight_reel`` to the rollout's
 * ``final_state``, the card promotes the auto-generated one-liner +
 * summary as the headline. Falls back to the judge's ``transcript_summary``
 * for legacy rollouts produced before PR #3 shipped.
 */
export default function RolloutSummaryCard({ summary, onClick }) {
  const {
    rolloutId,
    scenarioTitle,
    kIndex,
    headline,
    highlightReel,
    scores = {},
  } = summary;
  const scoreEntries = Object.entries(scores);

  const oneLiner = highlightReel?.one_liner?.trim();
  const reelBody = highlightReel?.summary?.trim();
  const fallbackBody = headline?.trim();
  const body = reelBody || fallbackBody || "";
  const isAutoHighlight = !!reelBody;

  return (
    <div
      className="card"
      onClick={() => onClick(rolloutId)}
      style={{
        cursor: "pointer",
        minWidth: 240,
        maxWidth: 320,
        flex: "0 0 auto",
        transition: "box-shadow 0.15s",
        display: "flex",
        flexDirection: "column",
      }}
      onMouseEnter={(e) =>
        (e.currentTarget.style.boxShadow = "0 4px 16px rgba(0,0,0,0.10)")
      }
      onMouseLeave={(e) => (e.currentTarget.style.boxShadow = "none")}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: 8,
        }}
      >
        <span className="label-mono">
          Rollout #{kIndex}
          {scenarioTitle ? ` · ${scenarioTitle}` : ""}
        </span>
        {isAutoHighlight && (
          <span
            style={{
              fontFamily: FONT_MONO,
              fontSize: 9,
              letterSpacing: "0.12em",
              textTransform: "uppercase",
              padding: "2px 6px",
              border: `1px solid ${COLORS.rule}`,
              color: COLORS.muted,
            }}
            title="Auto-generated highlight reel"
          >
            highlight
          </span>
        )}
      </div>

      {oneLiner && (
        <div
          style={{
            fontFamily: FONT_DISPLAY,
            fontSize: 17,
            fontWeight: 500,
            lineHeight: 1.35,
            marginBottom: 8,
            color: COLORS.ink,
          }}
        >
          {oneLiner}
        </div>
      )}

      {body ? (
        <div
          style={{
            fontFamily: FONT_DISPLAY,
            fontSize: 14,
            fontStyle: isAutoHighlight ? "normal" : "italic",
            color: isAutoHighlight ? COLORS.ink : COLORS.muted,
            lineHeight: 1.45,
            marginBottom: 12,
            minHeight: 56,
          }}
        >
          {body.length > 220 ? body.slice(0, 217) + "…" : body}
        </div>
      ) : (
        <div style={{ minHeight: 56, marginBottom: 12 }} />
      )}

      {scoreEntries.length > 0 && (
        <div
          style={{
            display: "flex",
            gap: 6,
            flexWrap: "wrap",
            marginTop: "auto",
          }}
        >
          {scoreEntries.map(([key, score]) => (
            <div key={key} style={{ display: "flex", alignItems: "center", gap: 4 }}>
              <div
                style={{
                  width: 8,
                  height: 8,
                  borderRadius: "50%",
                  background: scoreTick(score),
                }}
              />
              <span
                style={{ fontFamily: FONT_MONO, fontSize: 10, color: COLORS.muted }}
              >
                {Math.round(score)}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
