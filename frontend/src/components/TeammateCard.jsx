import React, { useState } from "react";
import { COLORS, FONT_DISPLAY, FONT_MONO, FONT_BODY } from "../design.js";

const SENIORITY_OPTIONS = ["junior", "mid", "senior", "lead"];

// Compact trait-sheet display with bar visualisation for Big Five (0-5 scale)
// and skill/work_style (0-1 scale rendered as percentage).
function TraitBar({ label, value, max = 5 }) {
  const pct = Math.round((value / max) * 100);
  return (
    <div style={{ marginBottom: 6 }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 2 }}>
        <span style={{ fontFamily: FONT_MONO, fontSize: 10, letterSpacing: "0.1em", textTransform: "uppercase", color: COLORS.muted }}>
          {label}
        </span>
        <span style={{ fontFamily: FONT_MONO, fontSize: 10, color: COLORS.muted }}>
          {value.toFixed(1)}{max === 5 ? "/5" : ""}
        </span>
      </div>
      <div style={{ height: 4, background: COLORS.rule, position: "relative" }}>
        <div style={{ position: "absolute", left: 0, top: 0, height: "100%", width: `${pct}%`, background: COLORS.ink, transition: "width 0.3s" }} />
      </div>
    </div>
  );
}

function TraitSection({ title, traits, max = 5 }) {
  if (!traits || Object.keys(traits).length === 0) return null;
  return (
    <div style={{ marginBottom: 16 }}>
      <div className="label-mono" style={{ marginBottom: 8 }}>{title}</div>
      {Object.entries(traits).map(([k, v]) => (
        <TraitBar key={k} label={k.replace(/_/g, " ")} value={Number(v)} max={max} />
      ))}
    </div>
  );
}

export default function TeammateCard({ teammate, companyId, onUpdate, onDelete }) {
  const [expanded, setExpanded] = useState(false);
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  // Edit form state
  const [name, setName] = useState(teammate.name);
  const [role, setRole] = useState(teammate.role_on_team);
  const [seniority, setSeniority] = useState(teammate.seniority);
  const [narrative, setNarrative] = useState(teammate.narrative);

  function startEdit() {
    setName(teammate.name);
    setRole(teammate.role_on_team);
    setSeniority(teammate.seniority);
    setNarrative(teammate.narrative);
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
      const updated = await onUpdate(teammate.id, {
        name,
        role_on_team: role,
        seniority,
        narrative,
      });
      setEditing(false);
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  }

  const bf = teammate.trait_sheet?.big_five || {};
  const skills = teammate.trait_sheet?.skill_profile || {};
  const ws = teammate.trait_sheet?.work_style || {};
  const provenance = teammate.generated_from?.provenance_notes || "";

  return (
    <div
      style={{
        background: COLORS.cardBg,
        border: `1px solid ${teammate.is_edited ? COLORS.ink : COLORS.rule}`,
        padding: "20px 24px",
        transition: "border-color 0.15s",
      }}
    >
      {/* Header */}
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 12, marginBottom: 8 }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          {editing ? (
            <>
              <input
                className="ed"
                value={name}
                onChange={(e) => setName(e.target.value)}
                style={{ fontSize: 18, fontFamily: FONT_DISPLAY, fontWeight: 500, marginBottom: 6 }}
              />
              <input
                className="ed"
                value={role}
                onChange={(e) => setRole(e.target.value)}
                style={{ fontSize: 13, marginBottom: 6 }}
              />
              <div style={{ display: "flex", gap: 6 }}>
                {SENIORITY_OPTIONS.map((s) => (
                  <button
                    key={s}
                    onClick={() => setSeniority(s)}
                    style={{
                      padding: "3px 10px",
                      fontFamily: FONT_MONO,
                      fontSize: 10,
                      letterSpacing: "0.12em",
                      textTransform: "uppercase",
                      border: `1px solid ${seniority === s ? COLORS.ink : COLORS.rule}`,
                      background: seniority === s ? COLORS.ink : "transparent",
                      color: seniority === s ? COLORS.paper : COLORS.ink,
                      cursor: "pointer",
                    }}
                  >
                    {s}
                  </button>
                ))}
              </div>
            </>
          ) : (
            <>
              <div style={{ fontFamily: FONT_DISPLAY, fontSize: 20, fontWeight: 500 }}>
                {teammate.name}
                {teammate.is_edited && (
                  <span style={{ fontFamily: FONT_MONO, fontSize: 9, letterSpacing: "0.12em", color: COLORS.muted, marginLeft: 8, verticalAlign: "middle" }}>
                    EDITED
                  </span>
                )}
              </div>
              <div style={{ color: COLORS.muted, fontSize: 14 }}>{teammate.role_on_team}</div>
              <div style={{ fontFamily: FONT_MONO, fontSize: 10, letterSpacing: "0.12em", textTransform: "uppercase", color: COLORS.muted, marginTop: 2 }}>
                {teammate.seniority}
              </div>
            </>
          )}
        </div>

        {/* Action buttons */}
        <div style={{ display: "flex", gap: 6, flexShrink: 0 }}>
          {editing ? (
            <>
              <button
                className="primary"
                style={{ padding: "6px 14px" }}
                onClick={saveEdit}
                disabled={saving}
              >
                {saving ? "Saving…" : "Save"}
              </button>
              <button
                className="ghost"
                style={{ padding: "6px 14px" }}
                onClick={cancelEdit}
                disabled={saving}
              >
                Cancel
              </button>
            </>
          ) : (
            <>
              <button
                className="ghost"
                style={{ padding: "5px 12px", fontSize: 11 }}
                onClick={startEdit}
              >
                Edit
              </button>
              <button
                className="ghost"
                style={{ padding: "5px 12px", fontSize: 11, borderColor: COLORS.accent, color: COLORS.accent }}
                onClick={() => onDelete(teammate.id)}
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

      {/* Narrative excerpt (or full edit field) */}
      {editing ? (
        <textarea
          className="ed"
          value={narrative}
          onChange={(e) => setNarrative(e.target.value)}
          style={{ minHeight: 140, marginTop: 10 }}
        />
      ) : (
        <p style={{ fontSize: 15, color: COLORS.muted, lineHeight: 1.5, margin: "10px 0" }}>
          {expanded ? teammate.narrative : `${teammate.narrative.slice(0, 200)}…`}
        </p>
      )}

      {/* Expand / collapse */}
      {!editing && (
        <button
          onClick={() => setExpanded((v) => !v)}
          style={{
            background: "transparent",
            border: "none",
            fontFamily: FONT_MONO,
            fontSize: 10,
            letterSpacing: "0.15em",
            textTransform: "uppercase",
            color: COLORS.muted,
            cursor: "pointer",
            padding: "4px 0",
            marginBottom: expanded ? 16 : 0,
          }}
        >
          {expanded ? "▲ Collapse" : "▼ Trait sheet"}
        </button>
      )}

      {/* Trait sheet — only when expanded and not editing */}
      {expanded && !editing && (
        <div style={{ borderTop: `1px solid ${COLORS.rule}`, paddingTop: 16, marginTop: 8 }}>
          <TraitSection title="Big Five (0–5)" traits={bf} max={5} />
          <TraitSection title="Skills (0–5)" traits={skills} max={5} />
          <TraitSection title="Work style (0–1)" traits={ws} max={1} />

          {/* Private goals */}
          {teammate.private_goals?.length > 0 && (
            <div style={{ marginBottom: 16 }}>
              <div className="label-mono" style={{ marginBottom: 8 }}>Private goals (rollout-internal)</div>
              <ul style={{ margin: 0, paddingLeft: 18 }}>
                {teammate.private_goals.map((g, i) => (
                  <li key={i} style={{ fontSize: 14, color: COLORS.muted, marginBottom: 4 }}>{g}</li>
                ))}
              </ul>
            </div>
          )}

          {/* Provenance footnote */}
          {provenance && (
            <div
              title={provenance}
              style={{
                borderTop: `1px solid ${COLORS.rule}`,
                paddingTop: 10,
                fontSize: 12,
                color: COLORS.muted,
                fontStyle: "italic",
                cursor: "help",
              }}
            >
              <span style={{ fontFamily: FONT_MONO, fontSize: 9, letterSpacing: "0.12em", textTransform: "uppercase", marginRight: 6 }}>
                Provenance:
              </span>
              {provenance.length > 120 ? `${provenance.slice(0, 120)}…` : provenance}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
