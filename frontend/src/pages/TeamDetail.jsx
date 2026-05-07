import React, { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { COLORS, FONT_DISPLAY, FONT_MONO } from "../design.js";
import { teams } from "../api.js";
import { GeneratingScreen } from "../components/Widgets.jsx";

/**
 * Roadmap 2 / PR #2d.2 — Team detail page.
 *
 * Edit team-level artefacts (name, team_structure, sample_comms),
 * see all positions hiring into this team, and reach the synthetic team
 * + scenarios management screens.
 */
export default function TeamDetail() {
  const { teamId } = useParams();
  const nav = useNavigate();
  const [team, setTeam] = useState(null);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!teamId) return;
    teams
      .get(teamId)
      .then(setTeam)
      .catch((e) => setError(e.message));
  }, [teamId]);

  async function save(fields) {
    setSaving(true);
    try {
      const updated = await teams.update(teamId, fields);
      setTeam({ ...team, ...updated });
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  }

  if (!team && !error) return <GeneratingScreen note="Loading team…" />;

  return (
    <main className="container" style={{ maxWidth: 880 }}>
      <div className="label-mono" style={{ marginBottom: 12 }}>
        Manager · Settings · Team
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
        {team?.name || "Team"}
      </h2>
      <p style={{ color: COLORS.muted, fontSize: 16, marginBottom: 28 }}>
        Team-level artefacts feed into the simulation team synthesis +
        scenario library. Shared by every position under this team.
      </p>

      {error && (
        <div style={{ color: COLORS.accent, marginBottom: 20, fontStyle: "italic" }}>
          {error}
        </div>
      )}

      {team && <TeamIdentityCard team={team} saving={saving} onSave={save} />}
      {team && (
        <PositionsCard
          team={team}
          onOpenPosition={(id) => nav(`/manager/templates/${id}`)}
          onCreatePosition={() =>
            nav(`/manager/templates?team_id=${teamId}`)
          }
        />
      )}
      {team && (
        <SimulationLinksCard
          team={team}
          onOpenTeammates={(positionId) =>
            nav(`/manager/positions/${positionId}/team`)
          }
          onOpenScenarios={(positionId) =>
            nav(`/manager/positions/${positionId}/scenarios`)
          }
        />
      )}

      <div style={{ marginTop: 36 }}>
        <button
          className="ghost"
          onClick={() => nav(`/manager/organizations/${team.organization_id}`)}
        >
          ← Back to organization
        </button>
      </div>
    </main>
  );
}

function TeamIdentityCard({ team, saving, onSave }) {
  const [name, setName] = useState(team.name);
  const [structure, setStructure] = useState(team.artifact_team_structure || "");
  const [comms, setComms] = useState(team.artifact_sample_comms || "");
  const dirty =
    name !== team.name ||
    structure !== (team.artifact_team_structure || "") ||
    comms !== (team.artifact_sample_comms || "");

  return (
    <section className="card" style={{ marginBottom: 28 }}>
      <div className="label-mono" style={{ marginBottom: 16 }}>
        Team identity
      </div>
      <Field label="Name">
        <input className="ed" value={name} onChange={(e) => setName(e.target.value)} />
      </Field>
      <Field label="Team structure">
        <textarea
          className="ed"
          value={structure}
          placeholder="Hierarchy, decision rituals, who-reads-what."
          onChange={(e) => setStructure(e.target.value)}
        />
      </Field>
      <Field label="Sample communication">
        <textarea
          className="ed"
          value={comms}
          placeholder="An IC memo excerpt, a Slack thread, a partner note — paste an unredacted snippet that shows the texture."
          onChange={(e) => setComms(e.target.value)}
        />
      </Field>

      {dirty && (
        <button
          className="primary"
          disabled={saving}
          onClick={() =>
            onSave({
              name,
              artifact_team_structure: structure,
              artifact_sample_comms: comms,
            })
          }
        >
          {saving ? "Saving…" : "Save team →"}
        </button>
      )}
    </section>
  );
}

function PositionsCard({ team, onOpenPosition, onCreatePosition }) {
  const positions = team.positions || [];
  return (
    <section className="card" style={{ marginBottom: 28 }}>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: 16,
        }}
      >
        <div className="label-mono">Positions on this team</div>
        <button
          className="ghost"
          onClick={onCreatePosition}
          style={{ padding: "8px 14px", fontSize: 11 }}
        >
          + New position
        </button>
      </div>
      {positions.length === 0 ? (
        <div style={{ color: COLORS.muted, fontStyle: "italic" }}>
          No positions yet. Create one to start hiring.
        </div>
      ) : (
        <ul style={{ margin: 0, padding: 0, listStyle: "none" }}>
          {positions.map((p) => (
            <li
              key={p.id}
              onClick={() => onOpenPosition(p.id)}
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
                  {p.role}
                </div>
                <div
                  style={{
                    color: COLORS.muted,
                    fontSize: 12,
                    fontFamily: FONT_MONO,
                    textTransform: "uppercase",
                    letterSpacing: "0.1em",
                  }}
                >
                  {[p.role_family?.replace(/_/g, " "), p.target_seniority]
                    .filter(Boolean)
                    .join(" · ")}
                  {p.is_open === false && " · closed"}
                </div>
              </div>
              <span className="label-mono" style={{ color: COLORS.ink, fontSize: 11 }}>
                edit →
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function SimulationLinksCard({ team, onOpenTeammates, onOpenScenarios }) {
  // The legacy /companies/:id/team and /companies/:id/scenarios routes
  // resolve teammates / scenarios by team_id internally — but they look
  // up Company first, so we need a Position id (Company.id) from this
  // team. Pick the first position; if there are none, prompt to create one.
  const firstPosition = (team.positions || [])[0];

  if (!firstPosition) {
    return (
      <section className="card">
        <div className="label-mono" style={{ marginBottom: 16 }}>
          Simulation
        </div>
        <p style={{ color: COLORS.muted, fontSize: 14, margin: 0 }}>
          Add at least one position above to set up synthetic teammates and
          scenarios for this team.
        </p>
      </section>
    );
  }

  return (
    <section className="card">
      <div className="label-mono" style={{ marginBottom: 16 }}>
        Simulation
      </div>
      <p style={{ color: COLORS.muted, fontSize: 14, margin: "0 0 16px" }}>
        Synthesised teammates and scenarios are shared by every position on this team.
      </p>
      <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
        <button
          className="ghost"
          onClick={() => onOpenTeammates(firstPosition.id)}
          style={{ padding: "12px 18px" }}
        >
          Synthetic teammates →
        </button>
        <button
          className="ghost"
          onClick={() => onOpenScenarios(firstPosition.id)}
          style={{ padding: "12px 18px" }}
        >
          Scenario library →
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
