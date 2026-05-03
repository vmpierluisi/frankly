import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { COLORS, FONT_DISPLAY, FONT_MONO } from "../design.js";
import { candidates, companies } from "../api.js";
import { GeneratingScreen } from "../components/Widgets.jsx";
import PositionLeaderboard from "../components/PositionLeaderboard.jsx";
import Tabs from "../components/Tabs.jsx";

const TABS = [
  { id: "overview", label: "Overview" },
  { id: "positions", label: "Positions" },
];

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
  const [tab, setTab] = useState("overview");

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

  // Selecting a position from Overview should jump to the Positions tab.
  function selectPositionAndShow(id) {
    setSelectedCompany(id);
    setTab("positions");
  }

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
        {tab === "overview"
          ? "Pipeline at a glance."
          : "Select a position. Review the candidate leaderboard."}
      </h2>
      <p style={{ color: COLORS.muted, fontStyle: "italic", marginBottom: 28, fontSize: 17 }}>
        {tab === "overview"
          ? "Snapshot across all your open positions and the candidate pool."
          : "Candidates are ranked by simulation fit score — updated automatically as new candidates complete intake. Screening signal only; not a hiring decision."}
      </p>

      <Tabs value={tab} onChange={setTab} items={TABS} />

      {error && (
        <div style={{ color: COLORS.accent, marginBottom: 24, fontStyle: "italic" }}>{error}</div>
      )}

      {tab === "overview" && (
        <OverviewTab
          companies={companyList}
          seedCount={seedCount}
          onPick={selectPositionAndShow}
          onCreate={() => nav("/manager/templates")}
        />
      )}

      {tab === "positions" && (
        <PositionsTab
          nav={nav}
          companyList={companyList}
          seedCount={seedCount}
          selectedCompany={selectedCompany}
          setSelectedCompany={setSelectedCompany}
          company={company}
        />
      )}
    </main>
  );
}

// ===========================================================================
// Overview tab — KPI strip + open positions list
// ===========================================================================
function OverviewTab({ companies: companyList, seedCount, onPick, onCreate }) {
  const open = companyList.filter((c) => c.is_open !== false);
  const closed = companyList.length - open.length;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 28 }}>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
          gap: 16,
        }}
      >
        <Stat label="Open positions" value={open.length} />
        <Stat label="Total positions" value={companyList.length} />
        <Stat label="Closed" value={closed} muted />
        <Stat label="Candidate pool" value={seedCount ?? "—"} />
      </div>

      <section className="card">
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            marginBottom: 16,
          }}
        >
          <div className="label-mono">Open positions</div>
          <button
            className="ghost"
            onClick={onCreate}
            style={{ padding: "8px 14px", fontSize: 11 }}
          >
            + New position
          </button>
        </div>
        {open.length === 0 ? (
          <p style={{ color: COLORS.muted, fontSize: 14, fontStyle: "italic" }}>
            No open positions yet — click "+ New position" to set one up.
          </p>
        ) : (
          <ul style={{ margin: 0, padding: 0, listStyle: "none" }}>
            {open.map((c) => (
              <li
                key={c.id}
                onClick={() => onPick(c.id)}
                style={{
                  padding: "12px 4px",
                  borderTop: `1px solid ${COLORS.rule}`,
                  cursor: "pointer",
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  gap: 12,
                }}
              >
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontFamily: FONT_DISPLAY, fontSize: 17, fontWeight: 500 }}>
                    {c.name}
                  </div>
                  <div style={{ color: COLORS.muted, fontSize: 13 }}>{c.role}</div>
                </div>
                <div
                  style={{
                    fontFamily: FONT_MONO,
                    fontSize: 10,
                    color: COLORS.muted,
                    textTransform: "uppercase",
                    letterSpacing: "0.12em",
                    whiteSpace: "nowrap",
                  }}
                >
                  {c.role_family?.replace(/_/g, " ")}
                  {c.target_seniority && ` · ${c.target_seniority}`}
                  <span style={{ marginLeft: 12, color: COLORS.ink }}>view →</span>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function Stat({ label, value, muted = false }) {
  return (
    <div
      style={{
        background: COLORS.cardBg,
        border: `1px solid ${COLORS.rule}`,
        padding: "16px 20px",
      }}
    >
      <div className="label-mono" style={{ marginBottom: 6 }}>{label}</div>
      <div
        style={{
          fontFamily: FONT_DISPLAY,
          fontSize: 36,
          fontWeight: 500,
          lineHeight: 1,
          color: muted ? COLORS.muted : COLORS.ink,
        }}
      >
        {value}
      </div>
    </div>
  );
}

// ===========================================================================
// Positions tab — original positions grid + leaderboard
// ===========================================================================
function PositionsTab({
  nav,
  companyList,
  seedCount,
  selectedCompany,
  setSelectedCompany,
  company,
}) {
  return (
    <>
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
    </>
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
