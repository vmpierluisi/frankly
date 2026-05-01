import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { COLORS, FONT_DISPLAY, FONT_MONO } from "../design.js";
import { candidates, companies } from "../api.js";
import { GeneratingScreen } from "../components/Widgets.jsx";
import PositionLeaderboard from "../components/PositionLeaderboard.jsx";

// Manager dashboard — position-first leaderboard surface.
//
// Flow:
//   1. Manager selects a position from the grid.
//   2. Leaderboard renders immediately, showing V2 fit reports ranked by score.
//   3. Rows grow over time as candidates complete intake and simulations finish.
//   4. Click any row to expand FitProfileV2 inline.

export default function ManagerDashboard() {
  const nav = useNavigate();
  const [companyList, setCompanyList] = useState([]);
  const [seedCount, setSeedCount] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selectedCompany, setSelectedCompany] = useState(null);

  useEffect(() => {
    Promise.all([
      companies.list(),
      candidates.list({ is_seed: true }),
    ])
      .then(([cos, seeds]) => {
        setCompanyList(cos);
        setSeedCount(seeds.length);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  // Reset leaderboard when a different position is selected.
  useEffect(() => {
    setError("");
  }, [selectedCompany]);

  if (loading) return <GeneratingScreen note="Loading dashboard…" />;

  const company = companyList.find((c) => c.id === selectedCompany);

  return (
    <main className="container" style={{ maxWidth: 1280 }}>
      <div className="label-mono" style={{ marginBottom: 12 }}>Manager · Dashboard</div>
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
        Select a position. Review the candidate leaderboard.
      </h2>
      <p style={{ color: COLORS.muted, fontStyle: "italic", marginBottom: 32, fontSize: 17 }}>
        Candidates are ranked by simulation fit score — updated automatically as
        new candidates complete intake. Screening signal only; not a hiring decision.
      </p>
      <hr className="rule-thick" style={{ margin: "0 0 32px" }} />

      {/* ── Positions grid ──────────────────────────────────────────────────── */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "baseline",
          marginBottom: 12,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <div className="label-mono">Positions ({companyList.length})</div>
          {seedCount !== null && seedCount > 0 && (
            <div
              style={{
                fontFamily: FONT_MONO,
                fontSize: 10,
                letterSpacing: "0.12em",
                textTransform: "uppercase",
                color: COLORS.muted,
                border: `1px solid ${COLORS.rule}`,
                padding: "2px 8px",
              }}
            >
              Pool: {seedCount}
            </div>
          )}
        </div>
        <button
          className="ghost"
          onClick={() => nav("/manager/templates")}
          style={{ padding: "8px 14px" }}
        >
          + New position
        </button>
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
          gap: 8,
          marginBottom: 28,
        }}
      >
        {companyList.map((c) => (
          <PositionCard
            key={c.id}
            company={c}
            selected={selectedCompany === c.id}
            onSelect={() => setSelectedCompany(c.id)}
            onEdit={(e) => { e.stopPropagation(); nav(`/manager/templates/${c.id}`); }}
            onViewTeam={(e) => { e.stopPropagation(); nav(`/manager/companies/${c.id}/team`); }}
            onViewScenarios={(e) => { e.stopPropagation(); nav(`/manager/companies/${c.id}/scenarios`); }}
          />
        ))}
        {companyList.length === 0 && (
          <p style={{ color: COLORS.muted, fontSize: 14, gridColumn: "1/-1" }}>
            No positions yet. Create one with "+ New position".
          </p>
        )}
      </div>

      {/* ── Action bar (shown once a position is selected) ──────────────────── */}
      {selectedCompany && (
        <div
          className="card"
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 16,
            marginBottom: 32,
            flexWrap: "wrap",
          }}
        >
          <div style={{ flex: 1, minWidth: 240 }}>
            <div className="label-mono" style={{ marginBottom: 4 }}>Selected position</div>
            <div style={{ fontFamily: FONT_DISPLAY, fontSize: 20, fontWeight: 500 }}>
              {company?.name}
            </div>
            <div style={{ color: COLORS.muted, fontSize: 14 }}>{company?.role}</div>
          </div>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            <button
              className="ghost"
              onClick={() => nav(`/manager/companies/${selectedCompany}/team`)}
              style={{ padding: "14px 20px" }}
            >
              Team
            </button>
            <button
              className="ghost"
              onClick={() => nav(`/manager/companies/${selectedCompany}/scenarios`)}
              style={{ padding: "14px 20px" }}
            >
              Scenarios
            </button>
            <button
              className="ghost"
              onClick={() => nav(`/manager/templates/${selectedCompany}`)}
              style={{ padding: "14px 20px" }}
            >
              Edit position
            </button>
          </div>
        </div>
      )}

      {error && (
        <div style={{ color: COLORS.accent, marginBottom: 24, fontStyle: "italic" }}>{error}</div>
      )}

      {/* ── Leaderboard ─────────────────────────────────────────────────────── */}
      {selectedCompany ? (
        <PositionLeaderboard companyId={selectedCompany} />
      ) : (
        <div
          style={{
            padding: "64px 0",
            textAlign: "center",
            borderTop: `1px solid ${COLORS.rule}`,
            color: COLORS.muted,
            fontStyle: "italic",
          }}
        >
          Select a position above to see its candidate leaderboard.
        </div>
      )}
    </main>
  );
}

// ── Sub-components ──────────────────────────────────────────────────────────

function PositionCard({ company, selected, onSelect, onEdit, onViewTeam, onViewScenarios }) {
  return (
    <div
      onClick={onSelect}
      style={{
        display: "flex",
        alignItems: "flex-start",
        justifyContent: "space-between",
        gap: 10,
        padding: "14px 16px",
        border: `1px solid ${selected ? COLORS.ink : COLORS.rule}`,
        background: selected ? "#fff" : "transparent",
        cursor: "pointer",
        transition: "border 0.15s, background 0.15s",
      }}
    >
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontFamily: FONT_DISPLAY, fontSize: 18, fontWeight: 500 }}>
          {company.name}
        </div>
        <div style={{ color: COLORS.muted, fontSize: 13 }}>{company.role}</div>
        {company.tagline && (
          <div style={{ color: COLORS.muted, fontSize: 12, fontStyle: "italic", marginTop: 2 }}>
            {company.tagline}
          </div>
        )}
        {(company.role_family || company.target_seniority) && (
          <div
            style={{
              fontFamily: FONT_MONO,
              fontSize: 9,
              color: COLORS.muted,
              textTransform: "uppercase",
              letterSpacing: "0.1em",
              marginTop: 4,
            }}
          >
            {company.role_family?.replace(/_/g, " ")}
            {company.target_seniority && ` · ${company.target_seniority}`}
            {company.is_open === false && " · closed"}
          </div>
        )}
      </div>
      <div style={{ display: "flex", gap: 4, flexShrink: 0 }}>
        <button
          className="ghost"
          style={{ padding: "4px 10px", fontSize: 11, whiteSpace: "nowrap" }}
          onClick={onViewTeam}
        >
          Team
        </button>
        <button
          className="ghost"
          style={{ padding: "4px 10px", fontSize: 11, whiteSpace: "nowrap" }}
          onClick={onEdit}
        >
          Edit
        </button>
      </div>
    </div>
  );
}
