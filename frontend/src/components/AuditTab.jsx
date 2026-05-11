import React, { useEffect, useMemo, useState } from "react";
import { COLORS, FONT_DISPLAY, FONT_MONO } from "../design.js";
import { audit as auditApi, API_BASE } from "../api.js";
import { ReliabilitySection, FairnessSection, Empty } from "./AuditCharts.jsx";

/**
 * Roadmap 2 / PR #6 follow-up — Audit tab on the Manager dashboard.
 *
 * Single surface, four scopes:
 *   - "all"      → every audit-enabled position rolled up.
 *   - "open"     → audit-enabled open vacancies only.
 *   - "closed"   → audit-enabled closed vacancies only.
 *   - "position" → a single chosen position (uses the per-position
 *                  endpoints; same chart primitives).
 *
 * Deep-link via ?tab=audit&scope=...&positionId=...
 *
 * Reads the company list to populate the position picker AND to detect
 * whether any org has the audit toggle on — if none, we render an
 * empty-state pointing the recruiter to Org Settings.
 */
export default function AuditTab({ companyList = [], initialScope, initialPositionId, onScopeChange }) {
  const [scope, setScope] = useState(initialScope || "all");
  const [positionId, setPositionId] = useState(initialPositionId || "");
  const [reliability, setReliability] = useState(null);
  const [fairness, setFairness] = useState(null);
  const [err, setErr] = useState("");

  // The positions list already carries the org-level toggle (see
  // backend/app/routes/positions.py::list_companies). Filter to the
  // audit-enabled positions; if none, render an empty state.
  const eligiblePositions = (companyList || []).filter(
    (p) => p.reliability_audit_enabled,
  );
  const auditOnAnywhere = eligiblePositions.length > 0;

  useEffect(() => {
    setErr("");
    setReliability(null);
    setFairness(null);
    if (scope === "position") {
      if (!positionId) return;
      auditApi.reliability(positionId).then(setReliability).catch((e) => setErr(e.message));
      auditApi.fairness(positionId).then(setFairness).catch((e) => setErr(e.message));
    } else {
      auditApi.reliabilityOverview(scope).then(setReliability).catch((e) => setErr(e.message));
      auditApi.fairnessOverview(scope).then(setFairness).catch((e) => setErr(e.message));
    }
  }, [scope, positionId]);

  const exportUrl = useMemo(() => {
    if (scope === "position" && positionId) {
      return `${API_BASE}/audit/positions/${positionId}/export.csv`;
    }
    return `${API_BASE}/audit/overview/export.csv?scope=${encodeURIComponent(scope)}`;
  }, [scope, positionId]);

  function changeScope(next, nextPositionId = "") {
    setScope(next);
    setPositionId(nextPositionId);
    onScopeChange && onScopeChange({ scope: next, positionId: nextPositionId });
  }

  // No audit-enabled org? Render an empty-state.
  if (!auditOnAnywhere) {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: 22 }}>
        <Empty>
          No organization has the Reliability + Fairness audit enabled yet.
          Open <strong>Settings → Organization</strong>, toggle{" "}
          <em>"Enable the recruiter-only audit panel"</em>, save, and this
          tab will populate.
        </Empty>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 22 }}>
      <ScopePicker
        scope={scope}
        positionId={positionId}
        positions={eligiblePositions || []}
        onChange={changeScope}
      />

      {err && (
        <div
          style={{
            padding: 14,
            border: `1px solid ${COLORS.accent}`,
            color: COLORS.accent,
            fontSize: 13,
          }}
        >
          {err}
        </div>
      )}

      {reliability && <ReliabilitySection data={reliability} />}
      {fairness && <FairnessSection data={fairness} />}

      <div>
        <a
          href={exportUrl}
          style={{
            display: "inline-block",
            background: COLORS.ink,
            color: "#fff",
            textDecoration: "none",
            padding: "10px 18px",
            fontSize: 14,
            fontWeight: 500,
          }}
        >
          Export audit CSV
        </a>
      </div>
    </div>
  );
}


function ScopePicker({ scope, positionId, positions, onChange }) {
  const segs = [
    { id: "all", label: "All vacancies" },
    { id: "open", label: "Open" },
    { id: "closed", label: "Closed" },
  ];
  return (
    <section className="card">
      <div className="label-mono" style={{ marginBottom: 12 }}>
        Scope
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
        {segs.map((s) => (
          <button
            key={s.id}
            type="button"
            onClick={() => onChange(s.id)}
            style={{
              padding: "8px 14px",
              border: `1px solid ${scope === s.id ? COLORS.ink : COLORS.rule}`,
              background: scope === s.id ? COLORS.ink : "transparent",
              color: scope === s.id ? "#fff" : COLORS.ink,
              fontFamily: FONT_MONO,
              fontSize: 11,
              letterSpacing: "0.12em",
              textTransform: "uppercase",
              cursor: "pointer",
            }}
          >
            {s.label}
          </button>
        ))}
        <div style={{ width: 1, height: 22, background: COLORS.rule, margin: "0 4px" }} />
        <select
          value={scope === "position" ? positionId : ""}
          onChange={(e) => {
            const next = e.target.value;
            if (next) onChange("position", next);
          }}
          style={{
            padding: "8px 10px",
            border: `1px solid ${scope === "position" ? COLORS.ink : COLORS.rule}`,
            background: "transparent",
            fontFamily: "inherit",
            fontSize: 13,
            minWidth: 220,
          }}
        >
          <option value="">Pick a specific vacancy…</option>
          {positions.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name} {p.is_open === false ? "(closed)" : ""}
            </option>
          ))}
        </select>
      </div>
    </section>
  );
}
