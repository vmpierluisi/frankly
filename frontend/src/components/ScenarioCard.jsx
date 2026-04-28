import React, { useState } from "react";
import { COLORS, FONT_DISPLAY, FONT_MONO } from "../design.js";

const TYPE_LABELS = { dyad: "1:1", small_group: "Group", written: "Written" };
const TYPE_COLORS = { dyad: "#3a6b8a", small_group: "#6b4a8a", written: "#8a6b3a" };
const SENIORITY_OPTIONS = ["dyad", "small_group", "written"];

export default function ScenarioCard({ scenario, criteriaIndex = {}, onUpdate, onDelete }) {
  const [expanded, setExpanded] = useState(false);
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const [title, setTitle] = useState(scenario.title);
  const [type, setType] = useState(scenario.scenario_type);
  const [prompt, setPrompt] = useState(scenario.prompt);
  const [candidateRole, setCandidateRole] = useState(scenario.candidate_role);
  const [expectedArc, setExpectedArc] = useState(scenario.expected_arc);
  const [maxTurns, setMaxTurns] = useState(scenario.max_turns);

  function startEdit() {
    setTitle(scenario.title);
    setType(scenario.scenario_type);
    setPrompt(scenario.prompt);
    setCandidateRole(scenario.candidate_role);
    setExpectedArc(scenario.expected_arc);
    setMaxTurns(scenario.max_turns);
    setEditing(true);
    setExpanded(true);
    setError("");
  }

  function cancelEdit() {
    setEditing(false);
    setError("");
  }

  async function saveEdit() {
    setSaving(true);
    setError("");
    try {
      await onUpdate(scenario.id, {
        title,
        scenario_type: type,
        prompt,
        candidate_role: candidateRole,
        expected_arc: expectedArc,
        max_turns: Number(maxTurns),
      });
      setEditing(false);
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  }

  const typeColor = TYPE_COLORS[scenario.scenario_type] || COLORS.muted;
  const typeLabel = TYPE_LABELS[scenario.scenario_type] || scenario.scenario_type;

  return (
    <div
      style={{
        background: "#fff",
        border: `1px solid ${scenario.is_llm_drafted ? COLORS.rule : COLORS.ink}`,
        padding: "18px 22px",
        transition: "border-color 0.15s",
      }}
    >
      {/* Header row */}
      <div style={{ display: "flex", alignItems: "flex-start", gap: 12, marginBottom: 8 }}>
        {/* Type chip */}
        <span
          style={{
            fontFamily: FONT_MONO,
            fontSize: 9,
            letterSpacing: "0.14em",
            textTransform: "uppercase",
            color: "#fff",
            background: typeColor,
            padding: "3px 8px",
            flexShrink: 0,
            marginTop: 4,
          }}
        >
          {typeLabel}
        </span>

        <div style={{ flex: 1, minWidth: 0 }}>
          {editing ? (
            <>
              <input
                className="ed"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                style={{ fontFamily: FONT_DISPLAY, fontSize: 17, fontWeight: 500, marginBottom: 6 }}
              />
              <div style={{ display: "flex", gap: 6, marginBottom: 4 }}>
                {SENIORITY_OPTIONS.map((t) => (
                  <button
                    key={t}
                    onClick={() => setType(t)}
                    style={{
                      padding: "3px 10px",
                      fontFamily: FONT_MONO,
                      fontSize: 10,
                      letterSpacing: "0.12em",
                      textTransform: "uppercase",
                      border: `1px solid ${type === t ? COLORS.ink : COLORS.rule}`,
                      background: type === t ? COLORS.ink : "transparent",
                      color: type === t ? "#fff" : COLORS.ink,
                      cursor: "pointer",
                    }}
                  >
                    {TYPE_LABELS[t]}
                  </button>
                ))}
                <label style={{ fontFamily: FONT_MONO, fontSize: 10, display: "flex", alignItems: "center", gap: 6, marginLeft: 8, color: COLORS.muted }}>
                  Max turns:
                  <input
                    type="number"
                    value={maxTurns}
                    onChange={(e) => setMaxTurns(e.target.value)}
                    style={{ width: 48, fontFamily: FONT_MONO, fontSize: 12, padding: "2px 6px", border: `1px solid ${COLORS.rule}` }}
                  />
                </label>
              </div>
            </>
          ) : (
            <>
              <div style={{ fontFamily: FONT_DISPLAY, fontSize: 18, fontWeight: 500, lineHeight: 1.2 }}>
                {scenario.title}
                {!scenario.is_llm_drafted && (
                  <span style={{ fontFamily: FONT_MONO, fontSize: 9, letterSpacing: "0.12em", color: COLORS.muted, marginLeft: 8, verticalAlign: "middle" }}>
                    AUTHORED
                  </span>
                )}
              </div>
              <div style={{ fontFamily: FONT_MONO, fontSize: 10, color: COLORS.muted, marginTop: 2 }}>
                max {scenario.max_turns} turns
              </div>
            </>
          )}
        </div>

        {/* Action buttons */}
        <div style={{ display: "flex", gap: 6, flexShrink: 0 }}>
          {editing ? (
            <>
              <button className="primary" style={{ padding: "5px 12px" }} onClick={saveEdit} disabled={saving}>
                {saving ? "Saving…" : "Save"}
              </button>
              <button className="ghost" style={{ padding: "5px 12px" }} onClick={cancelEdit} disabled={saving}>
                Cancel
              </button>
            </>
          ) : (
            <>
              <button className="ghost" style={{ padding: "4px 10px", fontSize: 11 }} onClick={startEdit}>
                Edit
              </button>
              <button
                className="ghost"
                style={{ padding: "4px 10px", fontSize: 11, borderColor: COLORS.accent, color: COLORS.accent }}
                onClick={() => onDelete(scenario.id)}
              >
                ×
              </button>
            </>
          )}
        </div>
      </div>

      {error && (
        <div style={{ color: COLORS.accent, fontSize: 13, fontStyle: "italic", marginBottom: 8 }}>{error}</div>
      )}

      {/* Scoring dims chips */}
      {scenario.scoring_dims?.length > 0 && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 5, marginBottom: 8 }}>
          {scenario.scoring_dims.map((k) => (
            <span
              key={k}
              style={{
                fontFamily: FONT_MONO,
                fontSize: 9,
                letterSpacing: "0.1em",
                textTransform: "uppercase",
                border: `1px solid ${COLORS.rule}`,
                padding: "2px 8px",
                color: COLORS.muted,
              }}
            >
              {criteriaIndex[k]?.label || k}
            </span>
          ))}
        </div>
      )}

      {/* Prompt preview (or edit fields) */}
      {editing ? (
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <div>
            <div className="label-mono" style={{ marginBottom: 4 }}>Scenario prompt</div>
            <textarea
              className="ed"
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              style={{ minHeight: 80 }}
            />
          </div>
          <div>
            <div className="label-mono" style={{ marginBottom: 4 }}>Candidate role</div>
            <textarea
              className="ed"
              value={candidateRole}
              onChange={(e) => setCandidateRole(e.target.value)}
              style={{ minHeight: 60 }}
            />
          </div>
          <div>
            <div className="label-mono" style={{ marginBottom: 4 }}>Expected arc</div>
            <textarea
              className="ed"
              value={expectedArc}
              onChange={(e) => setExpectedArc(e.target.value)}
              style={{ minHeight: 60 }}
            />
          </div>
        </div>
      ) : (
        <p style={{ fontSize: 14, color: COLORS.muted, lineHeight: 1.5, margin: "0 0 6px" }}>
          {expanded ? scenario.prompt : `${scenario.prompt.slice(0, 160)}${scenario.prompt.length > 160 ? "…" : ""}`}
        </p>
      )}

      {/* Expand toggle + full detail */}
      {!editing && (
        <button
          onClick={() => setExpanded((v) => !v)}
          style={{
            background: "transparent", border: "none",
            fontFamily: FONT_MONO, fontSize: 10, letterSpacing: "0.15em",
            textTransform: "uppercase", color: COLORS.muted,
            cursor: "pointer", padding: "2px 0",
          }}
        >
          {expanded ? "▲ Collapse" : "▼ Details"}
        </button>
      )}

      {expanded && !editing && (
        <div style={{ borderTop: `1px solid ${COLORS.rule}`, paddingTop: 14, marginTop: 10 }}>
          <div style={{ marginBottom: 12 }}>
            <div className="label-mono" style={{ marginBottom: 4 }}>Candidate role</div>
            <p style={{ fontSize: 14, color: COLORS.muted, margin: 0, lineHeight: 1.5 }}>{scenario.candidate_role}</p>
          </div>
          <div style={{ marginBottom: 12 }}>
            <div className="label-mono" style={{ marginBottom: 4 }}>Expected arc</div>
            <p style={{ fontSize: 14, color: COLORS.muted, margin: 0, lineHeight: 1.5, fontStyle: "italic" }}>{scenario.expected_arc}</p>
          </div>
          {scenario.grounding && (
            <div style={{ borderTop: `1px solid ${COLORS.rule}`, paddingTop: 10, fontSize: 12, color: COLORS.muted, fontStyle: "italic" }}>
              <span style={{ fontFamily: FONT_MONO, fontSize: 9, letterSpacing: "0.12em", textTransform: "uppercase", marginRight: 6 }}>
                Grounding:
              </span>
              {scenario.grounding}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
