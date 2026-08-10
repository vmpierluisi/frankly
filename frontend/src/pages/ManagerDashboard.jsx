import React, { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { COLORS, FONT_DISPLAY, FONT_MONO } from "../design.js";
import { candidates, positions, organizations } from "../api.js";
import { GeneratingScreen } from "../components/Widgets.jsx";
import PositionLeaderboard from "../components/PositionLeaderboard.jsx";
import Tabs from "../components/Tabs.jsx";
import KebabMenu from "../components/KebabMenu.jsx";
import NewPositionModal from "../components/NewPositionModal.jsx";
import NotificationBell from "../components/NotificationBell.jsx";
import AuditTab from "../components/AuditTab.jsx";

const TABS = [
  { id: "overview", label: "Overview" },
  { id: "positions", label: "Positions" },
  { id: "audit", label: "Audit" },
  { id: "settings", label: "Settings" },
];

// Manager dashboard — position-first leaderboard surface.
//
// Flow:
//   1. Manager selects a position from the grid.
//   2. Leaderboard renders immediately, showing V2 fit reports ranked by score.
//   3. Rows grow over time as candidates complete intake and simulations finish.
//   4. Click any row to expand FitProfileV3 inline.

export default function ManagerDashboard() {
  const nav = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [positionList, setPositionList] = useState([]);
  const [seedCount, setSeedCount] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selectedPosition, setSelectedPosition] = useState(null);
  // Tab is mirrored into ?tab=... so other routes can deep-link
  // ("Positions / + New position" → /manager?tab=settings).
  const initialTab = searchParams.get("tab") || "overview";
  const [tab, setTab] = useState(initialTab);

  // Keep the URL in sync when the user switches tabs in the UI.
  function changeTab(next) {
    setTab(next);
    const params = new URLSearchParams(searchParams);
    if (next === "overview") params.delete("tab");
    else params.set("tab", next);
    setSearchParams(params, { replace: true });
  }

  // React to back/forward / external nav.
  useEffect(() => {
    const t = searchParams.get("tab") || "overview";
    if (t !== tab) setTab(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  const [newPositionOpen, setNewPositionOpen] = useState(false);
  function openNewPosition() {
    setNewPositionOpen(true);
  }
  function pickedTeam({ team }) {
    setNewPositionOpen(false);
    if (team) nav(`/manager/templates?team_id=${team.id}`);
  }

  useEffect(() => {
    Promise.all([
      positions.list(),
      candidates.list({ is_seed: true }),
    ])
      .then(([cos, seeds]) => {
        setPositionList(cos);
        setSeedCount(seeds.length);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  // Reset leaderboard when a different position is selected.
  useEffect(() => {
    setError("");
  }, [selectedPosition]);

  // Selecting a position from Overview should jump to the Positions tab.
  function selectPositionAndShow(id) {
    setSelectedPosition(id);
    changeTab("positions");
  }

  if (loading) return <GeneratingScreen note="Loading dashboard…" />;

  const company = positionList.find((c) => c.id === selectedPosition);

  return (
    <main className="container" style={{ maxWidth: 1280 }}>
      <div className="label-mono" style={{ marginBottom: 12 }}>
        Manager · Dashboard
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
        {tab === "overview"
          ? "Pipeline at a glance."
          : "Select a position. Review the candidate leaderboard."}
      </h2>
      <p style={{ color: COLORS.muted, fontStyle: "italic", marginBottom: 28, fontSize: 17 }}>
        {tab === "overview"
          ? "Snapshot across all your open positions and the candidate pool."
          : "Candidates are ranked by simulation fit score — updated automatically as new candidates complete intake. Screening signal only; not a hiring decision."}
      </p>

      <div style={{ position: "relative" }}>
        <Tabs value={tab} onChange={changeTab} items={TABS} />
        <div style={{ position: "absolute", right: 0, top: 4 }}>
          <NotificationBell />
        </div>
      </div>

      {error && (
        <div style={{ color: COLORS.accent, marginBottom: 24, fontStyle: "italic" }}>{error}</div>
      )}

      {tab === "overview" && (
        <OverviewTab
          companies={positionList}
          seedCount={seedCount}
          onPick={selectPositionAndShow}
          onCreate={openNewPosition}
        />
      )}

      {tab === "positions" && (
        <PositionsTab
          nav={nav}
          onCreate={openNewPosition}
          positionList={positionList}
          seedCount={seedCount}
          selectedPosition={selectedPosition}
          setSelectedPosition={setSelectedPosition}
          company={company}
        />
      )}

      {tab === "audit" && (
        <AuditTab
          positionList={positionList}
          initialScope={searchParams.get("scope") || "all"}
          initialPositionId={searchParams.get("positionId") || ""}
          onScopeChange={({ scope, positionId }) => {
            const params = new URLSearchParams(searchParams);
            params.set("tab", "audit");
            if (scope === "all") params.delete("scope");
            else params.set("scope", scope);
            if (positionId) params.set("positionId", positionId);
            else params.delete("positionId");
            setSearchParams(params, { replace: true });
          }}
        />
      )}

      {tab === "settings" && <SettingsTab nav={nav} />}

      <NewPositionModal
        open={newPositionOpen}
        onClose={() => setNewPositionOpen(false)}
        onPick={pickedTeam}
      />
    </main>
  );
}

// ===========================================================================
// Settings tab — Organizations management.
// Roadmap 2 / PR #2d.2: org owns culture (mission, code_of_conduct, tagline);
// each org owns one or more teams; positions live under teams.
// ===========================================================================
function SettingsTab({ nav }) {
  const [orgs, setOrgs] = useState(null);
  const [error, setError] = useState("");
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");

  useEffect(() => {
    organizations
      .list()
      .then(setOrgs)
      .catch((e) => setError(e.message));
  }, []);

  async function createOrg() {
    if (!newName.trim()) return;
    setCreating(true);
    try {
      const created = await organizations.create({
        name: newName.trim(),
        tagline: null,
        mission: "",
        code_of_conduct: "",
      });
      nav(`/manager/organizations/${created.id}`);
    } catch (e) {
      setError(e.message);
    } finally {
      setCreating(false);
    }
  }

  if (orgs === null && !error) {
    return (
      <div style={{ padding: "32px 0", color: COLORS.muted, fontStyle: "italic" }}>
        Loading organizations…
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
      {error && (
        <div style={{ color: COLORS.accent, fontStyle: "italic" }}>{error}</div>
      )}

      <section className="card">
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            marginBottom: 16,
          }}
        >
          <div className="label-mono">Organizations</div>
        </div>
        <p style={{ color: COLORS.muted, fontSize: 14, margin: "0 0 18px" }}>
          Mission and code of conduct live here — uploaded once per
          organization, reused across every team and position. Click an
          organization to manage its teams.
        </p>

        {(orgs || []).length === 0 ? (
          <div style={{ color: COLORS.muted, fontStyle: "italic", marginBottom: 18 }}>
            No organizations yet.
          </div>
        ) : (
          <ul style={{ margin: 0, padding: 0, listStyle: "none", marginBottom: 18 }}>
            {(orgs || []).map((o) => (
              <li
                key={o.id}
                onClick={() => nav(`/manager/organizations/${o.id}`)}
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
                    {o.name}
                  </div>
                  {o.tagline && (
                    <div style={{ color: COLORS.muted, fontSize: 13 }}>{o.tagline}</div>
                  )}
                </div>
                <span className="label-mono" style={{ fontSize: 11, color: COLORS.ink }}>
                  manage →
                </span>
              </li>
            ))}
          </ul>
        )}

        <div style={{ display: "flex", gap: 10 }}>
          <input
            className="ed"
            value={newName}
            placeholder="New organization name"
            onChange={(e) => setNewName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") createOrg();
            }}
          />
          <button
            className="ghost"
            onClick={createOrg}
            disabled={creating || !newName.trim()}
            style={{ padding: "12px 18px", whiteSpace: "nowrap" }}
          >
            {creating ? "Creating…" : "+ New organization"}
          </button>
        </div>
      </section>
    </div>
  );
}

// ===========================================================================
// Overview tab — KPI strip + open positions list
// ===========================================================================
function OverviewTab({ companies: positionList, seedCount, onPick, onCreate }) {
  const open = positionList.filter((c) => c.is_open !== false);
  const closed = positionList.length - open.length;

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
        <Stat label="Total positions" value={positionList.length} />
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
            + New Position
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
  onCreate,
  positionList,
  seedCount,
  selectedPosition,
  setSelectedPosition,
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
          <div className="label-mono">Positions ({positionList.length})</div>
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
          onClick={onCreate}
          style={{ padding: "8px 14px" }}
        >
          + New Position
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
        {positionList.map((c) => (
          <PositionCard
            key={c.id}
            company={c}
            selected={selectedPosition === c.id}
            onSelect={() => setSelectedPosition(c.id)}
            onOpenShortlist={(e) => { e.stopPropagation(); nav(`/manager/positions/${c.id}/shortlist`); }}
            onOpenTriage={(e) => { e.stopPropagation(); nav(`/manager/positions/${c.id}/triage`); }}
            onEdit={(e) => { e.stopPropagation(); nav(`/manager/templates/${c.id}`); }}
            onViewTeam={(e) => { e.stopPropagation(); nav(`/manager/positions/${c.id}/team`); }}
            onViewScenarios={(e) => { e.stopPropagation(); nav(`/manager/positions/${c.id}/scenarios`); }}
          />
        ))}
        {positionList.length === 0 && (
          <p style={{ color: COLORS.muted, fontSize: 14, gridColumn: "1/-1" }}>
            No positions yet. Create one with "+ New position".
          </p>
        )}
      </div>

      {/* ── Leaderboard ─────────────────────────────────────────────────────── */}
      {selectedPosition ? (
        <PositionLeaderboard positionId={selectedPosition} />
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

function PositionCard({
  company,
  selected,
  onSelect,
  onOpenShortlist,
  onOpenTriage,
  onEdit,
  onViewTeam,
  onViewScenarios,
}) {
  return (
    <div
      onClick={onSelect}
      style={{
        display: "flex",
        flexDirection: "column",
        gap: 12,
        padding: "14px 16px",
        border: `1px solid ${selected ? COLORS.ink : COLORS.rule}`,
        background: selected ? "#fff" : "transparent",
        cursor: "pointer",
        transition: "border 0.15s, background 0.15s",
      }}
    >
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 10 }}>
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
        <div style={{ flexShrink: 0 }} onClick={(e) => e.stopPropagation()}>
          <KebabMenu
            ariaLabel={`Actions for ${company.name}`}
            items={[
              { label: "Team", onClick: onViewTeam },
              { label: "Scenarios", onClick: onViewScenarios },
              { label: "Edit", onClick: onEdit },
            ]}
          />
        </div>
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
        <button
          className="primary"
          onClick={onOpenShortlist}
          style={{ padding: "8px 16px", fontSize: 11 }}
        >
          Open shortlist →
        </button>
        <button
          onClick={onOpenTriage}
          style={{
            background: "transparent",
            border: "none",
            cursor: "pointer",
            fontFamily: FONT_MONO,
            fontSize: 11,
            letterSpacing: "0.14em",
            textTransform: "uppercase",
            color: COLORS.muted,
            padding: 0,
          }}
        >
          Open triage
        </button>
      </div>
    </div>
  );
}
