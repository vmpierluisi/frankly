import React, { useCallback, useEffect, useRef, useState } from "react";
import { COLORS, FONT_MONO } from "../../design.js";
import TriageCard from "./TriageCard.jsx";

// Manager Shortlist V7 — swipe stack.
// Renders the top ~3 candidates as stacked cards. Commit via keyboard
// (← pass, → shortlist, ↵ shortlist), mouse drag (30% width threshold), or the
// explicit Pass / Shortlist buttons. Advances on commit; shows a cleared state
// with "Compare shortlist →" when the queue empties.
const DRAG_COMMIT = 0.3; // fraction of card width

export default function TriageStack({ candidates, decided = {}, onDecide, onOpenShortlist }) {
  // Queue = candidates not yet decided this session.
  const [index, setIndex] = useState(0);
  const [drag, setDrag] = useState(0);
  const [committing, setCommitting] = useState(null); // 'pass' | 'shortlist'
  const cardRef = useRef(null);
  const dragState = useRef({ active: false, startX: 0, width: 1 });

  const remaining = candidates.slice(index);
  const current = remaining[0];

  const commit = useCallback(
    (decision) => {
      if (!current) return;
      setCommitting(decision);
      onDecide?.(current.id, decision);
      // Let the exit animation play before advancing.
      setTimeout(() => {
        setIndex((i) => i + 1);
        setDrag(0);
        setCommitting(null);
      }, 220);
    },
    [current, onDecide],
  );

  // Keyboard navigation.
  useEffect(() => {
    function onKey(e) {
      if (!current) return;
      if (e.key === "ArrowLeft") commit("pass");
      else if (e.key === "ArrowRight" || e.key === "Enter") commit("shortlist");
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [current, commit]);

  // Mouse drag.
  function onMouseDown(e) {
    dragState.current = {
      active: true,
      startX: e.clientX,
      width: cardRef.current?.offsetWidth || 1,
    };
  }
  useEffect(() => {
    function onMove(e) {
      if (!dragState.current.active) return;
      setDrag(e.clientX - dragState.current.startX);
    }
    function onUp() {
      if (!dragState.current.active) return;
      dragState.current.active = false;
      const frac = drag / dragState.current.width;
      if (frac > DRAG_COMMIT) commit("shortlist");
      else if (frac < -DRAG_COMMIT) commit("pass");
      else setDrag(0);
    }
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
  }, [drag, commit]);

  const total = candidates.length;
  const done = Math.min(index, total);

  if (!current) {
    const shortlisted = candidates.filter(
      (c) => decided[c.id] === "shortlist",
    ).length;
    return (
      <div style={{ textAlign: "center", padding: "64px 0" }}>
        <div className="label-mono" style={{ fontFamily: FONT_MONO, fontSize: 10, marginBottom: 12 }}>
          Queue cleared
        </div>
        <p style={{ color: COLORS.muted, marginBottom: 24 }}>
          You triaged {total} candidate{total === 1 ? "" : "s"}
          {shortlisted > 0 ? ` · ${shortlisted} shortlisted` : ""}.
        </p>
        <button className="primary" onClick={onOpenShortlist}>
          Compare shortlist →
        </button>
      </div>
    );
  }

  const rotate = drag / 24;
  const tint =
    committing === "shortlist" || drag > 40
      ? "rgba(63,122,52,0.10)"
      : committing === "pass" || drag < -40
        ? "rgba(184,57,26,0.10)"
        : "transparent";

  return (
    <div style={{ maxWidth: 520, margin: "0 auto" }}>
      {/* Progress */}
      <div style={{ marginBottom: 16 }}>
        <div style={{ display: "flex", justifyContent: "space-between", fontFamily: FONT_MONO, fontSize: 11, color: COLORS.muted, marginBottom: 6 }}>
          <span>{done} / {total}</span>
          <span>← pass · shortlist →</span>
        </div>
        <div style={{ height: 3, background: COLORS.rule }}>
          <div style={{ height: "100%", width: `${(done / total) * 100}%`, background: COLORS.ink, transition: "width 0.22s" }} />
        </div>
      </div>

      {/* Card stack. The top card sits in normal flow so it defines the
          container height (no fixed height → no content overflow / overlap);
          the peeking back cards are absolutely positioned behind it. */}
      <div style={{ position: "relative" }}>
        {remaining.slice(1, 3).map((c, i) => {
          const depth = i + 1; // 1 = first card behind
          return (
            <div
              key={c.id}
              aria-hidden
              style={{
                position: "absolute",
                inset: 0,
                transform: `translateY(${depth * 10}px) scale(${1 - depth * 0.04})`,
                transition: "transform 0.22s ease",
                zIndex: 1,
                pointerEvents: "none",
              }}
            >
              <TriageCard candidate={c} />
            </div>
          );
        })}

        <div
          ref={cardRef}
          onMouseDown={onMouseDown}
          style={{
            position: "relative",
            zIndex: 5,
            transform: `translateX(${drag}px) rotate(${rotate}deg)`,
            transition: dragState.current.active ? "none" : "transform 0.22s ease, opacity 0.22s ease",
            opacity: committing ? 0 : 1,
            cursor: "grab",
            background: tint,
            userSelect: "none",
          }}
        >
          <TriageCard candidate={current} />
        </div>
      </div>

      {/* Explicit buttons */}
      <div style={{ display: "flex", gap: 12, justifyContent: "center", marginTop: 20 }}>
        <button className="ghost" onClick={() => commit("pass")} style={{ padding: "12px 24px" }}>
          ← Pass
        </button>
        <button className="primary" onClick={() => commit("shortlist")} style={{ padding: "12px 24px" }}>
          Shortlist →
        </button>
      </div>
    </div>
  );
}
