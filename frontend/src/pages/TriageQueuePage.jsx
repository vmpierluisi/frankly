import React from "react";
import { useNavigate, useParams } from "react-router-dom";
import { COLORS, FONT_DISPLAY } from "../design.js";

// Placeholder — full swipe stack lands in Phase 5.
export default function TriageQueuePage() {
  const { positionId } = useParams();
  const nav = useNavigate();
  return (
    <main className="container" style={{ maxWidth: 720 }}>
      <div className="label-mono">Triage</div>
      <h2 style={{ fontFamily: FONT_DISPLAY, fontSize: 34, fontWeight: 500, margin: "6px 0 16px" }}>
        Manual triage — coming in Phase 5.
      </h2>
      <button
        className="ghost"
        onClick={() => nav(`/manager/positions/${positionId}/shortlist`)}
      >
        ← Back to shortlist
      </button>
    </main>
  );
}
