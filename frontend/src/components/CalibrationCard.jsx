import React, { useEffect, useState } from "react";
import { COLORS, FONT_DISPLAY, FONT_MONO } from "../design.js";
import { calibration as calibApi } from "../api.js";

/**
 * Roadmap 2 / PR #5 — Calibration card.
 *
 * Shown on the candidate Overview tab when there is a pending calibration
 * request. Tap → modal with the agent's response + 4 shuffled options +
 * optional free-text. Submitting bumps the profile-accuracy ring.
 */
export default function CalibrationCard({ onChanged }) {
  const [pending, setPending] = useState([]);
  const [open, setOpen] = useState(null); // calibration row being answered
  const [loading, setLoading] = useState(true);

  const reload = () => {
    setLoading(true);
    calibApi
      .list()
      .then((rows) => {
        setPending((rows || []).filter((r) => r.status === "pending"));
      })
      .catch(() => setPending([]))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    reload();
  }, []);

  if (loading || pending.length === 0) return null;

  return (
    <section
      className="card"
      style={{
        background: COLORS.cardBg,
        border: `1px solid ${COLORS.ink}`,
      }}
    >
      <div
        className="label-mono"
        style={{ color: COLORS.ink, marginBottom: 8 }}
      >
        Calibration · {pending.length} pending
      </div>
      <h3
        style={{
          fontFamily: FONT_DISPLAY,
          fontSize: 22,
          fontWeight: 500,
          letterSpacing: "-0.01em",
          margin: "0 0 8px",
        }}
      >
        Help us sharpen your profile
      </h3>
      <p style={{ color: COLORS.muted, fontSize: 14, lineHeight: 1.5, margin: "0 0 14px" }}>
        We simulated how you might respond in a scenario. Take 60 seconds to
        tell us how close we got — every answer lifts your accuracy ring.
      </p>
      <button
        onClick={() => setOpen(pending[0])}
        style={{
          background: COLORS.ink,
          color: "#fff",
          border: "none",
          padding: "10px 18px",
          fontSize: 14,
          fontWeight: 500,
          cursor: "pointer",
        }}
      >
        Calibrate now
      </button>
      {open && (
        <CalibrationDialog
          row={open}
          onClose={() => setOpen(null)}
          onSubmitted={() => {
            setOpen(null);
            reload();
            onChanged && onChanged();
          }}
        />
      )}
    </section>
  );
}


function CalibrationDialog({ row, onClose, onSubmitted }) {
  const [selection, setSelection] = useState(null);
  const [freeText, setFreeText] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  const isMcq = row.mode === "mcq_plus_text" && (row.mcq_options || []).length > 0;

  const submit = async () => {
    setError("");
    setSubmitting(true);
    try {
      await calibApi.submit(row.id, {
        selection_index: selection,
        free_text: freeText || null,
      });
      onSubmitted();
    } catch (e) {
      setError(e.message || "Failed to submit");
    } finally {
      setSubmitting(false);
    }
  };

  const canSubmit =
    !submitting && (selection !== null || (freeText && freeText.trim().length > 0));

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
          maxWidth: 640,
          width: "100%",
          maxHeight: "90vh",
          overflowY: "auto",
          padding: 28,
        }}
      >
        <div className="label-mono" style={{ marginBottom: 8 }}>
          Calibration · 1 of 1
        </div>
        <h2 style={{ fontFamily: FONT_DISPLAY, fontSize: 24, fontWeight: 500, margin: "0 0 14px" }}>
          {isMcq
            ? "Which of these sounds most like you?"
            : "How would you have handled this?"}
        </h2>

        <div
          style={{
            background: COLORS.paper,
            border: `1px solid ${COLORS.rule}`,
            padding: 14,
            marginBottom: 18,
            fontSize: 13,
            lineHeight: 1.55,
            color: COLORS.muted,
            fontStyle: "italic",
            maxHeight: 120,
            overflowY: "auto",
          }}
        >
          We won't show you the simulation's exact answer — that's the whole
          point. Pick the option closest to your real instinct, or write a
          better one below.
        </div>

        {isMcq && (
          <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 18 }}>
            {(row.mcq_options || []).map((opt, i) => (
              <label
                key={i}
                style={{
                  display: "flex",
                  gap: 10,
                  padding: 12,
                  border: `1px solid ${selection === i ? COLORS.ink : COLORS.rule}`,
                  background: selection === i ? COLORS.paper : "#fff",
                  cursor: "pointer",
                  fontSize: 14,
                  lineHeight: 1.5,
                }}
              >
                <input
                  type="radio"
                  name="calibration-option"
                  checked={selection === i}
                  onChange={() => setSelection(i)}
                  style={{ marginTop: 3 }}
                />
                <span>{opt.text}</span>
              </label>
            ))}
          </div>
        )}

        <label
          className="label-mono"
          style={{ display: "block", marginBottom: 6 }}
        >
          {isMcq ? "Or write your own (optional)" : "Your answer"}
        </label>
        <textarea
          value={freeText}
          onChange={(e) => setFreeText(e.target.value)}
          rows={isMcq ? 3 : 6}
          placeholder="In your own words…"
          style={{
            width: "100%",
            padding: 12,
            border: `1px solid ${COLORS.rule}`,
            fontFamily: "inherit",
            fontSize: 14,
            lineHeight: 1.5,
            resize: "vertical",
            marginBottom: 16,
          }}
        />

        {error && (
          <div style={{ color: COLORS.accent, fontSize: 13, marginBottom: 12 }}>
            {error}
          </div>
        )}

        <div style={{ display: "flex", gap: 10, justifyContent: "flex-end" }}>
          <button
            onClick={onClose}
            style={{
              background: "transparent",
              border: `1px solid ${COLORS.rule}`,
              padding: "10px 16px",
              fontSize: 14,
              cursor: "pointer",
            }}
          >
            Later
          </button>
          <button
            onClick={submit}
            disabled={!canSubmit}
            style={{
              background: canSubmit ? COLORS.ink : COLORS.rule,
              color: "#fff",
              border: "none",
              padding: "10px 18px",
              fontSize: 14,
              fontWeight: 500,
              cursor: canSubmit ? "pointer" : "not-allowed",
            }}
          >
            {submitting ? "Submitting…" : "Submit"}
          </button>
        </div>
      </div>
    </div>
  );
}
