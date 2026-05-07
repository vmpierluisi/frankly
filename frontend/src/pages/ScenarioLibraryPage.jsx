import React, { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { COLORS, FONT_DISPLAY, FONT_MONO } from "../design.js";
import { positions, scenarios } from "../api.js";
import { GeneratingScreen } from "../components/Widgets.jsx";
import ScenarioCard from "../components/ScenarioCard.jsx";

// Manager page: view, draft, and manage the scenario library for a company.
// Route: /manager/companies/:companyId/scenarios

const BLANK_FORM = {
  title: "",
  scenario_type: "dyad",
  prompt: "",
  candidate_role: "",
  expected_arc: "",
  scoring_dims: [],
  participating_roles: [],
  max_turns: 6,
  grounding: "",
};

const TYPE_LABELS = { dyad: "1:1 Dyad", small_group: "Small Group", written: "Written" };

export default function ScenarioLibraryPage() {
  const { companyId } = useParams();
  const nav = useNavigate();

  const [company, setCompany] = useState(null);
  const [scenarioList, setScenarioList] = useState([]);
  const [loading, setLoading] = useState(true);
  const [drafting, setDrafting] = useState(false);
  const [error, setError] = useState("");

  // Hand-authored creation modal state
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState(BLANK_FORM);
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState("");

  useEffect(() => {
    Promise.all([positions.get(companyId), scenarios.list(companyId)])
      .then(([co, sc]) => {
        setCompany(co);
        setScenarioList(sc);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [companyId]);

  const criteriaIndex = company
    ? Object.fromEntries(company.criteria.map((c) => [c.key, { label: c.label, weight: c.weight }]))
    : {};

  async function handleDraft() {
    setError("");
    setDrafting(true);
    try {
      const result = await scenarios.draft(companyId);
      setScenarioList(result);
    } catch (e) {
      setError(`Drafting failed: ${e.message}`);
    } finally {
      setDrafting(false);
    }
  }

  const handleUpdate = useCallback(async (scenarioId, payload) => {
    const updated = await scenarios.update(companyId, scenarioId, payload);
    setScenarioList((prev) =>
      prev.map((s) => (s.id === scenarioId ? updated : s))
    );
    return updated;
  }, [companyId]);

  const handleDelete = useCallback(async (scenarioId) => {
    await scenarios.remove(companyId, scenarioId);
    setScenarioList((prev) => prev.filter((s) => s.id !== scenarioId));
  }, [companyId]);

  function updateForm(field, value) {
    setForm((f) => ({ ...f, [field]: value }));
  }

  function toggleDim(key) {
    setForm((f) => ({
      ...f,
      scoring_dims: f.scoring_dims.includes(key)
        ? f.scoring_dims.filter((k) => k !== key)
        : [...f.scoring_dims, key],
    }));
  }

  async function handleCreate(e) {
    e.preventDefault();
    setCreateError("");
    setCreating(true);
    try {
      const created = await scenarios.create(companyId, form);
      setScenarioList((prev) => [...prev, created]);
      setShowCreate(false);
      setForm(BLANK_FORM);
    } catch (err) {
      setCreateError(err.message);
    } finally {
      setCreating(false);
    }
  }

  if (loading) return <GeneratingScreen note="Loading scenarios…" />;

  const llmCount = scenarioList.filter((s) => s.is_llm_drafted).length;
  const authoredCount = scenarioList.length - llmCount;

  return (
    <main className="container" style={{ maxWidth: 1000 }}>
      {/* Breadcrumb */}
      <div className="label-mono" style={{ marginBottom: 12, display: "flex", gap: 8, alignItems: "center" }}>
        <button
          onClick={() => nav("/manager")}
          style={{ background: "none", border: "none", fontFamily: FONT_MONO, fontSize: 11, letterSpacing: "0.18em", textTransform: "uppercase", color: COLORS.muted, cursor: "pointer", padding: 0 }}
        >
          Manager
        </button>
        <span style={{ color: COLORS.rule }}>›</span>
        <button
          onClick={() => nav(`/manager/positions/${companyId}/team`)}
          style={{ background: "none", border: "none", fontFamily: FONT_MONO, fontSize: 11, letterSpacing: "0.18em", textTransform: "uppercase", color: COLORS.muted, cursor: "pointer", padding: 0 }}
        >
          {company?.name || companyId}
        </button>
        <span style={{ color: COLORS.rule }}>›</span>
        <span>Scenarios</span>
      </div>

      <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between", gap: 24, flexWrap: "wrap", marginBottom: 8 }}>
        <div>
          <h2 style={{ fontFamily: FONT_DISPLAY, fontSize: 38, fontWeight: 500, letterSpacing: "-0.015em", lineHeight: 1.1, margin: "0 0 6px" }}>
            Scenario Library
          </h2>
          {company && (
            <div style={{ color: COLORS.muted, fontSize: 15 }}>
              {company.name} · {company.role}
            </div>
          )}
        </div>

        <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
          <button
            className="ghost"
            onClick={() => { setForm(BLANK_FORM); setShowCreate(true); setCreateError(""); }}
            style={{ padding: "12px 20px" }}
          >
            + Hand-author
          </button>
          <button
            className="primary"
            onClick={handleDraft}
            disabled={drafting}
          >
            {drafting ? "Drafting…" : scenarioList.length > 0 ? "Re-draft from artifacts" : "Draft from artifacts"}
          </button>
        </div>
      </div>

      <p style={{ color: COLORS.muted, fontStyle: "italic", fontSize: 15, margin: "0 0 8px" }}>
        Scenarios probe specific criteria in realistic workplace situations. The LLM drafts from
        your artifacts; you review and edit before running simulations.
      </p>

      <hr className="rule-thick" style={{ margin: "16px 0 28px" }} />

      {error && (
        <div style={{ color: COLORS.accent, fontStyle: "italic", marginBottom: 24 }}>{error}</div>
      )}

      {/* Drafting animation */}
      {drafting && <DraftingAnimation />}

      {/* Empty state */}
      {!drafting && scenarioList.length === 0 && (
        <div style={{ padding: "64px 0", textAlign: "center", borderTop: `1px solid ${COLORS.rule}`, borderBottom: `1px solid ${COLORS.rule}` }}>
          <div style={{ fontFamily: FONT_DISPLAY, fontSize: 22, color: COLORS.muted, fontStyle: "italic", marginBottom: 16 }}>
            No scenarios yet.
          </div>
          <p style={{ color: COLORS.muted, fontSize: 15, maxWidth: 420, margin: "0 auto 24px" }}>
            Click "Draft from artifacts" to generate 5–8 situation scenarios grounded in the role
            spec and team structure, or hand-author your own.
          </p>
          <button className="primary" onClick={handleDraft}>
            Draft from artifacts →
          </button>
        </div>
      )}

      {/* Scenario list */}
      {!drafting && scenarioList.length > 0 && (
        <>
          <div className="label-mono" style={{ marginBottom: 16 }}>
            {scenarioList.length} scenario{scenarioList.length !== 1 ? "s" : ""} ·{" "}
            {llmCount} LLM-drafted · {authoredCount} hand-authored
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {scenarioList
              .slice()
              .sort((a, b) => a.ordering - b.ordering)
              .map((s) => (
                <ScenarioCard
                  key={s.id}
                  scenario={s}
                  criteriaIndex={criteriaIndex}
                  onUpdate={handleUpdate}
                  onDelete={handleDelete}
                />
              ))}
          </div>
          <div style={{ marginTop: 28, padding: "14px 0", borderTop: `1px solid ${COLORS.rule}`, color: COLORS.muted, fontSize: 13, fontStyle: "italic" }}>
            Re-drafting replaces LLM-drafted scenarios only. Hand-authored scenarios are preserved.
          </div>
        </>
      )}

      {/* Create modal */}
      {showCreate && (
        <CreateModal
          form={form}
          onChange={updateForm}
          onToggleDim={toggleDim}
          criteriaIndex={criteriaIndex}
          onSubmit={handleCreate}
          onClose={() => setShowCreate(false)}
          creating={creating}
          error={createError}
        />
      )}
    </main>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function DraftingAnimation() {
  const LABELS = [
    "Reading role specification…",
    "Identifying value tensions…",
    "Mapping criteria to situations…",
    "Calibrating difficulty mix…",
    "Grounding scenarios in artifacts…",
  ];
  const [tick, setTick] = React.useState(0);
  React.useEffect(() => {
    const id = setInterval(() => setTick((n) => n + 1), 1800);
    return () => clearInterval(id);
  }, []);
  return (
    <div style={{ padding: "60px 0", textAlign: "center", borderTop: `1px solid ${COLORS.rule}`, borderBottom: `1px solid ${COLORS.rule}`, marginBottom: 32 }}>
      <div className="label-mono" style={{ marginBottom: 18 }}>
        <span className="pulse-dot" />&nbsp;<span className="pulse-dot" />&nbsp;<span className="pulse-dot" />
      </div>
      <div style={{ fontFamily: FONT_DISPLAY, fontSize: 24, fontStyle: "italic", color: COLORS.muted }}>
        {LABELS[tick % LABELS.length]}
      </div>
    </div>
  );
}

function CreateModal({ form, onChange, onToggleDim, criteriaIndex, onSubmit, onClose, creating, error }) {
  return (
    <div
      style={{
        position: "fixed", inset: 0, background: "rgba(26,24,20,0.6)",
        display: "flex", alignItems: "center", justifyContent: "center",
        zIndex: 1000, padding: 24,
      }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div
        style={{
          background: "#f7f3ec", border: `2px solid ${COLORS.ink}`,
          padding: "32px 36px", maxWidth: 640, width: "100%",
          maxHeight: "90vh", overflowY: "auto",
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 24 }}>
          <div className="label-mono">Hand-author scenario</div>
          <button
            onClick={onClose}
            style={{ background: "none", border: "none", fontSize: 20, cursor: "pointer", color: COLORS.muted }}
          >
            ×
          </button>
        </div>

        <form onSubmit={onSubmit} style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <div>
            <div className="label-mono" style={{ marginBottom: 4 }}>Title</div>
            <input className="ed" required value={form.title} onChange={(e) => onChange("title", e.target.value)} />
          </div>

          <div>
            <div className="label-mono" style={{ marginBottom: 6 }}>Type</div>
            <div style={{ display: "flex", gap: 8 }}>
              {Object.entries(TYPE_LABELS).map(([k, label]) => (
                <button
                  key={k}
                  type="button"
                  onClick={() => onChange("scenario_type", k)}
                  style={{
                    padding: "6px 14px", fontFamily: FONT_MONO, fontSize: 11,
                    letterSpacing: "0.12em", textTransform: "uppercase", cursor: "pointer",
                    border: `1px solid ${form.scenario_type === k ? COLORS.ink : COLORS.rule}`,
                    background: form.scenario_type === k ? COLORS.ink : "transparent",
                    color: form.scenario_type === k ? "#fff" : COLORS.ink,
                  }}
                >
                  {label}
                </button>
              ))}
              <label style={{ fontFamily: FONT_MONO, fontSize: 10, display: "flex", alignItems: "center", gap: 6, marginLeft: 8, color: COLORS.muted }}>
                Max turns:
                <input
                  type="number"
                  value={form.max_turns}
                  onChange={(e) => onChange("max_turns", Number(e.target.value))}
                  style={{ width: 52, fontFamily: FONT_MONO, fontSize: 12, padding: "2px 6px", border: `1px solid ${COLORS.rule}` }}
                />
              </label>
            </div>
          </div>

          <div>
            <div className="label-mono" style={{ marginBottom: 4 }}>Scenario prompt</div>
            <textarea className="ed" required value={form.prompt} onChange={(e) => onChange("prompt", e.target.value)} style={{ minHeight: 80 }} />
          </div>

          <div>
            <div className="label-mono" style={{ marginBottom: 4 }}>Candidate role</div>
            <textarea className="ed" required value={form.candidate_role} onChange={(e) => onChange("candidate_role", e.target.value)} style={{ minHeight: 60 }} />
          </div>

          <div>
            <div className="label-mono" style={{ marginBottom: 4 }}>Expected arc</div>
            <textarea className="ed" required value={form.expected_arc} onChange={(e) => onChange("expected_arc", e.target.value)} style={{ minHeight: 60 }} />
          </div>

          {Object.keys(criteriaIndex).length > 0 && (
            <div>
              <div className="label-mono" style={{ marginBottom: 6 }}>Scoring dimensions</div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                {Object.entries(criteriaIndex).map(([key, { label }]) => (
                  <button
                    key={key}
                    type="button"
                    onClick={() => onToggleDim(key)}
                    style={{
                      padding: "4px 12px", fontFamily: FONT_MONO, fontSize: 10,
                      letterSpacing: "0.1em", textTransform: "uppercase", cursor: "pointer",
                      border: `1px solid ${form.scoring_dims.includes(key) ? COLORS.ink : COLORS.rule}`,
                      background: form.scoring_dims.includes(key) ? COLORS.ink : "transparent",
                      color: form.scoring_dims.includes(key) ? "#fff" : COLORS.muted,
                    }}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>
          )}

          <div>
            <div className="label-mono" style={{ marginBottom: 4 }}>Artifact grounding (optional)</div>
            <textarea className="ed" value={form.grounding} onChange={(e) => onChange("grounding", e.target.value)} style={{ minHeight: 50 }} />
          </div>

          {error && (
            <div style={{ color: COLORS.accent, fontStyle: "italic", fontSize: 14 }}>{error}</div>
          )}

          <div style={{ display: "flex", gap: 10, justifyContent: "flex-end", paddingTop: 8 }}>
            <button type="button" className="ghost" onClick={onClose} disabled={creating} style={{ padding: "10px 20px" }}>
              Cancel
            </button>
            <button type="submit" className="primary" disabled={creating} style={{ padding: "10px 24px" }}>
              {creating ? "Creating…" : "Create scenario"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
