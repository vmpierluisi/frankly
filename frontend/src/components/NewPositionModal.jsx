import React, { useEffect, useState } from "react";
import { COLORS, FONT_DISPLAY, FONT_MONO } from "../design.js";
import { organizations } from "../api.js";

/**
 * Roadmap 2 / PR #2d.2 — Quick "+ New Position" modal.
 *
 * Lets a recruiter pick an organization + team without leaving the page,
 * then hands off to TemplateSetup (`/manager/templates?team_id=…`) which
 * is already the position-only form. Keeps the Settings flow available
 * for users who prefer to drill in by hand.
 */
export default function NewPositionModal({ open, onClose, onPick }) {
  const [orgs, setOrgs] = useState(null);
  const [error, setError] = useState("");
  const [orgId, setOrgId] = useState("");
  const [teams, setTeams] = useState([]);
  const [teamId, setTeamId] = useState("");
  const [loadingTeams, setLoadingTeams] = useState(false);

  useEffect(() => {
    if (!open) return;
    setError("");
    setOrgId("");
    setTeamId("");
    setTeams([]);
    organizations
      .list()
      .then(setOrgs)
      .catch((e) => setError(e.message));
  }, [open]);

  useEffect(() => {
    if (!orgId) {
      setTeams([]);
      setTeamId("");
      return;
    }
    setLoadingTeams(true);
    organizations
      .listTeams(orgId)
      .then((rows) => {
        setTeams(rows);
        setTeamId(rows.length === 1 ? rows[0].id : "");
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoadingTeams(false));
  }, [orgId]);

  if (!open) return null;

  const selectedOrg = (orgs || []).find((o) => o.id === orgId);
  const canContinue = !!orgId && !!teamId;

  return (
    <div
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(26,24,20,0.55)",
        zIndex: 100,
        display: "flex",
        justifyContent: "center",
        alignItems: "flex-start",
        padding: "60px 20px 20px",
      }}
    >
      <div
        style={{
          background: COLORS.cardBg,
          width: "100%",
          maxWidth: 540,
          padding: "28px 32px 32px",
          border: `1px solid ${COLORS.rule}`,
          borderTop: `2px solid ${COLORS.ink}`,
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "flex-start",
            justifyContent: "space-between",
            marginBottom: 20,
          }}
        >
          <div>
            <div className="label-mono">New Position</div>
            <div style={{ color: COLORS.muted, fontSize: 13, marginTop: 4 }}>
              Pick where this role lives. You'll fill in role spec, criteria,
              and skills next.
            </div>
          </div>
          <button
            onClick={onClose}
            aria-label="Close"
            style={{
              background: "transparent",
              border: "none",
              cursor: "pointer",
              fontSize: 28,
              color: COLORS.muted,
              lineHeight: 1,
            }}
          >
            ×
          </button>
        </div>

        {error && (
          <div style={{ color: COLORS.accent, marginBottom: 16, fontSize: 13 }}>
            {error}
          </div>
        )}

        {orgs === null ? (
          <div style={{ color: COLORS.muted, fontStyle: "italic" }}>
            Loading organizations…
          </div>
        ) : (
          <>
            <Field label="Organization">
              <select
                className="ed"
                value={orgId}
                onChange={(e) => setOrgId(e.target.value)}
                style={selectStyle}
              >
                <option value="">— Select organization —</option>
                {(orgs || []).map((o) => (
                  <option key={o.id} value={o.id}>
                    {o.name}
                  </option>
                ))}
              </select>
              {(orgs || []).length === 0 && (
                <div
                  style={{
                    color: COLORS.muted,
                    fontSize: 12,
                    marginTop: 6,
                    fontStyle: "italic",
                  }}
                >
                  No organizations yet — create one in Settings first.
                </div>
              )}
            </Field>

            <Field label="Team">
              <select
                className="ed"
                value={teamId}
                onChange={(e) => setTeamId(e.target.value)}
                disabled={!orgId || loadingTeams}
                style={selectStyle}
              >
                <option value="">
                  {loadingTeams
                    ? "Loading teams…"
                    : !orgId
                    ? "— Select organization first —"
                    : teams.length === 0
                    ? "— No teams in this org —"
                    : "— Select team —"}
                </option>
                {teams.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name}
                  </option>
                ))}
              </select>
            </Field>

            {selectedOrg && (
              <div
                style={{
                  marginTop: 4,
                  padding: "8px 12px",
                  background: COLORS.paper,
                  border: `1px solid ${COLORS.rule}`,
                  fontFamily: FONT_MONO,
                  fontSize: 11,
                  color: COLORS.muted,
                  letterSpacing: "0.04em",
                }}
              >
                Position will be created under{" "}
                <strong style={{ color: COLORS.ink, fontWeight: 500 }}>
                  {selectedOrg.name}
                </strong>
                {teams.find((t) => t.id === teamId) && (
                  <>
                    {" / "}
                    <strong style={{ color: COLORS.ink, fontWeight: 500 }}>
                      {teams.find((t) => t.id === teamId).name}
                    </strong>
                  </>
                )}
              </div>
            )}
          </>
        )}

        <div style={{ display: "flex", gap: 12, marginTop: 24 }}>
          <button
            className="primary"
            disabled={!canContinue}
            onClick={() =>
              onPick({
                org: selectedOrg,
                team: teams.find((t) => t.id === teamId),
              })
            }
          >
            Continue →
          </button>
          <button className="ghost" onClick={onClose}>
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}

function Field({ label, children }) {
  return (
    <div style={{ marginBottom: 18 }}>
      <label className="label-mono" style={{ display: "block", marginBottom: 6 }}>
        {label}
      </label>
      {children}
    </div>
  );
}

const selectStyle = {
  appearance: "none",
  background: COLORS.cardBg,
  cursor: "pointer",
  paddingRight: 32,
};
