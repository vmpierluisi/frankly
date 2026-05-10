import React, { useState } from "react";
import { COLORS, FONT_DISPLAY, FONT_MONO } from "../design.js";
import { interviews as interviewsApi } from "../api.js";

/**
 * Roadmap 2 / PR #4 — recruiter slot picker.
 *
 * Three required slots (datetime-local). Submits via POST /interviews
 * which fires both an in-app notification and a Resend email to the
 * candidate.
 */
export default function ScheduleInterviewModal({ matchId, candidateName, onClose, onSubmitted }) {
  const [slots, setSlots] = useState(["", "", ""]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  function setSlot(i, value) {
    setSlots((prev) => prev.map((s, idx) => (idx === i ? value : s)));
  }

  function addSlot() {
    if (slots.length >= 5) return;
    setSlots((prev) => [...prev, ""]);
  }

  function removeSlot(i) {
    if (slots.length <= 1) return;
    setSlots((prev) => prev.filter((_, idx) => idx !== i));
  }

  async function submit() {
    const cleaned = slots
      .map((s) => s.trim())
      .filter(Boolean)
      // datetime-local returns "YYYY-MM-DDTHH:mm"; convert to ISO with the
      // browser's local timezone offset so the recipient sees the recruiter's
      // intended wall-clock moment.
      .map((s) => new Date(s).toISOString());
    if (cleaned.length === 0) {
      setError("Add at least one time slot.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await interviewsApi.propose(matchId, cleaned);
      if (onSubmitted) onSubmitted();
      onClose();
    } catch (e) {
      setError(e.message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(26,24,20,0.45)",
        zIndex: 100,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 24,
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        className="card"
        style={{
          background: COLORS.cardBg,
          padding: 32,
          maxWidth: 520,
          width: "100%",
        }}
      >
        <div className="label-mono" style={{ marginBottom: 8 }}>
          Schedule interview
        </div>
        <h2
          style={{
            fontFamily: FONT_DISPLAY,
            fontSize: 30,
            fontWeight: 500,
            margin: "0 0 8px",
            letterSpacing: "-0.01em",
          }}
        >
          Propose times{candidateName ? ` to ${candidateName}` : ""}
        </h2>
        <p style={{ color: COLORS.muted, margin: "0 0 20px", fontSize: 14 }}>
          The candidate will see the vacancy details for the first time, then
          accept, decline, or counter-propose.
        </p>
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {slots.map((s, i) => (
            <div key={i} style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <input
                type="datetime-local"
                className="ed"
                value={s}
                onChange={(e) => setSlot(i, e.target.value)}
                style={{ flex: 1 }}
              />
              {slots.length > 1 && (
                <button
                  type="button"
                  onClick={() => removeSlot(i)}
                  aria-label="Remove slot"
                  style={{
                    background: "transparent",
                    border: `1px solid ${COLORS.rule}`,
                    color: COLORS.muted,
                    padding: "10px 14px",
                    cursor: "pointer",
                    fontFamily: FONT_MONO,
                    fontSize: 14,
                  }}
                >
                  ×
                </button>
              )}
            </div>
          ))}
        </div>
        {slots.length < 5 && (
          <button
            type="button"
            onClick={addSlot}
            style={{
              marginTop: 10,
              background: "transparent",
              border: "none",
              color: COLORS.ink,
              fontFamily: FONT_MONO,
              fontSize: 11,
              letterSpacing: "0.15em",
              textTransform: "uppercase",
              cursor: "pointer",
              padding: 0,
            }}
          >
            + Add another slot
          </button>
        )}
        {error && (
          <div style={{ color: COLORS.accent, marginTop: 12, fontSize: 14 }}>{error}</div>
        )}
        <div style={{ display: "flex", gap: 12, marginTop: 24, justifyContent: "flex-end" }}>
          <button type="button" className="ghost" onClick={onClose} disabled={submitting}>
            Cancel
          </button>
          <button type="button" className="primary" onClick={submit} disabled={submitting}>
            {submitting ? "Sending…" : "Send invite"}
          </button>
        </div>
      </div>
    </div>
  );
}
