import React, { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { COLORS, FONT_DISPLAY, FONT_MONO } from "../design.js";
import { organizations } from "../api.js";
import { GeneratingScreen } from "../components/Widgets.jsx";

/**
 * Roadmap 2 / PR #2d.2 — Org-level settings.
 *
 * One page per organization. Edit name + tagline + mission +
 * code_of_conduct (uploaded once, reused across every team / position).
 *
 * Lists the teams beneath the org with a "+ New team" affordance. Click
 * a team → /manager/teams/:teamId.
 */
export default function OrganizationSettings() {
  const { orgId } = useParams();
  const nav = useNavigate();
  const [org, setOrg] = useState(null);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [creatingTeam, setCreatingTeam] = useState(false);
  const [newTeamName, setNewTeamName] = useState("");

  useEffect(() => {
    if (!orgId) return;
    organizations
      .get(orgId)
      .then(setOrg)
      .catch((e) => setError(e.message));
  }, [orgId]);

  async function save(fields) {
    setSaving(true);
    try {
      const updated = await organizations.update(orgId, fields);
      setOrg({ ...org, ...updated });
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  }

  async function createTeam() {
    if (!newTeamName.trim()) return;
    setCreatingTeam(true);
    try {
      await organizations.createTeam(orgId, {
        name: newTeamName.trim(),
        artifact_team_structure: "",
        artifact_sample_comms: "",
      });
      setNewTeamName("");
      const fresh = await organizations.get(orgId);
      setOrg(fresh);
    } catch (e) {
      setError(e.message);
    } finally {
      setCreatingTeam(false);
    }
  }

  if (!org && !error) return <GeneratingScreen note="Loading organization…" />;

  return (
    <main className="container" style={{ maxWidth: 880 }}>
      <div className="label-mono" style={{ marginBottom: 12 }}>
        Manager · Settings · Organization
      </div>
      <h2
        style={{
          fontFamily: FONT_DISPLAY,
          fontSize: 36,
          fontWeight: 500,
          letterSpacing: "-0.015em",
          margin: "0 0 8px",
        }}
      >
        {org?.name || "Organization"}
      </h2>
      <p style={{ color: COLORS.muted, fontSize: 16, marginBottom: 28 }}>
        Identity and culture artefacts. Uploaded once, reused across every team
        and position under this organization.
      </p>

      {error && (
        <div style={{ color: COLORS.accent, marginBottom: 20, fontStyle: "italic" }}>
          {error}
        </div>
      )}

      {org && <OrgIdentityCard org={org} saving={saving} onSave={save} />}
      {org && (
        <TeamsCard
          org={org}
          newTeamName={newTeamName}
          setNewTeamName={setNewTeamName}
          creatingTeam={creatingTeam}
          onCreateTeam={createTeam}
          onOpenTeam={(id) => nav(`/manager/teams/${id}`)}
        />
      )}

      <div style={{ marginTop: 36 }}>
        <button className="ghost" onClick={() => nav("/manager")}>
          ← Back to dashboard
        </button>
      </div>
    </main>
  );
}

function OrgIdentityCard({ org, saving, onSave }) {
  const [name, setName] = useState(org.name);
  const [tagline, setTagline] = useState(org.tagline || "");
  const [mission, setMission] = useState(org.mission || "");
  const [code, setCode] = useState(org.code_of_conduct || "");
  const dirty =
    name !== org.name ||
    tagline !== (org.tagline || "") ||
    mission !== (org.mission || "") ||
    code !== (org.code_of_conduct || "");

  return (
    <section className="card" style={{ marginBottom: 28 }}>
      <div className="label-mono" style={{ marginBottom: 16 }}>
        Identity
      </div>
      <Field label="Name">
        <input className="ed" value={name} onChange={(e) => setName(e.target.value)} />
      </Field>
      <Field label="Tagline">
        <input
          className="ed"
          value={tagline}
          placeholder="Short one-liner — what your culture actually feels like."
          onChange={(e) => setTagline(e.target.value)}
        />
      </Field>
      <Field label="Mission">
        <textarea
          className="ed"
          value={mission}
          placeholder="Why you exist. The unvarnished version."
          onChange={(e) => setMission(e.target.value)}
        />
      </Field>
      <Field label="Code of conduct">
        <textarea
          className="ed"
          value={code}
          placeholder="The behavioural baseline. What gets you fired, what gets you promoted."
          onChange={(e) => setCode(e.target.value)}
        />
      </Field>

      {dirty && (
        <button
          className="primary"
          disabled={saving}
          onClick={() =>
            onSave({
              name,
              tagline: tagline || null,
              mission,
              code_of_conduct: code,
            })
          }
        >
          {saving ? "Saving…" : "Save organization →"}
        </button>
      )}
    </section>
  );
}

function TeamsCard({
  org,
  newTeamName,
  setNewTeamName,
  creatingTeam,
  onCreateTeam,
  onOpenTeam,
}) {
  const teams = org.teams || [];
  return (
    <section className="card">
      <div className="label-mono" style={{ marginBottom: 16 }}>
        Teams
      </div>
      <p style={{ color: COLORS.muted, fontSize: 14, margin: "0 0 16px" }}>
        Each team owns its own structure, sample communication, synthetic
        teammates, and scenarios — and any number of positions hire into it.
      </p>

      {teams.length === 0 ? (
        <div style={{ color: COLORS.muted, fontStyle: "italic", marginBottom: 16 }}>
          No teams yet. Create one to start hiring.
        </div>
      ) : (
        <ul style={{ margin: 0, padding: 0, listStyle: "none", marginBottom: 16 }}>
          {teams.map((t) => (
            <li
              key={t.id}
              onClick={() => onOpenTeam(t.id)}
              style={{
                padding: "12px 4px",
                borderTop: `1px solid ${COLORS.rule}`,
                cursor: "pointer",
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
              }}
            >
              <div>
                <div style={{ fontFamily: FONT_DISPLAY, fontSize: 17, fontWeight: 500 }}>
                  {t.name}
                </div>
                <div
                  style={{
                    color: COLORS.muted,
                    fontSize: 13,
                    fontFamily: FONT_MONO,
                  }}
                >
                  {(t.artifact_team_structure || "").slice(0, 80) || "no team structure yet"}
                  {(t.artifact_team_structure || "").length > 80 ? "…" : ""}
                </div>
              </div>
              <span
                className="label-mono"
                style={{ color: COLORS.ink, fontSize: 11 }}
              >
                manage →
              </span>
            </li>
          ))}
        </ul>
      )}

      <div style={{ display: "flex", gap: 10 }}>
        <input
          className="ed"
          value={newTeamName}
          placeholder="New team name (e.g. Analytics)"
          onChange={(e) => setNewTeamName(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") onCreateTeam();
          }}
        />
        <button
          className="ghost"
          disabled={creatingTeam || !newTeamName.trim()}
          onClick={onCreateTeam}
          style={{ padding: "12px 18px", whiteSpace: "nowrap" }}
        >
          {creatingTeam ? "Creating…" : "+ New team"}
        </button>
      </div>
    </section>
  );
}

function Field({ label, children }) {
  return (
    <div style={{ marginBottom: 16 }}>
      <label className="label-mono" style={{ display: "block", marginBottom: 6 }}>
        {label}
      </label>
      {children}
    </div>
  );
}
