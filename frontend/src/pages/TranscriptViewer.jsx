import React, { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { COLORS, FONT_DISPLAY, FONT_MONO } from "../design.js";
import { matches as matchesApi } from "../api.js";
import TranscriptTurn from "../components/TranscriptTurn.jsx";
import { formatCriterion } from "../components/Widgets.jsx";

export default function TranscriptViewer() {
  const { matchId, rolloutId } = useParams();
  const navigate = useNavigate();

  const [rollout, setRollout] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showIntents, setShowIntents] = useState(false);
  const [selectedDimension, setSelectedDimension] = useState(null);

  const turnRefs = useRef({});

  useEffect(() => {
    setLoading(true);
    matchesApi.getRollout(matchId, rolloutId)
      .then(setRollout)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [matchId, rolloutId]);

  if (loading) {
    return (
      <div className="container">
        <div style={{ display: "flex", gap: 6, paddingTop: 48 }}>
          <span className="pulse-dot" /><span className="pulse-dot" /><span className="pulse-dot" />
        </div>
      </div>
    );
  }

  if (error || !rollout) {
    return (
      <div className="container">
        <div className="label-mono" style={{ color: COLORS.accent, marginBottom: 12 }}>Error</div>
        <p style={{ color: COLORS.muted }}>{error || "Rollout not found."}</p>
        <button className="ghost" onClick={() => navigate(-1)}>← Back</button>
      </div>
    );
  }

  const transcript = rollout.transcript || [];
  const scoreRows = rollout.score_rows || [];

  // Build evidence map: dimension → Set of turn indices
  const evidenceByDim = {};
  for (const s of scoreRows) {
    evidenceByDim[s.dimension_key] = new Set(s.evidence_turns || []);
  }

  const highlightedIndices = selectedDimension
    ? (evidenceByDim[selectedDimension] || new Set())
    : new Set();

  const scenarioTitle = rollout.final_state?.scenario_title || `Rollout #${rollout.rollout_index}`;
  const scenarioPrompt = rollout.final_state?.scenario_prompt || "";

  function toggleDimension(key) {
    setSelectedDimension((prev) => {
      const next = prev === key ? null : key;
      if (next) {
        // Scroll first highlighted turn into view
        const idx = [...(evidenceByDim[next] || [])].sort((a, b) => a - b)[0];
        if (idx != null) {
          setTimeout(() => turnRefs.current[idx]?.scrollIntoView({ behavior: "smooth", block: "center" }), 50);
        }
      }
      return next;
    });
  }

  return (
    <div className="container" style={{ maxWidth: 1100 }}>
      {/* Back */}
      <button
        className="ghost"
        style={{ marginBottom: 32, padding: "8px 16px", fontSize: 11 }}
        onClick={() => navigate(-1)}
      >
        ← Back
      </button>

      {/* Header */}
      <div className="label-mono" style={{ marginBottom: 8 }}>
        Transcript · Match {matchId.slice(0, 8)}
      </div>
      <h1 style={{ fontFamily: FONT_DISPLAY, fontSize: 32, fontWeight: 500, margin: "0 0 12px", lineHeight: 1.15 }}>
        {scenarioTitle}
      </h1>
      {scenarioPrompt && (
        <blockquote
          style={{
            borderLeft: `3px solid ${COLORS.rule}`,
            margin: "0 0 24px",
            padding: "8px 20px",
            color: COLORS.muted,
            fontStyle: "italic",
            fontSize: 16,
          }}
        >
          {scenarioPrompt}
        </blockquote>
      )}

      {rollout.status === "failed" && (
        <div
          className="label-mono"
          style={{
            color: COLORS.accent,
            background: COLORS.accentSoft,
            padding: "10px 16px",
            marginBottom: 20,
            borderLeft: `3px solid ${COLORS.accent}`,
          }}
        >
          rollout failed: {rollout.failure_reason || "unknown reason"}
        </div>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "1fr 300px", gap: 40, alignItems: "start" }}>
        {/* Main transcript column */}
        <div>
          {/* Toolbar */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 10,
              flexWrap: "wrap",
              marginBottom: 20,
              paddingBottom: 16,
              borderBottom: `1px solid ${COLORS.rule}`,
            }}
          >
            {scoreRows.map((s) => (
              <button
                key={s.dimension_key}
                onClick={() => toggleDimension(s.dimension_key)}
                style={{
                  fontFamily: FONT_MONO,
                  fontSize: 10,
                  letterSpacing: "0.12em",
                  textTransform: "uppercase",
                  padding: "5px 10px",
                  border: `1px solid ${selectedDimension === s.dimension_key ? COLORS.accent : COLORS.rule}`,
                  background: selectedDimension === s.dimension_key ? COLORS.accentSoft : "transparent",
                  color: selectedDimension === s.dimension_key ? COLORS.accent : COLORS.muted,
                  cursor: "pointer",
                }}
              >
                {formatCriterion(s.dimension_key)}
              </button>
            ))}
            <label
              style={{
                display: "flex",
                alignItems: "center",
                gap: 6,
                fontFamily: FONT_MONO,
                fontSize: 10,
                letterSpacing: "0.12em",
                textTransform: "uppercase",
                color: COLORS.muted,
                cursor: "pointer",
                marginLeft: "auto",
              }}
            >
              <input
                type="checkbox"
                checked={showIntents}
                onChange={(e) => setShowIntents(e.target.checked)}
                style={{ accentColor: COLORS.accent }}
              />
              Show intents
            </label>
          </div>

          {transcript.length === 0 ? (
            <div className="label-mono" style={{ color: COLORS.muted }}>No turns recorded.</div>
          ) : (
            <div>
              {transcript.map((turn, i) => {
                const idx = turn.turn ?? i;
                return (
                  <div key={i} ref={(el) => (turnRefs.current[idx] = el)}>
                    <TranscriptTurn
                      turn={turn}
                      isHighlighted={highlightedIndices.has(idx)}
                      showIntents={showIntents}
                    />
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Sidebar — dimension scores */}
        <div style={{ position: "sticky", top: 32 }}>
          <div className="label-mono" style={{ marginBottom: 16 }}>Dimension scores</div>
          {scoreRows.length === 0 ? (
            <div style={{ color: COLORS.muted, fontSize: 14 }}>No scores recorded.</div>
          ) : (
            scoreRows.map((s) => {
              const isSelected = selectedDimension === s.dimension_key;
              return (
                <div
                  key={s.dimension_key}
                  onClick={() => toggleDimension(s.dimension_key)}
                  style={{
                    padding: "14px 16px",
                    marginBottom: 8,
                    border: `1px solid ${isSelected ? COLORS.accent : COLORS.rule}`,
                    background: isSelected ? COLORS.accentSoft : COLORS.cardBg,
                    cursor: "pointer",
                    transition: "border-color 0.15s, background 0.15s",
                  }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 4 }}>
                    <span style={{ fontFamily: FONT_MONO, fontSize: 11, letterSpacing: "0.1em", textTransform: "uppercase", color: isSelected ? COLORS.accent : COLORS.muted }}>
                      {formatCriterion(s.dimension_key)}
                    </span>
                    <span style={{ fontFamily: FONT_MONO, fontSize: 18, fontWeight: 600, color: isSelected ? COLORS.accent : COLORS.ink }}>
                      {s.score ?? "—"}
                    </span>
                  </div>
                  {isSelected && s.justification && (
                    <div style={{ fontSize: 13, color: COLORS.muted, lineHeight: 1.5, marginTop: 6 }}>
                      {s.justification}
                    </div>
                  )}
                  {isSelected && (
                    <div className="label-mono" style={{ marginTop: 6, color: COLORS.accent }}>
                      {evidenceByDim[s.dimension_key]?.size || 0} evidence turn{(evidenceByDim[s.dimension_key]?.size || 0) !== 1 ? "s" : ""}
                    </div>
                  )}
                </div>
              );
            })
          )}

          <div style={{ marginTop: 24, paddingTop: 16, borderTop: `1px solid ${COLORS.rule}` }}>
            <div className="label-mono" style={{ marginBottom: 8 }}>Run details</div>
            <div style={{ fontFamily: FONT_MONO, fontSize: 11, color: COLORS.muted, lineHeight: 1.8 }}>
              <div>Turns: {rollout.duration_turns}</div>
              <div>Status: {rollout.status}</div>
              <div>Index: #{rollout.rollout_index}</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
