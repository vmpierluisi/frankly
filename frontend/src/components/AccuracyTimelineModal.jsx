import React, { useEffect, useState } from "react";
import { COLORS, FONT_DISPLAY } from "../design.js";
import { calibration as calibApi } from "../api.js";

/**
 * Roadmap 2 / PR #5 — Profile-accuracy timeline.
 *
 * Tap the "How well we know you" ring → this modal pops up showing how
 * the number sharpened over weeks: one row per submitted calibration,
 * with the before/after deltas. Single number on top; provenance below.
 */
export default function AccuracyTimelineModal({ open, onClose, displayedAccuracy = 0 }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!open) return;
    setData(null);
    setError("");
    calibApi
      .timeline()
      .then(setData)
      .catch((e) => setError(e.message || "Failed to load timeline"));
  }, [open]);

  if (!open) return null;

  const points = data?.points || [];

  return (
    <div
      onClick={onClose}
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(20,20,20,0.45)",
        zIndex: 1000,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 16,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: "#fff",
          border: `1px solid ${COLORS.rule}`,
          maxWidth: 560,
          width: "100%",
          maxHeight: "85vh",
          overflowY: "auto",
          padding: 28,
        }}
      >
        <div className="label-mono" style={{ marginBottom: 8 }}>
          Profile accuracy · history
        </div>
        <h2
          style={{
            fontFamily: FONT_DISPLAY,
            fontSize: 36,
            fontWeight: 500,
            margin: "0 0 10px",
            letterSpacing: "-0.015em",
          }}
        >
          {Math.max(displayedAccuracy, data?.current_accuracy ?? 0)}%
        </h2>
        <p style={{ color: COLORS.muted, fontSize: 14, lineHeight: 1.5, margin: "0 0 22px" }}>
          A single number that grows with every calibration. Below is how
          it sharpened over time.
        </p>

        {error && (
          <div style={{ color: COLORS.accent, fontSize: 13, marginBottom: 14 }}>
            {error}
          </div>
        )}

        {points.length === 0 ? (
          <div
            style={{
              padding: 14,
              border: `1px solid ${COLORS.rule}`,
              background: COLORS.paper,
              color: COLORS.muted,
              fontSize: 13,
              lineHeight: 1.55,
            }}
          >
            No calibrations submitted yet. After your next simulated match
            we may invite you to calibrate — each submission lifts this
            ring.
          </div>
        ) : (
          <ol
            style={{
              listStyle: "none",
              padding: 0,
              margin: 0,
              display: "flex",
              flexDirection: "column",
              gap: 12,
            }}
          >
            {points.map((p, i) => {
              const delta = (p.accuracy_after ?? 0) - (p.accuracy_before ?? 0);
              const when = p.submitted_at
                ? new Date(p.submitted_at).toLocaleDateString()
                : "";
              return (
                <li
                  key={p.calibration_id || i}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 14,
                    padding: 12,
                    border: `1px solid ${COLORS.rule}`,
                    background: COLORS.cardBg,
                  }}
                >
                  <div
                    style={{
                      fontFamily: FONT_DISPLAY,
                      fontSize: 22,
                      fontWeight: 500,
                      minWidth: 72,
                    }}
                  >
                    {p.accuracy_after ?? "—"}%
                  </div>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: 13, color: COLORS.ink }}>
                      Calibration · {when || "recent"}
                    </div>
                    <div style={{ fontSize: 12, color: COLORS.muted, marginTop: 2 }}>
                      {delta > 0 ? `+${delta} pts` : `${delta} pts`}
                      {p.divergence !== null && p.divergence !== undefined
                        ? ` · divergence ${p.divergence.toFixed(2)}`
                        : ""}
                    </div>
                  </div>
                </li>
              );
            })}
          </ol>
        )}

        <div style={{ marginTop: 22, display: "flex", justifyContent: "flex-end" }}>
          <button
            onClick={onClose}
            style={{
              background: "transparent",
              border: `1px solid ${COLORS.rule}`,
              padding: "8px 16px",
              fontSize: 14,
              cursor: "pointer",
            }}
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
