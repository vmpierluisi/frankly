import React, { useState } from "react";
import { COLORS, FONT_DISPLAY, FONT_MONO } from "../design.js";

/**
 * Inline editor for the public verified-profile fields. Mounted in a modal
 * sheet from the candidate Overview tab.
 *
 * Supports add/remove/edit on three lists:
 *   - skills:     [{ name }]            — chips
 *   - experience: [{ role, company, start, end, bullets[] }]
 *   - education:  [{ institution, degree, field, start, end }]
 *
 * On save, calls PATCH /candidates/me/profile with the field(s) that changed.
 * Edits are tracked server-side in `edited_fields` so a future re-extraction
 * won't clobber the candidate's corrections.
 */
export default function VerifiedProfileEditor({ profile, saving, onSave, onClose }) {
  const initial = profile || { skills: [], experience: [], education: [] };
  const [skills, setSkills] = useState(normaliseSkills(initial.skills));
  const [experience, setExperience] = useState(normaliseList(initial.experience));
  const [education, setEducation] = useState(normaliseList(initial.education));

  function commit() {
    onSave({
      skills: skills
        .map((s) => s.trim())
        .filter(Boolean)
        .map((name) => ({ name })),
      experience: experience.map((e) => ({
        role: e.role || "",
        company: e.company || "",
        start: e.start || "",
        end: e.end || "",
        bullets: (e.bullets || []).map((b) => b.trim()).filter(Boolean),
      })),
      education: education.map((e) => ({
        institution: e.institution || "",
        degree: e.degree || "",
        field: e.field || "",
        start: e.start || "",
        end: e.end || "",
      })),
    });
  }

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(26,24,20,0.55)",
        zIndex: 100,
        display: "flex",
        justifyContent: "center",
        alignItems: "flex-start",
        padding: "40px 20px",
        overflowY: "auto",
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        style={{
          background: COLORS.cardBg,
          width: "100%",
          maxWidth: 760,
          padding: "28px 32px 36px",
          border: `1px solid ${COLORS.rule}`,
          borderTop: `2px solid ${COLORS.ink}`,
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            marginBottom: 18,
          }}
        >
          <div>
            <div className="label-mono">Edit verified profile</div>
            <div style={{ color: COLORS.muted, fontSize: 13, marginTop: 4 }}>
              Your edits stick. Re-extracting won't overwrite fields you've changed here.
            </div>
          </div>
          <button
            onClick={onClose}
            style={{
              background: "transparent",
              border: "none",
              cursor: "pointer",
              fontSize: 24,
              color: COLORS.muted,
              lineHeight: 1,
            }}
            aria-label="Close"
          >
            ×
          </button>
        </div>

        <SectionHeader title="Skills" onAdd={() => setSkills([...skills, ""])} />
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 24 }}>
          {skills.map((s, i) => (
            <SkillEdit
              key={i}
              value={s}
              onChange={(v) => setSkills(replaceAt(skills, i, v))}
              onRemove={() => setSkills(removeAt(skills, i))}
            />
          ))}
          {skills.length === 0 && (
            <span style={{ color: COLORS.muted, fontSize: 14, fontStyle: "italic" }}>
              No skills yet — click + to add.
            </span>
          )}
        </div>

        <SectionHeader
          title="Experience"
          onAdd={() => setExperience([...experience, blankExperience()])}
        />
        {experience.map((e, i) => (
          <ExperienceEdit
            key={i}
            entry={e}
            onChange={(updated) => setExperience(replaceAt(experience, i, updated))}
            onRemove={() => setExperience(removeAt(experience, i))}
          />
        ))}
        {experience.length === 0 && (
          <p style={{ color: COLORS.muted, fontSize: 14, fontStyle: "italic", marginBottom: 24 }}>
            No experience yet — click + to add a role.
          </p>
        )}

        <SectionHeader
          title="Education"
          onAdd={() => setEducation([...education, blankEducation()])}
        />
        {education.map((e, i) => (
          <EducationEdit
            key={i}
            entry={e}
            onChange={(updated) => setEducation(replaceAt(education, i, updated))}
            onRemove={() => setEducation(removeAt(education, i))}
          />
        ))}
        {education.length === 0 && (
          <p style={{ color: COLORS.muted, fontSize: 14, fontStyle: "italic", marginBottom: 24 }}>
            No education yet — click + to add a degree.
          </p>
        )}

        <div style={{ display: "flex", gap: 12, marginTop: 12 }}>
          <button className="primary" disabled={saving} onClick={commit}>
            {saving ? "Saving…" : "Save changes →"}
          </button>
          <button className="ghost" onClick={onClose} disabled={saving}>
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function SectionHeader({ title, onAdd }) {
  return (
    <div
      style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        marginBottom: 10,
        marginTop: 8,
      }}
    >
      <div className="label-mono">{title}</div>
      <button
        onClick={onAdd}
        style={{
          background: "transparent",
          border: `1px solid ${COLORS.rule}`,
          width: 28,
          height: 28,
          borderRadius: "50%",
          cursor: "pointer",
          fontSize: 16,
          color: COLORS.ink,
          padding: 0,
          lineHeight: 1,
        }}
        aria-label={`Add ${title}`}
      >
        +
      </button>
    </div>
  );
}

function SkillEdit({ value, onChange, onRemove }) {
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        padding: "3px 4px 3px 10px",
        border: `1px solid ${COLORS.rule}`,
        background: COLORS.cardBg,
        fontFamily: FONT_MONO,
        fontSize: 12,
      }}
    >
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="Skill"
        style={{
          border: "none",
          outline: "none",
          fontFamily: FONT_MONO,
          fontSize: 12,
          padding: "2px 0",
          width: Math.max(60, (value?.length || 6) * 8),
        }}
      />
      <button
        onClick={onRemove}
        aria-label="Remove skill"
        style={{
          background: "transparent",
          border: "none",
          cursor: "pointer",
          color: COLORS.muted,
          fontSize: 14,
          padding: "0 6px",
          lineHeight: 1,
        }}
      >
        ×
      </button>
    </span>
  );
}

function ExperienceEdit({ entry, onChange, onRemove }) {
  function set(field, v) {
    onChange({ ...entry, [field]: v });
  }
  function setBullet(i, v) {
    const bullets = [...(entry.bullets || [])];
    bullets[i] = v;
    set("bullets", bullets);
  }
  function addBullet() {
    set("bullets", [...(entry.bullets || []), ""]);
  }
  function removeBullet(i) {
    const bullets = [...(entry.bullets || [])];
    bullets.splice(i, 1);
    set("bullets", bullets);
  }

  return (
    <div
      style={{
        border: `1px solid ${COLORS.rule}`,
        padding: "16px 18px",
        marginBottom: 16,
        background: COLORS.paper,
      }}
    >
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 10 }}>
        <FieldInput label="Role" value={entry.role} onChange={(v) => set("role", v)} />
        <FieldInput label="Company" value={entry.company} onChange={(v) => set("company", v)} />
        <FieldInput label="Start" value={entry.start} onChange={(v) => set("start", v)} placeholder="2021" />
        <FieldInput label="End" value={entry.end} onChange={(v) => set("end", v)} placeholder="2024 or present" />
      </div>
      <div className="label-mono" style={{ marginBottom: 6 }}>Bullets</div>
      {(entry.bullets || []).map((b, i) => (
        <div key={i} style={{ display: "flex", gap: 6, marginBottom: 6 }}>
          <input
            className="ed"
            value={b}
            onChange={(e) => setBullet(i, e.target.value)}
            placeholder="What you did, in your words"
            style={{ fontSize: 14, padding: "8px 10px" }}
          />
          <button
            onClick={() => removeBullet(i)}
            style={{
              background: "transparent",
              border: `1px solid ${COLORS.rule}`,
              cursor: "pointer",
              padding: "0 10px",
              color: COLORS.muted,
            }}
            aria-label="Remove bullet"
          >
            ×
          </button>
        </div>
      ))}
      <button
        onClick={addBullet}
        style={{
          background: "transparent",
          border: "none",
          cursor: "pointer",
          fontFamily: FONT_MONO,
          fontSize: 11,
          color: COLORS.muted,
          letterSpacing: "0.12em",
          padding: 0,
          marginBottom: 10,
        }}
      >
        + Add bullet
      </button>
      <div>
        <button
          onClick={onRemove}
          style={{
            background: "transparent",
            border: "none",
            cursor: "pointer",
            color: COLORS.accent,
            fontFamily: FONT_MONO,
            fontSize: 11,
            letterSpacing: "0.12em",
            padding: 0,
          }}
        >
          Remove this role
        </button>
      </div>
    </div>
  );
}

function EducationEdit({ entry, onChange, onRemove }) {
  function set(field, v) {
    onChange({ ...entry, [field]: v });
  }
  return (
    <div
      style={{
        border: `1px solid ${COLORS.rule}`,
        padding: "16px 18px",
        marginBottom: 16,
        background: COLORS.paper,
      }}
    >
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 10 }}>
        <FieldInput
          label="Institution"
          value={entry.institution}
          onChange={(v) => set("institution", v)}
          full
        />
        <FieldInput label="Degree" value={entry.degree} onChange={(v) => set("degree", v)} />
        <FieldInput label="Field" value={entry.field} onChange={(v) => set("field", v)} />
        <FieldInput label="Start" value={entry.start} onChange={(v) => set("start", v)} placeholder="2018" />
        <FieldInput label="End" value={entry.end} onChange={(v) => set("end", v)} placeholder="2020" />
      </div>
      <button
        onClick={onRemove}
        style={{
          background: "transparent",
          border: "none",
          cursor: "pointer",
          color: COLORS.accent,
          fontFamily: FONT_MONO,
          fontSize: 11,
          letterSpacing: "0.12em",
          padding: 0,
        }}
      >
        Remove this entry
      </button>
    </div>
  );
}

function FieldInput({ label, value, onChange, placeholder, full = false }) {
  return (
    <div style={{ gridColumn: full ? "1 / -1" : "auto" }}>
      <label className="label-mono" style={{ display: "block", marginBottom: 4, fontSize: 10 }}>
        {label}
      </label>
      <input
        className="ed"
        value={value || ""}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        style={{ fontSize: 14, padding: "8px 10px" }}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function normaliseSkills(skills) {
  if (!Array.isArray(skills)) return [];
  return skills
    .map((s) => (typeof s === "string" ? s : s?.name || ""))
    .filter(Boolean);
}

function normaliseList(list) {
  return Array.isArray(list) ? list.map((x) => ({ ...x })) : [];
}

function replaceAt(arr, i, v) {
  const out = [...arr];
  out[i] = v;
  return out;
}

function removeAt(arr, i) {
  const out = [...arr];
  out.splice(i, 1);
  return out;
}

function blankExperience() {
  return { role: "", company: "", start: "", end: "", bullets: [] };
}

function blankEducation() {
  return { institution: "", degree: "", field: "", start: "", end: "" };
}
