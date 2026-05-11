import React, { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { COLORS, FONT_DISPLAY, FONT_MONO } from "../design.js";
import { positions, team } from "../api.js";
import { GeneratingScreen } from "../components/Widgets.jsx";
import TeammateCard from "../components/TeammateCard.jsx";

// Manager page: view and manage the synthetic team for a company.
// Route: /manager/companies/:positionId/team

export default function SyntheticTeamPage() {
  const { positionId } = useParams();
  const nav = useNavigate();

  const [company, setCompany] = useState(null);
  const [teammates, setTeammates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [synthesizing, setSynthesizing] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([
      positions.get(positionId),
      team.list(positionId),
    ])
      .then(([co, tm]) => {
        setCompany(co);
        setTeammates(tm);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [positionId]);

  async function handleSynthesize() {
    setError("");
    setSynthesizing(true);
    try {
      const result = await team.synthesize(positionId);
      setTeammates(result);
    } catch (e) {
      setError(`Synthesis failed: ${e.message}`);
    } finally {
      setSynthesizing(false);
    }
  }

  const handleUpdate = useCallback(async (teammateId, payload) => {
    const updated = await team.update(positionId, teammateId, payload);
    setTeammates((prev) =>
      prev.map((t) => (t.id === teammateId ? updated : t))
    );
    return updated;
  }, [positionId]);

  const handleDelete = useCallback(async (teammateId) => {
    await team.remove(positionId, teammateId);
    setTeammates((prev) => prev.filter((t) => t.id !== teammateId));
  }, [positionId]);

  if (loading) return <GeneratingScreen note="Loading team…" />;

  return (
    <main className="container" style={{ maxWidth: 1100 }}>
      {/* Breadcrumb */}
      <div
        className="label-mono"
        style={{ marginBottom: 12, display: "flex", gap: 8, alignItems: "center" }}
      >
        <button
          onClick={() => nav("/manager")}
          style={{ background: "none", border: "none", fontFamily: FONT_MONO, fontSize: 11, letterSpacing: "0.18em", textTransform: "uppercase", color: COLORS.muted, cursor: "pointer", padding: 0 }}
        >
          Manager
        </button>
        <span style={{ color: COLORS.rule }}>›</span>
        <span>{company?.name || positionId}</span>
        <span style={{ color: COLORS.rule }}>›</span>
        <span>Synthetic Team</span>
      </div>

      <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between", gap: 24, flexWrap: "wrap", marginBottom: 8 }}>
        <div>
          <h2
            style={{
              fontFamily: FONT_DISPLAY,
              fontSize: 38,
              fontWeight: 500,
              letterSpacing: "-0.015em",
              lineHeight: 1.1,
              margin: "0 0 6px",
            }}
          >
            Synthetic Team
          </h2>
          {company && (
            <div style={{ color: COLORS.muted, fontSize: 15 }}>
              {company.name} · {company.role}
            </div>
          )}
        </div>

        <div style={{ display: "flex", gap: 10 }}>
          <button
            className="ghost"
            onClick={() => nav(`/manager/positions/${positionId}/scenarios`)}
            style={{ padding: "12px 20px" }}
          >
            Scenarios →
          </button>
          <button
            className="primary"
            onClick={handleSynthesize}
            disabled={synthesizing}
            style={{ whiteSpace: "nowrap" }}
          >
            {synthesizing ? "Generating…" : teammates.length > 0 ? "Regenerate team" : "Generate team"}
          </button>
        </div>
      </div>

      <p style={{ color: COLORS.muted, fontStyle: "italic", fontSize: 15, margin: "0 0 8px" }}>
        Teammates are sampled from the company's artifact centroid. Edited teammates are preserved on
        regeneration.
      </p>

      <hr className="rule-thick" style={{ margin: "16px 0 28px" }} />

      {error && (
        <div style={{ color: COLORS.accent, fontStyle: "italic", marginBottom: 24 }}>{error}</div>
      )}

      {/* Synthesis in progress */}
      {synthesizing && (
        <SynthesisAnimation />
      )}

      {/* Empty state */}
      {!synthesizing && teammates.length === 0 && (
        <div
          style={{
            padding: "64px 0",
            textAlign: "center",
            borderTop: `1px solid ${COLORS.rule}`,
            borderBottom: `1px solid ${COLORS.rule}`,
          }}
        >
          <div style={{ fontFamily: FONT_DISPLAY, fontSize: 22, color: COLORS.muted, fontStyle: "italic", marginBottom: 16 }}>
            No teammates yet.
          </div>
          <p style={{ color: COLORS.muted, fontSize: 15, maxWidth: 440, margin: "0 auto 24px" }}>
            Click "Generate team" to create 5 synthetic teammates from this company's artifacts. The
            manager can edit any teammate after generation.
          </p>
          <button className="primary" onClick={handleSynthesize}>
            Generate team →
          </button>
        </div>
      )}

      {/* Team grid */}
      {!synthesizing && teammates.length > 0 && (
        <>
          <div
            className="label-mono"
            style={{ marginBottom: 16 }}
          >
            {teammates.length} teammate{teammates.length !== 1 ? "s" : ""} ·{" "}
            {teammates.filter((t) => t.is_edited).length} edited
          </div>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(420px, 1fr))",
              gap: 12,
            }}
          >
            {teammates
              .slice()
              .sort((a, b) => a.ordering - b.ordering)
              .map((t) => (
                <TeammateCard
                  key={t.id}
                  teammate={t}
                  positionId={positionId}
                  onUpdate={handleUpdate}
                  onDelete={handleDelete}
                />
              ))}
          </div>
          <div
            style={{
              marginTop: 32,
              padding: "16px 0",
              borderTop: `1px solid ${COLORS.rule}`,
              color: COLORS.muted,
              fontSize: 13,
              fontStyle: "italic",
            }}
          >
            Trait values are sampled from a Gaussian centroid extracted from the company artifacts.
            Regenerating replaces unedited teammates only.
          </div>
        </>
      )}
    </main>
  );
}

const SYNTHESIS_LABELS = [
  "Extracting team centroid from artifacts…",
  "Sampling trait distributions…",
  "Generating teammate personas…",
  "Grounding narratives in artifact passages…",
  "Calibrating private goals…",
];

function SynthesisAnimation() {
  const [tick, setTick] = React.useState(0);
  React.useEffect(() => {
    const id = setInterval(() => setTick((n) => n + 1), 1600);
    return () => clearInterval(id);
  }, []);
  return (
    <div
      style={{
        padding: "60px 0",
        textAlign: "center",
        borderTop: `1px solid ${COLORS.rule}`,
        borderBottom: `1px solid ${COLORS.rule}`,
        marginBottom: 32,
      }}
    >
      <div className="label-mono" style={{ marginBottom: 18 }}>
        <span className="pulse-dot" />
        &nbsp;
        <span className="pulse-dot" />
        &nbsp;
        <span className="pulse-dot" />
      </div>
      <div
        style={{
          fontFamily: FONT_DISPLAY,
          fontSize: 24,
          fontStyle: "italic",
          color: COLORS.muted,
        }}
      >
        {SYNTHESIS_LABELS[tick % SYNTHESIS_LABELS.length]}
      </div>
    </div>
  );
}
