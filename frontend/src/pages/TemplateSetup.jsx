import React, { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { COLORS, FONT_DISPLAY, FONT_MONO } from "../design.js";
import { companies, templates } from "../api.js";
import { GeneratingScreen } from "../components/Widgets.jsx";

// Manager-facing template setup. Two-step flow:
//   1. Identify the company + role + four artifacts (paste OR file upload).
//   2. Run extract_criteria, review the 5-7 suggested criteria, edit weights /
//      labels / descriptions, save.
//
// The four artifacts always end up as TEXT in the backend. PDFs and DOCX are
// parsed server-side (POST /templates/parse-artifact) before we send them to
// the criteria extractor.

const ARTIFACT_FIELDS = [
  { key: "artifact_values", label: "Values document", placeholder: "What you stand for. The honest version, not the careers-page version." },
  { key: "artifact_role_spec", label: "Role specification", placeholder: "What the analyst actually owns end-to-end." },
  { key: "artifact_team_structure", label: "Team structure", placeholder: "Hierarchy, decision rituals, who-reads-what." },
  { key: "artifact_sample_comms", label: "Sample communication", placeholder: "An IC memo excerpt, an internal Slack thread, a partner note — paste an unredacted snippet that shows the texture of how the team writes." },
];

export default function TemplateSetup() {
  const nav = useNavigate();
  const { companyId } = useParams();

  const [form, setForm] = useState({
    id: "",
    name: "",
    tagline: "",
    role: "",
    artifact_values: "",
    artifact_role_spec: "",
    artifact_team_structure: "",
    artifact_sample_comms: "",
  });
  const [criteria, setCriteria] = useState([]);
  const [loading, setLoading] = useState(false);
  const [extracting, setExtracting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  // Load existing company if editing.
  useEffect(() => {
    if (!companyId) return;
    setLoading(true);
    companies
      .get(companyId)
      .then((c) => {
        setForm({
          id: c.id,
          name: c.name,
          tagline: c.tagline || "",
          role: c.role,
          artifact_values: c.artifact_values || "",
          artifact_role_spec: c.artifact_role_spec || "",
          artifact_team_structure: c.artifact_team_structure || "",
          artifact_sample_comms: c.artifact_sample_comms || "",
        });
        setCriteria(c.criteria || []);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [companyId]);

  function update(field, value) {
    setForm((f) => ({ ...f, [field]: value }));
  }

  async function handleUpload(field, file) {
    if (!file) return;
    setError("");
    try {
      const out = await templates.parseArtifact(file);
      update(field, out.text || "");
    } catch (e) {
      setError(`Upload failed: ${e.message}`);
    }
  }

  async function runExtract() {
    setError("");
    setExtracting(true);
    try {
      const out = await templates.extractCriteria(
        {
          artifact_values: form.artifact_values,
          artifact_role_spec: form.artifact_role_spec,
          artifact_team_structure: form.artifact_team_structure,
          artifact_sample_comms: form.artifact_sample_comms,
        },
        form.role,
      );
      setCriteria(out.criteria.map((c, i) => ({ ...c, ordering: i })));
    } catch (e) {
      setError(`Extraction failed: ${e.message}`);
    } finally {
      setExtracting(false);
    }
  }

  function updateCriterion(idx, field, value) {
    setCriteria((arr) => arr.map((c, i) => (i === idx ? { ...c, [field]: value } : c)));
  }
  function removeCriterion(idx) {
    setCriteria((arr) => arr.filter((_, i) => i !== idx));
  }
  function addCriterion() {
    setCriteria((arr) => [
      ...arr,
      { key: "", label: "", description: "", weight: 0, ordering: arr.length },
    ]);
  }

  const weightSum = criteria.reduce((s, c) => s + (Number(c.weight) || 0), 0);
  const weightOk = Math.abs(weightSum - 1) < 0.005;

  async function save() {
    setError("");
    if (!form.name || !form.role) {
      setError("Name and role are required.");
      return;
    }
    if (criteria.length < 3) {
      setError("Need at least 3 criteria. Run extraction or add some manually.");
      return;
    }
    if (!weightOk) {
      // Renormalize before save instead of erroring.
      if (weightSum > 0) {
        const fixed = criteria.map((c) => ({
          ...c,
          weight: Number((Number(c.weight) / weightSum).toFixed(3)),
        }));
        setCriteria(fixed);
      }
    }
    setSaving(true);
    const payload = {
      ...form,
      id: form.id || undefined,
      criteria: criteria.map(({ id, ordering, ...c }) => ({
        ...c,
        weight: Number(c.weight) || 0,
      })),
    };
    try {
      const saved = companyId
        ? await companies.update(companyId, payload)
        : await companies.create(payload);
      nav(`/manager`, { state: { savedCompany: saved.id } });
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  }

  if (loading) return <GeneratingScreen note="Loading company…" />;

  return (
    <main className="container">
      <div className="label-mono" style={{ marginBottom: 12 }}>
        Manager · {companyId ? "Edit template" : "New template"}
      </div>
      <h2
        style={{
          fontFamily: FONT_DISPLAY,
          fontSize: 40,
          fontWeight: 500,
          letterSpacing: "-0.015em",
          lineHeight: 1.1,
          margin: "0 0 8px",
        }}
      >
        Tell us how this company actually decides.
      </h2>
      <p style={{ color: COLORS.muted, fontStyle: "italic", marginBottom: 32, fontSize: 17 }}>
        Paste sanctioned artifacts. Upload PDFs or DOCX if that's easier. The extractor reads
        what you give it and proposes criteria you'll review before saving.
      </p>
      <hr className="rule-thick" style={{ margin: "0 0 32px" }} />

      {/* Identity */}
      <div className="label-mono" style={{ marginBottom: 12 }}>1. Identity</div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 16 }}>
        <div>
          <label className="label-mono" style={{ display: "block", marginBottom: 6 }}>Name</label>
          <input className="ed" value={form.name} onChange={(e) => update("name", e.target.value)} placeholder="Meridian Capital Partners" />
        </div>
        <div>
          <label className="label-mono" style={{ display: "block", marginBottom: 6 }}>Role</label>
          <input className="ed" value={form.role} onChange={(e) => update("role", e.target.value)} placeholder="Financial Analyst — Credit Underwriting" />
        </div>
      </div>
      <div style={{ marginBottom: 32 }}>
        <label className="label-mono" style={{ display: "block", marginBottom: 6 }}>Tagline (optional)</label>
        <input
          className="ed"
          value={form.tagline}
          onChange={(e) => update("tagline", e.target.value)}
          placeholder="One-sentence positioning."
        />
      </div>

      {/* Artifacts */}
      <div className="label-mono" style={{ marginBottom: 12 }}>2. Sanctioned artifacts</div>
      {ARTIFACT_FIELDS.map((f) => (
        <div key={f.key} style={{ marginBottom: 28 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 6 }}>
            <label
              style={{
                fontFamily: FONT_DISPLAY,
                fontSize: 18,
                fontWeight: 500,
              }}
            >
              {f.label}
            </label>
            <label
              className="label-mono"
              style={{ cursor: "pointer", color: COLORS.accent }}
              title="Upload .pdf, .docx, .txt or .md — text is extracted server-side"
            >
              upload file
              <input
                type="file"
                accept=".pdf,.docx,.txt,.md"
                style={{ display: "none" }}
                onChange={(e) => handleUpload(f.key, e.target.files?.[0])}
              />
            </label>
          </div>
          <textarea
            className="ed"
            value={form[f.key]}
            onChange={(e) => update(f.key, e.target.value)}
            placeholder={f.placeholder}
            rows={f.key === "artifact_sample_comms" ? 6 : 5}
          />
        </div>
      ))}

      {/* Extraction */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginTop: 16,
          marginBottom: 24,
          gap: 12,
          flexWrap: "wrap",
        }}
      >
        <div>
          <div className="label-mono" style={{ marginBottom: 6 }}>3. Criteria</div>
          <div style={{ color: COLORS.muted, fontSize: 14 }}>
            Run extraction once you've got at least the values doc and role spec in.
          </div>
        </div>
        <button className="ghost" onClick={runExtract} disabled={extracting}>
          {extracting ? "Extracting…" : criteria.length ? "Re-run extraction" : "Run extraction"}
        </button>
      </div>

      {extracting && <GeneratingScreen note="Reading artifacts and proposing criteria…" />}

      {!extracting && criteria.map((c, i) => (
        <div
          key={`${c.key || "new"}-${i}`}
          style={{
            border: `1px solid ${COLORS.rule}`,
            background: "#fff",
            padding: "16px 20px",
            marginBottom: 12,
          }}
        >
          <div style={{ display: "grid", gridTemplateColumns: "2fr 2fr 1fr auto", gap: 12, alignItems: "start" }}>
            <div>
              <label className="label-mono" style={{ display: "block", marginBottom: 4 }}>Key</label>
              <input
                className="ed"
                value={c.key}
                onChange={(e) => updateCriterion(i, "key", e.target.value)}
                placeholder="camelCase"
                style={{ fontFamily: FONT_MONO, fontSize: 14 }}
              />
            </div>
            <div>
              <label className="label-mono" style={{ display: "block", marginBottom: 4 }}>Label</label>
              <input className="ed" value={c.label} onChange={(e) => updateCriterion(i, "label", e.target.value)} />
            </div>
            <div>
              <label className="label-mono" style={{ display: "block", marginBottom: 4 }}>Weight</label>
              <input
                className="ed"
                type="number"
                step="0.01"
                min="0"
                max="1"
                value={c.weight}
                onChange={(e) => updateCriterion(i, "weight", e.target.value)}
                style={{ fontFamily: FONT_MONO }}
              />
            </div>
            <button
              className="ghost"
              onClick={() => removeCriterion(i)}
              style={{ padding: "8px 12px", marginTop: 22 }}
            >
              ×
            </button>
          </div>
          <div style={{ marginTop: 12 }}>
            <label className="label-mono" style={{ display: "block", marginBottom: 4 }}>
              Description (cite artifact text)
            </label>
            <textarea
              className="ed"
              rows={2}
              value={c.description}
              onChange={(e) => updateCriterion(i, "description", e.target.value)}
            />
          </div>
        </div>
      ))}

      {!extracting && (
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            marginTop: 8,
            gap: 12,
            flexWrap: "wrap",
          }}
        >
          <button className="ghost" onClick={addCriterion}>+ Add criterion manually</button>
          <div className="label-mono" style={{ color: weightOk ? COLORS.muted : COLORS.accent }}>
            Weights sum to {weightSum.toFixed(2)} {weightOk ? "✓" : "(will renormalize on save)"}
          </div>
        </div>
      )}

      {error && (
        <div style={{ color: COLORS.accent, marginTop: 24, fontStyle: "italic" }}>{error}</div>
      )}

      <div style={{ marginTop: 32, display: "flex", gap: 12 }}>
        <button className="primary" onClick={save} disabled={saving}>
          {saving ? "Saving…" : "Save template"}
        </button>
        <button className="ghost" onClick={() => nav("/manager")}>Cancel</button>
      </div>
    </main>
  );
}
